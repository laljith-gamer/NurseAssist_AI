import 'dart:convert';

// Validates structured clinical actions before they can change patient data.
// Natural-language interpretation is performed by the on-device LLM first;
// the pattern parser below is retained only as an offline fallback.

enum ClinicalAction {
  recordVitals,
  queryVitals,
  queryTrends,
  recordMedication,
  recordNote,
  queryMedications,
  summarize,
  greeting,
  help,
  cancel,
  unknown,
}

class ParsedVital {
  const ParsedVital({
    required this.type,
    required this.value,
    required this.unit,
  });

  final String type;
  final double value;
  final String unit;

  String get label => switch (type) {
    'systolic' => 'Systolic BP',
    'diastolic' => 'Diastolic BP',
    'heart_rate' => 'Heart rate',
    'temperature' => 'Temperature',
    'spo2' => 'SpO₂',
    'respiratory_rate' => 'Respiratory rate',
    'weight' => 'Weight',
    _ => type,
  };

  String get displayValue {
    final number = value == value.roundToDouble()
        ? value.toStringAsFixed(0)
        : value.toStringAsFixed(1);
    return '$number $unit';
  }
}

class ParsedMedication {
  const ParsedMedication({
    required this.name,
    required this.status,
    this.dose,
    this.route,
  });

  final String name;
  final String status;
  final String? dose;
  final String? route;
}

class ClinicalCommand {
  const ClinicalCommand({
    required this.action,
    this.vitals = const [],
    this.medication,
    this.noteCategory,
  });

  final ClinicalAction action;
  final List<ParsedVital> vitals;
  final ParsedMedication? medication;
  final String? noteCategory;
}

class ClinicalCommandParser {
  /// Converts the LLM's strict JSON response into a safe local command.
  /// Invalid, incomplete, or unsupported output returns null. The result is
  /// later presented to the nurse for explicit confirmation before any write.
  static ClinicalCommand? fromAiJson(String raw) {
    Map<String, dynamic>? data;
    final trimmed = raw.trim();
    for (final candidate in [
      trimmed,
      if (trimmed.contains('{') && trimmed.contains('}'))
        trimmed.substring(trimmed.indexOf('{'), trimmed.lastIndexOf('}') + 1),
    ]) {
      try {
        final decoded = jsonDecode(candidate);
        if (decoded is Map) {
          data = Map<String, dynamic>.from(decoded);
          break;
        }
      } catch (_) {
        // Try the next JSON envelope.
      }
    }
    if (data == null || data['v'] != 1) return null;

    switch (data['action']?.toString()) {
      case 'record_vitals':
        final rawVitals = data['vitals'];
        if (rawVitals is! List) return null;
        final vitals = <ParsedVital>[];
        for (final item in rawVitals) {
          if (item is! Map) return null;
          final vital = Map<String, dynamic>.from(item);
          final type = vital['type']?.toString();
          if (type == 'blood_pressure') {
            _addIfInRange(
              vitals,
              'systolic',
              _number(vital['systolic']),
              'mmHg',
              40,
              260,
            );
            _addIfInRange(
              vitals,
              'diastolic',
              _number(vital['diastolic']),
              'mmHg',
              20,
              180,
            );
          } else if (type == 'heart_rate') {
            _addIfInRange(
              vitals,
              'heart_rate',
              _number(vital['value']),
              'bpm',
              20,
              260,
            );
          } else if (type == 'temperature') {
            _addIfInRange(
              vitals,
              'temperature',
              _number(vital['value']),
              '°C',
              25,
              45,
            );
          } else if (type == 'spo2') {
            _addIfInRange(
              vitals,
              'spo2',
              _number(vital['value']),
              '%',
              40,
              100,
            );
          } else if (type == 'respiratory_rate') {
            _addIfInRange(
              vitals,
              'respiratory_rate',
              _number(vital['value']),
              '/min',
              4,
              80,
            );
          } else if (type == 'weight') {
            _addIfInRange(
              vitals,
              'weight',
              _number(vital['value']),
              'kg',
              2,
              500,
            );
          } else {
            return null;
          }
        }
        return vitals.isEmpty
            ? null
            : ClinicalCommand(
                action: ClinicalAction.recordVitals,
                vitals: vitals,
              );
      case 'record_medication':
        final rawMedication = data['medication'];
        if (rawMedication is! Map) return null;
        final medication = Map<String, dynamic>.from(rawMedication);
        final name = medication['name']?.toString().trim() ?? '';
        if (name.isEmpty) return null;
        const statuses = {'administered', 'held', 'started', 'discontinued'};
        final status = medication['status']?.toString();
        if (!statuses.contains(status)) return null;
        return ClinicalCommand(
          action: ClinicalAction.recordMedication,
          medication: ParsedMedication(
            name: name,
            dose: medication['dose']?.toString(),
            route: medication['route']?.toString(),
            status: status!,
          ),
        );
      case 'record_note':
        return const ClinicalCommand(
          action: ClinicalAction.recordNote,
          noteCategory: 'nursing_observation',
        );
      case 'query_vitals':
        return const ClinicalCommand(action: ClinicalAction.queryVitals);
      case 'query_trends':
        return const ClinicalCommand(action: ClinicalAction.queryTrends);
      case 'query_medications':
        return const ClinicalCommand(action: ClinicalAction.queryMedications);
      case 'summarize':
        return const ClinicalCommand(action: ClinicalAction.summarize);
      case 'greeting':
        return const ClinicalCommand(action: ClinicalAction.greeting);
      case 'help':
        return const ClinicalCommand(action: ClinicalAction.help);
      case 'cancel':
        return const ClinicalCommand(action: ClinicalAction.cancel);
      default:
        return null;
    }
  }

