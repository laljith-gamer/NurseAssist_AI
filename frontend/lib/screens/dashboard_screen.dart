import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/patient_provider.dart';
import '../widgets/patient_sidebar.dart';
import '../widgets/chat_interface.dart';
import '../providers/settings_provider.dart';
import '../widgets/clinical_change_banner.dart';
import '../widgets/charts/vital_history_charts.dart';
import '../widgets/patient_score_tab.dart';
import '../services/model_manager.dart';
import '../services/llm_service.dart';
import '../services/api_service.dart';
import 'dart:ui';
import 'package:flutter_animate/flutter_animate.dart';

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
          title: const Text('Settings', style: TextStyle(fontWeight: FontWeight.bold)),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          contentPadding: const EdgeInsets.fromLTRB(24, 20, 24, 8),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Consumer<SettingsProvider>(
                  builder: (context, settingsRef, _) => SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Dark Mode', style: TextStyle(fontWeight: FontWeight.w600)),
                    value: settingsRef.isDarkMode,
                    onChanged: (val) {
                      settingsRef.toggleTheme();
                    },
                  ),
                ),
                const SizedBox(height: 8),
                const Divider(),
                const SizedBox(height: 16),
                const Text(
                  'AI Model Management (Offline)',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                const SizedBox(height: 12),
                const ModelManagementWidget(),
                const SizedBox(height: 12),
                Consumer<LlmService>(
                  builder: (context, llm, _) {
                    final String llmStatus;
                    final Color statusColor;
                    if (llm.isReady) {
                      llmStatus = 'Gemma 3 1B: ready';
                      statusColor = Colors.green;
                    } else if (llm.isInitializing) {
                      llmStatus = 'Gemma 3 1B: ${llm.statusMessage}';
                      statusColor = Colors.orange;
                    } else if (llm.errorMessage != null) {
                      llmStatus = 'Gemma 3 1B: ${llm.errorMessage}';
                      statusColor = Colors.red;
                    } else {
                      llmStatus = llm.statusMessage;
                      statusColor = Colors.grey;
                    }
                    return Text(
                      llmStatus,
                      style: TextStyle(fontSize: 13, color: statusColor, fontWeight: FontWeight.w500),
                    );
                  },
                ),
                const SizedBox(height: 16),
                const Divider(),
                const SizedBox(height: 16),
                const Text(
                  'Suggestion Telemetry',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                const SizedBox(height: 12),
                Consumer<SettingsProvider>(
                  builder: (context, settingsRef, _) => Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      SwitchListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Share suggestion feedback', style: TextStyle(fontSize: 15)),
                        subtitle: const Text(
                          'Help improve observation suggestions by sharing de-identified label feedback.',
                          style: TextStyle(fontSize: 13),
                        ),
                        value: settingsRef.telemetrySharingEnabled,
                        onChanged: (val) {
                          settingsRef.setTelemetrySharingEnabled(val);
                        },
                      ),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            'Queued events: ${settingsRef.queuedTelemetryCount}',
                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                          ),
                          TextButton.icon(
                            onPressed: settingsRef.queuedTelemetryCount == 0
                                ? null
                                : () {
                                    settingsRef.updateQueuedTelemetryCount(0);
                                  },
                            icon: const Icon(Icons.delete_outline, size: 16),
                            label: const Text('Clear queued', style: TextStyle(fontSize: 13)),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                const Divider(),
                const SizedBox(height: 16),
                const Text(
                  'Data Management',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () async {
                          final api = context.read<ApiService>();
                          final success = await api.backupDatabase();
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text(success ? 'Database backed up locally.' : 'Backup failed.')),
                            );
                          }
                        },
                        icon: const Icon(Icons.backup_outlined, size: 18),
                        label: const Text('Backup'),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () async {
                          final api = context.read<ApiService>();
                          final success = await api.restoreDatabase();
                          if (context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(content: Text(success ? 'Database restored. Please restart the app.' : 'Restore failed.')),
                            );
                          }
                        },
                        icon: const Icon(Icons.restore, size: 18),
                        label: const Text('Restore'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Close', style: TextStyle(fontWeight: FontWeight.bold)),
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
                  stops: const [0.0, 0.3, 0.7, 1.0],
                  colors: isDark
                      ? [
                          const Color(0xFF0F172A), // Dark slate
                          const Color(0xFF1E293B), // Slightly lighter
                          const Color(0xFF0B1221), // Deep space
                          const Color(0xFF06B6D4).withValues(alpha: 0.1), // Hint of cyan at bottom right
                        ]
                      : [
                          const Color(0xFFF8FAFC),
                          const Color(0xFFF1F5F9),
                          const Color(0xFFE2E8F0),
                          const Color(0xFF3B82F6).withValues(alpha: 0.05), // Hint of blue
                        ],
                ),
              ),
              child: Column(
                children: [
                  if (isDesktop)
                    ClipRRect(
                      child: BackdropFilter(
                        filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30), // Increased blur for premium glass feel
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 32,
                            vertical: 20,
                          ),
                          decoration: BoxDecoration(
                            color: isDark
                                ? const Color(0xFF0F172A).withValues(alpha: 0.5) // More transparent for more glass effect
                                : Colors.white.withValues(alpha: 0.6),
                            border: Border(
                              bottom: BorderSide(
                                color: isDark
                                    ? Colors.white.withValues(alpha: 0.05)
                                    : Colors.black.withValues(alpha: 0.05),
                              ),
                            ),
                          ),
                          width: double.infinity,
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                "NurseAssist AI Dashboard",
                                style: TextStyle(
                                  fontSize: 28,
                                  fontWeight: FontWeight.w800,
                                  letterSpacing: -0.5,
                                  color: isDark ? Colors.white : const Color(0xFF0F172A),
                                ),
                              ),
                              IconButton(
                                icon: const Icon(Icons.settings_outlined),
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
                ).animate().fadeIn(duration: 400.ms).slideX(begin: -0.05, end: 0, duration: 400.ms, curve: Curves.easeOut),
              ),
              const SizedBox(width: 16),
              Expanded(
                flex: 1,
                child: Column(
                  children: const [
                    Expanded(child: VitalHistoryCharts()),
                  ],
                ).animate().fadeIn(duration: 400.ms, delay: 100.ms).slideX(begin: 0.05, end: 0, duration: 400.ms, curve: Curves.easeOut),
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
                      const ChatInterface().animate().fadeIn(duration: 300.ms),
                      Column(
                        children: const [
                          ClinicalChangeBanner(),
                          SizedBox(height: 8),
                          Expanded(
                            child: VitalHistoryCharts(),
                          ),
                        ],
                      ).animate().fadeIn(duration: 300.ms),
                      const PatientScoreTab().animate().fadeIn(duration: 300.ms),
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
                if (manager.status == ModelStatus.updateAvailable)
                  ElevatedButton(
                    onPressed: () => manager.downloadUpdate(),
                    child: const Text('Download Update Now'),
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
