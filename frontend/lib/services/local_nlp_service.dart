import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

/// A label suggested by the small, real-data nursing observation model.
///
/// It is deliberately advisory only: it is fed to the on-device LLM as a
/// contextual hint and can never create or update a clinical record by itself.
class ClinicalObservation {
  const ClinicalObservation({required this.name, required this.confidence});

  final String name;
  final double confidence;
}

class LocalNlpService {
  Map<String, dynamic>? _observationModel;
  bool _isReady = false;

  bool get isReady => _isReady;
  bool get hasUsableModels => _observationModel != null;

  Future<void> loadModels() async {
    _observationModel = null;
    _isReady = false;
    if (kIsWeb) return;

    try {
      final appDir = await getApplicationDocumentsDirectory();
      final modelFile = File(
        '${appDir.path}/local_models/current/observations.json',
      );
      if (!await modelFile.exists()) {
        debugPrint('No installed nursing-observation model.');
        return;
      }
      final decoded = jsonDecode(await modelFile.readAsString());
      if (decoded is! Map) throw const FormatException('Model root is invalid');
      final model = Map<String, dynamic>.from(decoded);
      _validateModel(model);
      _observationModel = model;
      _isReady = true;
      debugPrint('Loaded verified SYNUR nursing-observation model.');
    } catch (error) {
      _observationModel = null;
      _isReady = false;
      debugPrint('Could not load nursing-observation model: $error');
    }
  }

  /// Returns only high-confidence context labels. The value is not used as an
  /// instruction, an extracted measurement, or an authorization to chart.
  List<ClinicalObservation> predictClinicalObservations(
    String text, {
    int maxResults = 3,
  }) {
    final model = _observationModel;
    if (!_isReady || model == null || text.trim().isEmpty || maxResults < 1) {
      return const [];
    }
    try {
      final threshold = (model['threshold'] as num?)?.toDouble();
      if (threshold == null || threshold <= 0 || threshold >= 1) {
        throw const FormatException('Observation threshold is invalid');
      }
      final scores = _predictScores(_charWbNgrams(text), model);
      final observations =
          scores.entries
              .where((entry) => entry.value >= threshold)
              .map(
                (entry) => ClinicalObservation(
                  name: entry.key,
                  confidence: entry.value,
                ),
              )
              .toList();

      // Clinical Reasoning Rules
      final activeLabels = observations.map((e) => e.name).toSet();
      if (activeLabels.contains('Hypertension') && activeLabels.contains('Tachycardia')) {
        observations.insert(0, const ClinicalObservation(name: 'Hemodynamic Instability', confidence: 1.0));
      }
      if (activeLabels.contains('Hypoxia') && activeLabels.contains('Respiratory Distress')) {
        observations.insert(0, const ClinicalObservation(name: 'Respiratory Compromise', confidence: 1.0));
      }
      if (activeLabels.contains('Severe pain') && activeLabels.contains('Agitated')) {
        observations.insert(0, const ClinicalObservation(name: 'Inadequate Pain Control', confidence: 1.0));
      }

      observations.sort((left, right) => right.confidence.compareTo(left.confidence));
      return observations.take(maxResults).toList(growable: false);
    } catch (error) {
      debugPrint('Nursing observation inference error: $error');
      return const [];
    }
  }

  /// Mirrors the exported scikit-learn ``char_wb`` analyzer. This is model
  /// preprocessing, not a natural-language rule set.
  List<String> _charWbNgrams(String text) {
    final normalized = text
        .toLowerCase()
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    if (normalized.isEmpty) return const [];
    final tokens = <String>[];
    for (final word in normalized.split(' ')) {
      final padded = ' $word ';
      for (var size = 3; size <= 6 && size <= padded.length; size++) {
        for (var index = 0; index <= padded.length - size; index++) {
          tokens.add(padded.substring(index, index + size));
        }
      }
    }
    return tokens;
  }

