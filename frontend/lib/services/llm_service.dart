import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_gemma/flutter_gemma.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Wraps flutter_gemma for on-device LLM inference.
/// Downloads Gemma 3 270M on first launch, then runs fully offline.
class LlmService extends ChangeNotifier {
  static const String _modelUrl =
      'https://github.com/laljith-gamer/NurseAssist_AI/releases/download/v1.0.0/gemma-4-E2B-it.litertlm';

  static const String _prefKeyModelInstalled = 'llm_model_installed';

  bool _isModelInstalled = false;
  bool _isDownloading = false;
  bool _isReady = false;
  double _downloadProgress = 0.0;
  String _statusMessage = 'Checking...';
  String? _errorMessage;
  InferenceChat? _chat;

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
      final bool hasUpgraded = prefs.getBool('upgraded_litertlm_v5') ?? false;
      
      if (!hasUpgraded) {
         // Wipe all previous models (270M and GPU-only 2GB) since we are upgrading to hybrid 2.5GB Gemma 4
         try {
           await FlutterGemma.uninstallModel('gemma3-270m-it-q8.litertlm');
           await FlutterGemma.uninstallModel('gemma3-270M-it-int4.litertlm');
           await FlutterGemma.uninstallModel('gemma-4-E2B-it-gpu.litertlm');
         } catch(e) {}
         await prefs.setBool('upgraded_litertlm_v5', true);
      }

      _isModelInstalled = await FlutterGemma.isModelInstalled(
        'gemma-4-E2B-it.litertlm',
      );
    } catch (e) {
      // Fall back to shared prefs check
      final prefs = await SharedPreferences.getInstance();
      _isModelInstalled = prefs.getBool(_prefKeyModelInstalled) ?? false;
    }
    notifyListeners();
    return _isModelInstalled;
  }

  /// Download the Gemma 3 270M model from HuggingFace
  Future<bool> downloadModel() async {
    if (_isDownloading) return false;

    _isDownloading = true;
    _downloadProgress = 0.0;
    _statusMessage = 'Preparing download...';
    _errorMessage = null;
    notifyListeners();

    try {
      _statusMessage = 'Downloading AI model (~2.6GB)...';
      notifyListeners();

      await FlutterGemma.installModel(
        modelType: ModelType.gemma4,
        fileType: ModelFileType.litertlm,
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

      final model = await FlutterGemma.getActiveModel(
        preferredBackend:
            preferCpu ? PreferredBackend.cpu : PreferredBackend.gpu,
        maxTokens: 1024,
      );
      
      _chat = await model.createChat(
        temperature: 0.5,
        topK: 20,
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

  /// Generate a response from the LLM using streaming
  Stream<String> generateResponseStream(String prompt) async* {
    if (!_isReady) {
      yield 'AI model not loaded. Please download the model first.';
      return;
    }

    try {
      if (_chat == null) {
        yield 'Chat session not available.';
        return;
      }

      await _chat!.addQueryChunk(Message(text: prompt, isUser: true));
      await for (final token in _chat!.session.getResponseAsync()) {
        yield token;
      }
    } catch (e) {
      debugPrint('LLM generation error: $e');
      yield 'Sorry, I encountered an error generating a response.';
    }
  }

  /// Generate a complete response (non-streaming)
  Future<String> generateResponse(String prompt) async {
    if (!_isReady) {
      return 'AI model not loaded.';
    }

    try {
      if (_chat == null) return 'Chat session not available.';

      await _chat!.addQueryChunk(Message(text: prompt, isUser: true));
      final response = await _chat!.session.getResponse();
      return response.trim();
    } catch (e) {
      debugPrint('LLM generation error: $e');
      return 'Sorry, I encountered an error.';
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
