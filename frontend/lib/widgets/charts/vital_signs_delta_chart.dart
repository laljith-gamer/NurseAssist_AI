import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/patient_provider.dart';

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
        return Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF1E1E1E) : Colors.white,
            borderRadius: BorderRadius.circular(12),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.05),
                blurRadius: 10,
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Current Vitals & Delta',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 16),
              if (metrics.current['systolic'] != null &&
                  metrics.current['diastolic'] != null)
                _buildVitalRow(
                  'Blood Pressure',
                  '${_format(metrics.current['systolic'])}/${_format(metrics.current['diastolic'])} mmHg',
                  deltas['bp_systolic']?.trend ?? 'stable',
                ),
              if (metrics.current['heart_rate'] != null)
                _buildVitalRow(
                  'Heart Rate',
                  '${_format(metrics.current['heart_rate'])} ${metrics.current['heart_rate_unit'] ?? 'bpm'}',
                  deltas['heart_rate']?.trend ?? 'stable',
                ),
              if (metrics.current['temperature'] != null)
                _buildVitalRow(
                  'Temperature',
                  '${_format(metrics.current['temperature'])} ${metrics.current['temperature_unit'] ?? '°C'}',
                  deltas['temperature']?.trend ?? 'stable',
                ),
              if (metrics.current['spo2'] != null)
                _buildVitalRow(
                  'SpO₂',
                  '${_format(metrics.current['spo2'])}${metrics.current['spo2_unit'] ?? '%'}',
                  deltas['spo2']?.trend ?? 'stable',
                ),
              if (metrics.current['respiratory_rate'] != null)
                _buildVitalRow(
                  'Respiratory Rate',
                  '${_format(metrics.current['respiratory_rate'])} ${metrics.current['respiratory_rate_unit'] ?? '/min'}',
                  deltas['respiratory_rate']?.trend ?? 'stable',
                ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildVitalRow(String name, String value, String trend) {
    final (trendIcon, trendColor) = switch (trend) {
      'increasing' || 'rapidly_increasing' => (Icons.arrow_upward, Colors.red),
      'decreasing' ||
      'rapidly_decreasing' => (Icons.arrow_downward, Colors.blue),
      _ => (Icons.arrow_forward, Colors.grey),
    };

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Text(
              name,
              style: const TextStyle(fontWeight: FontWeight.w500),
              overflow: TextOverflow.ellipsis,
            ),
          ),
          Row(
            children: [
              Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(width: 8),
              Icon(trendIcon, color: trendColor, size: 16),
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
