import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite_common_ffi_web/sqflite_ffi_web.dart';

/// The device is the source of truth for patient-facing actions. Network
/// synchronization, if added later, can consume [action_queue], but recording
/// a vital or medication must never depend on a server being available.
class LocalDbService {
  static final LocalDbService _instance = LocalDbService._internal();
  factory LocalDbService() => _instance;
  LocalDbService._internal();

  static const _databaseVersion = 5;
  Database? _database;

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDatabase();
    return _database!;
  }

  Future<bool> backupDatabase() async {
    if (kIsWeb) return false;
    try {
      final documentsDirectory = await getApplicationDocumentsDirectory();
      final dbFile = File(join(documentsDirectory.path, 'nurseassist_offline.db'));
      if (!await dbFile.exists()) return false;
      
      final backupFile = File(join(documentsDirectory.path, 'nurseassist_backup.db'));
      await dbFile.copy(backupFile.path);
      return true;
    } catch (e) {
      debugPrint('Backup error: $e');
      return false;
    }
  }

  Future<bool> restoreDatabase() async {
    if (kIsWeb) return false;
    try {
      final documentsDirectory = await getApplicationDocumentsDirectory();
      final backupFile = File(join(documentsDirectory.path, 'nurseassist_backup.db'));
      if (!await backupFile.exists()) return false;
      
      final dbFile = File(join(documentsDirectory.path, 'nurseassist_offline.db'));
      
      // Close existing database before restoring
      if (_database != null) {
        await _database!.close();
        _database = null;
      }
      
      await backupFile.copy(dbFile.path);
      // Re-initialize after restore
      await database; 
      return true;
    } catch (e) {
      debugPrint('Restore error: $e');
      return false;
    }
  }

  Future<Database> _initDatabase() async {
    if (kIsWeb) {
      databaseFactory = databaseFactoryFfiWeb;
      return openDatabase(
        'nurseassist_offline.db',
        version: _databaseVersion,
        onCreate: _onCreate,
        onUpgrade: _onUpgrade,
      );
    }

    if (defaultTargetPlatform == TargetPlatform.windows ||
        defaultTargetPlatform == TargetPlatform.linux) {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
    }

    final documentsDirectory = await getApplicationDocumentsDirectory();
    return openDatabase(
      join(documentsDirectory.path, 'nurseassist_offline.db'),
      version: _databaseVersion,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );
  }

  Future<void> _onCreate(Database db, int version) async {
    await _createCacheTables(db);
    await _createClinicalTables(db);
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    if (oldVersion < 2) {
      await _createClinicalTables(db);
    }
    if (oldVersion < 3) {
      await _createNursingNotesTable(db);
    }
    if (oldVersion < 4) {
      await _migrateChatSessions(db);
    }
    if (oldVersion < 5) {
      await _createTelemetryQueueTable(db);
    }
  }

  Future<void> _createCacheTables(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS patients_cache (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at INTEGER NOT NULL
      )
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS action_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at INTEGER NOT NULL
      )
    ''');
  }

  Future<void> _createClinicalTables(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS vital_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        vital_type TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT NOT NULL,
        recorded_at INTEGER NOT NULL,
        source_text TEXT
      )
    ''');
    await db.execute('''
      CREATE INDEX IF NOT EXISTS idx_vital_readings_patient_time
      ON vital_readings(patient_id, recorded_at DESC)
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS medication_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        name TEXT NOT NULL,
        dose TEXT,
        route TEXT,
        status TEXT NOT NULL,
        recorded_at INTEGER NOT NULL,
        source_text TEXT
      )
    ''');
    await db.execute('''
      CREATE INDEX IF NOT EXISTS idx_medication_records_patient_time
      ON medication_records(patient_id, recorded_at DESC)
    ''');
    await db.execute('''
      CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        data TEXT,
        created_at INTEGER NOT NULL
      )
    ''');
    await db.execute('''
      CREATE INDEX IF NOT EXISTS idx_chat_messages_patient_session_time
      ON chat_messages(patient_id, session_id, created_at ASC)
    ''');
    await _createNursingNotesTable(db);
    await _createChatSessionsTable(db);
    await _createTelemetryQueueTable(db);
  }

  Future<void> _createTelemetryQueueTable(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS telemetry_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        redacted_transcript TEXT NOT NULL,
        suggested_labels TEXT NOT NULL,
        accepted_labels TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        synced_at INTEGER
      )
    ''');
    await db.execute('''
      CREATE INDEX IF NOT EXISTS idx_telemetry_queue_synced
      ON telemetry_queue(synced_at)
    ''');
  }

  Future<void> _createNursingNotesTable(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS nursing_notes (
        id TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        content TEXT NOT NULL,
        category TEXT NOT NULL,
        source_text TEXT NOT NULL,
        recorded_at INTEGER NOT NULL
      )
    ''');
    await db.execute('''
      CREATE INDEX IF NOT EXISTS idx_nursing_notes_patient_time
      ON nursing_notes(patient_id, recorded_at DESC)
    ''');
  }

  Future<void> _createChatSessionsTable(Database db) async {
    await db.execute('''
      CREATE TABLE IF NOT EXISTS chat_sessions (
        id TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        title TEXT NOT NULL,
        created_at INTEGER NOT NULL
      )
    ''');
    await db.execute('''
      CREATE INDEX IF NOT EXISTS idx_chat_sessions_patient_time
      ON chat_sessions(patient_id, created_at DESC)
    ''');
  }

  Future<void> _migrateChatSessions(Database db) async {
    await _createChatSessionsTable(db);
    final columns = await db.rawQuery('PRAGMA table_info(chat_messages)');
    final hasSessionId = columns.any(
      (column) => column['name'] == 'session_id',
    );
    if (!hasSessionId) {
      await db.execute('ALTER TABLE chat_messages ADD COLUMN session_id TEXT');
    }
    final patients = await db.rawQuery(
      'SELECT DISTINCT patient_id FROM chat_messages',
    );
    for (final row in patients) {
      final patientId = row['patient_id']?.toString();
      if (patientId == null || patientId.isEmpty) continue;
      final sessionId = 'legacy_$patientId';
      await db.insert('chat_sessions', {
        'id': sessionId,
        'patient_id': patientId,
        'title': 'Previous chat history',
        'created_at': 0,
      }, conflictAlgorithm: ConflictAlgorithm.ignore);
      await db.update(
        'chat_messages',
        {'session_id': sessionId},
        where: 'patient_id = ? AND session_id IS NULL',
        whereArgs: [patientId],
      );
    }
    await db.execute('''
      CREATE INDEX IF NOT EXISTS idx_chat_messages_patient_session_time
      ON chat_messages(patient_id, session_id, created_at ASC)
    ''');
  }

  // Patients ---------------------------------------------------------------

  Future<void> cachePatientsList(List<dynamic> patients) async {
    final db = await database;
    await db.transaction((transaction) async {
      await transaction.delete('patients_cache');
      for (final patient in patients) {
        if (patient is! Map) continue;
        final data = Map<String, dynamic>.from(patient);
        final id =
            data['id']?.toString() ??
            data['mrn']?.toString() ??
            DateTime.now().microsecondsSinceEpoch.toString();
        await transaction.insert('patients_cache', {
          'id': id,
          'data': jsonEncode(data),
          'updated_at': DateTime.now().millisecondsSinceEpoch,
        });
      }
    });
  }

  Future<List<dynamic>> getCachedPatients() async {
    final db = await database;
    final rows = await db.query('patients_cache', orderBy: 'updated_at DESC');
    return rows.map((row) => jsonDecode(row['data'] as String)).toList();
  }

  Future<void> cacheNewPatient(Map<String, dynamic> patient) async {
    final db = await database;
    final id =
        patient['id']?.toString() ??
        patient['mrn']?.toString() ??
        DateTime.now().microsecondsSinceEpoch.toString();
    await db.insert('patients_cache', {
      'id': id,
      'data': jsonEncode(patient),
      'updated_at': DateTime.now().millisecondsSinceEpoch,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  // Clinical records -------------------------------------------------------

  Future<void> saveVital({
    required String patientId,
    required String vitalType,
    required num value,
    required String unit,
    required String sourceText,
    DateTime? recordedAt,
  }) async {
    final db = await database;
    await db.insert('vital_readings', {
      'patient_id': patientId,
      'vital_type': vitalType,
      'value': value,
      'unit': unit,
      'recorded_at': (recordedAt ?? DateTime.now()).millisecondsSinceEpoch,
      'source_text': sourceText,
    });
  }

  Future<List<Map<String, dynamic>>> getVitalReadings(
    String patientId, {
    int limit = 200,
  }) async {
    final db = await database;
    final rows = await db.query(
      'vital_readings',
      where: 'patient_id = ?',
      whereArgs: [patientId],
      orderBy: 'recorded_at DESC, id DESC',
      limit: limit,
    );
    return rows.map((row) => Map<String, dynamic>.from(row)).toList();
  }

  Future<void> saveMedication({
    required String patientId,
    required String name,
    required String status,
    required String sourceText,
    String? dose,
    String? route,
    DateTime? recordedAt,
  }) async {
    final db = await database;
    await db.insert('medication_records', {
      'patient_id': patientId,
      'name': name,
      'dose': dose,
      'route': route,
      'status': status,
      'recorded_at': (recordedAt ?? DateTime.now()).millisecondsSinceEpoch,
      'source_text': sourceText,
    });
  }

  Future<List<Map<String, dynamic>>> getMedicationRecords(
    String patientId, {
    int limit = 100,
  }) async {
    final db = await database;
    final rows = await db.query(
      'medication_records',
      where: 'patient_id = ?',
      whereArgs: [patientId],
      orderBy: 'recorded_at DESC, id DESC',
      limit: limit,
    );
    return rows.map((row) => Map<String, dynamic>.from(row)).toList();
  }

  Future<void> saveNursingNote({
    required String id,
    required String patientId,
    required String content,
    required String category,
    required String sourceText,
    DateTime? recordedAt,
  }) async {
    final db = await database;
    await db.insert('nursing_notes', {
      'id': id,
      'patient_id': patientId,
      'content': content,
      'category': category,
      'source_text': sourceText,
      'recorded_at': (recordedAt ?? DateTime.now()).millisecondsSinceEpoch,
    });
  }

  Future<List<Map<String, dynamic>>> getNursingNotes(
    String patientId, {
    int limit = 50,
  }) async {
    final db = await database;
    final rows = await db.query(
      'nursing_notes',
      where: 'patient_id = ?',
      whereArgs: [patientId],
      orderBy: 'recorded_at DESC, id DESC',
      limit: limit,
    );
    return rows.map((row) => Map<String, dynamic>.from(row)).toList();
  }

  // Chat history -----------------------------------------------------------

  Future<Map<String, dynamic>> createChatSession({
    required String id,
    required String patientId,
    required String title,
    DateTime? createdAt,
  }) async {
    final timestamp = createdAt ?? DateTime.now();
    final db = await database;
    await db.insert('chat_sessions', {
      'id': id,
      'patient_id': patientId,
      'title': title,
      'created_at': timestamp.millisecondsSinceEpoch,
    });
    return {
      'id': id,
      'patient_id': patientId,
      'title': title,
      'created_at': timestamp.millisecondsSinceEpoch,
    };
  }

  Future<List<Map<String, dynamic>>> getChatSessions(String patientId) async {
    final db = await database;
    final rows = await db.query(
      'chat_sessions',
      where: 'patient_id = ?',
      whereArgs: [patientId],
      orderBy: 'created_at DESC',
    );
    return rows.map((row) => Map<String, dynamic>.from(row)).toList();
  }

  Future<void> updateChatSessionTitle(String id, String title) async {
    final db = await database;
    await db.update(
      'chat_sessions',
      {'title': title},
      where: 'id = ?',
      whereArgs: [id],
    );
  }

  Future<void> deleteChatSession(String sessionId) async {
    final db = await database;
    await db.transaction((txn) async {
      await txn.delete(
        'chat_messages',
        where: 'session_id = ?',
        whereArgs: [sessionId],
      );
      await txn.delete(
        'chat_sessions',
        where: 'id = ?',
        whereArgs: [sessionId],
      );
    });
  }

  Future<void> saveChatMessage({
    required String id,
    required String patientId,
    required String sessionId,
    required String role,
    required String content,
    Map<String, dynamic>? data,
    DateTime? createdAt,
  }) async {
    final db = await database;
    await db.insert('chat_messages', {
      'id': id,
      'patient_id': patientId,
      'session_id': sessionId,
      'role': role,
      'content': content,
      'data': data == null ? null : jsonEncode(data),
      'created_at': (createdAt ?? DateTime.now()).millisecondsSinceEpoch,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<List<Map<String, dynamic>>> getChatMessages(
    String patientId, {
    String? sessionId,
    int? limit,
  }) async {
    final db = await database;
    final where = sessionId == null
        ? 'patient_id = ?'
        : 'patient_id = ? AND session_id = ?';
    final arguments = sessionId == null ? [patientId] : [patientId, sessionId];
    final rows = await db.query(
      'chat_messages',
      where: where,
      whereArgs: arguments,
      orderBy: 'created_at ASC',
      limit: limit,
    );
    return rows.map((row) {
      final data = row['data'];
      return {
        ...row,
        if (data is String && data.isNotEmpty) 'data': jsonDecode(data),
      };
    }).toList();
  }

  Future<List<Map<String, dynamic>>> getRecentNurseMessages(
    String patientId, {
    int limit = 6,
  }) async {
    final db = await database;
    final rows = await db.query(
      'chat_messages',
      columns: ['content', 'created_at'],
      where: 'patient_id = ? AND role = ?',
      whereArgs: [patientId, 'user'],
      orderBy: 'created_at DESC',
      limit: limit,
    );
    return rows.map((row) => Map<String, dynamic>.from(row)).toList();
  }

  // Deferred feedback / future sync ---------------------------------------

  Future<void> queueAction(
    String endpoint,
    Map<String, dynamic> payload,
  ) async {
    final db = await database;
    await db.insert('action_queue', {
      'endpoint': endpoint,
      'payload': jsonEncode(payload),
      'created_at': DateTime.now().millisecondsSinceEpoch,
    });
  }

  Future<List<Map<String, dynamic>>> getActionQueue() async {
    final db = await database;
    final rows = await db.query('action_queue', orderBy: 'created_at ASC');
    return rows.map((row) => Map<String, dynamic>.from(row)).toList();
  }

  Future<void> removeActionFromQueue(int id) async {
    final db = await database;
    await db.delete('action_queue', where: 'id = ?', whereArgs: [id]);
  }
}
