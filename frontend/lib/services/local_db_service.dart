import 'dart:convert';

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

  static const _databaseVersion = 2;
  Database? _database;

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDatabase();
    return _database!;
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
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        data TEXT,
        created_at INTEGER NOT NULL
      )
    ''');
    await db.execute('''
      CREATE INDEX IF NOT EXISTS idx_chat_messages_patient_time
      ON chat_messages(patient_id, created_at ASC)
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
      orderBy: 'recorded_at DESC',
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
      orderBy: 'recorded_at DESC',
      limit: limit,
    );
    return rows.map((row) => Map<String, dynamic>.from(row)).toList();
  }

  // Chat history -----------------------------------------------------------

  Future<void> saveChatMessage({
    required String id,
    required String patientId,
    required String role,
    required String content,
    Map<String, dynamic>? data,
    DateTime? createdAt,
  }) async {
    final db = await database;
    await db.insert('chat_messages', {
      'id': id,
      'patient_id': patientId,
      'role': role,
      'content': content,
      'data': data == null ? null : jsonEncode(data),
      'created_at': (createdAt ?? DateTime.now()).millisecondsSinceEpoch,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<List<Map<String, dynamic>>> getChatMessages(String patientId) async {
    final db = await database;
    final rows = await db.query(
      'chat_messages',
      where: 'patient_id = ?',
      whereArgs: [patientId],
      orderBy: 'created_at ASC',
    );
    return rows.map((row) {
      final data = row['data'];
      return {
        ...row,
        if (data is String && data.isNotEmpty) 'data': jsonDecode(data),
      };
    }).toList();
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
