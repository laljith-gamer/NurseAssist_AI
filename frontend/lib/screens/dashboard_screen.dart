import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/patient_provider.dart';
import '../widgets/patient_sidebar.dart';
import '../widgets/chat_interface.dart';
import '../providers/settings_provider.dart';
import '../widgets/clinical_change_banner.dart';
import '../widgets/charts/vital_signs_delta_chart.dart';
import '../services/model_manager.dart';
import '../services/llm_service.dart';
import 'model_download_screen.dart';
import 'dart:ui';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  void initState() {
    super.initState();
    // Inject LLM service into PatientProvider after first frame
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final llmService = context.read<LlmService>();
      final patientProvider = context.read<PatientProvider>();
      patientProvider.setLlmService(llmService);
    });
  }

  void _showSettingsModal(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          title: const Text('Settings'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Consumer<SettingsProvider>(
                builder: (context, settingsRef, _) => SwitchListTile(
                  title: const Text('Dark Mode'),
                  value: settingsRef.isDarkMode,
                  onChanged: (val) {
                    settingsRef.toggleTheme();
                  },
                ),
              ),
              const SizedBox(height: 16),
              const Divider(),
              const SizedBox(height: 8),
              const Text(
                'AI Model Management (Offline)',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
              ),
              const SizedBox(height: 8),
              const ModelManagementWidget(),
              const SizedBox(height: 16),
              Consumer<LlmService>(
                builder: (context, llm, _) {
                  if (llm.isModelInstalled) {
                    return Text(
                      llm.isReady
                          ? 'Optional LLM: ready'
                          : llm.isInitializing
                          ? 'Optional LLM: starting in the background...'
                          : llm.statusMessage,
                      style: const TextStyle(fontSize: 12),
                    );
                  }
                  return Align(
                    alignment: Alignment.centerLeft,
                    child: OutlinedButton.icon(
                      onPressed: () {
                        Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) => const ModelDownloadScreen(),
                          ),
                        );
                      },
                      icon: const Icon(Icons.download),
                      label: const Text('Download optional LLM'),
                    ),
                  );
                },
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Close'),
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
              title: const Text(
                'NurseAssist AI',
                style: TextStyle(fontWeight: FontWeight.w600),
              ),
              backgroundColor: isDark ? Colors.black : Colors.blue[800],
              foregroundColor: Colors.white,
              actions: [
                IconButton(
                  icon: const Icon(Icons.settings),
                  onPressed: () => _showSettingsModal(context),
                ),
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
                          padding: const EdgeInsets.symmetric(
                            horizontal: 24,
                            vertical: 16,
                          ),
                          color: isDark
                              ? Colors.white.withValues(alpha: 0.05)
                              : Colors.white.withValues(alpha: 0.5),
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
                              ),
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
                    Tab(
                      text: 'Vitals',
                      icon: Icon(Icons.monitor_heart_outlined),
                    ),
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
                          Expanded(
                            child: SingleChildScrollView(
                              child: VitalSignsDeltaChart(),
                            ),
                          ),
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
            ...status.entries.map(
              (e) => Card(
                margin: const EdgeInsets.only(bottom: 8.0),
                child: ListTile(
                  title: Text(e.key.toUpperCase()),
                  subtitle: Text(e.value),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

class ModelManagementWidget extends StatelessWidget {
  const ModelManagementWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<ModelManager>(
      builder: (context, manager, _) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Current Version:'),
                Text(
                  manager.currentVersion,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Status:'),
                Expanded(
                  child: Text(
                    manager.status.name,
                    textAlign: TextAlign.right,
                    style: TextStyle(
                      color: manager.status == ModelStatus.error
                          ? Colors.red
                          : Colors.green,
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
                  onPressed: () => manager.checkForUpdates(),
                  child: const Text('Check GitHub for Update'),
                ),
              ],
            ),
            if (manager.status == ModelStatus.downloading)
              LinearProgressIndicator(
                value:
                    double.tryParse(
                          manager.downloadProgress.replaceAll('%', ''),
                        ) !=
                        null
                    ? double.parse(
                            manager.downloadProgress.replaceAll('%', ''),
                          ) /
                          100
                    : null,
              ),
          ],
        );
      },
    );
  }
}
