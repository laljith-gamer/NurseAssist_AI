import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/patient_provider.dart';
import 'pulse_animation.dart';

class VitalSignsDeltaChart extends StatelessWidget {
  const VitalSignsDeltaChart({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        final metrics = provider.currentMetrics;
        if (metrics == null || !metrics.hasData) {
          return const Center(child: Text('No vital sign data available'));
        }

        final deltas = metrics.deltas;
        final isDark = Theme.of(context).brightness == Brightness.dark;
        return Padding(
          padding: const EdgeInsets.only(bottom: 16.0),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(24),
            child: BackdropFilter(
              filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
              child: Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topLeft,
                    end: Alignment.bottomRight,
                    colors: isDark
                        ? [
                            Colors.white.withValues(alpha: 0.1),
                            Colors.white.withValues(alpha: 0.03),
                          ]
                        : [
                            Colors.white.withValues(alpha: 0.8),
                            Colors.white.withValues(alpha: 0.4),
                          ],
                  ),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(
                    color: isDark
                        ? Colors.white.withValues(alpha: 0.1)
                        : Colors.white.withValues(alpha: 0.5),
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.05),
                      blurRadius: 10,
                      offset: const Offset(0, 4),
                    ),
                  ],
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.monitor_heart,
                          color: isDark ? Colors.white : Colors.blue[800],
                          size: 24,
                        ),
                        const SizedBox(width: 12),
                        Text(
                          'Current Vitals',
                          style: TextStyle(
                            fontSize: 22,
                            fontWeight: FontWeight.w800,
                            letterSpacing: -0.5,
                            color: isDark ? Colors.white : Colors.black87,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    if (metrics.current['systolic'] != null &&
                        metrics.current['diastolic'] != null)
                      _buildVitalRow(
                        'Blood Pressure',
                        '${_format(metrics.current['systolic'])}/${_format(metrics.current['diastolic'])} mmHg',
                        deltas['bp_systolic']?.trend ?? 'stable',
                        isDark,
                      ),
                    if (metrics.current['heart_rate'] != null)
                      _buildVitalRow(
                        'Heart Rate',
                        '${_format(metrics.current['heart_rate'])} ${metrics.current['heart_rate_unit'] ?? 'bpm'}',
                        deltas['heart_rate']?.trend ?? 'stable',
                        isDark,
                      ),
                    if (metrics.current['temperature'] != null)
                      _buildVitalRow(
                        'Temperature',
                        '${_format(metrics.current['temperature'])} ${metrics.current['temperature_unit'] ?? '°C'}',
                        deltas['temperature']?.trend ?? 'stable',
                        isDark,
                      ),
                    if (metrics.current['spo2'] != null)
                      _buildVitalRow(
                        'SpO₂',
                        '${_format(metrics.current['spo2'])}${metrics.current['spo2_unit'] ?? '%'}',
                        deltas['spo2']?.trend ?? 'stable',
                        isDark,
                      ),
                    if (metrics.current['respiratory_rate'] != null)
                      _buildVitalRow(
                        'Respiratory Rate',
                        '${_format(metrics.current['respiratory_rate'])} ${metrics.current['respiratory_rate_unit'] ?? '/min'}',
                        deltas['respiratory_rate']?.trend ?? 'stable',
                        isDark,
                      ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildVitalRow(String name, String value, String trend, bool isDark) {
    final (trendIcon, trendColor) = switch (trend) {
      'increasing' || 'rapidly_increasing' => (Icons.arrow_upward, Colors.red),
      'decreasing' ||
      'rapidly_decreasing' => (Icons.arrow_downward, Colors.blue),
      _ => (Icons.arrow_forward, Colors.grey),
    };

    final isHeartRate = name == 'Heart Rate';
    final iconWidget = Icon(
      isHeartRate ? Icons.favorite : trendIcon,
      color: isHeartRate ? Colors.red : trendColor,
      size: 16,
    );

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Text(
              name,
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: isDark ? Colors.white70 : Colors.black54,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Row(
            children: [
              Text(
                value,
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 16,
                  color: isDark ? Colors.white : Colors.black87,
                ),
              ),
              const SizedBox(width: 8),
              if (isHeartRate)
                PulseAnimation(child: iconWidget)
              else
                iconWidget,
            ],
          ),
        ],
      ),
    );
  }

  String _format(dynamic value) {
    final number = value is num
        ? value.toDouble()
        : double.tryParse(value.toString());
    if (number == null) return value.toString();
    return number == number.roundToDouble()
        ? number.toStringAsFixed(0)
        : number.toStringAsFixed(1);
  }
}
