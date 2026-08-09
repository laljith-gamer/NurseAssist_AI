import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive_io.dart';
import 'package:crypto/crypto.dart';

enum ModelStatus { ready, downloading, error, offline, checking, updateAvailable, verifying, installing }

class ModelManager extends ChangeNotifier {
  static const String _repoOwner = 'laljith-gamer';
  static const String _repoName = 'NurseAssist_AI';
  
  bool _isUpdating = false;
  ModelStatus _status = ModelStatus.ready;
  String _currentVersion = 'Unknown';
  String _downloadProgress = '';

  bool get isUpdating => _isUpdating;
  ModelStatus get status => _status;
  String get currentVersion => _currentVersion;
  String get downloadProgress => _downloadProgress;

  final VoidCallback? onModelUpdated;

  ModelManager({this.onModelUpdated}) {
    _initStatus().then((_) {
      if (_currentVersion == 'None') {
        checkForUpdates();
      }
    });
  }

  Future<void> _initStatus() async {
    final localMeta = await getLocalMetadata();
    if (localMeta != null) {
      _currentVersion = localMeta['model_version'] ?? 'Unknown';
      _status = ModelStatus.ready;
    } else {
      _currentVersion = 'None';
      _status = ModelStatus.offline;
    }
    notifyListeners();
  }

  Future<Directory> _getModelsDir() async {
    final appDir = await getApplicationDocumentsDirectory();
    final modelsDir = Directory('${appDir.path}/local_models');
    if (!await modelsDir.exists()) {
      await modelsDir.create(recursive: true);
    }
    return modelsDir;
  }

  Future<void> _initDirs() async {
    final baseDir = await _getModelsDir();
    final currentDir = Directory('${baseDir.path}/current');
    final previousDir = Directory('${baseDir.path}/previous');
    if (!await currentDir.exists()) await currentDir.create();
    if (!await previousDir.exists()) await previousDir.create();
  }

  Future<Map<String, dynamic>?> getLocalMetadata() async {
    final baseDir = await _getModelsDir();
    final file = File('${baseDir.path}/current/metadata.json');
    if (await file.exists()) {
      try {
        final contents = await file.readAsString();
        return jsonDecode(contents);
      } catch (e) {
        return null;
      }
    }
    return null;
  }

  Future<Map<String, dynamic>?> _fetchLatestRelease() async {
    try {
      final response = await http.get(
        Uri.parse('https://api.github.com/repos/$_repoOwner/$_repoName/releases/latest'),
      ).timeout(const Duration(seconds: 5));
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
    } catch (e) {
      // Offline or network error
    }
    return null;
  }

  Future<void> checkForUpdates() async {
    if (_isUpdating) return;
    
    _status = ModelStatus.downloading;
    _downloadProgress = 'Checking...';
    notifyListeners();

    try {
      final release = await _fetchLatestRelease();
      if (release == null) {
        _status = ModelStatus.offline;
        _downloadProgress = '';
        notifyListeners();
        return;
      }

      final latestVersion = release['tag_name'];
      final localMeta = await getLocalMetadata();
      
      if (localMeta == null || localMeta['model_version'] != latestVersion) {
        await _downloadAndInstallLatest(release);
      } else {
        _status = ModelStatus.ready;
        _downloadProgress = '';
        notifyListeners();
      }
    } catch (e) {
      _status = ModelStatus.error;
      _downloadProgress = '';
      notifyListeners();
    }
  }

  Future<void> _downloadAndInstallLatest(Map<String, dynamic> release) async {
    try {
      _isUpdating = true;
      
      final latestVersion = release['tag_name'];
      final assets = release['assets'] as List;
      
      if (assets.isEmpty) throw Exception('No assets');

      final asset = assets.firstWhere((a) => a['name'].toString().endsWith('.zip'), orElse: () => null);
      if (asset == null) throw Exception('No zip asset');

      final downloadUrl = asset['browser_download_url'];
      
      _downloadProgress = 'Downloading...';
      notifyListeners();
      
      final response = await http.get(Uri.parse(downloadUrl));
      if (response.statusCode != 200) throw Exception('Download failed');
      
      final baseDir = await _getModelsDir();
      final tempZip = File('${baseDir.path}/temp_model.zip');
      await tempZip.writeAsBytes(response.bodyBytes);
      
      _downloadProgress = 'Installing...';
      notifyListeners();
      
      final bytes = await tempZip.readAsBytes();
      final archive = ZipDecoder().decodeBytes(bytes);
      
      final tempExtracted = Directory('${baseDir.path}/temp_extracted');
      if (await tempExtracted.exists()) await tempExtracted.delete(recursive: true);
      await tempExtracted.create();
      
      for (final file in archive) {
        final filename = file.name;
        if (file.isFile) {
          final data = file.content as List<int>;
          File('${tempExtracted.path}/$filename')
            ..createSync(recursive: true)
            ..writeAsBytesSync(data);
        }
      }
      
      final tempMetaFile = File('${tempExtracted.path}/metadata.json');
      if (!await tempMetaFile.exists()) throw Exception('Invalid package');
      
      final newMeta = jsonDecode(await tempMetaFile.readAsString());
      if (newMeta['schema_version'] != 1) throw Exception('Incompatible schema');
      
      final intentSha = newMeta['intent_model']['sha256'];
      final intentBytes = await File('${tempExtracted.path}/intent.json').readAsBytes();
      if (intentSha != sha256.convert(intentBytes).toString()) throw Exception('Checksum error');
      
      await _initDirs();
      final currentDir = Directory('${baseDir.path}/current');
      final previousDir = Directory('${baseDir.path}/previous');
      
      if (await previousDir.exists()) await previousDir.delete(recursive: true);
      if (await currentDir.exists()) await currentDir.rename(previousDir.path);
      
      await tempExtracted.rename(currentDir.path);
      await tempZip.delete();
      
      _currentVersion = latestVersion;
      _status = ModelStatus.ready;
      _downloadProgress = '';
      
      onModelUpdated?.call();
    } catch (e) {
      _status = ModelStatus.error;
      _downloadProgress = '';
      debugPrint('Model update error: $e');
    } finally {
      _isUpdating = false;
      notifyListeners();
    }
  }

  Future<bool> rollback() async {
    final baseDir = await _getModelsDir();
    final currentDir = Directory('${baseDir.path}/current');
    final previousDir = Directory('${baseDir.path}/previous');
    
    if (await previousDir.exists()) {
      final tempDir = Directory('${baseDir.path}/temp_failed');
      if (await currentDir.exists()) await currentDir.rename(tempDir.path);
      await previousDir.rename(currentDir.path);
      if (await tempDir.exists()) await tempDir.delete(recursive: true);
      await _initStatus();
      return true;
    }
    return false;
  }
}
