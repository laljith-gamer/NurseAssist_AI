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

  List<String> _tokenizeIntent(String text) {
    text = text.toLowerCase().replaceAll(RegExp(r'[^\w\s]'), ' ');
    final words = text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();

    List<String> tokens = [];
    tokens.addAll(words);
    for (int i = 0; i < words.length - 1; i++) {
      tokens.add('${words[i]} ${words[i + 1]}');
    }
    return tokens;
  }

  Map<String, double> _sgdPredict(List<String> tokens, Map<String, dynamic> model, {bool useTfIdf = true}) {
    final vocab = Map<String, int>.from(model['vocabulary'] as Map);
    final idf = List<double>.from((model['idf'] as List).map((e) => (e as num).toDouble()));
    final coef = model['coef'] as List;
    final intercept = List<double>.from((model['intercept'] as List).map((e) => (e as num).toDouble()));
    final classes = List<String>.from(model['classes']);

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
      final classCoefs = List<double>.from((coef[i] as List).map((e) => (e as num).toDouble()));
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

    double confidence = 1.0 / (1.0 + exp(-maxScore));
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
      final words = text.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).toList();
      
      String currentEntityType = "O";
      List<String> currentEntityTokens = [];
      
      for (int i = 0; i < words.length; i++) {
        final w = words[i];
        final w_lower = w.toLowerCase();
        final prev_w = i > 0 ? words[i-1].toLowerCase() : 'BOS';
        final next_w = i < words.length - 1 ? words[i+1].toLowerCase() : 'EOS';
        final is_num = RegExp(r'\d').hasMatch(w) ? 'T' : 'F';
        
        final featureStr = "W:$w_lower P:$prev_w N:$next_w NUM:$is_num";
        
        // Predict tag for this token using CountVectorizer model (no IDF normalization)
        final result = _sgdPredict([featureStr], _nerModel!, useTfIdf: false);
        final tag = result.keys.first;
        
        if (tag != "O") {
          // If we were building an entity of a different type, save it
          if (currentEntityType != "O" && currentEntityType != tag) {
             entities.add(Entity(currentEntityType, currentEntityTokens.join(' ')));
             currentEntityTokens.clear();
          }
          currentEntityType = tag;
          currentEntityTokens.add(w);
        } else {
          // Finished an entity
          if (currentEntityType != "O") {
             entities.add(Entity(currentEntityType, currentEntityTokens.join(' ')));
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
