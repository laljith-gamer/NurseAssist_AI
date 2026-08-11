import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_gemma/flutter_gemma.dart';
import 'package:flutter_gemma_mediapipe/flutter_gemma_mediapipe.dart';

import 'providers/patient_provider.dart';
import 'providers/settings_provider.dart';
import 'screens/dashboard_screen.dart';
import 'services/model_manager.dart';
import 'services/local_nlp_service.dart';
import 'services/llm_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize Flutter Gemma with MediaPipe engine (.task files)
  await FlutterGemma.initialize(inferenceEngines: [MediaPipeEngine()]);

  final localNlpService = LocalNlpService();
  final llmService = LlmService();
  final modelManager = ModelManager(onModelUpdated: localNlpService.loadModels);
  await localNlpService.loadModels();

  // Check if LLM model is already installed
  final llmInstalled = await llmService.checkModelInstalled();
  if (llmInstalled) {
    // Initialize the LLM engine in background
    llmService.initializeEngine();
  }

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: modelManager),
        ChangeNotifierProvider.value(value: llmService),
        Provider.value(value: localNlpService),
        ChangeNotifierProvider(create: (_) => SettingsProvider()),
        ChangeNotifierProxyProvider2<
          SettingsProvider,
          ModelManager,
          PatientProvider
        >(
          create: (context) => PatientProvider(localNlpService),
          update: (context, settings, modelManager, patientProvider) {
            return patientProvider!;
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
            colorScheme: const ColorScheme.light(
              primary: Color(0xFF1E3A8A), // Deep Sapphire
              secondary: Color(0xFF3B82F6), // Vibrant Blue
              surface: Color(0xFFF8FAFC), // Soft Frost (formerly background)
              onPrimary: Colors.white,
              onSurface: Color(0xFF0F172A),
            ),
            useMaterial3: true,
            textTheme: GoogleFonts.outfitTextTheme(ThemeData.light().textTheme).apply(
              bodyColor: const Color(0xFF334155),
              displayColor: const Color(0xFF0F172A),
            ),
            scaffoldBackgroundColor: const Color(0xFFF8FAFC),
            cardTheme: CardThemeData(
              elevation: 4,
              shadowColor: Colors.black.withValues(alpha: 0.05),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              color: Colors.white,
            ),
            dialogTheme: DialogThemeData(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
              elevation: 8,
            ),
            elevatedButtonTheme: ElevatedButtonThemeData(
              style: ElevatedButton.styleFrom(
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                elevation: 0,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
            outlinedButtonTheme: OutlinedButtonThemeData(
              style: OutlinedButton.styleFrom(
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
            splashFactory: InkRipple.splashFactory, // Subtle ripple
          ),
          darkTheme: ThemeData(
            colorScheme: const ColorScheme.dark(
              primary: Color(0xFF06B6D4), // Vibrant Cyan
              secondary: Color(0xFF3B82F6), // Deep Blue
              surface: Color(0xFF0B0F19), // Deep Space (formerly background)
              onPrimary: Colors.black,
              onSurface: Color(0xFFF1F5F9),
            ),
            useMaterial3: true,
            textTheme: GoogleFonts.outfitTextTheme(ThemeData.dark().textTheme).apply(
              bodyColor: const Color(0xFFCBD5E1),
              displayColor: const Color(0xFFF8FAFC),
            ),
            scaffoldBackgroundColor: const Color(0xFF0B0F19),
            cardTheme: CardThemeData(
              elevation: 8,
              shadowColor: Colors.black.withValues(alpha: 0.3),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              color: const Color(0xFF1E293B).withValues(alpha: 0.8), // Translucent dark glass
            ),
            dialogTheme: DialogThemeData(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
              elevation: 12,
              backgroundColor: const Color(0xFF0F172A),
            ),
            elevatedButtonTheme: ElevatedButtonThemeData(
              style: ElevatedButton.styleFrom(
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                elevation: 0,
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
            outlinedButtonTheme: OutlinedButtonThemeData(
              style: OutlinedButton.styleFrom(
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
              ),
            ),
            splashFactory: InkRipple.splashFactory,
          ),
          // The LLM is an optional enhancement. Core recording, lookup, and
          // local NLP must be available immediately rather than hidden behind
          // a multi-gigabyte first-launch download.
          home: const DashboardScreen(),
        );
      },
    );
  }
}
