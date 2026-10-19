import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image_picker_platform_interface/image_picker_platform_interface.dart';
import 'package:elink_frame/main.dart';
import 'package:elink_frame/crop.dart';

class TestPicker extends ImagePickerPlatform {
  @override
  Future<LostDataResponse> getLostData() async => LostDataResponse.empty();
  @override
  Future<XFile?> getImageFromSource({
    required ImageSource source,
    ImagePickerOptions options = const ImagePickerOptions(),
  }) async => XFile(File('test/fixtures/photo.png').absolute.path);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    // Optional local fonts make exported review images readable. Tests do not
    // require these paths and assertions never depend on font rasterization.
    for (final pair in [
      ('Roboto', Platform.environment['ELINK_TEST_FONT']),
      ('MaterialIcons', Platform.environment['ELINK_TEST_ICONS']),
    ]) {
      if (pair.$2 != null && File(pair.$2!).existsSync()) {
        final loader = FontLoader(pair.$1)
          ..addFont(
            Future.value(
              ByteData.sublistView(File(pair.$2!).readAsBytesSync()),
            ),
          );
        await loader.load();
      }
    }
  });
  setUp(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('plugins.it_nomads.com/flutter_secure_storage'),
          (_) async => null,
        );
    ImagePickerPlatform.instance = TestPicker();
  });
  testWidgets('select, rotate, preview, and return to the saved crop', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(420, 960);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final boundaryKey = GlobalKey();
    await tester.pumpWidget(
      RepaintBoundary(key: boundaryKey, child: const ElinkApp()),
    );
    await tester.pumpAndSettle();
    expect(find.text('选择照片'), findsOneWidget);
    await tester.runAsync(() async {
      await tester.tap(find.text('选择照片'));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pumpAndSettle();
    expect(find.text('旋转 90°'), findsOneWidget);
    final crop = find.byType(CropCanvas);
    final center = tester.getCenter(crop);
    final initialScale = tester.widget<CropCanvas>(crop).pose.scale;
    final first = await tester.startGesture(
      center - const Offset(30, 0),
      pointer: 1,
    );
    final second = await tester.startGesture(
      center + const Offset(30, 0),
      pointer: 2,
    );
    await first.moveTo(center - const Offset(70, 25));
    await second.moveTo(center + const Offset(70, 25));
    await tester.pump();
    expect(
      tester.widget<CropCanvas>(crop).pose.scale,
      greaterThan(initialScale),
    );
    expect(tester.widget<CropCanvas>(crop).pose.angle.abs(), greaterThan(.05));
    await first.up();
    await second.up();
    await tester.pumpAndSettle();
    final previousCenter = tester.widget<CropCanvas>(crop).pose.center;
    await tester.drag(crop, const Offset(0, 30));
    await tester.pumpAndSettle();
    expect(tester.widget<CropCanvas>(crop).pose.center, isNot(previousCenter));
    await tester.tap(find.text('重置'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('旋转 90°'));
    await tester.pumpAndSettle();
    expect(find.text('90.0°'), findsOneWidget);
    await tester.runAsync(() async {
      final render =
          boundaryKey.currentContext!.findRenderObject()!
              as RenderRepaintBoundary;
      final image = await render.toImage(pixelRatio: 2);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      image.dispose();
      File(
        '../artifacts/app-editor.png',
      ).writeAsBytesSync(bytes!.buffer.asUint8List());
      await tester.tap(find.text('确定，生成预览'));
      await Future<void>.delayed(const Duration(seconds: 3));
    });
    await tester.pumpAndSettle();
    expect(find.text('返回编辑'), findsOneWidget);
    await tester.runAsync(() async {
      await precacheImage(
        tester.widget<Image>(find.byType(Image)).image,
        tester.element(find.byType(Image)),
      );
    });
    await tester.pumpAndSettle();
    expect(
      tester
          .widget<FilledButton>(
            find.byWidgetPredicate((widget) => widget is FilledButton),
          )
          .onPressed,
      isNull,
    );
    await tester.runAsync(() async {
      final render =
          boundaryKey.currentContext!.findRenderObject()!
              as RenderRepaintBoundary;
      final image = await render.toImage(pixelRatio: 2);
      final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
      image.dispose();
      File(
        '../artifacts/app-preview.png',
      ).writeAsBytesSync(bytes!.buffer.asUint8List());
    });
    await tester.tap(find.text('返回编辑'));
    await tester.pumpAndSettle();
    expect(find.text('90.0°'), findsOneWidget);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
  });
}
