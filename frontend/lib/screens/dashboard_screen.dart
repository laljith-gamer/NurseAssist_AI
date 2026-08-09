import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/patient_provider.dart';
import '../widgets/patient_sidebar.dart';
import '../widgets/chat_interface.dart';
import '../providers/settings_provider.dart';
import '../widgets/clinical_change_banner.dart';
import '../widgets/charts/vital_signs_delta_chart.dart';
import 'dart:ui';
import 'dart:async';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  void _showSettingsModal(BuildContext context) {
    final settings = Provider.of<SettingsProvider>(context, listen: false);
    final _urlController = TextEditingController(text: settings.backendUrl);

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Settings'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: _urlController,
                decoration: const InputDecoration(
                  labelText: 'Backend URL',
                  hintText: 'http://...',
                ),
              ),
              const SizedBox(height: 16),
              Consumer<SettingsProvider>(
                builder: (context, settingsRef, _) => SwitchListTile(
                  title: const Text('Dark Mode'),
                  value: settingsRef.isDarkMode,
                  onChanged: (val) {
                    settingsRef.toggleTheme();
                  },
                ),
              const SizedBox(height: 16),
              const Divider(),
              const SizedBox(height: 8),
              const Text('AI Model Management', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
              const SizedBox(height: 8),
              const ModelManagementWidget(),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () {
                settings.setBackendUrl(_urlController.text);
                Provider.of<PatientProvider>(context, listen: false).loadPatients();
                Navigator.pop(context);
              },
              child: const Text('Save'),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    // Determine layout based on screen width
    final isDesktop = MediaQuery.of(context).size.width > 800;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: isDesktop
          ? null
          : AppBar(
              title: const Text('NurseAssist AI', style: TextStyle(fontWeight: FontWeight.w600)),
              backgroundColor: isDark ? Colors.black : Colors.blue[800],
              foregroundColor: Colors.white,
              actions: [
                IconButton(
                  icon: const Icon(Icons.settings),
                  onPressed: () => _showSettingsModal(context),
                )
              ],
            ),
      drawer: isDesktop ? null : const Drawer(child: PatientSidebar()),
      body: Row(
        children: [
          if (isDesktop) const PatientSidebar(),
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                  colors: isDark 
                    ? [const Color(0xFF1A1A24), const Color(0xFF121212)]
                    : [const Color(0xFFF5F7FA), const Color(0xFFE4E9F2)],
                ),
              ),
              child: Column(
                children: [
                  if (isDesktop)
                    ClipRRect(
                      child: BackdropFilter(
                        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                          color: isDark ? Colors.white.withOpacity(0.05) : Colors.white.withOpacity(0.5),
                          width: double.infinity,
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                "NurseAssist AI Dashboard",
                                style: TextStyle(
                                  fontSize: 26,
                                  fontWeight: FontWeight.w700,
                                  letterSpacing: -0.5,
                                  color: isDark ? Colors.white : Colors.black87,
                                ),
                              ),
                              IconButton(
                                icon: const Icon(Icons.settings),
                                onPressed: () => _showSettingsModal(context),
                                tooltip: 'Settings',
                              )
                            ],
                          ),
                        ),
                      ),
                    ),
                  const Expanded(
                    child: Padding(
                      padding: EdgeInsets.all(16.0),
                      child: _DashboardContent(),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DashboardContent extends StatelessWidget {
  const _DashboardContent();

  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        if (provider.selectedPatient == null) {
          return const Center(child: Text("Select a patient to view details"));
        }

        final isDesktop = MediaQuery.of(context).size.width > 800;

        if (isDesktop) {
          // Split view for desktop
          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                flex: 2,
                child: Column(
                  children: const [
                    ClinicalChangeBanner(),
                    Expanded(child: ChatInterface()),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                flex: 1,
                child: Column(
                  children: const [
                    VitalSignsDeltaChart(),
                    // Additional charts can go here
                  ],
                ),
              ),
            ],
          );
        } else {
          // Tabbed view for mobile
          return DefaultTabController(
            length: 3,
            child: Column(
              children: [
                TabBar(
                  labelColor: Theme.of(context).primaryColor,
                  unselectedLabelColor: Colors.grey,
                  indicatorColor: Theme.of(context).primaryColor,
                  tabs: const [
                    Tab(text: 'Chat', icon: Icon(Icons.chat_bubble_outline)),
                    Tab(text: 'Vitals', icon: Icon(Icons.monitor_heart_outlined)),
                    Tab(text: 'Score', icon: Icon(Icons.score)),
                  ],
                ),
                Expanded(
                  child: TabBarView(
                    children: [
                      const ChatInterface(),
                      Column(
                        children: const [
                          ClinicalChangeBanner(),
                          SizedBox(height: 8),
                          Expanded(child: SingleChildScrollView(child: VitalSignsDeltaChart())),
                        ],
                      ),
                      _ScoreTabContent(),
                    ],
                  ),
                ),
              ],
            ),
          );
        }
      },
    );
  }
}

