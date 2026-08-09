import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

class IntentResult {
  final String intent;
  final double confidence;
  IntentResult(this.intent, this.confidence);
}

class Entity {
  final String type;
  final String value;
  Entity(this.type, this.value);
}

class LocalNlpService {
  Map<String, dynamic>? _intentModel;
  Map<String, dynamic>? _nerModel;
  bool _isReady = false;

  bool get isReady => _isReady;

  /// Load models: first try downloaded (updated) models, then fall back to bundled assets.
  Future<void> loadModels() async {
    // 1. Try loading from downloaded models on device storage
    if (!kIsWeb) {
      try {
        final appDir = await getApplicationDocumentsDirectory();
        final modelsDir = Directory('${appDir.path}/local_models/current');

        if (await modelsDir.exists()) {
          final intentFile = File('${modelsDir.path}/intent.json');
          final nerFile = File('${modelsDir.path}/ner.json');

          if (await intentFile.exists() && await nerFile.exists()) {
            _intentModel = jsonDecode(await intentFile.readAsString());
            _nerModel = jsonDecode(await nerFile.readAsString());
            _isReady = true;
            debugPrint("Loaded NLP models from device storage (downloaded).");
            return;
          }
        }
      } catch (e) {
        debugPrint("Could not load downloaded models: $e");
      }
    }

    // 2. Fall back to bundled assets (shipped inside the app)
    try {
      final intentJson = await rootBundle.loadString('assets/models/intent.json');
      final nerJson = await rootBundle.loadString('assets/models/ner.json');
      _intentModel = jsonDecode(intentJson);
      _nerModel = jsonDecode(nerJson);
      _isReady = true;
      debugPrint("Loaded NLP models from bundled assets.");
    } catch (e) {
      debugPrint("Failed to load bundled models: $e");
      _isReady = false;
    }
  }

  List<String> _tokenize(String text) {
    text = text.toLowerCase().replaceAll(RegExp(r'[^\w\s]'), ' ');
    final words = text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();

    // Create n-grams (1 and 2, as configured in the Python model)
    List<String> tokens = [];
    tokens.addAll(words);
    for (int i = 0; i < words.length - 1; i++) {
      tokens.add('${words[i]} ${words[i + 1]}');
    }
    return tokens;
  }

  IntentResult classifyIntent(String text) {
    if (!_isReady || _intentModel == null) {
      return IntentResult('unknown', 0.0);
    }

    try {
      final vocab = Map<String, int>.from(_intentModel!['vocabulary'] as Map);
      final idf = List<double>.from(
          (_intentModel!['idf'] as List).map((e) => (e as num).toDouble()));
      final coef = _intentModel!['coef'] as List;
      final intercept = List<double>.from(
          (_intentModel!['intercept'] as List).map((e) => (e as num).toDouble()));
      final classes = List<String>.from(_intentModel!['classes']);

      final tokens = _tokenize(text);

      // TF calculation
      Map<int, int> termCounts = {};
      for (var token in tokens) {
        if (vocab.containsKey(token)) {
          final idx = vocab[token]!;
          termCounts[idx] = (termCounts[idx] ?? 0) + 1;
        }
      }

      if (termCounts.isEmpty) {
        return IntentResult('unknown', 0.0);
      }

      // TF-IDF vector
      Map<int, double> tfIdfVector = {};
      double sumSquares = 0.0;
      for (var entry in termCounts.entries) {
        final tf = entry.value.toDouble();
        final val = tf * idf[entry.key];
        tfIdfVector[entry.key] = val;
        sumSquares += val * val;
      }

      // L2 Normalization (TfidfVectorizer default)
      final norm = sqrt(sumSquares);
      if (norm > 0) {
        for (var key in tfIdfVector.keys) {
          tfIdfVector[key] = tfIdfVector[key]! / norm;
        }
      }

      // SGD dot product
      List<double> scores = List.filled(classes.length, 0.0);
      for (int i = 0; i < classes.length; i++) {
        double score = intercept[i];
        final classCoefs = List<double>.from(
            (coef[i] as List).map((e) => (e as num).toDouble()));
        for (var entry in tfIdfVector.entries) {
          score += classCoefs[entry.key] * entry.value;
        }
        scores[i] = score;
      }

      // Argmax
      int bestIdx = 0;
      double maxScore = scores[0];
      for (int i = 1; i < scores.length; i++) {
        if (scores[i] > maxScore) {
          maxScore = scores[i];
          bestIdx = i;
        }
      }

      // Convert linear score to pseudo-probability (sigmoid for log_loss)
      double confidence = 1.0 / (1.0 + exp(-maxScore));

      if (confidence < 0.4) {
        return IntentResult('unknown', confidence);
      }

      return IntentResult(classes[bestIdx], confidence);
    } catch (e) {
      debugPrint("Local intent classification error: $e");
      return IntentResult('unknown', 0.0);
    }
  }

  List<Entity> extractEntities(String text) {
    if (!_isReady || _nerModel == null) {
      return [];
    }

    List<Entity> entities = [];
    try {
      final rules = Map<String, String>.from(_nerModel!['rules'] as Map);

      rules.forEach((type, pattern) {
        final regExp = RegExp(pattern);
        final matches = regExp.allMatches(text);
        for (final match in matches) {
          if (match.groupCount >= 1) {
            final value = match.group(1);
            if (value != null) {
              entities.add(Entity(type, value));
            }
          }
        }
      });
    } catch (e) {
      debugPrint("Local NER extraction error: $e");
    }

    return entities;
  }
}
