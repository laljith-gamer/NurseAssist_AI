import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:provider/provider.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../../providers/patient_provider.dart';
import 'pulse_animation.dart';

class VitalHistoryCharts extends StatelessWidget {
  const VitalHistoryCharts({super.key});

  @override
  Widget build(BuildContext context) {
    return Consumer<PatientProvider>(
      builder: (context, provider, child) {
        if (provider.selectedPatient == null) {
          return const SizedBox.shrink();
        }

        final data = provider.vitalHistory;
        final currentMetrics = provider.currentMetrics?.current ?? {};

        final uniqueTypes = data.map((d) => d['vital_type']?.toString()).whereType<String>().toSet();
        
        final metricsConfig = <_MetricConfig>[];
        for (final type in uniqueTypes) {
          switch (type) {
            case 'heart_rate':
              metricsConfig.add(_MetricConfig(
                id: 'heart_rate', title: 'Heart Rate', unit: 'bpm', icon: Icons.favorite, color: Colors.redAccent, isCritical: (val) => val < 50 || val > 100,
              ));
              break;
            case 'spo2':
              metricsConfig.add(_MetricConfig(
                id: 'spo2', title: 'SpO₂', unit: '%', icon: Icons.air, color: Colors.lightBlue, isCritical: (val) => val < 92,
              ));
              break;
            case 'respiratory_rate':
              metricsConfig.add(_MetricConfig(
                id: 'respiratory_rate', title: 'Respiratory Rate', unit: '/min', icon: Icons.waves, color: Colors.teal, isCritical: (val) => val < 12 || val > 20,
              ));
              break;
            case 'systolic':
              metricsConfig.add(_MetricConfig(
                id: 'systolic', title: 'Systolic BP', unit: 'mmHg', icon: Icons.monitor_heart_outlined, color: Colors.deepPurpleAccent, isCritical: (val) => val < 90 || val > 140,
              ));
              break;
            case 'diastolic':
              metricsConfig.add(_MetricConfig(
                id: 'diastolic', title: 'Diastolic BP', unit: 'mmHg', icon: Icons.monitor_heart, color: Colors.purple, isCritical: (val) => val < 60 || val > 90,
              ));
              break;
            case 'temperature':
              metricsConfig.add(_MetricConfig(
                id: 'temperature', title: 'Temperature', unit: '°C', icon: Icons.thermostat, color: Colors.orange, isCritical: (val) => val < 36.0 || val > 38.0,
              ));
              break;
            default:
              // Dynamically support ANY metric in the database!
              final title = type.replaceAll('_', ' ').split(' ').map((s) => s.isNotEmpty ? '${s[0].toUpperCase()}${s.substring(1)}' : '').join(' ');
              metricsConfig.add(_MetricConfig(
                id: type,
                title: title,
                unit: currentMetrics['${type}_unit']?.toString() ?? '',
                icon: Icons.timeline,
                color: Colors.blueGrey,
                isCritical: (val) => false,
              ));
          }
        }
        
        if (metricsConfig.isEmpty) {
          return const Center(child: Text('No vitals recorded yet.'));
        }

        return ListView.builder(
          padding: const EdgeInsets.symmetric(vertical: 16),
          itemCount: metricsConfig.length,
          itemBuilder: (context, index) {
            final config = metricsConfig[index];
            final currentValue = currentMetrics[config.id];
            final dVal = currentValue is num
                ? currentValue.toDouble()
                : double.tryParse(currentValue?.toString() ?? '');
            final isCrit = dVal != null ? config.isCritical(dVal) : false;

            return _ChartCard(
              config: config,
              data: data,
              currentValue: dVal,
              isCritical: isCrit,
            )
                .animate(delay: Duration(milliseconds: 100 * index))
                .fadeIn(duration: 400.ms)
                .slideY(begin: 0.1, end: 0, duration: 400.ms, curve: Curves.easeOutCubic);
          },
        );
      },
    );
  }
}

class _MetricConfig {
  final String id;
  final String title;
  final String unit;
  final IconData icon;
  final Color color;
  final bool Function(double) isCritical;

  _MetricConfig({
    required this.id,
    required this.title,
    required this.unit,
    required this.icon,
    required this.color,
    required this.isCritical,
  });
}

