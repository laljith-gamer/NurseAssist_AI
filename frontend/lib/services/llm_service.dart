import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_gemma/flutter_gemma.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

import 'clinical_command_parser.dart';
import 'local_nlp_service.dart';

/// Wraps flutter_gemma for on-device LLM inference.
/// Downloads the Gemma 3 1B IT model from GitHub Releases on first launch.
class LlmService extends ChangeNotifier {
  static const String _modelFileName = 'gemma3-1b-it-int4.task';
  static const String _modelId = 'gemma3-1b-it-int4';
  static const String _modelUrl = 'https://ghproxy.net/https://github.com/laljith-gamer/NurseAssist_AI/releases/download/model-v1.0.0/gemma3-1b-it-int4.task';

  bool _isInitializing = false;
  bool _isReady = false;
  String _statusMessage = 'Initializing...';
  String? _errorMessage;
  InferenceModel? _model;
  InferenceChat? _chat;
  bool _isGenerating = false;
  Future<void>? _initializationFuture;

  bool get isInitializing => _isInitializing;
  bool get isReady => _isReady;
  String get statusMessage => _statusMessage;
  String? get errorMessage => _errorMessage;

  /// Ensure the model file is installed, downloading it if necessary.
  Future<void> _ensureModelInstalled() async {
    if (kIsWeb) return;

    _statusMessage = 'Preparing AI model download...';
    notifyListeners();

    try {
      final docDir = await getApplicationDocumentsDirectory();
      final finalFile = File('${docDir.path}/$_modelFileName');

      if (await finalFile.exists()) {
        _statusMessage = 'Validating AI model file...';
        notifyListeners();
        
        final fileSize = await finalFile.length();
        final sizeMb = (fileSize / (1024 * 1024)).toStringAsFixed(1);
        
        if (fileSize < 500 * 1024 * 1024) {
          debugPrint('Corrupted LLM file detected (size: $fileSize). Deleting...');
          _statusMessage = 'Corrupted file detected ($sizeMb MB). Deleting...';
          notifyListeners();
          await Future.delayed(const Duration(seconds: 2)); // Give user time to read
          await finalFile.delete();
        } else {
          debugPrint('Model file already exists on disk. Re-registering...');
          _statusMessage = 'Model valid ($sizeMb MB). Linking AI...';
          notifyListeners();
          
          await FlutterGemma.installModel(
            modelType: ModelType.gemmaIt,
            fileType: ModelFileType.task,
          ).fromFile(finalFile.path).install();
          return;
        }
      }

      // Manual retry logic bypassing iOS background task (flutter_downloader) which fails on proxies
      int retries = 3;
      bool downloaded = false;
      while (retries > 0 && !downloaded) {
        try {
          final request = http.Request('GET', Uri.parse(_modelUrl));
          final response = await http.Client().send(request);
          if (response.statusCode >= 200 && response.statusCode < 300) {
            final contentLength = response.contentLength ?? 1;
            int bytesReceived = 0;
            final sink = finalFile.openWrite();
            await response.stream.map((chunk) {
              bytesReceived += chunk.length;
              final progress = ((bytesReceived / contentLength) * 100).toInt();
              _statusMessage = 'Downloading AI model... $progress%';
              notifyListeners();
              return chunk;
            }).pipe(sink);
            await sink.close();
            downloaded = true;
          } else {
            throw Exception('HTTP ${response.statusCode}');
          }
        } catch (e) {
          retries--;
          debugPrint('Manual download attempt failed: $e, retries left: $retries');
          if (retries == 0) rethrow;
          _statusMessage = 'Network error, retrying... ($retries left)';
          notifyListeners();
          await Future.delayed(const Duration(seconds: 3));
        }
      }

      _statusMessage = 'Installing model locally...';
      notifyListeners();

      // fromFile does NOT copy the file, it permanently links to the external file.
      // So we must pass the finalFile path and must NEVER delete it.
      await FlutterGemma.installModel(
        modelType: ModelType.gemmaIt,
        fileType: ModelFileType.task,
      ).fromFile(finalFile.path).install();

      _statusMessage = 'Model downloaded successfully. Verifying...';
      notifyListeners();
    } catch (e, stack) {
      debugPrint('Failed to download model from network: $e\n$stack');
      _errorMessage = 'Model download failed (Proxy/Network): $e';
      notifyListeners();
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
      // CPU gives a reliable on-device initialization path on Android and avoids Metal/OpenCL GPU crashes
      // We also use it on iOS now because the GPU backend duplicates the 550MB model in RAM (Metal buffers),
      // instantly causing a 1.4GB Jetsam OOM kill on free Apple Developer profiles. CPU avoids this entirely.
      final preferCpu = true;

      try {
        // Attempt to load the active model first. This bypasses the buggy isModelInstalled check
        // and avoids calling installModel() repeatedly, which causes a silent native crash on iOS.
        _model = await FlutterGemma.getActiveModel(
          preferredBackend: preferCpu ? PreferredBackend.cpu : PreferredBackend.gpu,
          maxTokens: 1024,
        );
      } catch (e) {
        // Not active yet. Let's ensure it's installed and try again.
        await _ensureModelInstalled();
        _model = await FlutterGemma.getActiveModel(
          preferredBackend: preferCpu ? PreferredBackend.cpu : PreferredBackend.gpu,
          maxTokens: 1024,
        );
      }

      _chat = await _model!.createChat(
        // Relaxed settings allow natural personality while keeping
        // clinical output reliable.
        temperature: 0.2,
        topK: 40,
        topP: 0.8,
        tokenBuffer: 512,
      );

      _isReady = true;
      _statusMessage = 'AI Ready';
      debugPrint('LLM engine initialized successfully (Gemma 3 1B IT).');
    } catch (e, stack) {
      debugPrint('LLM engine init error: $e\n$stack');
      _errorMessage = 'Engine init failed: ${e.toString()}';
      _isReady = false;
      _statusMessage = 'AI engine could not start';
      
      // If initialization fails, the model file might be corrupt or an HTML redirect page.
      // Uninstall it so the next attempt will re-download a fresh copy.
      try {
        debugPrint('Uninstalling potentially corrupt model $_modelId...');
        await FlutterGemma.uninstallModel(_modelId);
      } catch (uninstallError) {
        debugPrint('Failed to uninstall corrupt model: $uninstallError');
      }
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

  /// Interprets free-form nursing language into a structured JSON command.
  /// The JSON always includes a `reply` field — the model's natural-language
  /// response shown to the nurse. Clinical writes also include structured data
  /// for validation. This is a SINGLE inference call.
  Future<ClinicalCommand?> interpretClinicalCommand(
    String message, {
    List<ClinicalObservation> observationHints = const [],
    String patientMemory = '',
  }) async {
    // If the engine is still initializing, wait for it to finish so the prompt
    // isn't dropped and sent to the offline fallback immediately.
    if (_isInitializing && _initializationFuture != null) {
      await _initializationFuture;
    }

    if (!_isReady || _chat == null) return null;

    // Wait if the engine is currently generating, so we NEVER drop a prompt
    // and always pass it to the AI.
    while (_isGenerating) {
      await Future.delayed(const Duration(milliseconds: 100));
    }

    _isGenerating = true;
    try {
      await _prepareSingleTurn();
      final now = DateTime.now().toIso8601String();
      final hints = observationHints.isEmpty
          ? 'none'
          : observationHints.map((hint) => hint.name).join(', ');
      final schema =
          '''You are NurseAssist AI, a helpful on-device nursing assistant.
CRITICAL: Respond ONLY with a valid JSON object. Do not add conversational text outside the JSON.
Your JSON must contain "action", "reply", and relevant data arrays.

Actions: "record_vitals", "record_medication", "record_note", "conversation"

Example 1:
User: "BP 140/90 and HR 85"
{"action":"record_vitals","reply":"I have recorded a BP of 140/90 and heart rate of 85.","vitals":[{"type":"blood_pressure","systolic":140,"diastolic":90},{"type":"heart_rate","value":85,"unit":"bpm"}]}

Example 2:
User: "Patient complains of severe headache since 7pm"
{"action":"record_note","reply":"I've noted the severe headache.","note":"Patient complains of severe headache since 7pm.","category":"nursing_observation"}

Example 3:
User: "Hi, how are you?"
{"action":"conversation","reply":"Hello! I'm here to help you chart today."}''';

      final fullPrompt =
          '$schema\n\nPatient context (do not repeat as new facts):\n$patientMemory\nObservation hints: $hints\n\nPlease process this nursing input:\n"$message"';
      String currentPrompt = fullPrompt;
      int maxRetries = 3;
      String lastRawText = '';
      
      for (int attempt = 0; attempt < maxRetries; attempt++) {
        // Clear history to avoid unbounded session growth and ensure fresh context per command
        await _chat!.clearHistory();
        await _chat!.addQueryChunk(Message(text: currentPrompt, isUser: true));
        
        final response = await _chat!.generateChatResponse();
        final rawText = response is TextResponse ? response.token : response.toString();
        lastRawText = rawText;
        
        final parsedCommand = ClinicalCommandParser.fromAiJson(_sanitizeResponse(rawText));
        if (parsedCommand != null) {
          return parsedCommand;
        }
        
        // If we failed to parse valid JSON, try again with a stronger warning
        debugPrint('LLM retry attempt ${attempt + 1}: Failed to parse valid JSON. Retrying...');
        currentPrompt = '$fullPrompt\n\nCRITICAL ERROR: Your previous response was not a valid JSON object. You MUST reply ONLY with a valid JSON object matching the schema. Do not include any other text.';
      }
      
      return ClinicalCommand(
        action: ClinicalAction.conversation,
        replyText: '[DEVELOPER AI RAW LOG - JSON FAILED]:\n$lastRawText',
      );
    } catch (error, stackTrace) {
      debugPrint('AI clinical interpretation error: $error\nStackTrace: $stackTrace');
      return ClinicalCommand(
        action: ClinicalAction.conversation,
        replyText: '[DEVELOPER AI RAW LOG - EXCEPTION]:\n$error',
      );
    } finally {
      _isGenerating = false;
    }
  }
}
