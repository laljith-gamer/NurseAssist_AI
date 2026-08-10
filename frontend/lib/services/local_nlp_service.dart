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
              .toList()
            ..sort(
              (left, right) => right.confidence.compareTo(left.confidence),
            );
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
    final rawCoefficients = model['coef'];
    final rawIntercept = model['intercept'];
    final rawClasses = model['classes'];
    if (rawVocabulary is! Map ||
        rawIdf is! List ||
        rawCoefficients is! List ||
        rawIntercept is! List ||
        rawClasses is! List) {
      throw const FormatException('Observation model structure is invalid');
    }
    final vocabulary = <String, int>{
      for (final entry in rawVocabulary.entries)
        if (entry.value is num)
          entry.key.toString(): (entry.value as num).toInt(),
    };
    final idf = rawIdf.map((value) => (value as num).toDouble()).toList();
    if (rawClasses.length != rawCoefficients.length ||
        rawClasses.length != rawIntercept.length) {
      throw const FormatException('Observation model dimensions do not match');
    }

    final counts = <int, int>{};
    for (final token in tokens) {
      final index = vocabulary[token];
      if (index != null && index >= 0 && index < idf.length) {
        counts[index] = (counts[index] ?? 0) + 1;
      }
    }
    final vector = <int, double>{};
    var squares = 0.0;
    for (final entry in counts.entries) {
      final value = entry.value * idf[entry.key];
      vector[entry.key] = value;
      squares += value * value;
    }
    final norm = sqrt(squares);
    if (norm > 0) {
      for (final index in vector.keys.toList()) {
        vector[index] = vector[index]! / norm;
      }
    }

    final results = <String, double>{};
    for (var classIndex = 0; classIndex < rawClasses.length; classIndex++) {
      final coefficientRow = rawCoefficients[classIndex];
      if (coefficientRow is! List || coefficientRow.length != idf.length) {
        throw const FormatException('Observation coefficients are invalid');
      }
      var score = (rawIntercept[classIndex] as num).toDouble();
      for (final entry in vector.entries) {
        score += (coefficientRow[entry.key] as num).toDouble() * entry.value;
      }
      // Stable sigmoid calculation for the raw SGD log-loss score.
      final probability = score >= 0
          ? 1 / (1 + exp(-score))
          : exp(score) / (1 + exp(score));
      results[rawClasses[classIndex].toString()] = probability;
    }
    return results;
  }

  void _validateModel(Map<String, dynamic> model) {
    if (model['type'] != 'multi_label_sgd_classifier' ||
        model['role'] != 'advisory_clinical_observation_context' ||
        model['vocabulary'] is! Map ||
        model['idf'] is! List ||
        model['coef'] is! List ||
        model['intercept'] is! List ||
        model['classes'] is! List ||
        model['threshold'] is! num) {
      throw const FormatException('Unexpected observation model format');
    }
  }
}