  static double? _number(dynamic value) => value is num
      ? value.toDouble()
      : double.tryParse(value?.toString() ?? '');

  static final RegExp _bpPattern = RegExp(
    r'\b(?:bp|blood\s+pressure)\s*(?:is|of|as|at|:|=)?\s*(\d{2,3})\s*(?:/|over)\s*(\d{2,3})\b',
    caseSensitive: false,
  );
  static final RegExp _heartRatePattern = RegExp(
    r'\b(?:heart\s*rate|hr|pulse)\s*(?:is|of|:|=)?\s*(\d{2,3})\s*(?:bpm)?\b',
    caseSensitive: false,
  );
  static final RegExp _temperaturePattern = RegExp(
    r'\b(?:temperature|temp)\s*(?:is|of|:|=)?\s*(\d{2,3}(?:\.\d+)?)\s*(?:°?\s*([cf]))?\b',
    caseSensitive: false,
  );
  static final RegExp _spo2Pattern = RegExp(
    r'\b(?:spo2|o2\s*(?:sat(?:uration)?s?)?|oxygen\s+sat(?:uration)?)\s*(?:is|of|:|=)?\s*(\d{2,3})\s*%?\b',
    caseSensitive: false,
  );
  static final RegExp _respiratoryRatePattern = RegExp(
    r'\b(?:respiratory\s*rate|resp\s*rate|rr)\s*(?:is|of|:|=)?\s*(\d{1,2})\s*(?:/min|bpm)?\b',
    caseSensitive: false,
  );
  static final RegExp _weightPattern = RegExp(
    r'\b(?:weight|wt)\s*(?:is|of|:|=)?\s*(\d{2,3}(?:\.\d+)?)\s*(kg|kgs|lb|lbs|pounds?)\b',
    caseSensitive: false,
  );
  static final RegExp _bareBpPattern = RegExp(r'\b(\d{2,3})\s*/\s*(\d{2,3})\b');
  static final RegExp _dosePattern = RegExp(
    r'\b\d+(?:\.\d+)?\s*(?:mg|mcg|μg|g|units?|iu|ml|mL|tablets?|tabs?|puffs?)\b',
    caseSensitive: false,
  );
  static final RegExp _routePattern = RegExp(
    r'\b(?:po|oral|iv|im|sc|sq|subcut(?:aneous)?|topical|pr|sl|inhaled|neb(?:ulized)?)\b',
    caseSensitive: false,
  );
  static final RegExp _medicationActionPattern = RegExp(
    r'\b(gave|given|administer(?:ed)?|hold|held|withheld|start(?:ed)?|stop(?:ped)?|discontinue(?:d)?|dc)\b',
    caseSensitive: false,
  );

