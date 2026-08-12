import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:connectivity_plus/connectivity_plus.dart';

import 'local_db_service.dart';
import '../providers/settings_provider.dart';

/// Redacts PII from clinical text before it is queued for telemetry.
///
/// Patterns are ported from ml_pipeline/nlp/entity_extractor.py and extended
/// with MRN-like digit sequences. Redaction runs entirely on-device — raw
/// text never reaches the queue.
class TranscriptRedactor {
  static final _roomPattern = RegExp(
    r'\broom\s*\d{2,4}\b',
    caseSensitive: false,
  );

  /// Six or more consecutive digits that look like an MRN or similar ID.
  static final _mrnPattern = RegExp(r'\b\d{6,}\b');

  /// Common name-prefix patterns (Mr., Mrs., Dr., Pt., Patient:)
  static final _namePrefixPattern = RegExp(
    r'(?i:\b(?:mr\.?|mrs\.?|ms\.?|dr\.?|pt\.?|patient:?)\s+)[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?',
  );

  /// Redact all recognized PII patterns. Optionally strip a known patient name.
  static String redact(String text, {String? patientName}) {
    var redacted = text;

    // Strip known patient name first (first + last, or full display name)
    if (patientName != null && patientName.trim().isNotEmpty) {
      for (final namePart in patientName.split(RegExp(r'\s+'))) {
        if (namePart.length >= 2) {
          redacted = redacted.replaceAll(
            RegExp(RegExp.escape(namePart), caseSensitive: false),
            '[NAME]',
          );
        }
      }
    }

    redacted = redacted.replaceAll(_roomPattern, '[ROOM]');
    redacted = redacted.replaceAll(_mrnPattern, '[MRN]');
    redacted = redacted.replaceAll(_namePrefixPattern, '[NAME]');

    return redacted;
  }
}

/// Captures observation-label accept/dismiss events locally for future sync.
///
/// This service does nothing unless [SettingsProvider.telemetrySharingEnabled]
/// is true. Every check is performed at call time, not cached at startup.
class TelemetryService {
  final LocalDbService _db;
  final SettingsProvider _settings;

  static const int _maxQueueSize = 500;
  static const String _relayUrl = String.fromEnvironment(
    'TELEMETRY_RELAY_URL',
    defaultValue: 'https://telemetry-relay.example.workers.dev/intake',
  );
  static const String _appSecret = String.fromEnvironment(
    'TELEMETRY_APP_SECRET',
    defaultValue: '',
  );

  TelemetryService({
    required LocalDbService db,
    required SettingsProvider settings,
  })  : _db = db,
        _settings = settings;

