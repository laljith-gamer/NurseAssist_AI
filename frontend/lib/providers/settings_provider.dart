import 'package:flutter/material.dart';

class SettingsProvider with ChangeNotifier {
  String _backendUrl = 'https://nurseassist-ai-1.onrender.com';
  bool _isDarkMode = true; // Default to dark mode for premium look

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

  void setBackendUrl(String url) {
    if (url.endsWith('/')) {
      url = url.substring(0, url.length - 1);
    }
    _backendUrl = url;
    notifyListeners();
  }

  void toggleTheme() {
    _isDarkMode = !_isDarkMode;
    notifyListeners();
  }
}
