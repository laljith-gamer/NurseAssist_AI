import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SettingsProvider with ChangeNotifier {
  static const _keyBackendUrl = 'backend_url';
  static const _keyDarkMode = 'is_dark_mode';
  static const _keyTelemetrySharing = 'telemetry_sharing_enabled';
  static const _keyConsentDialogShown = 'telemetry_consent_shown';
  static const _keyLastTelemetrySync = 'last_telemetry_sync';

  String _backendUrl = 'https://nurseassist-ai-1.onrender.com';
  bool _isDarkMode = true; // Default to dark mode for premium look
  bool _telemetrySharingEnabled = false;
  bool _consentDialogShown = false;
  int _queuedTelemetryCount = 0;
  int _lastTelemetrySyncTime = 0;

  String get backendUrl => _backendUrl;

  String get httpUrl => _backendUrl.startsWith('http')
      ? _backendUrl
      : 'http://$_backendUrl';

  String get wsUrl {
    if (_backendUrl.startsWith('https://')) {
      return _backendUrl.replaceFirst('https://', 'wss://');
    } else if (_backendUrl.startsWith('http://')) {
      return _backendUrl.replaceFirst('http://', 'ws://');
    }
    return 'ws://$_backendUrl';
  }

  bool get isDarkMode => _isDarkMode;
  bool get telemetrySharingEnabled => _telemetrySharingEnabled;
  bool get consentDialogShown => _consentDialogShown;
  int get queuedTelemetryCount => _queuedTelemetryCount;
  int get lastTelemetrySyncTime => _lastTelemetrySyncTime;

  /// Load persisted settings from SharedPreferences. Call once at startup.
  Future<void> loadFromPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    _backendUrl = prefs.getString(_keyBackendUrl) ?? _backendUrl;
    _isDarkMode = prefs.getBool(_keyDarkMode) ?? _isDarkMode;
    _telemetrySharingEnabled =
        prefs.getBool(_keyTelemetrySharing) ?? false;
    _consentDialogShown =
        prefs.getBool(_keyConsentDialogShown) ?? false;
    _lastTelemetrySyncTime = prefs.getInt(_keyLastTelemetrySync) ?? 0;
    notifyListeners();
  }

  void setBackendUrl(String url) {
    if (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    _backendUrl = url;
    _persist(_keyBackendUrl, url);
    notifyListeners();
  }

  void toggleTheme() {
    _isDarkMode = !_isDarkMode;
    _persist(_keyDarkMode, _isDarkMode);
    notifyListeners();
  }

  void setTelemetrySharingEnabled(bool enabled) {
    _telemetrySharingEnabled = enabled;
    _persist(_keyTelemetrySharing, enabled);
    notifyListeners();
  }

  void markConsentDialogShown() {
    _consentDialogShown = true;
    _persist(_keyConsentDialogShown, true);
  }

  /// Called by telemetry service to keep the settings screen count up to date.
  void updateQueuedTelemetryCount(int count) {
    if (_queuedTelemetryCount != count) {
      _queuedTelemetryCount = count;
      notifyListeners();
    }
  }

  void setLastTelemetrySyncTime(int timestamp) {
    _lastTelemetrySyncTime = timestamp;
    _persist(_keyLastTelemetrySync, timestamp);
  }

  Future<void> _persist(String key, dynamic value) async {
    final prefs = await SharedPreferences.getInstance();
    if (value is bool) {
      await prefs.setBool(key, value);
    } else if (value is String) {
      await prefs.setString(key, value);
    } else if (value is int) {
      await prefs.setInt(key, value);
    }
  }
}
