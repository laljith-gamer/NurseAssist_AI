import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/services/model_manager.dart';

void main() {
  group('ModelManager._validateExportedModel', () {
    late Directory tempDir;
    late File testFile;

    setUp(() async {
      tempDir = await Directory.systemTemp.createTemp('model_manager_test');
      testFile = File('${tempDir.path}/test_model.json');
    });

    tearDown(() async {
      if (await tempDir.exists()) {
        await tempDir.delete(recursive: true);
      }
    });

    Future<void> runValidation(Map<String, dynamic> payload) async {
      await testFile.writeAsString(jsonEncode(payload));
      await ModelManager.validateExportedModelForTest(testFile);
    }

    test('accepts valid compact_clinical_mlp payload', () async {
      final validPayload = {
        "type": "compact_clinical_mlp",
        "format_version": 2,
        "role": "advisory_clinical_observation_context",
        "vocabulary": {"test": 0, "ngram": 1},
        "idf": [1.5, 2.0],
        "classes": ["LabelA", "LabelB"],
        "threshold": 0.5,
        "mlp": {
          "arch": {"input_dim": 2, "output_dim": 2},
          "layer1_weight": [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
          "layer1_bias": [0.1, 0.2, 0.3],
          "layer2_weight": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
          "layer2_bias": [0.1, 0.2],
          "output_weight": [[0.1, 0.2], [0.3, 0.4]],
          "output_bias": [0.1, 0.2]
        }
      };

      await expectLater(
        runValidation(validPayload),
        completes,
      );
    });

    test('rejects old multi_label_sgd_classifier payload', () async {
      final oldPayload = {
        "type": "multi_label_sgd_classifier",
        "role": "advisory_clinical_observation_context",
        "vocabulary": {"test": 0},
        "idf": [1.0],
        "coef": [[0.5]],
        "intercept": [0.1],
        "classes": ["LabelA"],
        "threshold": 0.5
      };

      await expectLater(
        runValidation(oldPayload),
        throwsA(isA<FormatException>()),
      );
    });

    test('rejects payloads missing required fields', () async {
      final basePayload = {
        "type": "compact_clinical_mlp",
        "format_version": 2,
        "role": "advisory_clinical_observation_context",
        "vocabulary": {"test": 0},
        "idf": [1.0],
        "classes": ["LabelA"],
        "threshold": 0.5,
        "mlp": {
          "arch": {"input_dim": 1, "output_dim": 1},
          "layer1_weight": [[0.1]],
          "layer1_bias": [0.1],
          "layer2_weight": [[0.1]],
          "layer2_bias": [0.1],
          "output_weight": [[0.1]],
          "output_bias": [0.1]
        }
      };

      final requiredKeys = ['type', 'role', 'vocabulary', 'idf', 'classes', 'threshold', 'mlp'];
      for (final key in requiredKeys) {
        final badPayload = Map<String, dynamic>.from(basePayload)..remove(key);
        await expectLater(
          runValidation(badPayload),
          throwsA(isA<FormatException>()),
          reason: 'Missing $key should fail',
        );
      }
    });
  });
}
