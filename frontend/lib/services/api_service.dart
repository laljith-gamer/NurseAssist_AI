import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'local_db_service.dart';

class ApiService {
  String baseUrl = 'https://nurseassist-ai-1.onrender.com';
  String wsUrl = 'wss://nurseassist-ai-1.onrender.com';
  
  void updateUrls(String httpUrl, String websocketUrl) {
    baseUrl = httpUrl;
    wsUrl = websocketUrl;
  }
  
  WebSocketChannel? _channel;
  
  // Create an online-only fallback for SyncService
  Future<dynamic> createPatientOnline(Map<String, dynamic> patientData) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/patients'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(patientData),
    );
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception('Failed to create patient');
    }
  }

  Future<void> sendCommandOnline(String patientId, String message) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/chat/command'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'patient_id': patientId, 'message': message}),
    );
    if (response.statusCode != 200) {
      throw Exception('Failed to send command online');
    }
  }
  
  // REST API Methods
  Future<List<dynamic>> getPatients() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/patients')).timeout(const Duration(seconds: 3));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        // Save to cache
        await LocalDbService().cachePatientsList(data);
        return data;
      }
    } catch (e) {
      // Offline or timeout, read from cache
      return await LocalDbService().getCachedPatients();
    }
    throw Exception('Failed to load patients');
  }

  Future<dynamic> createPatient(Map<String, dynamic> patientData) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/patients'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(patientData),
      ).timeout(const Duration(seconds: 3));
      
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        await LocalDbService().cacheNewPatient(data);
        return data;
      }
    } catch (e) {
      // Offline, queue action and cache locally
      await LocalDbService().queueAction('/api/patients', patientData);
      
      // Give it a temporary local ID
      patientData['id'] = 'TEMP_${DateTime.now().millisecondsSinceEpoch}';
      await LocalDbService().cacheNewPatient(patientData);
      return patientData;
    }
    throw Exception('Failed to create patient');
  }

  Future<bool> submitIntentFeedback(String text, String correctIntent) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/feedback/intent'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'text': text, 'correct_intent': correctIntent}),
    );
    return response.statusCode == 200;
  }

  Future<bool> submitNerFeedback(String text, String entityLabel, int startIdx, int endIdx) async {
    final response = await http.post(
      Uri.parse('$baseUrl/api/feedback/ner'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'text': text,
        'entity_label': entityLabel,
        'start_idx': startIdx,
        'end_idx': endIdx
      }),
    );
    return response.statusCode == 200;
  }

  Future<dynamic> getPatientMetrics(String patientId) async {
    final response = await http.get(Uri.parse('$baseUrl/api/patients/$patientId/metrics'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception('Failed to load patient metrics');
    }
  }
  Future<dynamic> getVitalsDelta(String patientId) async {
    final response = await http.get(Uri.parse('$baseUrl/api/patients/$patientId/vitals/delta'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception('Failed to load vitals delta');
    }
  }

  Future<dynamic> getChatHistory(String patientId) async {
    final response = await http.get(Uri.parse('$baseUrl/api/patients/$patientId/chat/sessions'));
    if (response.statusCode == 200) {
      final sessions = jsonDecode(response.body) as List;
      if (sessions.isNotEmpty) {
        final sessionId = sessions.first['id'];
        final sessionResponse = await http.get(Uri.parse('$baseUrl/api/patients/$patientId/chat/sessions/$sessionId'));
        if (sessionResponse.statusCode == 200) {
          return jsonDecode(sessionResponse.body);
        }
      }
      return null;
    } else {
      throw Exception('Failed to load chat history');
    }
  }

  // WebSocket Methods
  Stream<dynamic>? connectToPatientStream(String patientId) {
    _channel?.sink.close();
    
    // Connect to the WebSocket endpoint for a specific patient
    _channel = WebSocketChannel.connect(
      Uri.parse('$wsUrl/ws/$patientId'),
    );
    
    return _channel?.stream.map((message) => jsonDecode(message));
  }

  void disconnectStream() {
    _channel?.sink.close();
    _channel = null;
  }

  void sendCommand(String message) {
    if (_channel != null) {
      _channel!.sink.add(jsonEncode({
        'type': 'command',
        'message': message,
      }));
    } else {
      // If websocket is offline/null, queue it via REST fallback
      LocalDbService().queueAction('/api/chat/sync', {
        'patientId': 'unknown', // Need patient ID, handled in provider ideally
        'message': message,
      });
    }
  }
}
