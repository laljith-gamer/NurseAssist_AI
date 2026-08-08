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
          return const Center(child: Text("No vital sign data available"));
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
              )
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                "Current Vitals & Delta",
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 16),
              _buildVitalRow("Blood Pressure", "${metrics.current['systolic']}/${metrics.current['diastolic']} mmHg", deltas['bp_systolic']?.trend ?? 'stable'),
              _buildVitalRow("Heart Rate", "${metrics.current['heart_rate']} bpm", deltas['heart_rate']?.trend ?? 'stable'),
              _buildVitalRow("Temperature", "${metrics.current['temperature']} °F", deltas['temperature']?.trend ?? 'stable'),
              _buildVitalRow("SpO2", "${metrics.current['spo2']} %", deltas['spo2']?.trend ?? 'stable'),
            ],
          ),
        );
      },
    );
  }

  Widget _buildVitalRow(String name, String value, String trend) {
    IconData trendIcon;
    Color trendColor;
    
    switch (trend) {
      case 'increasing':
      case 'rapidly_increasing':
        trendIcon = Icons.arrow_upward;
        trendColor = Colors.red;
        break;
      case 'decreasing':
      case 'rapidly_decreasing':
        trendIcon = Icons.arrow_downward;
        trendColor = Colors.blue;
        break;
      default:
        trendIcon = Icons.arrow_forward;
        trendColor = Colors.grey;
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(child: Text(name, style: const TextStyle(fontWeight: FontWeight.w500), overflow: TextOverflow.ellipsis)),
          Row(
            children: [
              Text(value, style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(width: 8),
              Icon(trendIcon, color: trendColor, size: 16),
            ],
          )
        ],
      ),
    );
  }
}
