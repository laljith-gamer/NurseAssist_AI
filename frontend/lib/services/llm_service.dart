import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_gemma/flutter_gemma.dart';
import 'package:path_provider/path_provider.dart';
import 'package:path/path.dart' as path;

import 'clinical_command_parser.dart';
import 'local_nlp_service.dart';

/// Wraps flutter_gemma for on-device LLM inference.
/// Downloads the Gemma 3 1B IT model from GitHub Releases on first launch.
class LlmService extends ChangeNotifier {
  static const String _modelUrl =
      'https://huggingface.co/litert-community/Gemma3-1B-IT/resolve/main/gemma3-1b-it-int4.task?download=true';
  static const String _modelFileName =
      'gemma3-1b-it-int4.task';

  bool _isInitializing = false;
  bool _isReady = false;
  String _statusMessage = 'Checking...';
  String? _errorMessage;
  InferenceModel? _model;
  InferenceChat? _chat;
  bool _isGenerating = false;
  Future<void>? _initializationFuture;

  bool get isInitializing => _isInitializing;
  bool get isReady => _isReady;
  String get statusMessage => _statusMessage;
  String? get errorMessage => _errorMessage;

  /// Ensure the model file is installed from bundled app assets.
  Future<void> _ensureModelInstalled() async {
    if (kIsWeb) return;

    final isInstalled = await FlutterGemma.isModelInstalled(_modelFileName);
    if (isInstalled) return;

    _statusMessage = 'Unpacking AI model from app bundle...';
    notifyListeners();

    final appDir = await getApplicationDocumentsDirectory();
    final tempFile = File(path.join(appDir.path, _modelFileName));

    if (await tempFile.exists()) {
      try {
        await tempFile.delete();
      } catch (_) {}
    }

    try {
      final byteData = await rootBundle.load('assets/models/$_modelFileName');
      await tempFile.writeAsBytes(
        byteData.buffer.asUint8List(byteData.offsetInBytes, byteData.lengthInBytes),
        flush: true,
      );

      _statusMessage = 'Installing AI model...';
      notifyListeners();

      await FlutterGemma.installModel(
        modelType: ModelType.gemmaIt,
        fileType: ModelFileType.task,
      ).fromFile(tempFile.path).install();
    } catch (e) {
      if (await tempFile.exists()) {
        try {
          await tempFile.delete();
        } catch (_) {}
      }
      rethrow;
    }
  }

  /// Initialize the LLM engine for inference
  Future<void> initializeEngine() async {
    if (_isReady) return;

    // The native task-model allocation is expensive. Reuse the in-flight
    // initialization rather than starting another allocation from a route
    // change or an app-resume event.
    final activeInitialization = _initializationFuture;
    if (activeInitialization != null) return activeInitialization;

    final initialization = _initializeEngine();
    _initializationFuture = initialization;
    return initialization;
  }

  Future<void> _initializeEngine() async {
    _isInitializing = true;
    _errorMessage = null;
    _statusMessage = 'Loading AI engine...';
    notifyListeners();

    try {
      await _ensureModelInstalled();

      // CPU is slower but gives a reliable on-device initialization path,
      // especially on Android emulators where GPU/OpenCL can crash.
      final preferCpu = !kIsWeb;

      _model = await FlutterGemma.getActiveModel(
        preferredBackend: preferCpu
            ? PreferredBackend.cpu
            : PreferredBackend.gpu,
        maxTokens: 1280,
      );

      _chat = await _model!.createChat(
        // Slightly relaxed settings allow natural personality while keeping
        // clinical output reliable. topK=3 is still very conservative.
        temperature: 0.2,
        topK: 3,
        topP: 0.8,
        tokenBuffer: 128,
      );

      _isReady = true;
      _statusMessage = 'AI Ready';
      debugPrint('LLM engine initialized successfully (Gemma 3 1B IT).');
    } catch (e) {
      _errorMessage = 'Engine init failed: ${e.toString()}';
      _isReady = false;
      _statusMessage = 'AI engine could not start';
      debugPrint('LLM engine init error: $e');
    } finally {
      _isInitializing = false;
      _initializationFuture = null;
      notifyListeners();
    }
  }

  /// Regex to strip special/control tokens the model may emit
  static final RegExp _specialTokenPattern = RegExp(
    r'<pad>|<unk>|<s>|</s>|<bos>|<eos>|'
    r'<unused\d+>|'
    r'\[multimodal\]|\[unused\d+\]|'
    r'<\|.*?\|>',
    caseSensitive: false,
  );

