import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import '../services/llm_service.dart';
import 'dashboard_screen.dart';

/// Optional screen for downloading the on-device conversational model.
class ModelDownloadScreen extends StatefulWidget {
  const ModelDownloadScreen({super.key});

  @override
  State<ModelDownloadScreen> createState() => _ModelDownloadScreenState();
}

class _ModelDownloadScreenState extends State<ModelDownloadScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _pulseAnimation = Tween<double>(begin: 0.8, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  void _navigateToDashboard() {
    final navigator = Navigator.of(context);
    if (navigator.canPop()) {
      // This screen is opened from Settings, which is a dialog route. Return
      // to the actual dashboard rather than leaving that dialog on top and
      // making the app look blocked after the nurse chooses to continue.
      navigator.popUntil((route) => route.isFirst);
      return;
    }
    navigator.pushReplacement(
      MaterialPageRoute(builder: (_) => const DashboardScreen()),
    );
  }

  Future<void> _startDownload() async {
    final llmService = context.read<LlmService>();
    final success = await llmService.downloadModel();
    if (success && mounted) {
      // The service schedules engine startup itself, so this route can always
      // return control to the nurse as soon as the file is installed.
      _navigateToDashboard();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0A0E21),
      body: Consumer<LlmService>(
        builder: (context, llm, _) {
          return SafeArea(
            child: Center(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 32),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    // Animated AI Icon
                    AnimatedBuilder(
                      animation: _pulseController,
                      builder: (context, child) {
                        return Transform.scale(
                          scale: _pulseAnimation.value,
                          child: Container(
                            width: 120,
                            height: 120,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              gradient: const LinearGradient(
                                colors: [Color(0xFF1565C0), Color(0xFF42A5F5)],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              ),
                              boxShadow: [
                                BoxShadow(
                                  color: const Color(
                                    0xFF1565C0,
                                  ).withValues(alpha: 0.4),
                                  blurRadius: 30,
                                  spreadRadius: 5,
                                ),
                              ],
                            ),
                            child: const Icon(
                              Icons.psychology,
                              size: 60,
                              color: Colors.white,
                            ),
                          ),
                        );
                      },
                    ),

                    const SizedBox(height: 40),

                    // Title
                    Text(
                      'NurseAssist AI',
                      style: GoogleFonts.outfit(
                        fontSize: 32,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                    ),

                    const SizedBox(height: 12),

                    // Subtitle
                    Text(
                      'On-Device Intelligence',
                      style: GoogleFonts.outfit(
                        fontSize: 16,
                        color: Colors.white60,
                        letterSpacing: 2,
                      ),
                    ),

                    const SizedBox(height: 40),

                    // Description card
                    Container(
                      padding: const EdgeInsets.all(24),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.05),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: Colors.white.withValues(alpha: 0.1),
                        ),
                      ),
                      child: Column(
                        children: [
                          _infoRow(
                            Icons.download_rounded,
                            'Large optional download (2.7 GB)',
                          ),
                          const SizedBox(height: 12),
                          _infoRow(
                            Icons.wifi_off_rounded,
                            'Works 100% offline after download',
                          ),
                          const SizedBox(height: 12),
                          _infoRow(
                            Icons.lock_rounded,
                            'All data stays on your device',
                          ),
                          const SizedBox(height: 12),
                          _infoRow(
                            Icons.auto_awesome,
                            'Powered by Google Gemma 2',
                          ),
                        ],
                      ),
                    ),

                    const SizedBox(height: 32),

                    // Download progress or button
                    if (llm.isDownloading) ...[
                      // Progress bar
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: LinearProgressIndicator(
                          value: llm.downloadProgress,
                          minHeight: 8,
                          backgroundColor: Colors.white12,
                          valueColor: const AlwaysStoppedAnimation<Color>(
                            Color(0xFF42A5F5),
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Text(
                        llm.statusMessage,
                        style: GoogleFonts.outfit(
                          fontSize: 14,
                          color: Colors.white70,
                        ),
                      ),
                      const SizedBox(height: 20),
                      OutlinedButton.icon(
                        onPressed: _navigateToDashboard,
                        icon: const Icon(Icons.arrow_back),
                        label: const Text('Use app while download continues'),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'The download continues while NurseAssist stays open.',
                        style: GoogleFonts.outfit(
                          fontSize: 12,
                          color: Colors.white54,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ] else if (llm.errorMessage != null) ...[
                      // Error state
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.red.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          llm.errorMessage!,
                          style: GoogleFonts.outfit(
                            fontSize: 13,
                            color: Colors.redAccent,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                      const SizedBox(height: 16),
                      _downloadButton(),
                    ] else ...[
                      // Initial state - show download button
                      _downloadButton(),
                    ],

                    const SizedBox(height: 16),

                    // This is also available during download so the model
                    // screen can never trap the nurse in a loading state.
                    if (!llm.isDownloading)
                      TextButton(
                        onPressed: _navigateToDashboard,
                        child: Text(
                          'Continue without the optional LLM',
                          style: GoogleFonts.outfit(
                            fontSize: 14,
                            color: Colors.white38,
                            decoration: TextDecoration.underline,
                            decorationColor: Colors.white38,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _downloadButton() {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: ElevatedButton(
        onPressed: _startDownload,
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF1565C0),
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          elevation: 8,
          shadowColor: const Color(0xFF1565C0).withValues(alpha: 0.5),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.download_rounded, size: 24),
            const SizedBox(width: 12),
            Text(
              'Download AI Model',
              style: GoogleFonts.outfit(
                fontSize: 18,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _infoRow(IconData icon, String text) {
    return Row(
      children: [
        Icon(icon, size: 20, color: const Color(0xFF42A5F5)),
        const SizedBox(width: 12),
        Expanded(
          child: Text(
            text,
            style: GoogleFonts.outfit(fontSize: 14, color: Colors.white70),
          ),
        ),
      ],
    );
  }
}
