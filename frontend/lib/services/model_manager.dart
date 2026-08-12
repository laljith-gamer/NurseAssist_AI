import 'dart:convert';
import 'dart:io';

import 'package:archive/archive_io.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

enum ModelStatus {
  ready,
  downloading,
  error,
  offline,
  checking,
  updateAvailable,
  verifying,
  installing,
}

/// Installs only the small, data-backed nursing-observation package. The LLM
/// task file is managed separately by [LlmService], so model updates cannot
/// accidentally download the multi-gigabyte task model.
class ModelManager extends ChangeNotifier {
  static const String _repoOwner = 'laljith-gamer';
  static const String _repoName = 'NurseAssist_AI';
  static final RegExp _nlpZipName = RegExp(
    r'^nurseassist-observation-model-.+\.zip$',
  );

  bool _isUpdating = false;
  ModelStatus _status = ModelStatus.checking;
  String _currentVersion = 'Checking';
  String _downloadProgress = '';

  bool get isUpdating => _isUpdating;
  ModelStatus get status => _status;
  String get currentVersion => _currentVersion;
  String get downloadProgress => _downloadProgress;

  final Future<void> Function()? onModelUpdated;

  ModelManager({this.onModelUpdated}) {
    _initStatus().then((_) => checkForUpdates());
  }

  Future<void> _initStatus() async {
    if (kIsWeb) {
      _currentVersion = 'Web';
      _status = ModelStatus.offline;
      notifyListeners();
      return;
    }
    final localMeta = await getLocalMetadata();
    if (localMeta != null) {
      _currentVersion = localMeta['model_version']?.toString() ?? 'Unknown';
      _status = ModelStatus.ready;
    } else {
      _currentVersion = 'Not installed';
      _status = ModelStatus.offline;
    }
    notifyListeners();
  }

  Future<Directory> _getModelsDir() async {
    final appDir = await getApplicationDocumentsDirectory();
    final modelsDir = Directory(path.join(appDir.path, 'local_models'));
    if (!await modelsDir.exists()) await modelsDir.create(recursive: true);
    return modelsDir;
  }

  Future<Map<String, dynamic>?> getLocalMetadata() async {
    if (kIsWeb) return null;
    final baseDir = await _getModelsDir();
    final file = File(path.join(baseDir.path, 'current', 'metadata.json'));
    if (!await file.exists()) return null;
    try {
      final metadata = jsonDecode(await file.readAsString());
      if (metadata is! Map<String, dynamic> ||
          metadata['schema_version'] != 2 ||
          metadata['observation_model'] is! Map) {
        return null;
      }
      return metadata;
    } catch (_) {
      return null;
    }
  }

  Future<Map<String, dynamic>?> _fetchLatestNlpRelease() async {
    try {
      final response = await http
          .get(
            Uri.parse(
              'https://api.github.com/repos/$_repoOwner/$_repoName/releases?per_page=30',
            ),
            headers: const {'Accept': 'application/vnd.github+json'},
          )
          .timeout(const Duration(seconds: 8));
      if (response.statusCode != 200) return null;
      final releases = jsonDecode(response.body);
      if (releases is! List) return null;
      for (final rawRelease in releases) {
        if (rawRelease is! Map) continue;
        final release = Map<String, dynamic>.from(rawRelease);
        final assets = release['assets'];
        if (assets is List && assets.any(_isNlpZipAsset)) return release;
      }
    } catch (_) {
      // Offline is an expected state for the app.
    }
    return null;
  }

  bool _isNlpZipAsset(dynamic asset) {
    if (asset is! Map) return false;
    return _nlpZipName.hasMatch(asset['name']?.toString() ?? '');
  }

  Future<void> checkForUpdates() async {
    if (kIsWeb || _isUpdating) return;
    _status = ModelStatus.checking;
    _downloadProgress = 'Checking nursing-language updates...';
    notifyListeners();

    try {
      final release = await _fetchLatestNlpRelease();
      if (release == null) {
        // Continue to use a verified installed model when offline.
        _status = (await getLocalMetadata()) == null
            ? ModelStatus.offline
            : ModelStatus.ready;
        _downloadProgress = '';
        notifyListeners();
        return;
      }

      final latestVersion = release['tag_name']?.toString() ?? 'Unknown';
      final localMeta = await getLocalMetadata();
      if (localMeta != null &&
          localMeta['model_version']?.toString() == latestVersion) {
        _currentVersion = latestVersion;
        _status = ModelStatus.ready;
        _downloadProgress = '';
        notifyListeners();
        return;
      }

      _status = ModelStatus.updateAvailable;
      _downloadProgress = 'Nursing-language update available';
      notifyListeners();
      await _downloadAndInstallLatest(release);
    } catch (error) {
      debugPrint('Model update check failed: $error');
      _status = (await getLocalMetadata()) == null
          ? ModelStatus.error
          : ModelStatus.ready;
      _downloadProgress = '';
      notifyListeners();
    }
  }

