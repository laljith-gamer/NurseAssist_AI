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
    required this.command,
    required this.sourceText,
    required this.interpreter,
    required this.createdAt,
  });

  final String patientId;
  final String patientName;
  final ClinicalCommand command;
  final String sourceText;
  final String interpreter;
  final DateTime createdAt;

  String get summary {
    if (command.action == ClinicalAction.recordVitals) {
      return command.vitals.map((vital) => vital.displayValue).join(', ');
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
  ClinicalRecordProposal? _pendingProposal;
  bool _isLoading = false;
  bool _isResponding = false;

  List<Patient> get patients => List.unmodifiable(_patients);
  Patient? get selectedPatient => _selectedPatient;
  DeltaMetrics? get currentMetrics => _currentMetrics;
  List<ChatMessage> get messages => List.unmodifiable(_messages);
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
    notifyListeners();

    try {
      final results = await Future.wait([
        _apiService.getVitalsDelta(patientId),
        _apiService.getChatHistory(patientId),
      ]);
      // A user can select another patient while reads are in flight.
      if (_selectedPatient?.id != patientId) return;

      _currentMetrics = DeltaMetrics.fromJson(
        Map<String, dynamic>.from(results[0] as Map),
      );
      final chatRows = results[1] as List<Map<String, dynamic>>;
      _messages.addAll(chatRows.map(_messageFromRow));
    } catch (error) {
      debugPrint('Error loading local patient history: $error');
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
      role: row['role']?.toString() ?? 'assistant',
      content: row['content']?.toString() ?? '',
      timestamp: timestamp,
      data: rawData is Map ? Map<String, dynamic>.from(rawData) : null,
    );
  }

  Future<void> sendMessage(String message) async {
    final patient = _selectedPatient;
    if (patient == null || _isResponding) return;

    // A proposal is intentionally short-lived. Sending a new message discards
    // an unsigned proposal instead of leaving a stale chart action available.
    _pendingProposal = null;
    _isResponding = true;
    final userMessage = ChatMessage(
      id: 'user_${DateTime.now().microsecondsSinceEpoch}',
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
        role: userMessage.role,
        content: userMessage.content,
        createdAt: userMessage.timestamp,
      );

      // Gemma is the primary interpreter. The smaller model contributes only
      // data-driven nursing context; it cannot create a command or a value.
      final observationHints = _nlpService.predictClinicalObservations(message);
      final aiCommand = await _llmService?.interpretClinicalCommand(
        message,
        observationHints: observationHints,
      );
      final command = aiCommand ?? ClinicalCommandParser.parse(message);
      final response = await _respondToCommand(
        patient: patient,
        message: message,
        command: command,
        observationHints: observationHints,
        interpreter: aiCommand == null ? 'offline fallback' : 'on-device AI',
      );

      // Do not write a response against a patient that was switched during a
      // slow optional LLM call. The action itself is already tied to the
      // originally selected patient and has been stored locally.
      final assistantMessage = ChatMessage(
        id: 'assistant_${DateTime.now().microsecondsSinceEpoch}',
        role: 'assistant',
        content: response,
        timestamp: DateTime.now(),
      );
      if (_selectedPatient?.id == patient.id) {
        _messages.add(assistantMessage);
      }
      await _apiService.saveChatMessage(
        id: assistantMessage.id,
        patientId: patient.id,
        role: assistantMessage.role,
        content: assistantMessage.content,
        createdAt: assistantMessage.timestamp,
      );
    } catch (error) {
      debugPrint('Error handling clinical command: $error');
      final errorMessage = ChatMessage(
        id: 'assistant_${DateTime.now().microsecondsSinceEpoch}',
        role: 'assistant',
        content: 'I could not save that local record. Please try again.',
        timestamp: DateTime.now(),
      );
      if (_selectedPatient?.id == patient.id) _messages.add(errorMessage);
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
  }) async {
    switch (command.action) {
      case ClinicalAction.recordVitals:
        _stageProposal(
          patient: patient,
          command: command,
          sourceText: message,
          interpreter: interpreter,
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
        );
        return 'I prepared a medication documentation entry for ${patient.name}. Review it below, then tap Confirm & Save.';

      case ClinicalAction.queryMedications:
        return _medicationsResponse(patient);

      case ClinicalAction.summarize:
        return _summaryResponse(patient);

      case ClinicalAction.greeting:
        return 'Hello. Select or admit a patient, then record vitals such as "BP 120/80, HR 78" or document a medication such as "Administered Zofran 4 mg PO".';

      case ClinicalAction.help:
        return 'I can record vitals, document medications, show the latest records, show changes, or summarize this patient. Examples: "Temp 38.1 C", "What are the latest vitals?", and "Show medication history".';

      case ClinicalAction.cancel:
        return 'No new record was created.';

      case ClinicalAction.unknown:
        return _optionalLlmResponse(patient, message, observationHints);
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
  }) {
    _pendingProposal = ClinicalRecordProposal(
      patientId: patient.id,
      patientName: patient.name,
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
          );
          await _refreshMetrics(proposal.patientId);
          await _appendAssistantMessage(
            proposal.patientId,
            'Saved for ${proposal.patientName}: ${proposal.summary}.',
          );
          break;
        case ClinicalAction.recordMedication:
          final medication = proposal.command.medication!;
          await _apiService.recordMedication(
            proposal.patientId,
            name: medication.name,
            dose: medication.dose,
            route: medication.route,
            status: medication.status,
            sourceText: proposal.sourceText,
          );
          await _appendAssistantMessage(
            proposal.patientId,
            'Saved medication documentation for ${proposal.patientName}: ${proposal.summary}.',
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
    );
    notifyListeners();
  }

  Future<void> _appendAssistantMessage(String patientId, String content) async {
    final message = ChatMessage(
      id: 'assistant_${DateTime.now().microsecondsSinceEpoch}',
      role: 'assistant',
      content: content,
      timestamp: DateTime.now(),
    );
    if (_selectedPatient?.id == patientId) _messages.add(message);
    await _apiService.saveChatMessage(
      id: message.id,
      patientId: patientId,
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

  Future<String> _summaryResponse(Patient patient) async {
    final metrics = await _apiService.getVitalsDelta(patient.id);
    final medications = await _apiService.getMedications(patient.id, limit: 3);
    final vitalSummary = await _vitalsResponse(patient);
    final alerts = List<String>.from(metrics['alerts'] as List? ?? const []);
    final medicationSummary = medications.isEmpty
        ? 'No medications documented.'
        : 'Recent medications: ${medications.map((m) => m['name']).join(', ')}.';
    final alertSummary = alerts.isEmpty
        ? 'No configured alerts.'
        : alerts.join(' ');
    return '${patient.name}: $vitalSummary $medicationSummary $alertSummary';
  }

  Future<String> _optionalLlmResponse(
    Patient patient,
    String message,
    List<ClinicalObservation> observationHints,
  ) async {
    final llm = _llmService;
    if (llm?.isReady != true) {
      return 'I did not understand that as a record or query. Try "Help" to see supported local commands.';
    }
    final prompt = llm!.buildClinicalPrompt(
      patientName: patient.name,
      userMessage: message,
      observationHints: observationHints,
    );
    final response = await llm.generateResponse(prompt);
    return response.isEmpty
        ? 'I could not form a reliable response. Try "Help" for supported local commands.'
        : response;
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