class _ChartCard extends StatelessWidget {
  final _MetricConfig config;
  final List<Map<String, dynamic>> data;
  final double? currentValue;
  final bool isCritical;

  const _ChartCard({
    required this.config,
    required this.data,
    required this.currentValue,
    required this.isCritical,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    Widget cardContent = Container(
      height: 240,
      padding: const EdgeInsets.all(20),
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1E293B).withValues(alpha: 0.7) : Colors.white.withValues(alpha: 0.8),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: isCritical
              ? Colors.red.withValues(alpha: 0.6)
              : (isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.05)),
          width: isCritical ? 2.0 : 1.0,
        ),
        boxShadow: [
          if (isCritical)
            BoxShadow(
              color: Colors.red.withValues(alpha: 0.2),
              blurRadius: 20,
              spreadRadius: 2,
            )
          else
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.05),
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
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: config.color.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: isCritical 
                        ? PulseAnimation(child: Icon(config.icon, color: config.color, size: 20))
                        : Icon(config.icon, color: config.color, size: 20),
                  ),
                  const SizedBox(width: 12),
                  Text(
                    config.title,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                ],
              ),
              if (currentValue != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: isCritical 
                        ? Colors.red.withValues(alpha: 0.1) 
                        : (isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.05)),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    children: [
                      Text(
                        currentValue == currentValue!.roundToDouble()
                            ? currentValue!.toStringAsFixed(0)
                            : currentValue!.toStringAsFixed(1),
                        style: TextStyle(
                          fontSize: 20,
                          fontWeight: FontWeight.w800,
                          color: isCritical ? Colors.redAccent : (isDark ? Colors.white : Colors.black87),
                        ),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        config.unit,
                        style: TextStyle(
                          fontSize: 12,
                          color: isDark ? Colors.white54 : Colors.black54,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          const SizedBox(height: 24),
          Expanded(
            child: _buildChart(data, context, isDark),
          ),
        ],
      ),
    );

    return ClipRRect(
      borderRadius: BorderRadius.circular(24),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
        child: cardContent,
      ),
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
      final row = rawData[i];
      if (row['vital_type'] == config.id) {
        final val = row['value'];
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

    final chartColor = isCritical ? Colors.redAccent : config.color;

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
            getTooltipColor: (touchedSpot) => isDark ? const Color(0xFF334155) : Colors.white,
            getTooltipItems: (touchedSpots) {
              return touchedSpots.map((LineBarSpot touchedSpot) {
                final textStyle = TextStyle(
                  color: isDark ? Colors.white : Colors.black87,
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
            color: chartColor,
            barWidth: 3,
            isStrokeCapRound: true,
            dotData: FlDotData(
              show: true,
              getDotPainter: (spot, percent, barData, index) {
                return FlDotCirclePainter(
                  radius: 3.5,
                  color: chartColor,
                  strokeWidth: 2,
                  strokeColor: isDark ? const Color(0xFF1E293B) : Colors.white,
                );
              },
            ),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                colors: [
                  chartColor.withValues(alpha: 0.3),
                  chartColor.withValues(alpha: 0.0),
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
              color: Colors.orangeAccent.withValues(alpha: 0.7),
              barWidth: 2,
              isStrokeCapRound: true,
              dashArray: [6, 4],
              dotData: FlDotData(
                show: true,
                getDotPainter: (spot, percent, barData, index) {
                  return FlDotCirclePainter(
                    radius: 2.5,
                    color: Colors.orangeAccent,
                    strokeWidth: 1.5,
                    strokeColor: isDark ? const Color(0xFF1E293B) : Colors.white,
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
              reservedSize: 36,
              getTitlesWidget: (value, meta) {
                return Text(
                  value.toInt().toString(),
                  style: TextStyle(
                    color: isDark ? Colors.white54 : Colors.black54,
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
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
          horizontalInterval: ((maxY - minY) / 4).clamp(1.0, double.infinity),
          getDrawingHorizontalLine: (value) {
            return FlLine(
              color: isDark ? Colors.white.withValues(alpha: 0.05) : Colors.black.withValues(alpha: 0.03),
              strokeWidth: 1,
              dashArray: [4, 4],
            );
          },
        ),
        borderData: FlBorderData(show: false),
      ),
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeOutCubic,
    );
  }
}