  /// Parse only commands that can be safely represented in local records.
  /// The caller may use its ML intent as a fallback for conversational input.
  static ClinicalCommand parse(String text, {String? fallbackIntent}) {
    final normalized = text.trim().toLowerCase();
    if (normalized.isEmpty) {
      return const ClinicalCommand(action: ClinicalAction.unknown);
    }

    final hasQuestionLanguage = RegExp(
      r'\b(?:what|show|list|latest|last|recent|when|which|are|is|how)\b|\?',
    ).hasMatch(normalized);
    final startsAsQuestion = RegExp(
      r'^(?:what|when|which|how|show|list|was|were|has|have|did|is|are)\b',
    ).hasMatch(normalized);
    final asksForTrend = RegExp(
      r'\b(?:trend|trending|change|changed|compare|yesterday|history)\b',
    ).hasMatch(normalized);
    final mentionsMedication = RegExp(
      r'\b(?:meds?|medication|drug|dose|due)\b',
    ).hasMatch(normalized);
    final mentionsVitals = RegExp(
      r'\b(?:vitals?|bp|blood\s+pressure|heart\s*rate|\bhr\b|pulse|temp(?:erature)?|spo2|o2\s*sat|oxygen|resp(?:iratory)?\s*rate|\brr\b|weight)\b',
    ).hasMatch(normalized);

    final medication = _parseMedication(text);
    final vitals = _parseVitals(text);

    if (asksForTrend) {
      return const ClinicalCommand(action: ClinicalAction.queryTrends);
    }
    // Questions must be evaluated before recording: "What is the last BP?"
    // contains a vital cue but must not create a record.
    if (startsAsQuestion ||
        (hasQuestionLanguage && !_hasRecordLanguage(text))) {
      if (mentionsMedication) {
        return const ClinicalCommand(action: ClinicalAction.queryMedications);
      }
      if (mentionsVitals) {
        return const ClinicalCommand(action: ClinicalAction.queryVitals);
      }
    }
    if (hasQuestionLanguage && mentionsMedication && medication == null) {
      return const ClinicalCommand(action: ClinicalAction.queryMedications);
    }
    if (hasQuestionLanguage && mentionsVitals && vitals.isEmpty) {
      return const ClinicalCommand(action: ClinicalAction.queryVitals);
    }
    if (medication != null) {
      return ClinicalCommand(
        action: ClinicalAction.recordMedication,
        medication: medication,
      );
    }
    if (vitals.isNotEmpty) {
      return ClinicalCommand(
        action: ClinicalAction.recordVitals,
        vitals: vitals,
      );
    }

    if (RegExp(
      r'\b(?:summari[sz]e|summary|handoff|overview|snapshot)\b',
    ).hasMatch(normalized)) {
      return const ClinicalCommand(action: ClinicalAction.summarize);
    }
    if (RegExp(
      r'\b(?:help|commands?|what can you do)\b',
    ).hasMatch(normalized)) {
      return const ClinicalCommand(action: ClinicalAction.help);
    }
    if (RegExp(
      r'\b(?:cancel|abort|never\s*mind|stop|undo)\b',
    ).hasMatch(normalized)) {
      return const ClinicalCommand(action: ClinicalAction.cancel);
    }
    if (RegExp(
      r'^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|greetings)\b',
    ).hasMatch(normalized)) {
      return const ClinicalCommand(action: ClinicalAction.greeting);
    }

    return switch (fallbackIntent) {
      'query_vitals' => const ClinicalCommand(
        action: ClinicalAction.queryVitals,
      ),
      'query_trends' => const ClinicalCommand(
        action: ClinicalAction.queryTrends,
      ),
      'query_medications' => const ClinicalCommand(
        action: ClinicalAction.queryMedications,
      ),
      'summarize' => const ClinicalCommand(action: ClinicalAction.summarize),
      'greeting' => const ClinicalCommand(action: ClinicalAction.greeting),
      'command_help' => const ClinicalCommand(action: ClinicalAction.help),
      'command_cancel' => const ClinicalCommand(action: ClinicalAction.cancel),
      _ => const ClinicalCommand(action: ClinicalAction.unknown),
    };
  }

