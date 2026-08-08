import 'dart:async';
import 'package:flutter/material.dart';
import '../models/types.dart';
import '../services/api_service.dart';
import '../services/sync_service.dart';
import '../services/local_db_service.dart';

class PatientProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();
  final SyncService _syncService = SyncService();

  final List<Patient> _patients = [];
  Patient? _selectedPatient;
  DeltaMetrics? _currentMetrics;
  final List<ChatMessage> _messages = [];
  bool _isLoading = false;

  StreamSubscription? _streamSubscription;

  List<Patient> get patients => _patients;
  Patient? get selectedPatient => _selectedPatient;
  DeltaMetrics? get currentMetrics => _currentMetrics;
  List<ChatMessage> get messages => _messages;
  bool get isLoading => _isLoading;
  bool get isOffline => !_syncService.isOnline;
  ApiService get apiService => _apiService;

  PatientProvider() {
    _syncService.addListener(notifyListeners);
    loadPatients();
  }

  Future<void> loadPatients() async {
    _isLoading = true;
    notifyListeners();
    try {
      final data = await _apiService.getPatients();
      _patients.clear();
      _patients.addAll(data.map((json) => Patient.fromJson(json)).toList());
      
      if (_patients.isNotEmpty) {
        selectPatient(_patients.first);
      }
    } catch (e) {
      debugPrint('Error loading patients: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> addPatient(Map<String, dynamic> patientData) async {
    try {
      final newPatientJson = await _apiService.createPatient(patientData);
      final newPatient = Patient.fromJson(newPatientJson);
      _patients.insert(0, newPatient); // Add to top of list
      notifyListeners();
      selectPatient(newPatient);
      return true;
    } catch (e) {
      debugPrint('Error adding patient: $e');
      return false;
    }
  }

  void selectPatient(Patient patient) async {
    if (_selectedPatient?.id == patient.id) return;
    
    _selectedPatient = patient;
    _currentMetrics = null;
    _messages.clear();
    notifyListeners();

    // Fetch initial historical data
    try {
      final deltaData = await _apiService.getVitalsDelta(patient.id);
      _currentMetrics = DeltaMetrics.fromJson(deltaData);
      
      final chatData = await _apiService.getChatHistory(patient.id);
      if (chatData != null && chatData['messages'] != null) {
        final msgs = chatData['messages'] as List;
        _messages.addAll(msgs.map((m) => ChatMessage(
          id: m['id'] ?? DateTime.now().millisecondsSinceEpoch.toString(),
          role: m['role'] ?? 'user',
          content: m['content'] ?? '',
          timestamp: m['created_at'] != null ? DateTime.parse(m['created_at']) : DateTime.now(),
        )));
      }
      notifyListeners();
    } catch (e) {
      debugPrint('Error loading historical data: $e');
    }

    _listenToPatientUpdates(patient.id);
  }

  void _listenToPatientUpdates(String patientId) {
    _streamSubscription?.cancel();
    
    final stream = _apiService.connectToPatientStream(patientId);
    if (stream != null) {
      _streamSubscription = stream.listen((data) {
        if (data['type'] == 'metrics_update') {
          _currentMetrics = DeltaMetrics.fromJson(data['data']);
          notifyListeners();
        } else {
          // Treat any other message type as a chat response from the backend
          _messages.add(ChatMessage(
            id: DateTime.now().millisecondsSinceEpoch.toString(),
            role: data['role'] ?? 'assistant',
            content: data['message'] ?? data['content'] ?? '',
            timestamp: DateTime.now(),
          ));
          notifyListeners();
        }
      }, onError: (error) {
        debugPrint('WebSocket Error: $error');
      });
    }
  }

  void sendMessage(String message) {
    if (_selectedPatient == null) return;
    
    _messages.add(ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      role: 'user',
      content: message,
      timestamp: DateTime.now(),
    ));
    notifyListeners();
    
    if (_syncService.isOnline) {
      _apiService.sendCommand(message);
    } else {
      // Offline fallback: Queue via API service REST fallback logic
      LocalDbService().queueAction('/api/chat/sync', {
        'patientId': _selectedPatient!.id,
        'message': message,
      });
      
      _messages.add(ChatMessage(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        role: 'assistant',
        content: 'Offline Mode: Vitals recorded locally. AI analysis suspended until reconnected.',
        timestamp: DateTime.now(),
      ));
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _syncService.removeListener(notifyListeners);
    _streamSubscription?.cancel();
    _apiService.disconnectStream();
    super.dispose();
  }
}
