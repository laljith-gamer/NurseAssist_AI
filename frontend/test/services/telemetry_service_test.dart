import 'package:flutter_test/flutter_test.dart';
import 'package:frontend/services/telemetry_service.dart';

void main() {
  group('TranscriptRedactor', () {
    test('Redacts room numbers', () {
      expect(TranscriptRedactor.redact('Patient is in room 123.'),
          'Patient is in [ROOM].');
      expect(TranscriptRedactor.redact('Check Room 42 for updates.'),
          'Check [ROOM] for updates.');
      expect(TranscriptRedactor.redact('Patient in ROOM12 matched by regex strictly.'),
          'Patient in [ROOM] matched by regex strictly.');
    });

    test('Redacts MRN patterns', () {
      expect(TranscriptRedactor.redact('The MRN is 1234567.'),
          'The MRN is [MRN].');
      expect(TranscriptRedactor.redact('ID: 987654.'),
          'ID: [MRN].');
      expect(TranscriptRedactor.redact('Call at 12345 (too short).'),
          'Call at 12345 (too short).');
    });

    test('Redacts name prefixes', () {
      expect(TranscriptRedactor.redact('Mr. Smith is resting.'),
          '[NAME] is resting.');
      expect(TranscriptRedactor.redact('Dr. John Doe examined the patient.'),
          '[NAME] examined the patient.');
      expect(TranscriptRedactor.redact('Pt. Mary reported pain.'),
          '[NAME] reported pain.');
      expect(TranscriptRedactor.redact('Patient: Alice Smith feels better.'),
          '[NAME] feels better.');
    });

    test('Redacts exact patient name if provided', () {
      expect(
        TranscriptRedactor.redact('Jane Doe is walking. Call Jane.', patientName: 'Jane Doe'),
        '[NAME] [NAME] is walking. Call [NAME].',
      );
      expect(
        TranscriptRedactor.redact('Johnathan reported nausea.', patientName: 'Johnathan'),
        '[NAME] reported nausea.',
      );
    });

    test('Handles combination of PII', () {
      final input = 'Mr. Smith in room 405 has MRN 88997766. Dr. Jones says hi.';
      final expected = '[NAME] in [ROOM] has MRN [MRN]. [NAME] says hi.';
      expect(TranscriptRedactor.redact(input), expected);
    });
  });
}