  static List<ParsedVital> _parseVitals(String text) {
    final vitals = <ParsedVital>[];
    final bp =
        _bpPattern.firstMatch(text) ??
        (_hasRecordLanguage(text) ? _bareBpPattern.firstMatch(text) : null);
    if (bp != null) {
      _addIfInRange(
        vitals,
        'systolic',
        double.tryParse(bp.group(1)!),
        'mmHg',
        40,
        260,
      );
      _addIfInRange(
        vitals,
        'diastolic',
        double.tryParse(bp.group(2)!),
        'mmHg',
        20,
        180,
      );
    }

    final heartRate = _heartRatePattern.firstMatch(text);
    if (heartRate != null) {
      _addIfInRange(
        vitals,
        'heart_rate',
        double.tryParse(heartRate.group(1)!),
        'bpm',
        20,
        260,
      );
    }

    final temperature = _temperaturePattern.firstMatch(text);
    if (temperature != null) {
      var value = double.tryParse(temperature.group(1)!);
      final unit = temperature.group(2)?.toLowerCase();
      if (value != null && unit == 'f') value = (value - 32) * 5 / 9;
      _addIfInRange(vitals, 'temperature', value, '°C', 25, 45);
    }

    final spo2 = _spo2Pattern.firstMatch(text);
    if (spo2 != null) {
      _addIfInRange(
        vitals,
        'spo2',
        double.tryParse(spo2.group(1)!),
        '%',
        40,
        100,
      );
    }

    final respiratoryRate = _respiratoryRatePattern.firstMatch(text);
    if (respiratoryRate != null) {
      _addIfInRange(
        vitals,
        'respiratory_rate',
        double.tryParse(respiratoryRate.group(1)!),
        '/min',
        4,
        80,
      );
    }

    final weight = _weightPattern.firstMatch(text);
    if (weight != null) {
      var value = double.tryParse(weight.group(1)!);
      final unit = weight.group(2)!.toLowerCase();
      if (value != null && unit.startsWith('lb')) value *= 0.45359237;
      _addIfInRange(vitals, 'weight', value, 'kg', 2, 500);
    }
    return vitals;
  }

  static void _addIfInRange(
    List<ParsedVital> vitals,
    String type,
    double? value,
    String unit,
    double min,
    double max,
  ) {
    if (value != null && value >= min && value <= max) {
      vitals.add(ParsedVital(type: type, value: value, unit: unit));
    }
  }

  static bool _hasRecordLanguage(String text) {
    return RegExp(
      r'\b(?:record|log|document|enter|save|put|set|add|update|administer(?:ed)?|gave|give|hold|withhold(?:ing|held)?|start(?:ed)?|stop(?:ped)?|discontinue(?:d)?)\b',
      caseSensitive: false,
    ).hasMatch(text);
  }

  static ParsedMedication? _parseMedication(String text) {
    final action = _medicationActionPattern.firstMatch(text);
    if (action == null) return null;

    var remainder = text.substring(action.end).trim();
    remainder = remainder.replaceFirst(
      RegExp(r'^(?:the\s+)?(?:patient\s+)?', caseSensitive: false),
      '',
    );
    if (remainder.isEmpty) return null;

    final dose = _dosePattern
        .firstMatch(remainder)
        ?.group(0)
        ?.replaceAll(RegExp(r'\s+'), ' ');
    final route = _routePattern.firstMatch(remainder)?.group(0)?.toUpperCase();

    var namePart = remainder;
    final doseMatch = _dosePattern.firstMatch(remainder);
    if (doseMatch != null) {
      final beforeDose = remainder.substring(0, doseMatch.start).trim();
      final afterDose = remainder.substring(doseMatch.end).trim();
      // Handles both "gave Zofran 4 mg" and "gave 4 mg Zofran".
      namePart = beforeDose.isNotEmpty ? beforeDose : afterDose;
    }
    namePart = namePart
        .replaceFirst(_routePattern, '')
        .replaceFirst(
          RegExp(
            r'\b(?:to|for|at)\s+(?:the\s+)?patient\b.*$',
            caseSensitive: false,
          ),
          '',
        )
        .replaceFirst(
          RegExp(
            r'\b(?:now|today|this\s+morning|this\s+evening)\b.*$',
            caseSensitive: false,
          ),
          '',
        )
        .trim();
    final nameTokens = namePart
        .split(RegExp(r'\s+'))
        .where((token) => RegExp(r"^[A-Za-z][A-Za-z0-9'/-]*$").hasMatch(token))
        .take(3)
        .toList();
    const genericMedicationWords = {'medication', 'med', 'drug', 'dose', 'the'};
    while (nameTokens.isNotEmpty &&
        genericMedicationWords.contains(nameTokens.first.toLowerCase())) {
      nameTokens.removeAt(0);
    }
    if (nameTokens.isEmpty) return null;

    final verb = action.group(1)!.toLowerCase();
    final status = switch (verb) {
      'hold' || 'held' || 'withheld' => 'held',
      'stop' ||
      'stopped' ||
      'discontinue' ||
      'discontinued' ||
      'dc' => 'discontinued',
      'start' || 'started' => 'started',
      _ => 'administered',
    };
    return ParsedMedication(
      name: nameTokens.join(' '),
      dose: dose,
      route: route,
      status: status,
    );
  }
}
