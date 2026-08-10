import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
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

  /// True when both exported models have the structure expected by this
  /// runtime. A failed model update must not make the clinical command parser
  /// unusable, so callers should treat this as an enhancement, not a gate.
  bool get hasUsableModels => _intentModel != null && _nerModel != null;

  Future<void> loadModels() async {
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

    // The release manager installs verified artifacts into application storage.
    // There are intentionally no phantom asset paths here: a clean offline
    // launch still has deterministic command parsing rather than a build-time
    // dependency on ignored model files.
    _intentModel = null;
    _nerModel = null;
    _isReady = false;
    debugPrint(
      'No installed statistical NLP model; using clinical command parser.',
    );
  }

  List<String> _tokenizeIntent(String text) {
    text = text.toLowerCase().replaceAll(RegExp(r'[^\w\s]'), ' ');
    final words = text
        .split(RegExp(r'\s+'))
        .where((w) => w.isNotEmpty)
        .toList();

    List<String> tokens = [];
    tokens.addAll(words);
    for (int i = 0; i < words.length - 1; i++) {
      tokens.add('${words[i]} ${words[i + 1]}');
    }
    return tokens;
  }

  Map<String, double> _sgdPredict(
    List<String> tokens,
    Map<String, dynamic> model, {
    bool useTfIdf = true,
  }) {
    final rawVocab = model['vocabulary'];
    final rawIdf = model['idf'];
    final rawCoef = model['coef'];
    final rawIntercept = model['intercept'];
    final rawClasses = model['classes'];
    if (rawVocab is! Map ||
        rawIdf is! List ||
        rawCoef is! List ||
        rawIntercept is! List ||
        rawClasses is! List ||
        rawClasses.isEmpty) {
      throw const FormatException('Invalid exported model format');
    }

    final vocab = rawVocab.map(
      (key, value) => MapEntry(key.toString(), (value as num).toInt()),
    );
    final idf = rawIdf.map((e) => (e as num).toDouble()).toList();
    final coef = rawCoef;
    final intercept = rawIntercept.map((e) => (e as num).toDouble()).toList();
    final classes = rawClasses.map((e) => e.toString()).toList();
    if (coef.length != classes.length || intercept.length != classes.length) {
      throw const FormatException('Model class dimensions do not match');
    }

    Map<int, int> termCounts = {};
    for (var token in tokens) {
      if (vocab.containsKey(token)) {
        final idx = vocab[token]!;
        termCounts[idx] = (termCounts[idx] ?? 0) + 1;
      }
    }

    Map<int, double> vector = {};
    double sumSquares = 0.0;
    for (var entry in termCounts.entries) {
      final tf = entry.value.toDouble();
      final val = useTfIdf ? tf * idf[entry.key] : tf;
      vector[entry.key] = val;
      sumSquares += val * val;
    }

    if (useTfIdf) {
      final norm = sqrt(sumSquares);
      if (norm > 0) {
        for (var key in vector.keys) {
          vector[key] = vector[key]! / norm;
        }
      }
    }

    List<double> scores = List.filled(classes.length, 0.0);
    for (int i = 0; i < classes.length; i++) {
      double score = intercept[i];
      final classCoefs = List<double>.from(
        (coef[i] as List).map((e) => (e as num).toDouble()),
      );
      for (var entry in vector.entries) {
        score += classCoefs[entry.key] * entry.value;
      }
      scores[i] = score;
    }

    int bestIdx = 0;
    double maxScore = scores[0];
    for (int i = 1; i < scores.length; i++) {
      if (scores[i] > maxScore) {
        maxScore = scores[i];
        bestIdx = i;
      }
    }

    // SGDClassifier(loss='log_loss') uses one-vs-rest sigmoid scores for the
    // multiclass model. sklearn normalizes those scores in predict_proba().
    // Returning the normalized value gives the Dart threshold the same meaning
    // as the Python training-time confidence.
    final positiveScores = scores
        .map((score) => 1.0 / (1.0 + exp(-score)))
        .toList();
    final probabilityTotal = positiveScores.fold<double>(
      0.0,
      (sum, score) => sum + score,
    );
    final confidence = probabilityTotal == 0
        ? 0.0
        : positiveScores[bestIdx] / probabilityTotal;
    return {classes[bestIdx]: confidence};
  }

  IntentResult classifyIntent(String text) {
    if (!_isReady || _intentModel == null) {
      return IntentResult('unknown', 0.0);
    }

    try {
      final tokens = _tokenizeIntent(text);
      final result = _sgdPredict(tokens, _intentModel!, useTfIdf: true);

      final intent = result.keys.first;
      final conf = result.values.first;

      if (conf < 0.4) {
        return IntentResult('unknown', conf);
      }
      return IntentResult(intent, conf);
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
      final words = text
          .split(RegExp(r'\s+'))
          .where((w) => w.isNotEmpty)
          .toList();

      String currentEntityType = "O";
      List<String> currentEntityTokens = [];

      for (int i = 0; i < words.length; i++) {
        final word = words[i];
        final wordLower = word.toLowerCase();
        final previousWord = i > 0 ? words[i - 1].toLowerCase() : 'bos';
        final nextWord = i < words.length - 1
            ? words[i + 1].toLowerCase()
            : 'eos';
        final isNumber = RegExp(r'\d').hasMatch(word) ? 't' : 'f';

        final featureTokens = <String>[
          'w:$wordLower',
          'p:$previousWord',
          'n:$nextWord',
          'num:$isNumber',
        ];

        // The NER model's CountVectorizer was trained on the four whitespace
        // separated feature tokens above. Passing one concatenated string here
        // used to create an all-zero vector in Dart, so every word received the
        // same intercept-only prediction.
        final result = _sgdPredict(featureTokens, _nerModel!, useTfIdf: false);
        final tag = result.keys.first;
        final confidence = result.values.first;

        if (tag != 'O' && confidence >= 0.45) {
          // If we were building an entity of a different type, save it
          if (currentEntityType != "O" && currentEntityType != tag) {
            entities.add(
              Entity(currentEntityType, currentEntityTokens.join(' ')),
            );
            currentEntityTokens.clear();
          }
          currentEntityType = tag;
          currentEntityTokens.add(word);
        } else {
          // Finished an entity
          if (currentEntityType != "O") {
            entities.add(
              Entity(currentEntityType, currentEntityTokens.join(' ')),
            );
            currentEntityType = "O";
            currentEntityTokens.clear();
          }
        }
      }

      // Add trailing entity if exists
      if (currentEntityType != "O" && currentEntityTokens.isNotEmpty) {
        entities.add(Entity(currentEntityType, currentEntityTokens.join(' ')));
      }
    } catch (e) {
      debugPrint("Local NER extraction error: $e");
    }

    return entities;
  }
}
