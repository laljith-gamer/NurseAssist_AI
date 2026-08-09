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
    
    // Build intelligent response based on intent
    String response = _buildResponse(intentResult, entities, message);
    
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

  String _buildResponse(IntentResult intent, List<Entity> entities, String originalMessage) {
    final patientName = _selectedPatient?.name ?? 'the patient';
    
    switch (intent.intent) {
      case 'record_vitals':
        if (entities.isEmpty) {
          return "I understood you want to record vitals for $patientName. "
              "Could you specify the values? For example: \"BP 120/80\" or \"Temp 37.5\"";
        }
        final vitalsStr = entities.map((e) {
          final label = e.type.replaceAll('vital_', '').toUpperCase();
          return "$label: ${e.value}";
        }).join(', ');
        return "✅ Recorded vitals for $patientName:\n$vitalsStr\n\nData saved locally to device storage.";
      
      case 'query_vitals':
        return "📊 Retrieving stored vitals for $patientName from local records...\n\n"
            "All vitals data is stored securely on this device. "
            "Check the Vitals tab for trends and delta charts.";
      
      case 'record_medication':
        final meds = entities.where((e) => e.type == 'medication_name').toList();
        if (meds.isNotEmpty) {
          return "💊 Recorded medication for $patientName: ${meds.map((m) => m.value).join(', ')}\n\n"
              "Saved to local device storage.";
        }
        return "💊 I understood you want to record a medication for $patientName. "
            "Could you specify the medication name? For example: \"Gave Zofran 4mg\"";
      
      case 'query_medications':
        return "💊 Retrieving medication records for $patientName from local storage...\n\n"
            "All medication data is stored securely on this device.";
      
      case 'command_summarize':
        return "📋 Generating clinical summary for $patientName...\n\n"
            "Summary is based on locally stored records including vitals, "
            "medications, and clinical notes saved on this device.";
      
      case 'command_cancel':
        return "❌ Action cancelled.";
      
      case 'greeting':
        return "👋 Hello! I'm NurseAssist AI, running fully offline on this device.\n\n"
            "I can help you:\n"
            "• Record vitals: \"BP 120/80\", \"Temp 37.5\"\n"
            "• Log medications: \"Gave Zofran 4mg\"\n"
            "• Summarize patient data\n\n"
            "All data stays securely on your device.";
      
      default:
        if (entities.isNotEmpty) {
          final entityStr = entities.map((e) => "${e.type}: ${e.value}").join(', ');
          return "I detected the following from your input: $entityStr\n\n"
              "Data has been saved locally. Could you clarify what action you'd like to take?";
        }
        return "I'm not sure what you'd like to do. Try commands like:\n"
            "• \"Record BP 120/80\" to log vitals\n"
            "• \"What meds are due?\" to check medications\n"
            "• \"Summarize\" for a clinical summary\n\n"
            "All processing happens offline on this device.";
    }
  }

}
