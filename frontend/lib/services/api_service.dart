import 'local_db_service.dart';

class ApiService {
  // REST API Methods - Now purely Local Offline for Offline-First Architecture
  
  Future<List<dynamic>> getPatients() async {
    return await LocalDbService().getCachedPatients();
  }

  Future<dynamic> createPatient(Map<String, dynamic> patientData) async {
    patientData['id'] = 'LOCAL_${DateTime.now().millisecondsSinceEpoch}';
    await LocalDbService().cacheNewPatient(patientData);
    return patientData;
  }

  Future<bool> submitIntentFeedback(String text, String correctIntent) async {
    // Feedback is stored locally now
    await LocalDbService().queueAction('/api/feedback/intent', {
      'text': text,
      'correct_intent': correctIntent
    });
    return true;
  }

  Future<bool> submitNerFeedback(String text, String entityLabel, int startIdx, int endIdx) async {
    await LocalDbService().queueAction('/api/feedback/ner', {
      'text': text,
      'entity_label': entityLabel,
      'start_idx': startIdx,
      'end_idx': endIdx
    });
    return true;
  }

  Future<dynamic> getPatientMetrics(String patientId) async {
    // Simulated offline metrics based on local DB
    return {'status': 'Stable', 'last_updated': DateTime.now().toIso8601String()};
  }
  
  Future<dynamic> getVitalsDelta(String patientId) async {
    return {'bp_delta': 0, 'hr_delta': 0};
  }

  Future<dynamic> getChatHistory(String patientId) async {
    // Return empty or locally cached chat history
    return null; 
  }

  // Model Management Methods - Removed. Handled by model_manager.dart locally.
  
  // WebSocket Methods - Removed. NLP is local now.
}
