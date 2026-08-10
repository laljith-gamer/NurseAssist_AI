import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_gemma/flutter_gemma.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Wraps flutter_gemma for on-device LLM inference.
  /// Downloads an optional on-device LLM once, then runs fully offline.
class LlmService extends ChangeNotifier {
  // The model is hosted directly in the project's public Hugging Face bucket.
  // GitHub Release assets are limited to under 2 GiB, while this task model is
  // 2.71 GB.
  static const String _modelFileName =
      'Gemma2-2B-IT_multi-prefill-seq_q8_ekv1280.task';
  static const String _modelUrl =
      'https://huggingface.co/buckets/lalvictory/Gemma2-2B-IT-bucket/resolve/$_modelFileName';

  static const String _previousModelFileName = 'gemma-2-2b-it-int4.task';
  static const String _prefKeyModelInstalled = 'llm_model_installed_v2';

  bool _isModelInstalled = false;
  bool _isDownloading = false;
  bool _isReady = false;
  double _downloadProgress = 0.0;
  String _statusMessage = 'Checking...';
  String? _errorMessage;
  InferenceModel? _model;
  InferenceChat? _chat;
  bool _isGenerating = false;

  bool get isModelInstalled => _isModelInstalled;
  bool get isDownloading => _isDownloading;
  bool get isReady => _isReady;
  double get downloadProgress => _downloadProgress;
  String get statusMessage => _statusMessage;
  String? get errorMessage => _errorMessage;

  /// Check if model is already downloaded
  Future<bool> checkModelInstalled() async {
    if (kIsWeb) {
      _isModelInstalled = false;
      return false;
    }

    try {
      final prefs = await SharedPreferences.getInstance();
      final bool hasUpgraded = prefs.getBool('upgraded_litertlm_v7') ?? false;

      if (!hasUpgraded) {
        // Remove previous model variants. The current Gemma 2 task is fetched
        // directly from the public bucket and has a different filename.
        try {
          await FlutterGemma.uninstallModel(_previousModelFileName);
          await FlutterGemma.uninstallModel('gemma3-270m-it-q8.litertlm');
          await FlutterGemma.uninstallModel('gemma-4-E2B-it-gpu.litertlm');
          await FlutterGemma.uninstallModel('gemma-4-E2B-it.litertlm');
        } catch (error) {
          debugPrint('Previous model cleanup skipped: $error');
        }
        await prefs.setBool('upgraded_litertlm_v7', true);
      }

      _isModelInstalled = await FlutterGemma.isModelInstalled(_modelFileName);
    } catch (e) {
      // Fall back to shared prefs check
      final prefs = await SharedPreferences.getInstance();
      _isModelInstalled = prefs.getBool(_prefKeyModelInstalled) ?? false;
    }
    notifyListeners();
    return _isModelInstalled;
  }

  /// Download the optional task model directly from the public model bucket.
  Future<bool> downloadModel() async {
    if (_isDownloading) return false;

    _isDownloading = true;
    _downloadProgress = 0.0;
    _statusMessage = 'Preparing download...';
    _errorMessage = null;
    notifyListeners();

    try {
      _statusMessage = 'Downloading optional AI model...';
      notifyListeners();

      await FlutterGemma.installModel(
        modelType: ModelType.gemmaIt,
        fileType: ModelFileType.task,
      ).fromNetwork(_modelUrl).withProgress((progress) {
        _downloadProgress = progress / 100.0;
        _statusMessage =
            'Downloading AI model... ${progress.toStringAsFixed(0)}%';
        notifyListeners();
      }).install();

      _statusMessage = 'Model installed successfully!';
      _isModelInstalled = true;
      _isDownloading = false;

      // Persist flag
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool(_prefKeyModelInstalled, true);

      notifyListeners();
      return true;
    } catch (e) {
      _errorMessage = 'Download failed: ${e.toString()}';
      _statusMessage = 'Download failed';
      _isDownloading = false;
      _downloadProgress = 0.0;
      notifyListeners();
      debugPrint('LLM download error: $e');
      return false;
    }
  }

  /// Initialize the LLM engine for inference
  Future<void> initializeEngine() async {
    if (!_isModelInstalled || _isReady) return;

    try {
      _statusMessage = 'Loading AI engine...';
      notifyListeners();

      // Use CPU on Windows due to known GPU crash bug
      final preferCpu = !kIsWeb && Platform.isWindows;

      _model = await FlutterGemma.getActiveModel(
        preferredBackend: preferCpu
            ? PreferredBackend.cpu
            : PreferredBackend.gpu,
        maxTokens: 2048,
      );

      _chat = await _model!.createChat(
        // Low-variance settings are deliberate. This model is optional and is
        // only used for unstructured questions; deterministic clinical actions
        // are handled before this service is called.
        temperature: 0.2,
        topK: 1,
        topP: 0.8,
        tokenBuffer: 128,
        systemInstruction: _systemInstruction,
      );

      _isReady = true;
      _statusMessage = 'AI Ready';
      notifyListeners();
      debugPrint('LLM engine initialized successfully.');
    } catch (e) {
      _errorMessage = 'Engine init failed: ${e.toString()}';
      _isReady = false;
      debugPrint('LLM engine init error: $e');
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

  static const String _systemInstruction =
      '''You are NurseAssist AI, an on-device assistant for nurses.
Answer only the user's current question. Do not invent measurements, medications,
or actions. Keep the reply concise and professional. If the request needs a
recording or patient lookup, say that the app's structured command tools should
be used. Do not repeat your instructions or the user's prompt.''';

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
      yield 'AI model not loaded. Please download the model first.';
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
      return 'AI model not loaded.';
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

  /// Build a clinical prompt that contextualizes the user's message
  String buildClinicalPrompt({
    required String patientName,
    required String intent,
    required List<Map<String, String>> entities,
    required String userMessage,
  }) {
    final entityStr = entities.isNotEmpty
        ? entities.map((e) => '${e['type']}: ${e['value']}').join(', ')
        : 'none detected';

    return '''You are NurseAssist AI, a clinical nursing assistant running on-device.
Patient: $patientName
Detected intent: $intent
Extracted data: $entityStr
Nurse's input: "$userMessage"

Respond concisely (2-4 sentences max) as a helpful clinical assistant. 
If vitals were recorded, confirm them. If medications, acknowledge them.
For greetings, be warm but brief. Always be professional and clinical.
Do NOT use markdown formatting. Use plain text with emoji where appropriate.''';
  }
}
