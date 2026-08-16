import 'dart:convert';
import 'package:flutter/services.dart';

/// A service to look up clinical terms, diagnoses, and medications offline.
/// This connects to the offline clinical dictionary.
class TerminologyService {
  static final TerminologyService _instance = TerminologyService._internal();
  factory TerminologyService() => _instance;
  TerminologyService._internal();

  bool _isLoaded = false;
  final Map<String, String> _dictionary = {};

  Future<void> loadDictionary() async {
    if (_isLoaded) return;
    try {
      // In a full production scenario, this would connect to a local SQLite DB
      // containing the full SNOMED CT / ICD-10 datasets (often >1GB).
      // For this prototype, we load a bundled JSON dictionary of common terms.
      final String jsonString = await rootBundle.loadString(
        'assets/dictionary/clinical_terms.json',
      );
      final Map<String, dynamic> jsonMap = jsonDecode(jsonString);

      jsonMap.forEach((key, value) {
        _dictionary[key.toLowerCase()] = value.toString();
      });
      _isLoaded = true;
    } catch (e) {
      // If the file doesn't exist yet, we just start with an empty dictionary.
      _isLoaded = true;
    }
  }

  /// Looks up a term in the offline dictionary.
  /// Returns the standardized term or definition if found.
  String? lookupTerm(String query) {
    if (!_isLoaded) return null;
    return _dictionary[query.toLowerCase().trim()];
  }

  /// Searches for terms containing the query.
  List<String> searchTerms(String query) {
    if (!_isLoaded) return [];
    final lowerQuery = query.toLowerCase().trim();
    return _dictionary.keys
        .where((key) => key.contains(lowerQuery))
        .take(10)
        .toList();
  }
}
