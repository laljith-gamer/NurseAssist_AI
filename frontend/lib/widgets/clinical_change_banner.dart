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

        return Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 16),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.red[50],
            border: Border.all(color: Colors.red[300]!),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.warning_amber_rounded, color: Colors.red),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: alerts.map((alert) => Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      alert,
                      style: const TextStyle(
                        color: Colors.red,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  )).toList(),
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