  /// Strip special tokens and check if the response is usable
  String _sanitizeResponse(String raw) {
    // Remove special tokens
    var cleaned = raw.replaceAll(_specialTokenPattern, '');
    // Collapse excessive whitespace left behind
    cleaned = cleaned.replaceAll(RegExp(r'\s{2,}'), ' ').trim();
    // If what remains is too short or empty, treat as garbage
    if (cleaned.length < 3) return '';
    // A malformed task bundle can occasionally echo the exact prompt. That is
    // not a useful answer and was a major source of apparent repetition.
    if (cleaned.startsWith('You are NurseAssist AI,')) return '';
    return cleaned;
  }



  Future<void> _prepareSingleTurn() async {
    if (_chat == null) throw StateError('Chat session not available.');
    // The prior implementation kept every unrelated patient interaction in a
    // single model context. Small on-device models then echoed or repeated old
    // turns. Resetting is cheap because the loaded model weights stay in RAM.
    await _chat!.clearHistory();
  }

  /// Generate a response from the LLM using streaming
  Stream<String> generateResponseStream(String prompt) async* {
    if (!_isReady) {
      yield 'AI model is still loading. Please wait a moment.';
      return;
    }

    if (_isGenerating) {
      yield 'The AI is still responding to another request.';
      return;
    }
    _isGenerating = true;
    try {
      if (_chat == null) {
        yield 'Chat session not available.';
        return;
      }

      await _prepareSingleTurn();
      await _chat!.addQueryChunk(Message(text: prompt, isUser: true));
      await for (final token in _chat!.session.getResponseAsync()) {
        final cleaned = _sanitizeResponse(token);
        if (cleaned.isNotEmpty) {
          yield cleaned;
        }
      }
    } catch (e) {
      debugPrint('LLM generation error: $e');
      yield 'Sorry, I encountered an error generating a response.';
    } finally {
      _isGenerating = false;
    }
  }

  /// Generate a complete response (non-streaming)
  Future<String> generateResponse(String prompt) async {
    if (!_isReady) {
      return 'AI model is still loading.';
    }

    if (_isGenerating) {
      return '';
    }
    _isGenerating = true;
    try {
      if (_chat == null) return 'Chat session not available.';

      await _prepareSingleTurn();
      await _chat!.addQueryChunk(Message(text: prompt, isUser: true));
      final response = await _chat!.session.getResponse();
      final cleaned = _sanitizeResponse(response);
      // Return empty string so caller can fall back to template response
      if (cleaned.isEmpty) {
        debugPrint('LLM returned garbage output, falling back to template.');
        return '';
      }
      return cleaned;
    } catch (e) {
      debugPrint('LLM generation error: $e');
      return 'Sorry, I encountered an error.';
    } finally {
      _isGenerating = false;
    }
  }

