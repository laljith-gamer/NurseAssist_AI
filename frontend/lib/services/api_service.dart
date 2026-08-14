import 'local_db_service.dart';

/// Kept as the application's data facade while the app is offline-first.
/// These methods intentionally return plain maps so the presentation layer can
/// remain compatible with a future REST implementation.
class ApiService {
  final LocalDbService _db;

  ApiService({LocalDbService? database}) : _db = database ?? LocalDbService();

  Future<List<dynamic>> getPatients() => _db.getCachedPatients();

  Future<Map<String, dynamic>> createPatient(
    Map<String, dynamic> patientData,
  ) async {
    final now = DateTime.now();
    final firstName = patientData['first_name']?.toString().trim() ?? '';
    final lastName = patientData['last_name']?.toString().trim() ?? '';
    final suppliedName = patientData['name']?.toString().trim() ?? '';
    final name = suppliedName.isNotEmpty
        ? suppliedName
        : [firstName, lastName].where((part) => part.isNotEmpty).join(' ');

    final patient = <String, dynamic>{
      ...patientData,
      'id': 'LOCAL_${now.microsecondsSinceEpoch}',
      'mrn': patientData['mrn']?.toString().trim().isNotEmpty == true
          ? patientData['mrn']
          : 'MRN-${now.millisecondsSinceEpoch}',
      'first_name': firstName,
      'last_name': lastName,
      'name': name.isEmpty ? 'Unnamed patient' : name,
      'date_of_birth': patientData['date_of_birth'] ?? '',
      'age': patientData['age'] ?? 0,
      'gender': patientData['gender'] ?? 'Unknown',
      'room': patientData['room'] ?? '',
      'bed': patientData['bed'] ?? '',
      'admission_date': patientData['admission_date'] ?? now.toIso8601String(),
      'primary_diagnosis': patientData['primary_diagnosis'] ?? 'Pending',
      'allergies': patientData['allergies'] ?? 'Not recorded',
      'code_status': patientData['code_status'] ?? 'Not recorded',
      'insurance': patientData['insurance'] ?? '',
      'emergency_contact_name': patientData['emergency_contact_name'] ?? '',
      'emergency_contact_phone': patientData['emergency_contact_phone'] ?? '',
      'is_active': true,
      'created_at': now.toIso8601String(),
      'updated_at': now.toIso8601String(),
    };
    await _db.cacheNewPatient(patient);
    return patient;
  }

  Future<void> recordVitals(
    String patientId,
    List<Map<String, dynamic>> vitals, {
    required String sourceText,
    DateTime? recordedAt,
  }) async {
    for (final vital in vitals) {
      final type = vital['type']?.toString();
      final value = vital['value'];
      final unit = vital['unit']?.toString();
      if (type == null || value is! num || unit == null) continue;
      await _db.saveVital(
        patientId: patientId,
        vitalType: type,
        value: value,
        unit: unit,
        sourceText: sourceText,
        recordedAt: recordedAt,
      );
    }
  }

  Future<void> recordMedication(
    String patientId, {
    required String name,
    required String status,
    required String sourceText,
    String? dose,
    String? route,
    DateTime? recordedAt,
  }) {
    return _db.saveMedication(
      patientId: patientId,
      name: name,
      dose: dose,
      route: route,
      status: status,
      sourceText: sourceText,
      recordedAt: recordedAt,
    );
  }

  Future<List<Map<String, dynamic>>> getVitals(
    String patientId, {
    int limit = 200,
  }) => _db.getVitalReadings(patientId, limit: limit);

  Future<List<Map<String, dynamic>>> getMedications(
    String patientId, {
    int limit = 100,
  }) => _db.getMedicationRecords(patientId, limit: limit);

  Future<void> recordNursingNote(
    String patientId, {
    required String content,
    required String sourceText,
    String category = 'nursing_observation',
    DateTime? recordedAt,
  }) {
    final now = DateTime.now();
    return _db.saveNursingNote(
      id: 'NOTE_${now.microsecondsSinceEpoch}',
      patientId: patientId,
      content: content,
      category: category,
      sourceText: sourceText,
      recordedAt: recordedAt ?? now,
    );
  }

  Future<List<Map<String, dynamic>>> getNursingNotes(
    String patientId, {
    int limit = 50,
  }) => _db.getNursingNotes(patientId, limit: limit);

  /// A compact, selected-patient-only context for on-device AI. It contains
  /// local records and a small amount of prior nurse conversation, never data
  /// from another patient or a cloud source.
  Future<Map<String, List<Map<String, dynamic>>>> getPatientMemory(
    String patientId,
  ) async {
    final results = await Future.wait([
      _db.getNursingNotes(patientId, limit: 6),
      _db.getVitalReadings(patientId, limit: 8),
      _db.getMedicationRecords(patientId, limit: 5),
      _db.getRecentNurseMessages(patientId, limit: 4),
    ]);
    return {
      'notes': results[0],
      'vitals': results[1],
      'medications': results[2],
      'recent_nurse_messages': results[3],
    };
  }

  Future<Map<String, dynamic>> getPatientMetrics(String patientId) async {
    final metrics = await getVitalsDelta(patientId);
    return {
      'status':
          metrics['alerts'] is List && (metrics['alerts'] as List).isNotEmpty
          ? 'Review required'
          : 'No active alerts',
      'last_updated': DateTime.now().toIso8601String(),
    };
  }

