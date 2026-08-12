class Patient {
  final String id;
  final String mrn;
  final String firstName;
  final String lastName;
  final String name;
  final String dateOfBirth;
  final int age;
  final String gender;
  final String room;
  final String bed;
  final String admissionDate;
  final String? dischargeDate;
  final String primaryDiagnosis;
  final String allergies;
  final String codeStatus;
  final String insurance;
  final String emergencyContactName;
  final String emergencyContactPhone;
  final bool isActive;
  final String createdAt;
  final String updatedAt;

  Patient({
    required this.id,
    required this.mrn,
    required this.firstName,
    required this.lastName,
    required this.name,
    required this.dateOfBirth,
    required this.age,
    required this.gender,
    required this.room,
    required this.bed,
    required this.admissionDate,
    this.dischargeDate,
    required this.primaryDiagnosis,
    required this.allergies,
    required this.codeStatus,
    required this.insurance,
    required this.emergencyContactName,
    required this.emergencyContactPhone,
    required this.isActive,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Patient.fromJson(Map<String, dynamic> json) {
    final firstName = json['first_name']?.toString() ?? '';
    final lastName = json['last_name']?.toString() ?? '';
    final suppliedName = json['name']?.toString().trim() ?? '';
    final displayName = suppliedName.isNotEmpty
        ? suppliedName
        : [firstName, lastName].where((part) => part.isNotEmpty).join(' ');
    return Patient(
      id: json['id']?.toString() ?? '',
      mrn: json['mrn']?.toString() ?? '',
      firstName: firstName,
      lastName: lastName,
      name: displayName.isEmpty ? 'Unnamed patient' : displayName,
      dateOfBirth: json['date_of_birth']?.toString() ?? '',
      age: json['age'] is num
          ? (json['age'] as num).toInt()
          : int.tryParse(json['age']?.toString() ?? '') ?? 0,
      gender: json['gender']?.toString() ?? '',
      room: json['room']?.toString() ?? '',
      bed: json['bed']?.toString() ?? '',
      admissionDate: json['admission_date']?.toString() ?? '',
      dischargeDate: json['discharge_date'],
      primaryDiagnosis: json['primary_diagnosis']?.toString() ?? '',
      allergies: json['allergies']?.toString() ?? '',
      codeStatus: json['code_status']?.toString() ?? '',
      insurance: json['insurance']?.toString() ?? '',
      emergencyContactName: json['emergency_contact_name']?.toString() ?? '',
      emergencyContactPhone: json['emergency_contact_phone']?.toString() ?? '',
      isActive: json['is_active'] ?? true,
      createdAt: json['created_at']?.toString() ?? '',
      updatedAt: json['updated_at']?.toString() ?? '',
    );
  }
}

class VitalDelta {
  final num current;
  final String significance;
  final Map<String, dynamic>? vsYesterday;
  final Map<String, dynamic>? vs7DayAvg;
  final Map<String, dynamic>? vsBaseline;
  final String trend;

  VitalDelta({
    required this.current,
    required this.significance,
    this.vsYesterday,
    this.vs7DayAvg,
    this.vsBaseline,
    required this.trend,
  });

  factory VitalDelta.fromJson(Map<String, dynamic> json) {
    return VitalDelta(
      current: json['current'] ?? 0,
      significance: json['significance'] ?? '',
      vsYesterday: json['vs_yesterday'],
      vs7DayAvg: json['vs_7day_avg'],
      vsBaseline: json['vs_baseline'],
      trend: json['trend'] ?? 'stable',
    );
  }
}

class DeltaMetrics {
  final String patientId;
  final bool hasData;
  final String timestamp;
  final Map<String, dynamic> current;
  final Map<String, VitalDelta> deltas;
  final List<String> alerts;
  final Map<String, String> clinicalStatus;

  DeltaMetrics({
    required this.patientId,
    required this.hasData,
    required this.timestamp,
    required this.current,
    required this.deltas,
    required this.alerts,
    required this.clinicalStatus,
  });

  factory DeltaMetrics.fromJson(Map<String, dynamic> json) {
    Map<String, VitalDelta> parsedDeltas = {};
    if (json['deltas'] != null) {
      (json['deltas'] as Map<String, dynamic>).forEach((key, value) {
        parsedDeltas[key] = VitalDelta.fromJson(value);
      });
    }

    Map<String, String> parsedClinicalStatus = {};
    if (json['clinical_status'] != null) {
      (json['clinical_status'] as Map<String, dynamic>).forEach((key, value) {
        parsedClinicalStatus[key] = value.toString();
      });
    }

    return DeltaMetrics(
      patientId: json['patient_id'] ?? '',
      hasData: json['has_data'] ?? false,
      timestamp: json['timestamp'] ?? '',
      current: json['current'] ?? {},
      deltas: parsedDeltas,
      alerts: List<String>.from(json['alerts'] ?? []),
      clinicalStatus: parsedClinicalStatus,
    );
  }
}

class ChatMessage {
  final String id;
  final String? sessionId;
  final String role;
  final String content;
  final DateTime timestamp;
  final Map<String, dynamic>? data;
  final String? type;

  /// Observation labels predicted for the user message that triggered this
  /// assistant response. Empty for user messages and historic messages loaded
  /// from the database.
  final List<String> observationHints;

  ChatMessage({
    required this.id,
    this.sessionId,
    required this.role,
    required this.content,
    required this.timestamp,
    this.data,
    this.type,
    this.observationHints = const [],
  });
}

class ChatSession {
  const ChatSession({
    required this.id,
    required this.patientId,
    required this.title,
    required this.createdAt,
  });

  final String id;
  final String patientId;
  final String title;
  final DateTime createdAt;

  factory ChatSession.fromJson(Map<String, dynamic> json) {
    final createdAt = json['created_at'];
    return ChatSession(
      id: json['id']?.toString() ?? '',
      patientId: json['patient_id']?.toString() ?? '',
      title: json['title']?.toString() ?? 'New chat',
      createdAt: createdAt is num
          ? DateTime.fromMillisecondsSinceEpoch(createdAt.toInt())
          : DateTime.now(),
    );
  }

  ChatSession copyWith({
    String? id,
    String? patientId,
    String? title,
    DateTime? createdAt,
  }) {
    return ChatSession(
      id: id ?? this.id,
      patientId: patientId ?? this.patientId,
      title: title ?? this.title,
      createdAt: createdAt ?? this.createdAt,
    );
  }
}

class NursingNote {
  const NursingNote({
    required this.id,
    required this.patientId,
    required this.content,
    required this.category,
    required this.recordedAt,
  });

  final String id;
  final String patientId;
  final String content;
  final String category;
  final DateTime recordedAt;

  factory NursingNote.fromJson(Map<String, dynamic> json) {
    final recordedAt = json['recorded_at'];
    return NursingNote(
      id: json['id']?.toString() ?? '',
      patientId: json['patient_id']?.toString() ?? '',
      content: json['content']?.toString() ?? '',
      category: json['category']?.toString() ?? 'nursing_observation',
      recordedAt: recordedAt is num
          ? DateTime.fromMillisecondsSinceEpoch(recordedAt.toInt())
          : DateTime.now(),
    );
  }
}