class _ScoreTabContent extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        final status = provider.currentMetrics?.clinicalStatus;
        if (status == null || status.isEmpty) {
          return const Center(child: Text("No scoring data available."));
        }
        
        return ListView(
          padding: const EdgeInsets.all(16.0),
          children: [
            const Text(
              "Clinical Status",
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            ...status.entries.map((e) => Card(
              margin: const EdgeInsets.only(bottom: 8.0),
              child: ListTile(
                title: Text(e.key.toUpperCase()),
                subtitle: Text(e.value),
              ),
            )).toList(),
          ],
        );
      },
    );
  }
}

class ModelManagementWidget extends StatefulWidget {
  const ModelManagementWidget({super.key});

  @override
  _ModelManagementWidgetState createState() => _ModelManagementWidgetState();
}

class _ModelManagementWidgetState extends State<ModelManagementWidget> {
  String _currentVersion = "Unknown";
  String _status = "Checking...";
  bool _isLoading = false;
  Timer? _pollingTimer;

  @override
  void initState() {
    super.initState();
    _fetchLatestModel();
  }
  
  @override
  void dispose() {
    _pollingTimer?.cancel();
    super.dispose();
  }

  Future<void> _fetchLatestModel() async {
    setState(() { _isLoading = true; _status = "Checking local model..."; });
    try {
      final api = Provider.of<PatientProvider>(context, listen: false).apiService;
      final settings = Provider.of<SettingsProvider>(context, listen: false);
      api.baseUrl = settings.httpUrl;
      
      final data = await api.getLatestModel();
      setState(() {
        _currentVersion = data['version'] ?? 'Unknown';
        _status = 'Up to date';
      });
    } catch (e) {
      setState(() {
        _status = 'Error loading model data';
      });
    } finally {
      setState(() { _isLoading = false; });
    }
  }

  Future<void> _triggerRetrain() async {
    setState(() { _isLoading = true; _status = "Training requested... Waiting for GitHub Actions..."; });
    try {
      final api = Provider.of<PatientProvider>(context, listen: false).apiService;
      final settings = Provider.of<SettingsProvider>(context, listen: false);
      api.baseUrl = settings.httpUrl;
      
      await api.trainModel();
      
      // Start polling status
      _pollingTimer?.cancel();
      _pollingTimer = Timer.periodic(const Duration(seconds: 10), (timer) async {
        try {
          final statusData = await api.getModelStatus();
          final status = statusData['status'];
          
          if (status == 'success') {
            timer.cancel();
            setState(() { _status = "Updating backend..."; });
            
            // Call update
            await api.updateBackendModel();
            
            setState(() { _status = "Model successfully updated."; });
            await _fetchLatestModel();
          } else if (status == 'failed') {
            timer.cancel();
            setState(() { _status = "Training failed."; _isLoading = false; });
          } else {
            setState(() { _status = "Training model... Intent/NER model training"; });
          }
        } catch (e) {
          // ignore polling errors
        }
      });
      
    } catch (e) {
      setState(() {
        _status = 'Error triggering training';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text('Current Version:'),
            Text(_currentVersion, style: const TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            const Text('Status:'),
            Expanded(
              child: Text(
                _status, 
                textAlign: TextAlign.right,
                style: TextStyle(
                  color: _status.contains('Error') || _status.contains('failed') ? Colors.red : Colors.green,
                  fontSize: 12,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            OutlinedButton(
              onPressed: _isLoading ? null : _fetchLatestModel,
              child: const Text('Check for Update'),
            ),
            ElevatedButton(
              onPressed: _isLoading ? null : _triggerRetrain,
              child: _isLoading 
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) 
                  : const Text('Retrain AI Model'),
            ),
          ],
        )
      ],
    );
  }
}
