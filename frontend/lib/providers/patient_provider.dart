import 'package:flutter/material.dart';

import '../models/types.dart';
import '../services/api_service.dart';
import '../services/clinical_command_parser.dart';
import '../services/llm_service.dart';
import '../services/local_nlp_service.dart';
import '../services/terminology_service.dart';

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
      return command.vitals.map((v) => v.displayValue).join(', ');
    }
    if (command.action == ClinicalAction.recordNote) {
      return command.noteText ?? sourceText;
    }
    if (command.action == ClinicalAction.recordMedication) {
      return command.medications
          .map(
            (m) => '${m.name} ${m.dose ?? ''} ${m.route ?? ''} (${m.status})'
                .trim(),
          )
          .join(', ');
    }
    if (command.action == ClinicalAction.batchRecord) {
      final parts = <String>[];
      if (command.vitals.isNotEmpty) {
        parts.add(
          'Vitals: ${command.vitals.map((v) => v.displayValue).join(', ')}',
        );
      }
      if (command.medications.isNotEmpty) {
        parts.add(
          'Meds: ${command.medications.map((m) => '${m.name} ${m.dose ?? ''} ${m.route ?? ''} (${m.status})'.trim()).join(', ')}',
        );
      }
      if (command.noteText != null) {
        parts.add('Note: ${command.noteText}');
      }
      return parts.join(' | ');
    }
    return '';
  }
}

