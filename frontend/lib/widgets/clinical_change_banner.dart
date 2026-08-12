import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../providers/patient_provider.dart';

class ClinicalChangeBanner extends StatelessWidget {
  const ClinicalChangeBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        final alerts = provider.currentMetrics?.alerts ?? [];
        if (alerts.isEmpty) return const SizedBox.shrink();
        
        final isDark = Theme.of(context).brightness == Brightness.dark;

        return Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 16),
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: isDark 
                ? const Color(0xFF7F1D1D).withValues(alpha: 0.2) // Dark mode red glass
                : const Color(0xFFFEF2F2).withValues(alpha: 0.9), // Light mode red glass
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: const Color(0xFFEF4444).withValues(alpha: 0.4),
              width: 1.5,
            ),
            boxShadow: [
              BoxShadow(
                color: const Color(0xFFEF4444).withValues(alpha: 0.15),
                blurRadius: 16,
                spreadRadius: 2,
              ),
            ],
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: const Color(0xFFEF4444).withValues(alpha: 0.15),
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.warning_amber_rounded, color: Color(0xFFEF4444)),
              )
              .animate(onPlay: (controller) => controller.repeat(reverse: true))
              .scaleXY(begin: 1.0, end: 1.15, duration: 800.ms, curve: Curves.easeInOut),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: alerts.map((alert) => Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Text(
                      alert,
                      style: TextStyle(
                        color: isDark ? const Color(0xFFFCA5A5) : const Color(0xFF991B1B),
                        fontWeight: FontWeight.w700,
                        letterSpacing: 0.3,
                        fontSize: 14,
                      ),
                    ),
                  )).toList(),
                ),
              ),
            ],
          ),
        )
        .animate()
        .slideY(begin: -0.2, end: 0, duration: 400.ms, curve: Curves.easeOutCubic)
        .fadeIn(duration: 400.ms);
      },
    );
  }
}

