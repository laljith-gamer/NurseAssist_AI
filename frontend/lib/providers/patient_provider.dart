import 'package:flutter/material.dart';
import '../models/types.dart';
import '../services/api_service.dart';
import '../services/local_db_service.dart';
import '../services/local_nlp_service.dart';

class PatientProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();
  final LocalNlpService _nlpService;

  final List<Patient> _patients = [];
  Patient? _selectedPatient;
  DeltaMetrics? _currentMetrics;
  final List<ChatMessage> _messages = [];
  bool _isLoading = false;

  List<Patient> get patients => _patients;
  Patient? get selectedPatient => _selectedPatient;
  DeltaMetrics? get currentMetrics => _currentMetrics;
  List<ChatMessage> get messages => _messages;
  bool get isLoading => _isLoading;
  ApiService get apiService => _apiService;

  PatientProvider(this._nlpService) {
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
  }

  void sendMessage(String message) {
    if (_selectedPatient == null) return;
    
    // Add user message
    _messages.add(ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      role: 'user',
      content: message,
      timestamp: DateTime.now(),
    ));
    notifyListeners();
    
    // Local Offline Inference
    final intentResult = _nlpService.classifyIntent(message);
    final entities = _nlpService.extractEntities(message);
    
    String response = "Analyzed offline: Intent is '${intentResult.intent}' (Confidence: ${(intentResult.confidence * 100).toStringAsFixed(1)}%). ";
    
    if (entities.isNotEmpty) {
       response += "Extracted entities: ";
       response += entities.map((e) => "${e.type} -> ${e.value}").join(", ");
       response += ". ";
    }
    
    response += "Data has been saved locally to device storage.";
    
    // Cache the data locally
    LocalDbService().queueAction('/api/chat/sync', {
      'patientId': _selectedPatient!.id,
      'message': message,
      'intent': intentResult.intent,
      'entities': entities.map((e) => {'type': e.type, 'value': e.value}).toList()
    });
    
    // Add assistant message
    _messages.add(ChatMessage(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      role: 'assistant',
      content: response,
      timestamp: DateTime.now(),
    ));
    notifyListeners();
  }

}
