import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_gemma/flutter_gemma.dart';
import 'package:flutter_gemma_litertlm/flutter_gemma_litertlm.dart';
import 'providers/patient_provider.dart';
import 'providers/settings_provider.dart';
import 'screens/dashboard_screen.dart';
import 'screens/model_download_screen.dart';
import 'services/model_manager.dart';
import 'services/local_nlp_service.dart';
import 'services/llm_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // Initialize Flutter Gemma with LiteRT-LM engine (supports all platforms)
  await FlutterGemma.initialize(
    inferenceEngines: [LiteRtLmEngine()],
  );

  final localNlpService = LocalNlpService();
  final llmService = LlmService();
  final modelManager = ModelManager(onModelUpdated: () => localNlpService.loadModels());
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
        ChangeNotifierProxyProvider2<SettingsProvider, ModelManager, PatientProvider>(
          create: (context) => PatientProvider(localNlpService),
          update: (context, settings, modelManager, patientProvider) {
            return patientProvider!;
          },
        ),
      ],
      child: NurseAssistApp(showDownloadScreen: !llmInstalled),
    ),
  );
}

class NurseAssistApp extends StatelessWidget {
  final bool showDownloadScreen;

  const NurseAssistApp({super.key, required this.showDownloadScreen});

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
          home: showDownloadScreen
              ? const ModelDownloadScreen()
              : const DashboardScreen(),
        );
      },
    );
  }
}
