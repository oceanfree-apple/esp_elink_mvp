import 'dart:math' as math;
import 'dart:typed_data';
import 'package:image/image.dart' as img;

// burkes-mobile-v1: fixed palette and enhancement preset, no server conversion.
const palette = <List<int>>[
  [0, 0, 0],
  [255, 255, 255],
  [255, 227, 0],
  [241, 20, 0],
  [0, 105, 246],
  [20, 166, 93],
];
const codes = [0, 1, 2, 3, 5, 6];

Uint8List enhance(Uint8List rgba, int width, int height) {
  final out = Uint8List(width * height * 3);
  double luminance(int r, int g, int b) =>
      (r * .299 + g * .587 + b * .114).roundToDouble();
  var sum = 0.0;
  for (var i = 0; i < width * height; i++) {
    sum += luminance(rgba[i * 4], rgba[i * 4 + 1], rgba[i * 4 + 2]);
  }
  final mean = (sum / (width * height)).round();
  int channel(num n) => n.clamp(0, 255).toInt();
  final gamma = List.generate(
    256,
    (i) => (255 * math.pow(i / 255, .88)).round().clamp(0, 255),
  );
  for (var i = 0; i < width * height; i++) {
    final r = channel(mean + (rgba[i * 4] - mean) * 1.14);
    final g = channel(mean + (rgba[i * 4 + 1] - mean) * 1.14);
    final b = channel(mean + (rgba[i * 4 + 2] - mean) * 1.14);
    final gray = luminance(r, g, b);
    final rgb = [r, g, b];
    for (var c = 0; c < 3; c++) {
      final saturated = channel(gray + (rgb[c] - gray) * 1.18);
      out[i * 3 + c] = gamma[channel(saturated * 1.10)];
    }
  }
  // Fixed separable Gaussian unsharp mask, explicitly versioned: Pillow's
  // internal blur rounding is not a cross-platform byte contract.
  final kernel = List.generate(
    9,
    (i) => math.exp(-math.pow(i - 4, 2) / (2 * 1.2 * 1.2)),
  );
  final total = kernel.reduce((a, b) => a + b);
  for (var i = 0; i < kernel.length; i++) {
    kernel[i] /= total;
  }
  final tmp = Float32List(out.length), blurred = Float32List(out.length);
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      for (var c = 0; c < 3; c++) {
        var v = 0.0;
        for (var k = -4; k <= 4; k++) {
          v +=
              out[(y * width + (x + k).clamp(0, width - 1)) * 3 + c] *
              kernel[k + 4];
        }
        tmp[(y * width + x) * 3 + c] = v;
      }
    }
  }
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      for (var c = 0; c < 3; c++) {
        var v = 0.0;
        for (var k = -4; k <= 4; k++) {
          v +=
              tmp[(((y + k).clamp(0, height - 1)) * width + x) * 3 + c] *
              kernel[k + 4];
        }
        blurred[(y * width + x) * 3 + c] = v;
      }
    }
  }
  for (var i = 0; i < out.length; i++) {
    final difference = out[i] - blurred[i];
    if (difference.abs() > 2) {
      out[i] = channel((out[i] + difference * 1.1).round());
    }
  }
  return out;
}

Uint8List quantize(Uint8List rgb, int width, int height) {
  if (width * height * 3 != rgb.length || width.isOdd) {
    throw ArgumentError('Invalid image shape');
  }
  final work = Float32List.fromList(rgb.map((v) => v.toDouble()).toList());
  final packed = Uint8List(width * height ~/ 2);
  const kernel = [
    (1, 0, 8),
    (2, 0, 4),
    (-2, 1, 2),
    (-1, 1, 4),
    (0, 1, 8),
    (1, 1, 4),
    (2, 1, 2),
  ];
  for (var y = 0; y < height; y++) {
    final direction = y.isEven ? 1 : -1;
    for (var step = 0; step < width; step++) {
      final x = y.isEven ? step : width - 1 - step;
      final pos = (y * width + x) * 3;
      final r = work[pos].clamp(0.0, 255.0),
          g = work[pos + 1].clamp(0.0, 255.0),
          b = work[pos + 2].clamp(0.0, 255.0);
      var best = 0;
      var distance = double.infinity;
      for (var c = 0; c < palette.length; c++) {
        final dr = palette[c][0] - r,
            dg = palette[c][1] - g,
            db = palette[c][2] - b;
        final d = dr * dr * .30 + dg * dg * .59 + db * db * .11;
        if (d < distance) {
          best = c;
          distance = d;
        }
      }
      final pixel = y * width + x;
      packed[pixel ~/ 2] |= codes[best] << (pixel.isEven ? 4 : 0);
      final er = r - palette[best][0],
          eg = g - palette[best][1],
          eb = b - palette[best][2];
      for (final (dx, dy, weight) in kernel) {
        final nx = x + dx * direction, ny = y + dy;
        if (nx < 0 || nx >= width || ny >= height) {
          continue;
        }
        final n = (ny * width + nx) * 3, factor = weight / 32;
        work[n] += er * factor;
        work[n + 1] += eg * factor;
        work[n + 2] += eb * factor;
      }
    }
  }
  return packed;
}

Uint8List previewPng(Uint8List packed, int width, int height) {
  final output = img.Image(width: width, height: height);
  for (var i = 0; i < width * height; i++) {
    final code = (packed[i ~/ 2] >> (i.isEven ? 4 : 0)) & 15;
    final index = codes.indexOf(code);
    if (index < 0) {
      throw ArgumentError('Invalid panel code');
    }
    final rgb = palette[index];
    output.setPixelRgb(i % width, i ~/ width, rgb[0], rgb[1], rgb[2]);
  }
  return Uint8List.fromList(img.encodePng(output));
}

Map<String, Uint8List> convertFrame(Uint8List rgba) {
  if (rgba.length != 800 * 480 * 4) {
    throw ArgumentError('Expected 800x480 RGBA');
  }
  final packed = quantize(enhance(rgba, 800, 480), 800, 480);
  return {'packed': packed, 'preview': previewPng(packed, 800, 480)};
}
