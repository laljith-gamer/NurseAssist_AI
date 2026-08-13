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

        final data = provider.vitalHistory;
        final isDark = Theme.of(context).brightness == Brightness.dark;

        return Container(
          padding: const EdgeInsets.all(20),
          margin: const EdgeInsets.only(top: 16),
          decoration: BoxDecoration(
            color: isDark ? const Color(0xFF1E1E1E) : Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isDark ? Colors.white10 : Colors.black12,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(isDark ? 0.2 : 0.05),
                blurRadius: 15,
                offset: const Offset(0, 5),
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
                    'Historical Trends',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12),
                    decoration: BoxDecoration(
                      color: isDark ? Colors.white10 : Colors.black.withOpacity(0.03),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: DropdownButtonHideUnderline(
                      child: DropdownButton<String>(
                        value: _selectedMetric,
                        icon: const Icon(Icons.keyboard_arrow_down, size: 20),
                        isDense: true,
                        style: TextStyle(
                          fontSize: 14,
                          color: isDark ? Colors.white : Colors.black87,
                          fontWeight: FontWeight.w500,
                        ),
                        items: const [
                          DropdownMenuItem(value: 'heart_rate', child: Text('Heart Rate')),
                          DropdownMenuItem(value: 'systolic', child: Text('Systolic BP')),
                          DropdownMenuItem(value: 'diastolic', child: Text('Diastolic BP')),
                          DropdownMenuItem(value: 'spo2', child: Text('SpO2')),
                          DropdownMenuItem(value: 'respiratory_rate', child: Text('Resp Rate')),
                          DropdownMenuItem(value: 'weight', child: Text('Weight')),
                        ],
                        onChanged: (val) {
                          if (val != null) setState(() => _selectedMetric = val);
                        },
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 30),
              SizedBox(
                height: 250,
                child: _buildChart(data, context, isDark),
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildChart(List<Map<String, dynamic>> rawData, BuildContext context, bool isDark) {
    if (rawData.isEmpty) {
      return Center(
        child: Text(
          'No history available',
          style: TextStyle(color: isDark ? Colors.white54 : Colors.black54),
        ),
      );
    }

    final spots = <FlSpot>[];
    double minX = 0;
    double minY = double.infinity;
    double maxY = double.negativeInfinity;

    int spotIndex = 0;
    for (int i = 0; i < rawData.length; i++) {
      final val = rawData[i][_selectedMetric];
      if (val != null) {
        final dVal = (val as num).toDouble();
        if (dVal.isFinite && !dVal.isNaN) {
          spots.add(FlSpot(spotIndex.toDouble(), dVal));
          if (dVal < minY) minY = dVal;
          if (dVal > maxY) maxY = dVal;
          spotIndex++;
        }
      }
    }

    if (spots.isEmpty) {
      return Center(
        child: Text(
          'No data for this metric',
          style: TextStyle(color: isDark ? Colors.white54 : Colors.black54),
        ),
      );
    }

    final maxX = spots.length.toDouble() - 1 + 2; // +2 for trendline prediction

    // Linear regression for prediction
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
      
      final denominator = (n * sumX2 - sumX * sumX);
      if (denominator != 0) {
        double slope = (n * sumXY - sumX * sumY) / denominator;
        double intercept = (sumY - slope * sumX) / n;

        final lastX = spots.last.x;
        predictionSpots.add(spots.last);
        for (int i = 1; i <= 2; i++) {
          final nextX = lastX + i;
          final nextY = slope * nextX + intercept;
          if (nextY.isFinite && !nextY.isNaN) {
            predictionSpots.add(FlSpot(nextX, nextY));
            if (nextY < minY) minY = nextY;
            if (nextY > maxY) maxY = nextY;
          }
        }
      }
    }

    // Safety checks for min/max to prevent fl_chart crashes
    if (minY == double.infinity || maxY == double.negativeInfinity || minY.isNaN || maxY.isNaN) {
      minY = 0;
      maxY = 100;
    }
    
    if (minY == maxY) {
      minY -= 10;
      maxY += 10;
    } else {
      final padding = (maxY - minY) * 0.2;
      minY -= padding;
      maxY += padding;
    }

    final primaryColor = Theme.of(context).primaryColor;

    return LineChart(
      LineChartData(
        minX: minX,
        maxX: maxX,
        minY: minY,
        maxY: maxY,
        lineTouchData: LineTouchData(
          handleBuiltInTouches: true,
          touchTooltipData: LineTouchTooltipData(
            tooltipPadding: const EdgeInsets.all(8),
            tooltipMargin: 16,
            getTooltipColor: (touchedSpot) => isDark ? Colors.white : Colors.black87,
            getTooltipItems: (touchedSpots) {
              return touchedSpots.map((LineBarSpot touchedSpot) {
                final textStyle = TextStyle(
                  color: isDark ? Colors.black : Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                );
                return LineTooltipItem(
                  touchedSpot.y.toStringAsFixed(1),
                  textStyle,
                );
              }).toList();
            },
          ),
        ),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            curveSmoothness: 0.35,
            color: primaryColor,
            barWidth: 4,
            isStrokeCapRound: true,
            dotData: FlDotData(
              show: true,
              getDotPainter: (spot, percent, barData, index) {
                return FlDotCirclePainter(
                  radius: 4,
                  color: primaryColor,
                  strokeWidth: 2,
                  strokeColor: isDark ? const Color(0xFF1E1E1E) : Colors.white,
                );
              },
            ),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                colors: [
                  primaryColor.withOpacity(0.4),
                  primaryColor.withOpacity(0.0),
                ],
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
              ),
            ),
          ),
          if (predictionSpots.isNotEmpty)
            LineChartBarData(
              spots: predictionSpots,
              isCurved: false,
              color: Colors.orangeAccent,
              barWidth: 3,
              isStrokeCapRound: true,
              dashArray: [8, 4],
              dotData: FlDotData(
                show: true,
                getDotPainter: (spot, percent, barData, index) {
                  return FlDotCirclePainter(
                    radius: 3,
                    color: Colors.orangeAccent,
                    strokeWidth: 1.5,
                    strokeColor: isDark ? const Color(0xFF1E1E1E) : Colors.white,
                  );
                },
              ),
            ),
        ],
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          bottomTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 40,
              getTitlesWidget: (value, meta) {
                return Text(
                  value.toInt().toString(),
                  style: TextStyle(
                    color: isDark ? Colors.white54 : Colors.black54,
                    fontSize: 12,
                  ),
                  textAlign: TextAlign.right,
                );
              },
            ),
          ),
        ),
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: ((maxY - minY) / 5).clamp(1.0, double.infinity),
          getDrawingHorizontalLine: (value) {
            return FlLine(
              color: isDark ? Colors.white10 : Colors.black.withOpacity(0.05),
              strokeWidth: 1,
            );
          },
        ),
        borderData: FlBorderData(show: false),
      ),
      duration: const Duration(milliseconds: 300), // Smooth animation on data change
      curve: Curves.easeInOut,
    );
  }
}
