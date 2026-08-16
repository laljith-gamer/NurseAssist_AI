import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/services/clinical_command_parser.dart';

void main() {
  group('Simulated Gemma 3 1B Output Tests', () {
    test('handles JSON prepended with conversational text', () {
      final rawOutput = '''Here is the JSON you requested:
      ```json
      {"v":1,"action":"record_vitals","reply":"Got it.","vitals":[{"type":"blood_pressure","systolic":120,"diastolic":80}]}
      ```
      Hope this helps!''';
      
      final command = ClinicalCommandParser.fromAiJson(rawOutput);
      expect(command, isNotNull);
      expect(command?.action, ClinicalAction.recordVitals);
      expect(command?.vitals.first.type, 'systolic');
    });

    test('handles unversioned JSON that fails parsing but triggers regex fallback', () {
      final rawOutput = 'I have noted the patient\'s blood pressure is 130/85.';
      
      final command = ClinicalCommandParser.fromAiJson(rawOutput);
      expect(command, isNotNull);
      expect(command?.action, ClinicalAction.recordVitals);
      expect(command?.vitals.first.value, 130); // Sys
    });

    test('treats pure conversational AI output without vitals as a conversation', () {
      final rawOutput = 'The patient seems to be doing well today, no critical issues noted.';
      final command = ClinicalCommandParser.fromAiJson(rawOutput);
      
      expect(command, isNotNull);
      expect(command?.action, ClinicalAction.conversation);
      expect(command?.replyText, rawOutput);
    });
  });
}