  Future<Map<String, dynamic>> getVitalsDelta(String patientId) async {
    final readings = await _db.getVitalReadings(patientId);
    final grouped = <String, List<Map<String, dynamic>>>{};
    for (final reading in readings) {
      final type = reading['vital_type']?.toString();
      if (type == null) continue;
      (grouped[type] ??= []).add(reading);
    }

    final current = <String, dynamic>{};
    final deltas = <String, dynamic>{};
    final clinicalStatus = <String, String>{};
    final alerts = <String>[];

    for (final entry in grouped.entries) {
      final latest = entry.value.first;
      final value = (latest['value'] as num).toDouble();
      final previous = entry.value.length > 1
          ? (entry.value[1]['value'] as num).toDouble()
          : null;
      final key = entry.key;
      final deltaKey = key == 'systolic'
          ? 'bp_systolic'
          : key == 'diastolic'
          ? 'bp_diastolic'
          : key;
      current[key] = value;
      current['${key}_unit'] = latest['unit'];
      final change = previous == null ? 0.0 : value - previous;
      final trend = change > 0.01
          ? 'increasing'
          : change < -0.01
          ? 'decreasing'
          : 'stable';
      deltas[deltaKey] = {
        'current': value,
        'significance': previous == null
            ? 'first reading'
            : 'change from prior reading',
        'trend': trend,
        if (previous != null)
          'vs_yesterday': {
            'absolute_change': change,
            'percent_change': previous == 0 ? 0.0 : (change / previous) * 100,
          },
      };
      clinicalStatus[key] = _statusForVital(key, value, alerts);
    }

    return {
      'patient_id': patientId,
      'has_data': current.isNotEmpty,
      'timestamp': DateTime.now().toIso8601String(),
      'current': current,
      'deltas': deltas,
      'alerts': alerts,
      'clinical_status': clinicalStatus,
    };
  }

  String _statusForVital(String type, double value, List<String> alerts) {
    switch (type) {
      case 'systolic':
        if (value >= 180 || value < 90) {
          alerts.add(
            'Critical Systolic BP (${_format(value)} mmHg) detected. Please evaluate the patient immediately.',
          );
          return 'Critical';
        }
        if (value >= 140) return 'Elevated';
        return 'Normal';
      case 'diastolic':
        if (value >= 120 || value < 60) {
          alerts.add(
            'Critical Diastolic BP (${_format(value)} mmHg) detected. Please evaluate the patient immediately.',
          );
          return 'Critical';
        }
        if (value >= 90) return 'Elevated';
        return 'Normal';
      case 'heart_rate':
        if (value < 50 || value > 130) {
          alerts.add(
            'Critical Heart Rate (${_format(value)} bpm) detected. Please evaluate the patient immediately.',
          );
          return 'Critical';
        }
        return value < 60 || value > 100
            ? 'Abnormal'
            : 'Normal';
      case 'temperature':
        if (value >= 39.5 || value < 35) {
          alerts.add(
            'Critical Temperature (${value.toStringAsFixed(1)} °C) detected. Please evaluate the patient immediately.',
          );
          return 'Critical';
        }
        return value >= 38.0 || value < 36.0
            ? 'Abnormal'
            : 'Normal';
      case 'spo2':
        if (value < 90) {
          alerts.add(
            'Critical SpO2 (${_format(value)}%) detected. Please evaluate the patient immediately.',
          );
          return 'Critical';
        }
        return value < 95
            ? 'Abnormal'
            : 'Normal';
      case 'respiratory_rate':
        if (value > 30 || value < 8) {
          alerts.add(
            'Critical Respiratory Rate (${_format(value)}/min) detected. Please evaluate the patient immediately.',
          );
          return 'Critical';
        }
        return value < 12 || value > 20
            ? 'Abnormal'
            : 'Normal';
      default:
        return 'recorded';
    }
  }

  String _format(double value) => value == value.roundToDouble()
      ? value.toStringAsFixed(0)
      : value.toStringAsFixed(1);

  Future<void> saveChatMessage({
    required String id,
    required String patientId,
    required String sessionId,
    required String role,
    required String content,
    Map<String, dynamic>? data,
    DateTime? createdAt,
  }) {
    return _db.saveChatMessage(
      id: id,
      patientId: patientId,
      sessionId: sessionId,
      role: role,
      content: content,
      data: data,
      createdAt: createdAt,
    );
  }

  Future<Map<String, dynamic>> createChatSession(
    String patientId, {
    required String title,
  }) {
    final now = DateTime.now();
    return _db.createChatSession(
      id: 'CHAT_${now.microsecondsSinceEpoch}',
      patientId: patientId,
      title: title,
      createdAt: now,
    );
  }

  Future<List<Map<String, dynamic>>> getChatSessions(String patientId) =>
      _db.getChatSessions(patientId);

  Future<void> updateChatSessionTitle(String id, String title) =>
      _db.updateChatSessionTitle(id, title);

  Future<void> deleteChatSession(String sessionId) =>
      _db.deleteChatSession(sessionId);

  Future<List<Map<String, dynamic>>> getChatHistory(
    String patientId, {
    String? sessionId,
  }) => _db.getChatMessages(patientId, sessionId: sessionId);

  Future<bool> submitIntentFeedback(String text, String correctIntent) async {
    await _db.queueAction('/api/feedback/intent', {
      'text': text,
      'correct_intent': correctIntent,
    });
    return true;
  }

  Future<bool> submitNerFeedback(
    String text,
    String entityLabel,
    int startIdx,
    int endIdx,
  ) async {
    await _db.queueAction('/api/feedback/ner', {
      'text': text,
      'entity_label': entityLabel,
      'start_idx': startIdx,
      'end_idx': endIdx,
    });
    return true;
  }

  Future<bool> backupDatabase() => _db.backupDatabase();

  Future<bool> restoreDatabase() => _db.restoreDatabase();
}
