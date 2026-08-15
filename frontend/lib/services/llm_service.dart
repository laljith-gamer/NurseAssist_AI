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
        // Low-variance settings reduce malformed structured output and
        // repetitive chat responses from the small on-device model.
        temperature: 0.2,
        topK: 1,
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

  /// Lets the model interpret free-form nursing language into a constrained
  /// JSON action. The JSON is validated by [ClinicalCommandParser] and then
  /// shown to the nurse for confirmation before a record can be saved. The
  /// trained SYNUR context is advisory; it never becomes a chart value.
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
          '''You are NurseAssist AI, an advanced, highly intelligent clinical nursing assistant. You possess vast medical knowledge, understand clinical triage (e.g. recognizing critical blood pressure or heart rate), and think like a professional charge nurse. 
Your primary job is to interpret free-form nursing notes and perfectly extract medical data into strict JSON format. 
Current date/time for reference: $now

CRITICAL RULES:
1. NO YAPPING. You must output ONLY valid JSON. Do not include markdown (```json), greetings, or explanations.
2. EXTRACT EVERYTHING. Look deeply into the message to find vitals, medications, or important clinical notes.
3. BE SMART. If the user says "BP is 120 over 80", you know that means systolic 120 and diastolic 80.

Schema: {"v":1,"action":"record_vitals|record_medication|record_note|batch_record|query_vitals|query_trends|query_medications|summarize|greeting|help|cancel|conversation","timestamp":"YYYY-MM-DDTHH:MM:SS or null",...}
Vital form: {"v":1,"action":"record_vitals","timestamp":"...","vitals":[{"type":"blood_pressure","systolic":120,"diastolic":80},{"type":"heart_rate|temperature|spo2|respiratory_rate|weight","value":78,"unit":"bpm|c|f|percent|per_min|kg|lb"}]}
Medication form: {"v":1,"action":"record_medication","timestamp":"...","medication":{"name":"...","dose":"... or null","route":"PO|IV|IM|SC|TOPICAL|INHALED or null","status":"administered|held|started|discontinued"}}
Note form: {"v":1,"action":"record_note","timestamp":"...","note":"...","category":"nursing_observation"}
Batch form: {"v":1,"action":"batch_record","timestamp":"...","vitals":[...],"medications":[...],"note":"..."}

Example 1: "BP 140/90 hr 85" -> {"v":1,"action":"record_vitals","timestamp":"$now","vitals":[{"type":"blood_pressure","systolic":140,"diastolic":90},{"type":"heart_rate","value":85,"unit":"bpm"}]}
Example 2: "BP 120/80 and I gave 500mg tylenol PO. Patient is resting." -> {"v":1,"action":"batch_record","timestamp":"$now","vitals":[{"type":"blood_pressure","systolic":120,"diastolic":80}],"medications":[{"name":"tylenol","dose":"500mg","route":"PO","status":"administered"}],"note":"Patient is resting."}
Example 3: "gave 500mg tylenol PO" -> {"v":1,"action":"record_medication","timestamp":"$now","medication":{"name":"tylenol","dose":"500mg","route":"PO","status":"administered"}}
''';
      
      final fullPrompt =
          '$schema\nSelected-patient memory (context only; do not repeat as new facts):\n$patientMemory\n<message>\n$message\n</message>';
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
  String buildClinicalPrompt({
    required String patientName,
    required String userMessage,
    List<ClinicalObservation> observationHints = const [],
    String patientMemory = '',
    ClinicalAction? action,
  }) {
    final hintText = observationHints.isEmpty
        ? 'none'
        : observationHints.map((hint) => hint.name).join(', ');

    String instruction = 'Respond as a world-class note-taking assistant. Synthesize the input into a concise, professional nursing note or summary.';
    
    if (action == ClinicalAction.greeting) {
      instruction = 'Politely and concisely greet the nurse. Do not list your features or explain what you can do unless explicitly asked. Just say hello.';
    } else if (action == ClinicalAction.help) {
      instruction = 'Briefly and concisely explain that you can record vitals, medications, and nursing observations, or query patient history.';
    } else if (action == ClinicalAction.unknown) {
      instruction = 'Respond naturally and concisely to the nurse\'s conversational input.';
    }

    return '''You are NurseAssist AI, a clinical nursing assistant running on-device.
You are assisting with the currently selected patient: $patientName.
Advisory nursing-observation context (not patient facts): $hintText
Selected-patient memory (context only):
$patientMemory
Nurse's input:
<message>
$userMessage
</message>

$instruction
Do not diagnose, prescribe, invent a record, or claim that anything was saved. If a request is unclear,
ask one focused clarification. Do not use markdown.''';
  }
}
