import 'dart:convert';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import 'package:path_provider/path_provider.dart';
import 'package:flutter/foundation.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite_common_ffi_web/sqflite_ffi_web.dart';

class LocalDbService {
  static final LocalDbService _instance = LocalDbService._internal();
  factory LocalDbService() => _instance;
  LocalDbService._internal();

  Database? _database;

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await _initDatabase();
    return _database!;
  }

  Future<Database> _initDatabase() async {
    if (kIsWeb) {
      databaseFactory = databaseFactoryFfiWeb;
      return await openDatabase('nurseassist_offline.db', version: 1, onCreate: _onCreate);
    }
    
    if (defaultTargetPlatform == TargetPlatform.windows || defaultTargetPlatform == TargetPlatform.linux) {
      sqfliteFfiInit();
      databaseFactory = databaseFactoryFfi;
    }

    final documentsDirectory = await getApplicationDocumentsDirectory();
    final path = join(documentsDirectory.path, 'nurseassist_offline.db');

    return await openDatabase(
      path,
      version: 1,
      onCreate: _onCreate,
    );
  }

  Future<void> _onCreate(Database db, int version) async {
    // Cache for patients list
    await db.execute('''
      CREATE TABLE patients_cache (
        id TEXT PRIMARY KEY,
        data TEXT NOT NULL,
        updated_at INTEGER NOT NULL
      )
    ''');

    // Queue for POST requests (offline actions)
    await db.execute('''
      CREATE TABLE action_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        endpoint TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at INTEGER NOT NULL
      )
    ''');
  }

  // --- Patients Cache Methods ---
  Future<void> cachePatientsList(List<dynamic> patients) async {
    final db = await database;
    await db.transaction((txn) async {
      await txn.delete('patients_cache');
      for (var patient in patients) {
        await txn.insert('patients_cache', {
          'id': patient['id'] ?? patient['mrn'] ?? DateTime.now().millisecondsSinceEpoch.toString(),
          'data': jsonEncode(patient),
          'updated_at': DateTime.now().millisecondsSinceEpoch,
        });
      }
    });
  }

  Future<List<dynamic>> getCachedPatients() async {
    final db = await database;
    final maps = await db.query('patients_cache', orderBy: 'updated_at DESC');
    return maps.map((e) => jsonDecode(e['data'] as String)).toList();
  }

  Future<void> cacheNewPatient(Map<String, dynamic> patient) async {
    final db = await database;
    await db.insert('patients_cache', {
      'id': patient['id'] ?? patient['mrn'] ?? DateTime.now().millisecondsSinceEpoch.toString(),
      'data': jsonEncode(patient),
      'updated_at': DateTime.now().millisecondsSinceEpoch,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  // --- Action Queue Methods ---
  Future<void> queueAction(String endpoint, Map<String, dynamic> payload) async {
    final db = await database;
    await db.insert('action_queue', {
      'endpoint': endpoint,
      'payload': jsonEncode(payload),
      'created_at': DateTime.now().millisecondsSinceEpoch,
    });
  }

  Future<List<Map<String, dynamic>>> getActionQueue() async {
    final db = await database;
    return await db.query('action_queue', orderBy: 'created_at ASC');
  }

  Future<void> removeActionFromQueue(int id) async {
    final db = await database;
    await db.delete('action_queue', where: 'id = ?', whereArgs: [id]);
  }
}