  Future<void> _downloadAndInstallLatest(Map<String, dynamic> release) async {
    _isUpdating = true;
    Directory? baseDir;
    try {
      final latestVersion = release['tag_name']?.toString();
      final rawAssets = release['assets'];
      if (latestVersion == null || rawAssets is! List) {
        throw const FormatException('Invalid release metadata');
      }
      final rawAsset = rawAssets.cast<dynamic>().firstWhere(
        _isNlpZipAsset,
        orElse: () => null,
      );
      if (rawAsset is! Map) {
        throw const FormatException('No NLP package asset found');
      }
      final asset = Map<String, dynamic>.from(rawAsset);
      final downloadUrl = asset['browser_download_url']?.toString();
      if (downloadUrl == null) {
        throw const FormatException('Missing package download URL');
      }

      _status = ModelStatus.downloading;
      _downloadProgress = 'Downloading nursing-language model...';
      notifyListeners();
      final response = await http
          .get(Uri.parse(downloadUrl))
          .timeout(const Duration(minutes: 2));
      if (response.statusCode != 200 || response.bodyBytes.isEmpty) {
        throw HttpException(
          'NLP package download failed (${response.statusCode})',
        );
      }

      baseDir = await _getModelsDir();
      final tempZip = File(path.join(baseDir.path, 'model_download.zip'));
      await tempZip.writeAsBytes(response.bodyBytes, flush: true);

      _status = ModelStatus.verifying;
      _downloadProgress = 'Verifying NLP model...';
      notifyListeners();
      final archive = ZipDecoder().decodeBytes(await tempZip.readAsBytes());
      final extracted = Directory(path.join(baseDir.path, 'model_staging'));
      if (await extracted.exists()) {
        await extracted.delete(recursive: true);
      }
      await extracted.create();

      const expectedFiles = {'observations.json', 'metadata.json'};
      final extractedFiles = <String>{};
      for (final archiveFile in archive) {
        final name = archiveFile.name.replaceAll('\\', '/');
        if (!archiveFile.isFile ||
            name.contains('..') ||
            name.startsWith('/') ||
            !expectedFiles.contains(name) ||
            extractedFiles.contains(name)) {
          throw const FormatException('NLP package contains an invalid file');
        }
        final target = File(path.join(extracted.path, name));
        await target.writeAsBytes(
          archiveFile.content as List<int>,
          flush: true,
        );
        extractedFiles.add(name);
      }
      if (extractedFiles.length != expectedFiles.length ||
          !extractedFiles.containsAll(expectedFiles)) {
        throw const FormatException('NLP package is incomplete');
      }

      final metadata = jsonDecode(
        await File(path.join(extracted.path, 'metadata.json')).readAsString(),
      );
      if (metadata is! Map<String, dynamic> ||
          metadata['schema_version'] != 2 ||
          metadata['model_version']?.toString() != latestVersion) {
        throw const FormatException('NLP package metadata is incompatible');
      }
      await _verifyArtifact(
        extracted,
        metadata,
        'observation_model',
        'observations.json',
      );
      await _validateExportedModel(
        File(path.join(extracted.path, 'observations.json')),
      );

      _status = ModelStatus.installing;
      _downloadProgress = 'Installing nursing-language model...';
      notifyListeners();
      final current = Directory(path.join(baseDir.path, 'current'));
      final previous = Directory(path.join(baseDir.path, 'previous'));
      if (await previous.exists()) {
        await previous.delete(recursive: true);
      }
      if (await current.exists()) {
        await current.rename(previous.path);
      }
      await extracted.rename(current.path);
      if (await tempZip.exists()) {
        await tempZip.delete();
      }

      _currentVersion = latestVersion;
      _status = ModelStatus.ready;
      _downloadProgress = '';
      await onModelUpdated?.call();
    } catch (error) {
      debugPrint('Model update error: $error');
      // If a failure occurs after the old `current` directory was moved aside,
      // restore it before reporting state. A partially installed model is never
      // allowed to replace a usable local one.
      if (baseDir != null) {
        final current = Directory(path.join(baseDir.path, 'current'));
        final previous = Directory(path.join(baseDir.path, 'previous'));
        if (!await current.exists() && await previous.exists()) {
          try {
            await previous.rename(current.path);
          } catch (rollbackError) {
            debugPrint('Automatic NLP rollback failed: $rollbackError');
          }
        }
      }
      _status = (await getLocalMetadata()) == null
          ? ModelStatus.error
          : ModelStatus.ready;
      _downloadProgress = '';
    } finally {
      _isUpdating = false;
      notifyListeners();
    }
  }

