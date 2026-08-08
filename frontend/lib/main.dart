import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import 'providers/patient_provider.dart';
import 'providers/settings_provider.dart';
import 'screens/dashboard_screen.dart';

void main() {
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => SettingsProvider()),
        ChangeNotifierProxyProvider<SettingsProvider, PatientProvider>(
          create: (context) => PatientProvider(),
          update: (context, settings, patientProvider) {
            patientProvider!.apiService.updateUrls(
              settings.httpUrl, 
              settings.wsUrl
            );
            return patientProvider;
          },
        ),
      ],
      child: const NurseAssistApp(),
    ),
  );
}

class NurseAssistApp extends StatelessWidget {
  const NurseAssistApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<SettingsProvider>(
      builder: (context, settings, child) {
        return MaterialApp(
          title: 'NurseAssist AI',
          debugShowCheckedModeBanner: false,
          themeMode: settings.isDarkMode ? ThemeMode.dark : ThemeMode.light,
          theme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xFF0D47A1), // Premium deep blue
              brightness: Brightness.light,
            ),
            useMaterial3: true,
            textTheme: GoogleFonts.outfitTextTheme(ThemeData.light().textTheme),
            scaffoldBackgroundColor: const Color(0xFFF5F7FA), // Light sleek background
          ),
          darkTheme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
              seedColor: const Color(0xFF1565C0), // Dark mode accent
              brightness: Brightness.dark,
            ),
            useMaterial3: true,
            textTheme: GoogleFonts.outfitTextTheme(ThemeData.dark().textTheme),
            scaffoldBackgroundColor: const Color(0xFF121212), // True dark
          ),
          home: const DashboardScreen(),
        );
      },
    );
  }
}
