import 'package:flutter/material.dart';

import '../models/types.dart';
import '../services/api_service.dart';
import '../services/clinical_command_parser.dart';
import '../services/llm_service.dart';
import '../services/local_nlp_service.dart';

/// A validated charting proposal that requires a nurse's explicit approval.
class ClinicalRecordProposal {
  const ClinicalRecordProposal({
    required this.patientId,
    required this.patientName,
    required this.chatSessionId,
    required this.command,
    required this.sourceText,
    required this.interpreter,
    required this.createdAt,
  });

  final String patientId;
  final String patientName;
  final String chatSessionId;
  final ClinicalCommand command;
  final String sourceText;
  final String interpreter;
  final DateTime createdAt;

  String get summary {
    if (command.action == ClinicalAction.recordVitals) {
      return command.vitals.map((vital) => vital.displayValue).join(', ');
    }
    if (command.action == ClinicalAction.recordNote) {
      return sourceText;
    }
    final medication = command.medication;
    if (medication == null) return '';
    return [
      medication.name,
      if (medication.dose != null) medication.dose!,
      if (medication.route != null) medication.route!,
      '(${medication.status})',
    ].join(' ');
  }
}

/// Coordinates the clinical command path. An on-device LLM interprets normal
/// nurse language; deterministic code only validates output and accesses the
/// local record store.
class PatientProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();
  final LocalNlpService _nlpService;
  LlmService? _llmService;

  final List<Patient> _patients = [];
  Patient? _selectedPatient;
  DeltaMetrics? _currentMetrics;
  final List<ChatMessage> _messages = [];
  final List<ChatSession> _chatSessions = [];
  ChatSession? _activeChatSession;
  ClinicalRecordProposal? _pendingProposal;
  bool _isLoading = false;
  bool _isResponding = false;

  List<Patient> get patients => List.unmodifiable(_patients);
  Patient? get selectedPatient => _selectedPatient;
  DeltaMetrics? get currentMetrics => _currentMetrics;
  List<ChatMessage> get messages => List.unmodifiable(_messages);
  List<ChatSession> get chatSessions => List.unmodifiable(_chatSessions);
  ChatSession? get activeChatSession => _activeChatSession;
  bool get isLoading => _isLoading;
  bool get isResponding => _isResponding;
  ClinicalRecordProposal? get pendingProposal => _pendingProposal;
  ApiService get apiService => _apiService;

  PatientProvider(this._nlpService) {
    loadPatients();
  }

  void setLlmService(LlmService service) {
    _llmService = service;
  }

  Future<void> loadPatients() async {
    _isLoading = true;
    notifyListeners();
    try {
      final data = await _apiService.getPatients();
      _patients
        ..clear()
        ..addAll(
          data.whereType<Map>().map(
            (json) => Patient.fromJson(Map<String, dynamic>.from(json)),
          ),
        );
      if (_selectedPatient == null && _patients.isNotEmpty) {
        await selectPatient(_patients.first);
      }
    } catch (error) {
      debugPrint('Error loading local patients: $error');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> addPatient(Map<String, dynamic> patientData) async {
    try {
      final newPatient = Patient.fromJson(
        await _apiService.createPatient(patientData),
      );
      _patients.insert(0, newPatient);
      notifyListeners();
      await selectPatient(newPatient);
      return true;
    } catch (error) {
      debugPrint('Error adding local patient: $error');
      return false;
    }
  }

  Future<void> selectPatient(Patient patient) async {
    if (_selectedPatient?.id == patient.id) return;
    final patientId = patient.id;
    _selectedPatient = patient;
    _currentMetrics = null;
    _pendingProposal = null;
    _messages.clear();
    _chatSessions.clear();
    _activeChatSession = null;
    notifyListeners();

    try {
      final results = await Future.wait([
        _apiService.getVitalsDelta(patientId),
        _apiService.getChatSessions(patientId),
      ]);
      // A user can select another patient while reads are in flight.
      if (_selectedPatient?.id != patientId) return;

      _currentMetrics = DeltaMetrics.fromJson(
        Map<String, dynamic>.from(results[0] as Map),
      );
      final sessions = (results[1] as List<Map<String, dynamic>>)
          .map(ChatSession.fromJson)
          .toList();
      if (sessions.isEmpty) {
        final created = await _apiService.createChatSession(
          patientId,
          title: 'New chat',
        );
        if (_selectedPatient?.id != patientId) return;
        sessions.add(ChatSession.fromJson(created));
      }
      _chatSessions.addAll(sessions);
      _activeChatSession = _chatSessions.first;
      final chatRows = await _apiService.getChatHistory(
        patientId,
        sessionId: _activeChatSession!.id,
      );
      if (_selectedPatient?.id != patientId) return;
      _messages.addAll(chatRows.map(_messageFromRow));
    } catch (error) {
      debugPrint('Error loading local patient history: $error');
    }
    notifyListeners();
  }

  Future<void> startNewChat() async {
    final patient = _selectedPatient;
    if (patient == null || _isResponding) return;
    
    // Prevent creating multiple empty new chats
    if (_messages.isEmpty && _activeChatSession != null) {
      return;
    }

    final session = ChatSession.fromJson(
      await _apiService.createChatSession(
        patient.id,
        title: 'New chat',
      ),
    );
    if (_selectedPatient?.id != patient.id) return;
    _pendingProposal = null;
    _chatSessions.insert(0, session);
    _activeChatSession = session;
    _messages.clear();
    notifyListeners();
  }

  Future<void> selectChatSession(ChatSession session) async {
    final patient = _selectedPatient;
    if (patient == null || session.patientId != patient.id || _isResponding) {
      return;
    }
    _pendingProposal = null;
    _activeChatSession = session;
    _messages.clear();
    notifyListeners();
    try {
      final rows = await _apiService.getChatHistory(
        patient.id,
        sessionId: session.id,
      );
      if (_selectedPatient?.id == patient.id &&
          _activeChatSession?.id == session.id) {
        _messages.addAll(rows.map(_messageFromRow));
      }
    } catch (error) {
      debugPrint('Error loading selected chat history: $error');
    }
    notifyListeners();
  }

  ChatMessage _messageFromRow(Map<String, dynamic> row) {
    final createdAt = row['created_at'];
    final timestamp = createdAt is num
        ? DateTime.fromMillisecondsSinceEpoch(createdAt.toInt())
        : DateTime.now();
    final rawData = row['data'];
    return ChatMessage(
      id: row['id']?.toString() ?? timestamp.microsecondsSinceEpoch.toString(),
      sessionId: row['session_id']?.toString(),
      role: row['role']?.toString() ?? 'assistant',
      content: row['content']?.toString() ?? '',
      timestamp: timestamp,
      data: rawData is Map ? Map<String, dynamic>.from(rawData) : null,
    );
  }

  Future<void> sendMessage(String message) async {
    final patient = _selectedPatient;
    final chatSession = _activeChatSession;
    if (patient == null || chatSession == null || _isResponding) return;

    // A proposal is intentionally short-lived. Sending a new message discards
    // an unsigned proposal instead of leaving a stale chart action available.
    _pendingProposal = null;
    _isResponding = true;
    final userMessage = ChatMessage(
      id: 'user_${DateTime.now().microsecondsSinceEpoch}',
      sessionId: chatSession.id,
      role: 'user',
      content: message,
      timestamp: DateTime.now(),
    );
    _messages.add(userMessage);
    notifyListeners();

    try {
      await _apiService.saveChatMessage(
        id: userMessage.id,
        patientId: patient.id,
        sessionId: chatSession.id,
        role: userMessage.role,
        content: userMessage.content,
        createdAt: userMessage.timestamp,
      );

      // Auto-assign title for a new chat
      if (_messages.length == 1) {
        String newTitle = message.trim();
        if (newTitle.length > 20) {
          newTitle = '${newTitle.substring(0, 20)}...';
        }
        await _apiService.updateChatSessionTitle(chatSession.id, newTitle);
        chatSession.title = newTitle;
        // Update the session list so the sidebar redraws
        final index = _chatSessions.indexWhere((s) => s.id == chatSession.id);
        if (index != -1) {
          _chatSessions[index] = chatSession;
        }
      }

      // Gemma is the primary interpreter. The smaller model contributes only
      // data-driven nursing context; it cannot create a command or a value.
      final observationHints = _nlpService.predictClinicalObservations(message);
      final patientMemory = _formatPatientMemory(
        await _apiService.getPatientMemory(patient.id),
      );
      final aiCommand = await _llmService?.interpretClinicalCommand(
        message,
        observationHints: observationHints,
        patientMemory: patientMemory,
      );
      final command = aiCommand ?? ClinicalCommandParser.parse(message);
      final response = await _respondToCommand(
        patient: patient,
        message: message,
        command: command,
        observationHints: observationHints,
        interpreter: aiCommand == null ? 'offline fallback' : 'on-device AI',
        chatSessionId: chatSession.id,
        patientMemory: patientMemory,
      );

      // Do not write a response against a patient that was switched during a
      // slow optional LLM call. The action itself is already tied to the
      // originally selected patient and has been stored locally.
      final assistantMessage = ChatMessage(
        id: 'assistant_${DateTime.now().microsecondsSinceEpoch}',
        sessionId: chatSession.id,
        role: 'assistant',
        content: response,
        timestamp: DateTime.now(),
        observationHints:
            observationHints.map((hint) => hint.name).toList(),
      );
      if (_selectedPatient?.id == patient.id &&
          _activeChatSession?.id == chatSession.id) {
        _messages.add(assistantMessage);
      }
      await _apiService.saveChatMessage(
        id: assistantMessage.id,
        patientId: patient.id,
        sessionId: chatSession.id,
        role: assistantMessage.role,
        content: assistantMessage.content,
        createdAt: assistantMessage.timestamp,
      );
    } catch (error) {
      debugPrint('Error handling clinical command: $error');
      final errorMessage = ChatMessage(
        id: 'assistant_${DateTime.now().microsecondsSinceEpoch}',
        sessionId: chatSession.id,
        role: 'assistant',
        content: 'I could not save that local record. Please try again.',
        timestamp: DateTime.now(),
      );
      if (_selectedPatient?.id == patient.id &&
          _activeChatSession?.id == chatSession.id) {
        _messages.add(errorMessage);
      }
    } finally {
      _isResponding = false;
      notifyListeners();
    }
  }

  Future<String> _respondToCommand({
    required Patient patient,
    required String message,
    required ClinicalCommand command,
    required List<ClinicalObservation> observationHints,
    required String interpreter,
    required String chatSessionId,
    required String patientMemory,
  }) async {
    switch (command.action) {
      case ClinicalAction.recordVitals:
        _stageProposal(
          patient: patient,
          command: command,
          sourceText: message,
          interpreter: interpreter,
          chatSessionId: chatSessionId,
        );
        return 'I prepared a vital-sign entry for ${patient.name}. Review it below, then tap Confirm & Save.';

      case ClinicalAction.queryVitals:
        return _vitalsResponse(patient);

      case ClinicalAction.queryTrends:
        return _trendsResponse(patient);

      case ClinicalAction.recordMedication:
        _stageProposal(
          patient: patient,
          command: command,
          sourceText: message,
          interpreter: interpreter,
          chatSessionId: chatSessionId,
        );
        return 'I prepared a medication documentation entry for ${patient.name}. Review it below, then tap Confirm & Save.';

      case ClinicalAction.recordNote:
        _stageProposal(
          patient: patient,
          command: command,
          sourceText: message,
          interpreter: interpreter,
          chatSessionId: chatSessionId,
        );
        return 'I prepared this nursing observation for ${patient.name}. Review it below, then tap Confirm & Save.';

      case ClinicalAction.queryMedications:
        return _medicationsResponse(patient);

      case ClinicalAction.summarize:
      case ClinicalAction.unknown:
        return _optionalLlmResponse(
          patient,
          message,
          observationHints,
          patientMemory,
        );

      case ClinicalAction.greeting:
        return 'Hello. Select or admit a patient, then record vitals such as "BP 120/80, HR 78" or document a medication such as "Administered Zofran 4 mg PO".';

      case ClinicalAction.help:
        return 'I can prepare vital, medication, and nursing-observation entries; show records; show changes; and summarize this selected patient. Every entry is reviewed before saving.';

      case ClinicalAction.cancel:
        return 'No new record was created.';
    }
  }

  Future<void> _refreshMetrics(String patientId) async {
    final metrics = await _apiService.getVitalsDelta(patientId);
    if (_selectedPatient?.id == patientId) {
      _currentMetrics = DeltaMetrics.fromJson(metrics);
    }
  }

  void _stageProposal({
    required Patient patient,
    required ClinicalCommand command,
    required String sourceText,
    required String interpreter,
    required String chatSessionId,
  }) {
    // A long on-device inference can finish after the nurse selects another
    // patient or another chat. Never surface a proposal outside its original
    // patient/session scope.
    if (_selectedPatient?.id != patient.id ||
        _activeChatSession?.id != chatSessionId) {
      return;
    }
    _pendingProposal = ClinicalRecordProposal(
      patientId: patient.id,
      patientName: patient.name,
      chatSessionId: chatSessionId,
      command: command,
      sourceText: sourceText,
      interpreter: interpreter,
      createdAt: DateTime.now(),
    );
  }

  Future<void> confirmPendingProposal() async {
    final proposal = _pendingProposal;
    if (proposal == null || _isResponding) return;
    if (_selectedPatient?.id != proposal.patientId) {
      _pendingProposal = null;
      notifyListeners();
      return;
    }

    _isResponding = true;
    notifyListeners();
    try {
      switch (proposal.command.action) {
        case ClinicalAction.recordVitals:
          await _apiService.recordVitals(
            proposal.patientId,
            proposal.command.vitals
                .map(
                  (vital) => {
                    'type': vital.type,
                    'value': vital.value,
                    'unit': vital.unit,
                  },
                )
                .toList(),
            sourceText: proposal.sourceText,
            recordedAt: proposal.command.recordedAt,
          );
          await _refreshMetrics(proposal.patientId);
          await _appendAssistantMessage(
            proposal.patientId,
            'Saved for ${proposal.patientName}: ${proposal.summary}.',
            sessionId: proposal.chatSessionId,
          );
          break;
        case ClinicalAction.recordMedication:
          await _apiService.recordMedication(
            proposal.patientId,
            name: proposal.command.medication!.name,
            dose: proposal.command.medication!.dose,
            route: proposal.command.medication!.route,
            status: proposal.command.medication!.status,
            sourceText: proposal.sourceText,
            recordedAt: proposal.command.recordedAt,
          );
          await _appendAssistantMessage(
            proposal.patientId,
            'Saved medication documentation for ${proposal.patientName}: ${proposal.summary}.',
            sessionId: proposal.chatSessionId,
          );
          break;
        case ClinicalAction.recordNote:
          await _apiService.recordNursingNote(
            proposal.patientId,
            content: proposal.sourceText,
            sourceText: proposal.sourceText,
            category: proposal.command.noteCategory ?? 'nursing_observation',
            recordedAt: proposal.command.recordedAt,
          );
          await _appendAssistantMessage(
            proposal.patientId,
            'Saved nursing observation for ${proposal.patientName}.',
            sessionId: proposal.chatSessionId,
          );
          break;
        default:
          throw StateError('Only charting proposals can be confirmed.');
      }
      _pendingProposal = null;
    } catch (error) {
      debugPrint('Error confirming clinical proposal: $error');
      await _appendAssistantMessage(
        proposal.patientId,
        'I could not save that record. Please review it and try again.',
        sessionId: proposal.chatSessionId,
      );
    } finally {
      _isResponding = false;
      notifyListeners();
    }
  }

  Future<void> discardPendingProposal() async {
    final proposal = _pendingProposal;
    if (proposal == null || _isResponding) return;
    _pendingProposal = null;
    await _appendAssistantMessage(
      proposal.patientId,
      'Proposal discarded. No clinical record was saved.',
      sessionId: proposal.chatSessionId,
    );
    notifyListeners();
  }

  Future<void> _appendAssistantMessage(
    String patientId,
    String content, {
    required String sessionId,
  }) async {
    final message = ChatMessage(
      id: 'assistant_${DateTime.now().microsecondsSinceEpoch}',
      sessionId: sessionId,
      role: 'assistant',
      content: content,
      timestamp: DateTime.now(),
    );
    if (_selectedPatient?.id == patientId &&
        _activeChatSession?.id == sessionId) {
      _messages.add(message);
    }
    await _apiService.saveChatMessage(
      id: message.id,
      patientId: patientId,
      sessionId: sessionId,
      role: message.role,
      content: message.content,
      createdAt: message.timestamp,
    );
  }

  Future<String> _vitalsResponse(Patient patient) async {
    final metrics = await _apiService.getVitalsDelta(patient.id);
    if (metrics['has_data'] != true) {
      return 'No vital readings have been recorded for ${patient.name} yet.';
    }
    final current = Map<String, dynamic>.from(metrics['current'] as Map);
    final values = <String>[];
    final systolic = current['systolic'];
    final diastolic = current['diastolic'];
    if (systolic != null && diastolic != null) {
      values.add(
        'BP ${_formatNumber(systolic)}/${_formatNumber(diastolic)} mmHg',
      );
    }
    _appendVital(
      values,
      'HR',
      current['heart_rate'],
      current['heart_rate_unit'] ?? 'bpm',
    );
    _appendVital(
      values,
      'Temp',
      current['temperature'],
      current['temperature_unit'] ?? '°C',
    );
    _appendVital(values, 'SpO₂', current['spo2'], current['spo2_unit'] ?? '%');
    _appendVital(
      values,
      'RR',
      current['respiratory_rate'],
      current['respiratory_rate_unit'] ?? '/min',
    );
    _appendVital(
      values,
      'Weight',
      current['weight'],
      current['weight_unit'] ?? 'kg',
    );
    return values.isEmpty
        ? 'No recognizable current vital readings are available for ${patient.name}.'
        : 'Latest records for ${patient.name}: ${values.join(', ')}.';
  }

  Future<String> _trendsResponse(Patient patient) async {
    final metrics = await _apiService.getVitalsDelta(patient.id);
    if (metrics['has_data'] != true) {
      return 'No vital history has been recorded for ${patient.name} yet.';
    }
    final deltas = Map<String, dynamic>.from(metrics['deltas'] as Map);
    final descriptions = <String>[];
    for (final entry in deltas.entries) {
      final value = Map<String, dynamic>.from(entry.value as Map);
      final trend = value['trend']?.toString() ?? 'stable';
      if (value['significance'] == 'first reading') continue;
      descriptions.add('${_displayVitalName(entry.key)} is $trend');
    }
    return descriptions.isEmpty
        ? 'There is one recorded reading for each available vital. Record another set to show a change over time.'
        : 'Since the prior recorded reading for ${patient.name}, ${descriptions.join('; ')}.';
  }

  Future<String> _medicationsResponse(Patient patient) async {
    final medications = await _apiService.getMedications(patient.id, limit: 10);
    if (medications.isEmpty) {
      return 'No medication records have been documented for ${patient.name} yet.';
    }
    final lines = medications.map((record) {
      final pieces = [
        record['name']?.toString() ?? 'Unnamed medication',
        if (record['dose']?.toString().isNotEmpty == true)
          record['dose'].toString(),
        if (record['route']?.toString().isNotEmpty == true)
          record['route'].toString(),
      ];
      return '${pieces.join(' ')} — ${record['status']}';
    }).toList();
    return 'Medication history for ${patient.name}:\n${lines.join('\n')}\n\nThis app does not calculate medication due times.';
  }

  Future<String> _optionalLlmResponse(
    Patient patient,
    String message,
    List<ClinicalObservation> observationHints,
    String patientMemory,
  ) async {
    final llm = _llmService;
    if (llm?.isReady != true) {
      return 'I did not understand that as a record or query. Try "Help" to see supported local commands.';
    }
    final prompt = llm!.buildClinicalPrompt(
      patientName: patient.name,
      userMessage: message,
      observationHints: observationHints,
      patientMemory: patientMemory,
    );
    final response = await llm.generateResponse(prompt);
    return response.isEmpty
        ? 'I could not form a reliable response. Try "Help" for supported local commands.'
        : response;
  }

  String _formatPatientMemory(Map<String, List<Map<String, dynamic>>> memory) {
    final lines = <String>[];
    final notes = memory['notes'] ?? const [];
    if (notes.isNotEmpty) {
      lines.add(
        'Recent nursing observations: ${notes.map((note) => note['content']).join(' | ')}',
      );
    }
    final vitals = memory['vitals'] ?? const [];
    if (vitals.isNotEmpty) {
      lines.add(
        'Recent vitals: ${vitals.map((vital) => '${vital['vital_type']} ${_formatNumber(vital['value'])} ${vital['unit']}').join(', ')}',
      );
    }
    final medications = memory['medications'] ?? const [];
    if (medications.isNotEmpty) {
      lines.add(
        'Recent medications: ${medications.map((medication) => '${medication['name']} ${medication['status']}').join(', ')}',
      );
    }
    final messages = memory['recent_nurse_messages'] ?? const [];
    if (messages.isNotEmpty) {
      lines.add(
        'Recent nurse messages: ${messages.reversed.map((entry) => entry['content']).join(' | ')}',
      );
    }
    final compact = lines.join('\n');
    return compact.length <= 1400 ? compact : compact.substring(0, 1400);
  }

  void _appendVital(
    List<String> values,
    String label,
    dynamic value,
    dynamic unit,
  ) {
    if (value != null) values.add('$label ${_formatNumber(value)} $unit');
  }

  String _formatNumber(dynamic value) {
    final number = value is num
        ? value.toDouble()
        : double.tryParse(value.toString());
    if (number == null) return value.toString();
    return number == number.roundToDouble()
        ? number.toStringAsFixed(0)
        : number.toStringAsFixed(1);
  }

  String _displayVitalName(String key) => switch (key) {
    'bp_systolic' => 'systolic BP',
    'bp_diastolic' => 'diastolic BP',
    'heart_rate' => 'heart rate',
    'temperature' => 'temperature',
    'spo2' => 'SpO₂',
    'respiratory_rate' => 'respiratory rate',
    'weight' => 'weight',
    _ => key,
  };
}
