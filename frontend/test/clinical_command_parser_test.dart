import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/services/clinical_command_parser.dart';

void main() {
  group('ClinicalCommandParser', () {
    test('records a complete set of common vital signs', () {
      final command = ClinicalCommandParser.parse(
        'Record BP 120/80, HR 78, Temp 98.6 F, SpO2 96%, RR 18',
      );

      expect(command.action, ClinicalAction.recordVitals);
      expect(
        command.vitals.map((vital) => vital.type),
        containsAll(<String>[
          'systolic',
          'diastolic',
          'heart_rate',
          'temperature',
          'spo2',
          'respiratory_rate',
        ]),
      );
      expect(
        command.vitals.firstWhere((vital) => vital.type == 'temperature').value,
        closeTo(37, 0.1),
      );
    });

    test('does not turn a question into a vital entry', () {
      final command = ClinicalCommandParser.parse('What was the BP 120/80?');

      expect(command.action, ClinicalAction.queryVitals);
      expect(command.vitals, isEmpty);
    });

    test('parses medication, dose, route, and status', () {
      final command = ClinicalCommandParser.parse(
        'Administered Zofran 4 mg PO',
      );

      expect(command.action, ClinicalAction.recordMedication);
      expect(command.medication?.name, 'Zofran');
      expect(command.medication?.dose, '4 mg');
      expect(command.medication?.route, 'PO');
      expect(command.medication?.status, 'administered');
    });

    test('handles dose-first medication wording', () {
      final command = ClinicalCommandParser.parse('Gave 4 mg Zofran IV');

      expect(command.action, ClinicalAction.recordMedication);
      expect(command.medication?.name, 'Zofran');
      expect(command.medication?.dose, '4 mg');
      expect(command.medication?.route, 'IV');
    });

    test('routes medication questions to the local history', () {
      final command = ClinicalCommandParser.parse('What meds are due?');

      expect(command.action, ClinicalAction.queryMedications);
    });

    test('routes questions about change to trends', () {
      final command = ClinicalCommandParser.parse('Has the BP changed?');

      expect(command.action, ClinicalAction.queryTrends);
    });
  });
}
