import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

class PulseAnimation extends StatelessWidget {
  final Widget child;
  final bool active;

  const PulseAnimation({
    super.key,
    required this.child,
    this.active = true,
  });

  @override
  Widget build(BuildContext context) {
    if (!active) return child;
    
    return child.animate(onPlay: (controller) => controller.repeat())
        .scale(
          duration: 800.ms,
          begin: const Offset(1.0, 1.0),
          end: const Offset(1.2, 1.2),
          curve: Curves.easeInOut,
        )
        .then(delay: 0.ms)
        .scale(
          duration: 400.ms,
          begin: const Offset(1.2, 1.2),
          end: const Offset(1.0, 1.0),
          curve: Curves.easeInOut,
        );
  }
}