  /// Interprets free-form nursing language into a structured JSON command.
  /// The JSON always includes a `reply` field — the model's natural-language
  /// response shown to the nurse. Clinical writes also include structured data
  /// for validation. This is a SINGLE inference call.
  Future<ClinicalCommand?> interpretClinicalCommand(
    String message, {
    List<ClinicalObservation> observationHints = const [],
    String patientMemory = '',
  }) async {
    if (!_isReady || _chat == null || _isGenerating) return null;
    _isGenerating = true;
    try {
      await _prepareSingleTurn();
      final now = DateTime.now().toIso8601String();
      final hints = observationHints.isEmpty
          ? 'none'
          : observationHints.map((hint) => hint.name).join(', ');
      final schema =
          '''You are NurseAssist AI, a warm, professional, and highly intelligent clinical nursing assistant running on-device.
You help nurses chart vitals, medications, and notes. You can also answer clinical questions, summarize patients, and have friendly conversations.
Current date/time: $now

RULES:
1. Output ONLY valid JSON. No markdown fences, no extra text.
2. ALWAYS include a "reply" field with a friendly, concise, natural response for the nurse.
3. For clinical data (vitals, meds, notes), ALSO include the structured fields.
4. Be warm and professional. Use the patient context to give informed answers.
5. For summaries, actually analyze the patient data and give a useful clinical overview.
6. If the nurse just wants to chat or asks a question, use action "conversation".
7. If the nurse describes patient symptoms, complaints, or observations conversationally, use action record_note to document them as a nursing observation.
8. If the nurse asks you to prepare, write, compile, or generate documentation, notes, a summary, or a report, use action summarize.
9. Always provide a warm, acknowledging reply. Never give a generic template response.

JSON Schema:
Clinical writes: {"v":1,"action":"record_vitals|record_medication|record_note|batch_record","reply":"Your friendly response","timestamp":"$now",...data fields...}
Queries: {"v":1,"action":"query_vitals|query_trends|query_medications|summarize","reply":"Your informed answer using the patient context below"}
Conversation: {"v":1,"action":"conversation|greeting|help|cancel","reply":"Your natural response"}

Vital form: "vitals":[{"type":"blood_pressure","systolic":120,"diastolic":80},{"type":"heart_rate|temperature|spo2|respiratory_rate|weight","value":N,"unit":"bpm|c|f|percent|per_min|kg|lb"}]
Medication form: "medication":{"name":"...","dose":"...","route":"PO|IV|IM|SC|TOPICAL|INHALED","status":"administered|held|started|discontinued"}
Note form: "note":"...","category":"nursing_observation"

Examples:
Nurse: "BP 140/90 hr 85" -> {"v":1,"action":"record_vitals","reply":"Got it — BP 140/90 and heart rate 85. I'll prepare that for your review.","timestamp":"$now","vitals":[{"type":"blood_pressure","systolic":140,"diastolic":90},{"type":"heart_rate","value":85,"unit":"bpm"}]}
Nurse: "hey" -> {"v":1,"action":"greeting","reply":"Hi there! How can I help you with charting today?"}
Nurse: "how critical is a systolic of 180?" -> {"v":1,"action":"conversation","reply":"A systolic BP of 180 mmHg is considered a hypertensive urgency. It warrants prompt clinical attention and potential intervention."}
Nurse: "Temperature is 38.2 degrees Celsius, pulse is 104, respiratory rate is 22, blood pressure is 108 over 68, and oxygen saturation is 96 percent" -> {"v":1,"action":"record_vitals","reply":"Got it — temp 38.2°C, pulse 104, RR 22, BP 108/68, SpO2 96%. I'll prepare those for charting.","timestamp":"$now","vitals":[{"type":"temperature","value":38.2,"unit":"c"},{"type":"heart_rate","value":104,"unit":"bpm"},{"type":"respiratory_rate","value":22,"unit":"per_min"},{"type":"blood_pressure","systolic":108,"diastolic":68},{"type":"spo2","value":96,"unit":"percent"}]}
Nurse: "He took one paracetamol tablet yesterday after dinner around 9 PM" -> {"v":1,"action":"record_medication","reply":"Noted — paracetamol taken around 9 PM yesterday.","medication":{"name":"paracetamol","dose":"1 tablet","route":"PO","status":"administered"}}
Nurse: "He complains of a headache that started yesterday evening, rates it 6 out of 10, worse when standing up" -> {"v":1,"action":"record_note","reply":"I've noted the headache — 6/10 severity, frontal, positional. I'll document this observation.","note":"Patient c/o headache since yesterday evening, 6/10 severity, worse with standing","category":"nursing_observation"}
Nurse: "He feels weak getting out of bed, slightly nauseous, only had one glass of water" -> {"v":1,"action":"record_note","reply":"Noted — weakness on standing, mild nausea, poor oral intake. I'll document these observations.","note":"Patient reports weakness on ambulation, mild nausea, poor PO intake (1 glass water)","category":"nursing_observation"}
Nurse: "Can you prepare a nursing documentation note based on what I've told you?" -> {"v":1,"action":"summarize","reply":"Here's a summary based on today's observations..."}
''';

      final fullPrompt =
          '$schema\nPatient context (do not repeat as new facts):\n$patientMemory\nObservation hints: $hints\n<message>\n$message\n</message>';
      await _chat!.addQueryChunk(
        Message(
          text: fullPrompt,
          isUser: true,
        ),
      );
      final raw = await _chat!.session.getResponse();
      return ClinicalCommandParser.fromAiJson(_sanitizeResponse(raw));
    } catch (error) {
      debugPrint('AI clinical interpretation error: $error');
      return null;
    } finally {
      _isGenerating = false;
    }
  }
}