/// Coordinates the clinical command path. An on-device LLM interprets normal
/// nurse language; deterministic code only validates output and accesses the
/// local record store.
class PatientProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();
  final LocalNlpService _nlpService;
  final TerminologyService _terminologyService = TerminologyService();
  LlmService? _llmService;

  final List<Patient> _patients = [];
  Patient? _selectedPatient;
  DeltaMetrics? _currentMetrics;
  final List<ChatMessage> _messages = [];
  final List<ChatSession> _chatSessions = [];
  ChatSession? _activeChatSession;
  List<Map<String, dynamic>> _vitalHistory = [];
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
  List<Map<String, dynamic>> get vitalHistory =>
      List.unmodifiable(_vitalHistory);
  ClinicalRecordProposal? get pendingProposal => _pendingProposal;
  ApiService get apiService => _apiService;

  PatientProvider(this._nlpService) {
    _terminologyService.loadDictionary();
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
    } catch (error, stackTrace) {
      debugPrint('Error loading patient details: $error\n$stackTrace');
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
    } catch (error, stackTrace) {
      debugPrint('Error refreshing metrics: $error\n$stackTrace');
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
        _apiService.getVitals(patientId),
      ]);
      // A user can select another patient while reads are in flight.
      if (_selectedPatient?.id != patientId) return;

      _currentMetrics = DeltaMetrics.fromJson(
        Map<String, dynamic>.from(results[0] as Map),
      );

      final history = (results[2] as List).cast<Map<String, dynamic>>();
      history.sort((a, b) {
        final timeA = a['recorded_at'] is int
            ? a['recorded_at'] as int
            : DateTime.parse(
                a['recorded_at'].toString(),
              ).millisecondsSinceEpoch;
        final timeB = b['recorded_at'] is int
            ? b['recorded_at'] as int
            : DateTime.parse(
                b['recorded_at'].toString(),
              ).millisecondsSinceEpoch;
        return timeA.compareTo(timeB);
      });
      _vitalHistory = history;

      final sessions = (results[1] as List)
          .cast<Map<String, dynamic>>()
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
    } catch (error, stackTrace) {
      debugPrint('Error loading local patient history: $error\n$stackTrace');
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
      await _apiService.createChatSession(patient.id, title: 'New chat'),
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
    } catch (error, stackTrace) {
      debugPrint('Error fetching specific chat session: $error\n$stackTrace');
    }
    notifyListeners();
  }

  Future<void> deleteChatSession(ChatSession session) async {
    final patient = _selectedPatient;
    if (patient == null || _isResponding) return;

    await _apiService.deleteChatSession(session.id);
    _chatSessions.removeWhere((s) => s.id == session.id);

    if (_activeChatSession?.id == session.id) {
      if (_chatSessions.isNotEmpty) {
        await selectChatSession(_chatSessions.first);
      } else {
        _activeChatSession = null;
        _messages.clear();
        await startNewChat();
      }
    } else {
      notifyListeners();
    }
  }

  Future<void> deleteMessage(ChatMessage msg) async {
    await _apiService.deleteChatMessage(msg.id);
    _messages.removeWhere((m) => m.id == msg.id);
    notifyListeners();
  }

  Future<void> updateMessageText(ChatMessage msg, String newText) async {
    await _apiService.updateChatMessageText(msg.id, newText);
    final index = _messages.indexWhere((m) => m.id == msg.id);
    if (index != -1) {
      _messages[index] = _messages[index].copyWith(content: newText);
      notifyListeners();
    }
  }

  Future<void> renameChatSession(ChatSession session, String newTitle) async {
    await _apiService.updateChatSessionTitle(session.id, newTitle);
    final index = _chatSessions.indexWhere((s) => s.id == session.id);
    if (index != -1) {
      _chatSessions[index] = _chatSessions[index].copyWith(title: newTitle);
      if (_activeChatSession?.id == session.id) {
        _activeChatSession = _chatSessions[index];
      }
      notifyListeners();
    }
  }

  Future<void> updatePatient(String name, String details) async {
    final patient = _selectedPatient;
    if (patient == null) return;
    await _apiService.updatePatient(patient.id, name, details);
    final index = _patients.indexWhere((p) => p.id == patient.id);
    if (index != -1) {
      _patients[index] = _patients[index].copyWith(name: name, details: details);
      _selectedPatient = _patients[index];
      notifyListeners();
    }
  }

  Future<void> deletePatient() async {
    final patient = _selectedPatient;
    if (patient == null) return;
    await _apiService.deletePatient(patient.id);
    _patients.removeWhere((p) => p.id == patient.id);
    if (_patients.isNotEmpty) {
      await selectPatient(_patients.first);
    } else {
      _selectedPatient = null;
      _chatSessions.clear();
      _activeChatSession = null;
      _messages.clear();
      notifyListeners();
    }
  }

  Future<void> deleteVital(String id) async {
    await _apiService.deleteVital(id);
    await _refreshMetrics(_selectedPatient!.id);
  }

  Future<void> deleteMedication(String id) async {
    await _apiService.deleteMedication(id);
    await _refreshMetrics(_selectedPatient!.id);
  }

  Future<void> deleteNursingNote(String id) async {
    await _apiService.deleteNursingNote(id);
    await _refreshMetrics(_selectedPatient!.id);
  }

  Future<Map<String, List<Map<String, dynamic>>>> getPatientMemoryRaw() async {
    final patient = _selectedPatient;
    if (patient == null) return {};
    return await _apiService.getPatientMemory(patient.id);
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
        final updatedSession = chatSession.copyWith(title: newTitle);
        if (_activeChatSession?.id == chatSession.id) {
          _activeChatSession = updatedSession;
        }
        // Update the session list so the sidebar redraws
        final index = _chatSessions.indexWhere((s) => s.id == chatSession.id);
        if (index != -1) {
          _chatSessions[index] = updatedSession;
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
        observationHints: observationHints.map((hint) => hint.name).toList(),
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
    } catch (error, stackTrace) {
      debugPrint('Error processing command: $error\n$stackTrace');
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
        await confirmPendingProposal(autoCommit: true);
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'Recorded vitals for ${patient.name}.';

      case ClinicalAction.queryVitals:
        if (command.replyText != null && command.replyText!.isNotEmpty) {
          return command.replyText!;
        }
        return _vitalsResponse(patient);

      case ClinicalAction.queryTrends:
        if (command.replyText != null && command.replyText!.isNotEmpty) {
          return command.replyText!;
        }
        return _trendsResponse(patient);

      case ClinicalAction.recordMedication:
        _stageProposal(
          patient: patient,
          command: command,
          sourceText: message,
          interpreter: interpreter,
          chatSessionId: chatSessionId,
        );
        await confirmPendingProposal(autoCommit: true);
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'Recorded medication for ${patient.name}.';

      case ClinicalAction.recordNote:
        _stageProposal(
          patient: patient,
          command: command,
          sourceText: message,
          interpreter: interpreter,
          chatSessionId: chatSessionId,
        );
        await confirmPendingProposal(autoCommit: true);
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'Recorded nursing observation for ${patient.name}.';

      case ClinicalAction.batchRecord:
        _stageProposal(
          patient: patient,
          command: command,
          sourceText: message,
          interpreter: interpreter,
          chatSessionId: chatSessionId,
        );
        await confirmPendingProposal(autoCommit: true);
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'Recorded batch entry for ${patient.name}.';

      case ClinicalAction.queryMedications:
        if (command.replyText != null && command.replyText!.isNotEmpty) {
          return command.replyText!;
        }
        return _medicationsResponse(patient);

      case ClinicalAction.summarize:
        if (command.replyText != null && command.replyText!.isNotEmpty) {
          return command.replyText!;
        }
        return _buildFallbackSummary(patient);

      case ClinicalAction.greeting:
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'Hello! I\'m NurseAssist, your clinical charting assistant. How can I help you today?';

      case ClinicalAction.help:
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'I can help you record vitals, medications, and nursing notes. You can also ask me to summarize a patient or query their history.';

      case ClinicalAction.cancel:
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'No new record was created.';

      case ClinicalAction.conversation:
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'I\'m not sure how to help with that. Try asking me to record vitals, medications, or notes.';

      case ClinicalAction.custom:
        final customCommand = ClinicalCommand(
          action: ClinicalAction.recordNote, // Map custom intents to notes locally
          customActionName: command.customActionName,
          noteCategory: 'custom_intent_log',
          noteText: 'Custom Action Extracted: ${command.customActionName}\nOriginal text: $message',
          recordedAt: command.recordedAt,
          replyText: command.replyText,
        );
        _stageProposal(
          patient: patient,
          command: customCommand,
          sourceText: message,
          interpreter: interpreter,
          chatSessionId: chatSessionId,
        );
        await confirmPendingProposal(autoCommit: true);
        return (command.replyText?.isNotEmpty == true)
            ? command.replyText!
            : 'Recorded custom interaction for ${patient.name}.';

      case ClinicalAction.unknown:
        if (command.replyText?.isNotEmpty == true) return command.replyText!;
        final hintNames = observationHints.map((h) => h.name).join(', ');
        if (hintNames.isNotEmpty) {
          return "I've noted some observations ($hintNames). Would you like me to document these as a nursing note for ${patient.name}?";
        }
        return "I hear you. Would you like me to record vitals, log a medication, or document an observation for ${patient.name}?";
    }
  }

  Future<void> _refreshMetrics(String patientId) async {
    final results = await Future.wait([
      _apiService.getVitalsDelta(patientId),
      _apiService.getVitals(patientId),
    ]);
    if (_selectedPatient?.id == patientId) {
      _currentMetrics = DeltaMetrics.fromJson(
        Map<String, dynamic>.from(results[0] as Map),
      );
      final history = (results[1] as List).cast<Map<String, dynamic>>();
      history.sort((a, b) {
        final timeA = a['recorded_at'] is int
            ? a['recorded_at'] as int
            : DateTime.parse(
                a['recorded_at'].toString(),
              ).millisecondsSinceEpoch;
        final timeB = b['recorded_at'] is int
            ? b['recorded_at'] as int
            : DateTime.parse(
                b['recorded_at'].toString(),
              ).millisecondsSinceEpoch;
        return timeA.compareTo(timeB);
      });
      _vitalHistory = history;
      notifyListeners();
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

    var finalCommand = command;
    if (command.action == ClinicalAction.recordNote &&
        command.noteText != null) {
      String modifiedNote = command.noteText!;
      final terms = _terminologyService.searchTerms(modifiedNote);
      for (final term in terms) {
        final standardized = _terminologyService.lookupTerm(term);
        if (standardized != null && !modifiedNote.contains(standardized)) {
          modifiedNote += ' [$standardized]';
        }
      }
      finalCommand = ClinicalCommand(
        action: command.action,
        noteCategory: command.noteCategory,
        noteText: modifiedNote,
        vitals: command.vitals,
        medications: command.medications,
        recordedAt: command.recordedAt,
        replyText: command.replyText,
      );
    }

    _pendingProposal = ClinicalRecordProposal(
      patientId: patient.id,
      patientName: patient.name,
      chatSessionId: chatSessionId,
      command: finalCommand,
      sourceText: sourceText,
      interpreter: interpreter,
      createdAt: DateTime.now(),
    );
  }

  Future<void> confirmPendingProposal({bool autoCommit = false}) async {
    final proposal = _pendingProposal;
    if (proposal == null || (_isResponding && !autoCommit)) return;
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
          if (!autoCommit) {
            await _appendAssistantMessage(
              proposal.patientId,
              'Saved for ${proposal.patientName}: ${proposal.summary}.',
              sessionId: proposal.chatSessionId,
            );
          }
          break;
        case ClinicalAction.recordMedication:
          for (final med in proposal.command.medications) {
            await _apiService.recordMedication(
              proposal.patientId,
              name: med.name,
              dose: med.dose,
              route: med.route,
              status: med.status,
              sourceText: proposal.sourceText,
              recordedAt: proposal.command.recordedAt,
            );
          }
          if (!autoCommit) {
            await _appendAssistantMessage(
              proposal.patientId,
              'Saved medication documentation for ${proposal.patientName}: ${proposal.summary}.',
              sessionId: proposal.chatSessionId,
            );
          }
          break;
        case ClinicalAction.recordNote:
          await _apiService.recordNursingNote(
            proposal.patientId,
            content: proposal.sourceText,
            sourceText: proposal.sourceText,
            category: proposal.command.noteCategory ?? 'nursing_observation',
            recordedAt: proposal.command.recordedAt,
          );
          if (!autoCommit) {
            await _appendAssistantMessage(
              proposal.patientId,
              'Saved nursing observation for ${proposal.patientName}.',
              sessionId: proposal.chatSessionId,
            );
          }
          break;
        case ClinicalAction.batchRecord:
          if (proposal.command.vitals.isNotEmpty) {
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
          }
          for (final med in proposal.command.medications) {
            await _apiService.recordMedication(
              proposal.patientId,
              name: med.name,
              dose: med.dose,
              route: med.route,
              status: med.status,
              sourceText: proposal.sourceText,
              recordedAt: proposal.command.recordedAt,
            );
          }
          if (proposal.command.noteText != null &&
              proposal.command.noteText!.isNotEmpty) {
            await _apiService.recordNursingNote(
              proposal.patientId,
              content: proposal.command.noteText!,
              sourceText: proposal.sourceText,
              category: proposal.command.noteCategory ?? 'nursing_observation',
              recordedAt: proposal.command.recordedAt,
            );
          }
          if (!autoCommit) {
            await _appendAssistantMessage(
              proposal.patientId,
              'Saved batch records for ${proposal.patientName}: ${proposal.summary}.',
              sessionId: proposal.chatSessionId,
            );
          }
          break;
        default:
          throw StateError('Only charting proposals can be confirmed.');
      }

      // Automatic ML reinforcement
      try {
        await _apiService.submitIntentFeedback(
          proposal.sourceText,
          proposal.command.customActionName ?? proposal.command.action.name,
        );
      } catch (e) {
        debugPrint('Failed to submit positive reinforcement: $e');
      }

      _pendingProposal = null;
    } catch (error, stackTrace) {
      debugPrint('Error confirming clinical proposal: $error\n$stackTrace');
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

    // Automatic ML reinforcement
    try {
      await _apiService.submitIntentFeedback(proposal.sourceText, 'rejected');
    } catch (e) {
      debugPrint('Failed to submit negative reinforcement: $e');
    }

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

  Future<String> _buildFallbackSummary(Patient patient) async {
    final memory = await _apiService.getPatientMemory(patient.id);
    final lines = <String>[];
    lines.add('Summary for ${patient.name}:');
    final notes = memory['notes'] ?? const [];
    if (notes.isNotEmpty) {
      lines.add(
        'Recent observations: ${notes.take(3).map((n) => n['content']).join('; ')}',
      );
    }
    final vitals = memory['vitals'] ?? const [];
    if (vitals.isNotEmpty) {
      lines.add(
        'Latest vitals: ${vitals.take(5).map((v) => '${v['vital_type']} ${v['value']} ${v['unit']}').join(', ')}',
      );
    }
    final meds = memory['medications'] ?? const [];
    if (meds.isNotEmpty) {
      lines.add(
        'Recent medications: ${meds.take(3).map((m) => '${m['name']} ${m['status']}').join(', ')}',
      );
    }
    if (lines.length == 1) {
      lines.add('No clinical data recorded yet.');
    }
    return lines.join('\n');
  }

  String _formatPatientMemory(Map<String, List<Map<String, dynamic>>> memory) {
    final lines = <String>[];
    final notes = memory['notes'] ?? const [];
    if (notes.isNotEmpty) {
      lines.add(
        'Recent nursing observations: ${notes.take(3).map((note) => note['content']).join(' | ')}',
      );
    }
    final vitals = memory['vitals'] ?? const [];
    if (vitals.isNotEmpty) {
      lines.add(
        'Recent vitals: ${vitals.take(3).map((vital) => '${vital['vital_type']} ${_formatNumber(vital['value'])} ${vital['unit']}').join(', ')}',
      );
    }
    final medications = memory['medications'] ?? const [];
    if (medications.isNotEmpty) {
      lines.add(
        'Recent medications: ${medications.take(3).map((med) => '${med['name']} (${med['dose']})').join(', ')}',
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
