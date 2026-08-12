import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:provider/provider.dart';

import '../../providers/patient_provider.dart';

class VitalHistoryCharts extends StatefulWidget {
  const VitalHistoryCharts({super.key});

  @override
  State<VitalHistoryCharts> createState() => _VitalHistoryChartsState();
}

class _VitalHistoryChartsState extends State<VitalHistoryCharts> {
  String _selectedMetric = 'heart_rate';

  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        if (provider.selectedPatient == null) {
          return const SizedBox.shrink();
        }

        return Container(
          padding: const EdgeInsets.all(16),
          margin: const EdgeInsets.only(top: 16),
          decoration: BoxDecoration(
            color: Theme.of(context).brightness == Brightness.dark
                ? const Color(0xFF1E1E1E)
                : Colors.white,
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
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Historical Trends & Prediction',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  DropdownButton<String>(
                    value: _selectedMetric,
                    items: const [
                      DropdownMenuItem(
                          value: 'heart_rate', child: Text('Heart Rate')),
                      DropdownMenuItem(
                          value: 'systolic', child: Text('Systolic BP')),
                      DropdownMenuItem(
                          value: 'diastolic', child: Text('Diastolic BP')),
                      DropdownMenuItem(value: 'spo2', child: Text('SpO2')),
                      DropdownMenuItem(
                          value: 'respiratory_rate',
                          child: Text('Resp Rate')),
                    ],
                    onChanged: (val) {
                      if (val != null) setState(() => _selectedMetric = val);
                    },
                  ),
                ],
              ),
              const SizedBox(height: 24),
              SizedBox(
                height: 250,
                child: FutureBuilder<List<Map<String, dynamic>>>(
                  future: provider.apiService
                      .getVitals(provider.selectedPatient!.id),
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    if (!snapshot.hasData || snapshot.data!.isEmpty) {
                      return const Center(child: Text('No history available'));
                    }

                    final data = snapshot.data!;
                    // Sort ascending by time for the chart
                    data.sort((a, b) => DateTime.parse(a['recorded_at'])
                        .compareTo(DateTime.parse(b['recorded_at'])));

                    final spots = <FlSpot>[];
                    double minX = 0;
                    double maxX = data.length.toDouble() + 2; // Extra space for prediction
                    double minY = double.infinity;
                    double maxY = double.negativeInfinity;

                    for (int i = 0; i < data.length; i++) {
                      final val = data[i][_selectedMetric];
                      if (val != null) {
                        final dVal = (val as num).toDouble();
                        spots.add(FlSpot(i.toDouble(), dVal));
                        if (dVal < minY) minY = dVal;
                        if (dVal > maxY) maxY = dVal;
                      }
                    }

                    if (spots.isEmpty) {
                      return const Center(
                          child: Text('No data for this metric'));
                    }

                    // Simple linear regression for prediction
                    final predictionSpots = <FlSpot>[];
                    if (spots.length >= 2) {
                      double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
                      int n = spots.length;
                      for (var s in spots) {
                        sumX += s.x;
                        sumY += s.y;
                        sumXY += s.x * s.y;
                        sumX2 += s.x * s.x;
                      }
                      double slope = (n * sumXY - sumX * sumY) /
                          (n * sumX2 - sumX * sumX);
                      double intercept = (sumY - slope * sumX) / n;

                      final lastX = spots.last.x;
                      predictionSpots.add(spots.last);
                      for (int i = 1; i <= 2; i++) {
                        final nextX = lastX + i;
                        final nextY = slope * nextX + intercept;
                        predictionSpots.add(FlSpot(nextX, nextY));
                        if (nextY < minY) minY = nextY;
                        if (nextY > maxY) maxY = nextY;
                      }
                    }

                    if (minY == double.infinity) minY = 0;
                    if (maxY == double.negativeInfinity) maxY = 100;
                    final padding = (maxY - minY) * 0.2;
                    if (padding == 0) {
                      minY -= 10;
                      maxY += 10;
                    } else {
                      minY -= padding;
                      maxY += padding;
                    }

                    return LineChart(
                      LineChartData(
                        minX: minX,
                        maxX: maxX,
                        minY: minY,
                        maxY: maxY,
                        lineBarsData: [
                          LineChartBarData(
                            spots: spots,
                            isCurved: true,
                            color: Theme.of(context).primaryColor,
                            barWidth: 3,
                            isStrokeCapRound: true,
                            dotData: const FlDotData(show: true),
                            belowBarData: BarAreaData(
                              show: true,
                              color: Theme.of(context)
                                  .primaryColor
                                  .withValues(alpha: 0.1),
                            ),
                          ),
                          if (predictionSpots.isNotEmpty)
                            LineChartBarData(
                              spots: predictionSpots,
                              isCurved: false,
                              color: Colors.orange,
                              barWidth: 3,
                              isStrokeCapRound: true,
                              dashArray: [5, 5],
                              dotData: const FlDotData(show: true),
                            ),
                        ],
                        titlesData: const FlTitlesData(
                          topTitles: AxisTitles(
                              sideTitles: SideTitles(showTitles: false)),
                          rightTitles: AxisTitles(
                              sideTitles: SideTitles(showTitles: false)),
                          bottomTitles: AxisTitles(
                              sideTitles: SideTitles(showTitles: false)),
                        ),
                        gridData: const FlGridData(show: true),
                        borderData: FlBorderData(show: false),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