  Future<void> _verifyArtifact(
    Directory extracted,
    Map<String, dynamic> metadata,
    String metadataKey,
    String filename,
  ) async {
    final descriptor = metadata[metadataKey];
    if (descriptor is! Map || descriptor['artifact'] != filename) {
      throw FormatException('Invalid $metadataKey metadata');
    }
    final expectedHash = descriptor['sha256']?.toString();
    final bytes = await File(path.join(extracted.path, filename)).readAsBytes();
    if (expectedHash == null ||
        sha256.convert(bytes).toString() != expectedHash) {
      throw FormatException('$filename checksum does not match');
    }
  }

  @visibleForTesting
  static Future<void> validateExportedModelForTest(File file) => _validateExportedModel(file);

  static Future<void> _validateExportedModel(File file) async {
    final model = jsonDecode(await file.readAsString());
    if (model is! Map ||
        model['type'] != 'compact_clinical_mlp' ||
        model['role'] != 'advisory_clinical_observation_context' ||
        model['vocabulary'] is! Map ||
        model['idf'] is! List ||
        model['mlp'] is! Map ||
        model['classes'] is! List ||
        model['threshold'] is! num ||
        (model['classes'] as List).isEmpty) {
      throw const FormatException('Invalid exported classifier');
    }

    final threshold = model['threshold'] as num;
    if (!threshold.isFinite || threshold <= 0 || threshold >= 1) {
      throw const FormatException('Classifier dimensions do not match');
    }

    final classes = model['classes'] as List;
    final idf = model['idf'] as List;
    final mlp = model['mlp'] as Map;
    final arch = mlp['arch'];

    if (arch is! Map || arch['input_dim'] is! num || arch['output_dim'] is! num) {
      throw const FormatException('Invalid exported classifier');
    }

    final inputDim = (arch['input_dim'] as num).toInt();

    final l1W = mlp['layer1_weight'];
    final l1B = mlp['layer1_bias'];
    final l2W = mlp['layer2_weight'];
    final l2B = mlp['layer2_bias'];
    final outW = mlp['output_weight'];
    final outB = mlp['output_bias'];

    if (l1W is! List || l1B is! List || l2W is! List || l2B is! List || outW is! List || outB is! List) {
      throw const FormatException('Invalid exported classifier');
    }

    if (outW.length != classes.length || outB.length != classes.length) {
      throw const FormatException('Classifier dimensions do not match');
    }

    int expectedIdfLength = inputDim;
    if (model['bert_projection'] is Map) {
      expectedIdfLength -= (model['bert_projection']['reduced_dim'] as num).toInt();
    }
    
    if (idf.length != expectedIdfLength) {
      throw const FormatException('Classifier dimensions do not match');
    }

    if (l1W.any((row) => row is! List || row.length != inputDim)) {
      throw const FormatException('Classifier coefficient dimensions do not match');
    }

    if (l2W.any((row) => row is! List || row.length != l1W.length) || l2B.length != l2W.length) {
      throw const FormatException('Classifier coefficient dimensions do not match');
    }

    if (outW.any((row) => row is! List || row.length != l2W.length)) {
      throw const FormatException('Classifier coefficient dimensions do not match');
    }
  }

  Future<bool> rollback() async {
    if (kIsWeb) return false;
    final baseDir = await _getModelsDir();
    final current = Directory(path.join(baseDir.path, 'current'));
    final previous = Directory(path.join(baseDir.path, 'previous'));
    if (!await previous.exists()) return false;

    final failed = Directory(path.join(baseDir.path, 'failed_rollback'));
    if (await failed.exists()) {
      await failed.delete(recursive: true);
    }
    if (await current.exists()) {
      await current.rename(failed.path);
    }
    await previous.rename(current.path);
    if (await failed.exists()) {
      await failed.delete(recursive: true);
    }
    await _initStatus();
    return true;
  }
}
