import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

class ApiService {
  String baseUrl = 'http://192.168.1.36:8001';
  String wsUrl = 'ws://192.168.1.36:8001';
  
  void updateUrls(String httpUrl, String websocketUrl) {
    baseUrl = httpUrl;
    wsUrl = websocketUrl;
  }
  
  WebSocketChannel? _channel;
  
  // REST API Methods
  Future<List<dynamic>> getPatients() async {
    final response = await http.get(Uri.parse('$baseUrl/api/patients'));
    if (response.statusCode == 200) {
      return jsonDecode(response.body);
    } else {
      throw Exception('Failed to load patients');
    }
  }

  Future<dynamic> createPatient(Map<String, dynamic> patientData) async {
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

  void sendCommand(String command) {
    if (_channel != null) {
      _channel!.sink.add(jsonEncode({
        'text': command,
      }));
    }
  }
}
