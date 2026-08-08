import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/patient_provider.dart';
import '../widgets/patient_sidebar.dart';
import '../widgets/chat_interface.dart';
import '../providers/settings_provider.dart';
import '../widgets/clinical_change_banner.dart';
import '../widgets/charts/vital_signs_delta_chart.dart';
import 'dart:ui';

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
              ),
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
                // Force a reconnect or reload if necessary
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
          // Stacked view for mobile
          return Column(
            children: const [
              ClinicalChangeBanner(),
              VitalSignsDeltaChart(),
              SizedBox(height: 16),
              Expanded(child: ChatInterface()),
            ],
          );
        }
      },
    );
  }
}