  Map<String, double> _predictScores(
    List<String> tokens,
    Map<String, dynamic> model,
  ) {
    final rawVocabulary = model['vocabulary'];
    final rawIdf = model['idf'];
    final mlp = model['mlp'];
    final rawClasses = model['classes'];
    
    if (rawVocabulary is! Map ||
        rawIdf is! List ||
        mlp is! Map ||
        rawClasses is! List) {
      throw const FormatException('Observation model structure is invalid');
    }
    
    final inputDim = (mlp['arch']['input_dim'] as num).toInt();

    final vocabulary = <String, int>{
      for (final entry in rawVocabulary.entries)
        if (entry.value is num)
          entry.key.toString(): (entry.value as num).toInt(),
    };
    final idf = rawIdf.map((value) => (value as num).toDouble()).toList();

    // 1. TF-IDF Feature Extraction
    final counts = <int, int>{};
    for (final token in tokens) {
      final index = vocabulary[token];
      if (index != null && index >= 0 && index < idf.length) {
        counts[index] = (counts[index] ?? 0) + 1;
      }
    }
    
    final vector = List<double>.filled(inputDim, 0.0);
    var squares = 0.0;
    for (final entry in counts.entries) {
      if (entry.key < inputDim) {
        final value = entry.value * idf[entry.key];
        vector[entry.key] = value;
        squares += value * value;
      }
    }
    final norm = sqrt(squares);
    if (norm > 0) {
      for (var i = 0; i < vector.length; i++) {
        vector[i] = vector[i] / norm;
      }
    }

    // 2. MLP Forward Pass
    final layer1W = _parseMatrix(mlp['layer1_weight']);
    final layer1B = _parseVector(mlp['layer1_bias']);
    final layer2W = _parseMatrix(mlp['layer2_weight']);
    final layer2B = _parseVector(mlp['layer2_bias']);
    final outW = _parseMatrix(mlp['output_weight']);
    final outB = _parseVector(mlp['output_bias']);

    final h1 = _relu(_dot(layer1W, vector, layer1B));
    final h2 = _relu(_dot(layer2W, h1, layer2B));
    final logits = _dot(outW, h2, outB);

    final results = <String, double>{};
    for (var i = 0; i < rawClasses.length; i++) {
      results[rawClasses[i].toString()] = _sigmoid(logits[i]);
    }
    
    return results;
  }

  List<List<double>> _parseMatrix(dynamic raw) {
    if (raw is! List) throw const FormatException('Invalid matrix');
    return raw.map((row) {
      if (row is! List) throw const FormatException('Invalid matrix row');
      return row.map((v) => (v as num).toDouble()).toList();
    }).toList();
  }

  List<double> _parseVector(dynamic raw) {
    if (raw is! List) throw const FormatException('Invalid vector');
    return raw.map((v) => (v as num).toDouble()).toList();
  }

  List<double> _dot(List<List<double>> matrix, List<double> vector, List<double> bias) {
    final result = List<double>.filled(matrix.length, 0.0);
    for (var i = 0; i < matrix.length; i++) {
      var sum = bias[i];
      final row = matrix[i];
      for (var j = 0; j < vector.length; j++) {
        sum += row[j] * vector[j];
      }
      result[i] = sum;
    }
    return result;
  }

  List<double> _relu(List<double> x) {
    for (var i = 0; i < x.length; i++) {
      if (x[i] < 0) x[i] = 0;
    }
    return x;
  }
  
  double _sigmoid(double score) {
    if (score >= 0) {
      return 1 / (1 + exp(-score));
    } else {
      final expScore = exp(score);
      return expScore / (1 + expScore);
    }
  }

  void _validateModel(Map<String, dynamic> model) {
    if (model['type'] != 'compact_clinical_mlp' ||
        model['role'] != 'advisory_clinical_observation_context' ||
        model['vocabulary'] is! Map ||
        model['idf'] is! List ||
        model['mlp'] is! Map ||
        model['classes'] is! List ||
        model['threshold'] is! num) {
      throw const FormatException('Unexpected observation model format');
    }
  }
}
