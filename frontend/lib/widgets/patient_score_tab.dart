import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../providers/patient_provider.dart';

class PatientScoreTab extends StatelessWidget {
  const PatientScoreTab({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        final status = provider.currentMetrics?.clinicalStatus;
        if (status == null || status.isEmpty) {
          return const Center(child: Text("No scoring data available."));
        }

        final isDark = Theme.of(context).brightness == Brightness.dark;
        
        // Extract a primary score if available, otherwise just use a generic representation.
        // E.g., if there's a NEWS or Early Warning Score.
        String primaryScoreKey = status.keys.firstWhere(
          (k) => k.toLowerCase().contains('score'),
          orElse: () => status.keys.first,
        );
        String primaryScoreValue = status[primaryScoreKey]!;

        // Remove primary from list
        final secondaryScores = Map<String, String>.from(status)..remove(primaryScoreKey);

        return SingleChildScrollView(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                "Clinical Assessment",
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.5,
                  color: isDark ? Colors.white : const Color(0xFF0F172A),
                ),
              ).animate().fadeIn(duration: 400.ms).slideX(begin: -0.1),
              const SizedBox(height: 24),
              
              // Primary Score Card
              _PrimaryScoreCard(
                title: primaryScoreKey,
                value: primaryScoreValue,
                isDark: isDark,
              ).animate(delay: 100.ms).fadeIn(duration: 500.ms).scale(begin: const Offset(0.95, 0.95)),
              
              const SizedBox(height: 32),
              
              if (secondaryScores.isNotEmpty)
                Text(
                  "Detailed Indicators",
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: isDark ? Colors.white70 : Colors.black87,
                  ),
                ).animate(delay: 200.ms).fadeIn(duration: 400.ms),
                
              const SizedBox(height: 16),
              
              // Secondary Scores Grid/List
              ...secondaryScores.entries.map((e) {
                final index = secondaryScores.keys.toList().indexOf(e.key);
                return _SecondaryScoreCard(
                  title: e.key,
                  value: e.value,
                  isDark: isDark,
                ).animate(delay: Duration(milliseconds: 300 + (100 * index)))
                 .fadeIn(duration: 400.ms)
                 .slideY(begin: 0.1);
              }),
            ],
          ),
        );
      },
    );
  }
}

class _PrimaryScoreCard extends StatelessWidget {
  final String title;
  final String value;
  final bool isDark;

  const _PrimaryScoreCard({
    required this.title,
    required this.value,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    // Determine color based on value string if possible (e.g., 'high', 'critical', 'low')
    final lowerValue = value.toLowerCase();
    Color primaryColor = Colors.blueAccent;
    IconData icon = Icons.health_and_safety;
    
    if (lowerValue.contains('high') || lowerValue.contains('critical') || lowerValue.contains('severe')) {
      primaryColor = Colors.redAccent;
      icon = Icons.warning_amber_rounded;
    } else if (lowerValue.contains('medium') || lowerValue.contains('elevated')) {
      primaryColor = Colors.orangeAccent;
      icon = Icons.info_outline;
    } else if (lowerValue.contains('low') || lowerValue.contains('stable') || lowerValue.contains('normal')) {
      primaryColor = Colors.green;
      icon = Icons.check_circle_outline;
    }

    return ClipRRect(
      borderRadius: BorderRadius.circular(28),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.all(32),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                primaryColor.withValues(alpha: isDark ? 0.2 : 0.1),
                primaryColor.withValues(alpha: isDark ? 0.05 : 0.02),
              ],
            ),
            borderRadius: BorderRadius.circular(28),
            border: Border.all(
              color: primaryColor.withValues(alpha: 0.3),
              width: 1.5,
            ),
            boxShadow: [
              BoxShadow(
                color: primaryColor.withValues(alpha: 0.1),
                blurRadius: 20,
                spreadRadius: 2,
              ),
            ],
          ),
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: primaryColor.withValues(alpha: 0.2),
                  shape: BoxShape.circle,
                ),
                child: Icon(icon, size: 48, color: primaryColor)
                    .animate(onPlay: (controller) => controller.repeat())
                    .shimmer(duration: 2.seconds, color: Colors.white54),
              ),
              const SizedBox(height: 24),
              Text(
                _formatTitle(title),
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: isDark ? Colors.white70 : Colors.black54,
                  letterSpacing: 1.2,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                value,
                style: TextStyle(
                  fontSize: 36,
                  fontWeight: FontWeight.w900,
                  color: isDark ? Colors.white : Colors.black87,
                  height: 1.1,
                ),
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatTitle(String raw) {
    return raw.replaceAll('_', ' ').toUpperCase();
  }
}

class _SecondaryScoreCard extends StatelessWidget {
  final String title;
  final String value;
  final bool isDark;

  const _SecondaryScoreCard({
    required this.title,
    required this.value,
    required this.isDark,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B).withValues(alpha: 0.5) : Colors.white.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.05),
        ),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF0F172A) : const Color(0xFFF1F5F9),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Icon(
              Icons.analytics_outlined,
              color: isDark ? Colors.white54 : Colors.black54,
              size: 24,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _formatTitle(title),
                  style: TextStyle(
                    fontSize: 14,
                    color: isDark ? Colors.white54 : Colors.black54,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  value,
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.bold,
                    color: isDark ? Colors.white : Colors.black87,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _formatTitle(String raw) {
    return raw.replaceAll('_', ' ').split(' ').map((word) {
      if (word.isEmpty) return '';
      return word[0].toUpperCase() + word.substring(1).toLowerCase();
    }).join(' ');
  }
}
