import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/patient_provider.dart';

class ClinicalChangeBanner extends StatelessWidget {
  const ClinicalChangeBanner({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        final alerts = provider.currentMetrics?.alerts ?? [];
        if (alerts.isEmpty) return const SizedBox.shrink();

        return TweenAnimationBuilder<double>(
          tween: Tween(begin: 0.0, end: 1.0),
          duration: const Duration(milliseconds: 1500),
          curve: Curves.easeInOutSine,
          builder: (context, value, child) {
            // Create a continuous pulse effect by bouncing between 0 and 1
            final pulse = sin(value * 3.14159).abs();
            
            return Container(
              width: double.infinity,
              margin: const EdgeInsets.only(bottom: 16),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFFFEF2F2), Color(0xFFFEE2E2)], // Subtle red glass
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: const Color(0xFFEF4444).withValues(alpha: 0.3 + (pulse * 0.4)),
                  width: 1.5,
                ),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFFEF4444).withValues(alpha: 0.1 + (pulse * 0.15)),
                    blurRadius: 12 + (pulse * 8),
                    spreadRadius: pulse * 2,
                  ),
                ],
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEF4444).withValues(alpha: 0.1),
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.warning_amber_rounded, color: Color(0xFFDC2626)),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: alerts.map((alert) => Padding(
                        padding: const EdgeInsets.only(bottom: 6),
                        child: Text(
                          alert,
                          style: const TextStyle(
                            color: Color(0xFF991B1B), // Deep crimson
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
            );
          },
          onEnd: () {
            // Optional: trigger rebuilds if we want an infinite loop, 
            // but a single pulse on appearance is often enough for a premium feel.
          },
        );
      },
    );
  }
}
