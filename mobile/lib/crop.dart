import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/material.dart';

class CropPose {
  CropPose(this.imageWidth, this.imageHeight) {
    reset();
  }
  final double imageWidth, imageHeight;
  double angle = 0, scale = 1;
  Offset center = Offset.zero;
  double get minimumScale => math.max(
    (800 * math.cos(angle).abs() + 480 * math.sin(angle).abs()) / imageWidth,
    (800 * math.sin(angle).abs() + 480 * math.cos(angle).abs()) / imageHeight,
  );
  void reset() {
    angle = 0;
    center = Offset.zero;
    scale = minimumScale;
  }

  void constrain() {
    scale = scale.clamp(minimumScale, minimumScale * 16);
    final c = math.cos(angle), s = math.sin(angle);
    final rx = 400 * c.abs() + 240 * s.abs(),
        ry = 400 * s.abs() + 240 * c.abs();
    final mx = math.max(0.0, imageWidth * scale / 2 - rx),
        my = math.max(0.0, imageHeight * scale / 2 - ry);
    final x = (center.dx * c + center.dy * s).clamp(-mx, mx),
        y = (-center.dx * s + center.dy * c).clamp(-my, my);
    center = Offset(c * x - s * y, s * x + c * y);
  }

  void paint(Canvas canvas, ui.Image image, Size size) {
    canvas.save();
    canvas.clipRect(Offset.zero & size);
    canvas.drawColor(Colors.white, BlendMode.src);
    canvas.scale(size.width / 800);
    canvas.translate(400 + center.dx, 240 + center.dy);
    canvas.rotate(angle);
    canvas.scale(scale);
    canvas.drawImage(
      image,
      Offset(-imageWidth / 2, -imageHeight / 2),
      Paint()..filterQuality = FilterQuality.high,
    );
    canvas.restore();
  }
}

class CropCanvas extends StatelessWidget {
  const CropCanvas({super.key, required this.image, required this.pose});
  final ui.Image image;
  final CropPose pose;
  @override
  Widget build(BuildContext context) =>
      CustomPaint(painter: _CropPainter(image, pose));
}

class _CropPainter extends CustomPainter {
  _CropPainter(this.image, this.pose);
  final ui.Image image;
  final CropPose pose;
  @override
  void paint(Canvas canvas, Size size) {
    pose.paint(canvas, image, size);
    final p = Paint()
      ..color = Colors.white.withValues(alpha: .45)
      ..strokeWidth = .6;
    for (var i = 1; i <= 2; i++) {
      canvas.drawLine(
        Offset(size.width * i / 3, 0),
        Offset(size.width * i / 3, size.height),
        p,
      );
      canvas.drawLine(
        Offset(0, size.height * i / 3),
        Offset(size.width, size.height * i / 3),
        p,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _CropPainter oldDelegate) => true;
}
