import 'dart:async';
import 'dart:convert';
import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/material.dart';
import 'local_db_service.dart';
import 'api_service.dart';

class SyncService with ChangeNotifier {
  final LocalDbService _localDb = LocalDbService();
  final ApiService _apiService = ApiService();
  
  bool _isOnline = true;
  bool get isOnline => _isOnline;

  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;

  SyncService() {
    _initConnectivity();
  }

  Future<void> _initConnectivity() async {
    final result = await Connectivity().checkConnectivity();
    _updateConnectionStatus(result);
    
    _connectivitySubscription = Connectivity().onConnectivityChanged.listen(_updateConnectionStatus);
  }

  void _updateConnectionStatus(List<ConnectivityResult> result) {
    bool wasOffline = !_isOnline;
    _isOnline = !result.contains(ConnectivityResult.none);
    notifyListeners();

    if (wasOffline && _isOnline) {
      _flushActionQueue();
    }
  }

  Future<void> _flushActionQueue() async {
    if (!_isOnline) return;

    debugPrint('Device is back online. Flushing offline action queue...');
    final queue = await _localDb.getActionQueue();
    
    for (var action in queue) {
      if (!_isOnline) break; // Stop flushing if connection drops again

      try {
        final endpoint = action['endpoint'] as String;
        final payloadStr = action['payload'] as String;
        final payload = jsonDecode(payloadStr);

        debugPrint('Syncing action to $endpoint');
        
        if (endpoint == '/api/patients') {
           await _apiService.createPatientOnline(payload);
        } else if (endpoint == '/api/chat/sync') {
           // For chatting we would send a REST fallback command since WebSocket is hard to queue natively
           final patientId = payload['patientId'];
           final message = payload['message'];
           await _apiService.sendCommandOnline(patientId, message);
        }
        
        // Remove from queue if successful
        await _localDb.removeActionFromQueue(action['id'] as int);
        debugPrint('Action synced successfully.');
      } catch (e) {
        debugPrint('Failed to sync action: $e');
        // If it fails due to network, it will stay in the queue. 
        // If it fails due to 400 Bad Request, we might want to drop it eventually, but we'll leave it for now.
      }
    }
  }

  @override
  void dispose() {
    _connectivitySubscription?.cancel();
    super.dispose();
  }
}