  /// Try syncing to relay (Task 3). Checks WiFi, limits batch to 50, and 
  /// throttles to once per 4 hours.
  Future<void> syncTelemetry() async {
    if (!_settings.telemetrySharingEnabled) return;

    final now = DateTime.now().millisecondsSinceEpoch;
    final lastSync = _settings.lastTelemetrySyncTime;

    // Throttle to once per 4 hours
    if (now - lastSync < 4 * 60 * 60 * 1000) return;

    // Check WiFi (prevent mobile data usage)
    final connectivityResult = await Connectivity().checkConnectivity();
    if (!connectivityResult.contains(ConnectivityResult.wifi)) return;

    final events = await getUnsyncedEvents(limit: 50);
    if (events.isEmpty) return;

    try {
      final response = await http.post(
        Uri.parse(_relayUrl),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_appSecret',
        },
        body: jsonEncode({
          'events': events,
          'app_version': '1.0.0',
        }),
      );

      // Relay returns 200 or 202 on success
      if (response.statusCode == 200 || response.statusCode == 202) {
        final syncedIds = events.map((e) => e['id'] as int).toList();
        await markSynced(syncedIds);
        _settings.setLastTelemetrySyncTime(now);
      } else {
        debugPrint('TelemetryService: relay returned ${response.statusCode}');
      }
    } catch (e) {
      debugPrint('TelemetryService: failed to sync to relay: $e');
    }
  }

  /// Queue a telemetry event if sharing is enabled. The transcript is redacted
  /// before storage — raw text never enters the queue.
  Future<void> recordLabelVerdict({
    required String transcript,
    required List<String> suggestedLabels,
    required Map<String, bool> verdicts,
    String? patientName,
  }) async {
    // Check every time, not cached
    if (!_settings.telemetrySharingEnabled) return;

    final acceptedLabels = verdicts.entries
        .where((e) => e.value == true)
        .map((e) => e.key)
        .toList();

    final redacted = TranscriptRedactor.redact(
      transcript,
      patientName: patientName,
    );

    try {
      final db = await _db.database;

      await db.insert('telemetry_queue', {
        'redacted_transcript': redacted,
        'suggested_labels': jsonEncode(suggestedLabels),
        'accepted_labels': jsonEncode(acceptedLabels),
        'created_at': DateTime.now().millisecondsSinceEpoch,
        'synced_at': null,
      });

      // Enforce cap
      await _enforceQueueCap(db);

      // Update settings count
      await refreshQueueCount();
    } catch (e) {
      debugPrint('TelemetryService: failed to queue event: $e');
    }
  }

  /// Returns the count of unsynced telemetry events.
  Future<int> getUnsyncedCount() async {
    try {
      final db = await _db.database;
      final result = await db.rawQuery(
        'SELECT COUNT(*) as cnt FROM telemetry_queue WHERE synced_at IS NULL',
      );
      return (result.first['cnt'] as int?) ?? 0;
    } catch (e) {
      return 0;
    }
  }

  /// Returns the total count of all queued telemetry events.
  Future<int> getTotalCount() async {
    try {
      final db = await _db.database;
      final result = await db.rawQuery(
        'SELECT COUNT(*) as cnt FROM telemetry_queue',
      );
      return (result.first['cnt'] as int?) ?? 0;
    } catch (e) {
      return 0;
    }
  }

  /// Refresh the queued count displayed in settings.
  Future<void> refreshQueueCount() async {
    final count = await getTotalCount();
    _settings.updateQueuedTelemetryCount(count);
  }

  /// Delete all queued telemetry events.
  Future<void> clearQueue() async {
    try {
      final db = await _db.database;
      await db.delete('telemetry_queue');
      _settings.updateQueuedTelemetryCount(0);
    } catch (e) {
      debugPrint('TelemetryService: failed to clear queue: $e');
    }
  }

  /// Retrieve unsynced events for batch upload (used by sync client, Task 3).
  Future<List<Map<String, dynamic>>> getUnsyncedEvents({int limit = 50}) async {
    try {
      final db = await _db.database;
      return await db.query(
        'telemetry_queue',
        where: 'synced_at IS NULL',
        orderBy: 'created_at ASC',
        limit: limit,
      );
    } catch (e) {
      return [];
    }
  }

  /// Mark events as synced after successful upload.
  Future<void> markSynced(List<int> ids) async {
    if (ids.isEmpty) return;
    try {
      final db = await _db.database;
      final now = DateTime.now().millisecondsSinceEpoch;
      await db.rawUpdate(
        'UPDATE telemetry_queue SET synced_at = ? WHERE id IN (${ids.join(",")})',
        [now],
      );
      await refreshQueueCount();
    } catch (e) {
      debugPrint('TelemetryService: failed to mark synced: $e');
    }
  }

  Future<void> _enforceQueueCap(dynamic db) async {
    final countResult = await db.rawQuery(
      'SELECT COUNT(*) as cnt FROM telemetry_queue',
    );
    final count = (countResult.first['cnt'] as int?) ?? 0;
    if (count > _maxQueueSize) {
      final excess = count - _maxQueueSize;
      await db.rawDelete(
        'DELETE FROM telemetry_queue WHERE id IN '
        '(SELECT id FROM telemetry_queue ORDER BY created_at ASC LIMIT ?)',
        [excess],
      );
    }
  }
}
