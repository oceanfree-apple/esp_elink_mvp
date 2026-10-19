import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:elink_frame/crop.dart';
import 'package:elink_frame/dither.dart';

void main() {
  test('arbitrary rotation keeps all four crop corners inside the image', () {
    final random = math.Random(17);
    for (final dimensions in [
      (800.0, 480.0),
      (400.0, 3000.0),
      (4000.0, 1000.0),
    ]) {
      for (var i = 0; i < 500; i++) {
        final pose = CropPose(dimensions.$1, dimensions.$2);
        pose.angle = random.nextDouble() * math.pi * 4 - math.pi * 2;
        pose.scale = random.nextDouble() * 5;
        pose.center = Offset(
          random.nextDouble() * 8000 - 4000,
          random.nextDouble() * 8000 - 4000,
        );
        pose.constrain();
        final c = math.cos(pose.angle), s = math.sin(pose.angle);
        for (final x in [-400.0, 400.0]) {
          for (final y in [-240.0, 240.0]) {
            final dx = x - pose.center.dx, dy = y - pose.center.dy;
            expect(
              ((dx * c + dy * s) / pose.scale).abs(),
              lessThanOrEqualTo(dimensions.$1 / 2 + 1e-7),
            );
            expect(
              ((-dx * s + dy * c) / pose.scale).abs(),
              lessThanOrEqualTo(dimensions.$2 / 2 + 1e-7),
            );
          }
        }
      }
    }
  });

  test('serpentine Burkes and nibble packing match the Python reference', () {
    final input = File('test/fixtures/burkes-input.rgb').readAsBytesSync();
    final reference = File(
      'test/fixtures/burkes-reference.bin',
    ).readAsBytesSync();
    expect(quantize(input, 32, 16), orderedEquals(reference));
    expect(
      quantize(Uint8List.fromList([0, 0, 0, 255, 255, 255]), 2, 1),
      orderedEquals([0x01]),
    );
  });

  test('full photo produces a valid frame and a preview from the same codes', () {
    final photo = img.decodePng(
      File('test/fixtures/photo.png').readAsBytesSync(),
    )!;
    final rgba = photo.getBytes(order: img.ChannelOrder.rgba);
    final watch = Stopwatch()..start();
    final result = convertFrame(rgba);
    final frame = result['packed']!;
    expect(frame.length, 192000);
    final preview = img.decodePng(result['preview']!)!;
    expect((preview.width, preview.height), (800, 480));
    for (var i = 0; i < 800 * 480; i++) {
      final code = (frame[i ~/ 2] >> (i.isEven ? 4 : 0)) & 15;
      expect(codes, contains(code));
      if (i % 997 == 0) {
        final pixel = preview.getPixel(i % 800, i ~/ 800),
            rgb = palette[codes.indexOf(code)];
        expect([pixel.r.toInt(), pixel.g.toInt(), pixel.b.toInt()], rgb);
      }
    }
    final output = Directory('../artifacts')..createSync(recursive: true);
    File('${output.path}/sample-frame.bin').writeAsBytesSync(frame);
    File(
      '${output.path}/sample-preview.png',
    ).writeAsBytesSync(result['preview']!);
    File('${output.path}/preview-benchmark.txt').writeAsStringSync(
      'Desktop Flutter test, ${watch.elapsedMilliseconds}ms. Not a Redmi measurement.\n',
    );
  });
}
