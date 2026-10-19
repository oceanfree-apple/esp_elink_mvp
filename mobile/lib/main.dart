import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:image_picker/image_picker.dart';
import 'api.dart';
import 'connection.dart';
import 'crop.dart';
import 'dither.dart';

const ink = Color(0xff203a34), paper = Color(0xfff5f3ed);
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ElinkApp());
}

class ElinkApp extends StatelessWidget {
  const ElinkApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: '墨间',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(seedColor: ink, surface: paper),
      scaffoldBackgroundColor: paper,
    ),
    home: const FramePage(),
  );
}

class FramePage extends StatefulWidget {
  const FramePage({super.key});
  @override
  State<FramePage> createState() => _FramePageState();
}

class _FramePageState extends State<FramePage> with WidgetsBindingObserver {
  final storage = const FlutterSecureStorage();
  RelayApi? api;
  ui.Image? source;
  CropPose? pose;
  Uint8List? preview, packed;
  String? imageId, idem;
  Map<String, dynamic>? device, job;
  String? message, networkError;
  bool working = false, polling = false;
  Timer? timer;
  double startScale = 1, startAngle = 0;
  Offset anchor = Offset.zero;
  int previewMs = 0;
  bool get active => [
    'created',
    'dispatched',
    'downloading',
    'refreshing',
  ].contains(job?['state']);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    initialize();
  }

  Future<void> initialize() async {
    try {
      final connection = await loadConnection(
        read: (key) => storage.read(key: key),
        write: (key, value) => storage.write(key: key, value: value),
      );
      if (!mounted) {
        return;
      }
      if (connection != null) {
        api = RelayApi(connection.baseUrl, connection.token);
      }
      setState(() {});
      await poll();
      if (!mounted) {
        return;
      }
      setState(() {});
      timer = Timer.periodic(const Duration(seconds: 1), (_) => poll());
      if (defaultTargetPlatform == TargetPlatform.android) {
        final lost = await ImagePicker().retrieveLostData();
        if (lost.files?.isNotEmpty == true) {
          await loadPhoto(lost.files!.first);
        }
      }
    } catch (e) {
      if (mounted) {
        setState(() => message = friendly(e));
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    timer?.cancel();
    if (state == AppLifecycleState.resumed) {
      poll();
      timer = Timer.periodic(const Duration(seconds: 1), (_) => poll());
    }
  }

  @override
  void dispose() {
    timer?.cancel();
    api?.close();
    source?.dispose();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  String friendly(Object e) => e.toString().replaceFirst('Exception: ', '');
  Future<void> poll() async {
    if (api == null || polling || !mounted) {
      return;
    }
    polling = true;
    try {
      final d = await api!.request('GET', '/v1/device');
      if (mounted) {
        setState(() {
          device = d;
          job = d['latest_job'] as Map<String, dynamic>?;
          networkError = null;
          if (idem != null && job?['idem'] == idem) message = null;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          device = null;
          networkError = friendly(e);
        });
      }
    } finally {
      polling = false;
    }
  }

  Future<void> pick() async {
    try {
      final file = await ImagePicker().pickImage(
        source: ImageSource.gallery,
        maxWidth: 4096,
        maxHeight: 4096,
        imageQuality: 100,
        requestFullMetadata: false,
      );
      if (file != null) {
        await loadPhoto(file);
      }
    } catch (e) {
      if (mounted) {
        setState(() => message = '无法打开照片：${friendly(e)}');
      }
    }
  }

  Future<void> loadPhoto(XFile file) async {
    final codec = await ui.instantiateImageCodec(await file.readAsBytes());
    final frame = await codec.getNextFrame();
    codec.dispose();
    if (!mounted) {
      frame.image.dispose();
      return;
    }
    source?.dispose();
    setState(() {
      source = frame.image;
      pose = CropPose(source!.width.toDouble(), source!.height.toDouble());
      invalidate();
      message = null;
    });
  }

  void invalidate() {
    preview = null;
    packed = null;
    imageId = null;
    idem = null;
  }

  Future<void> generate() async {
    if (source == null || working) {
      return;
    }
    setState(() {
      working = true;
      message = null;
    });
    final watch = Stopwatch()..start();
    try {
      final recorder = ui.PictureRecorder();
      pose!.paint(Canvas(recorder), source!, const Size(800, 480));
      final picture = recorder.endRecording();
      final image = await picture.toImage(800, 480);
      picture.dispose();
      final bytes = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      image.dispose();
      final result = await compute(convertFrame, bytes!.buffer.asUint8List());
      if (mounted) {
        setState(() {
          packed = result['packed'];
          preview = result['preview'];
          imageId = null;
          idem = null;
          previewMs = watch.elapsedMilliseconds;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() => message = '生成预览失败：${friendly(e)}');
      }
    } finally {
      if (mounted) {
        setState(() => working = false);
      }
    }
  }

  Future<void> send() async {
    if (api == null || packed == null || working || active) {
      return;
    }
    setState(() {
      working = true;
      message = '正在上传画面…';
    });
    try {
      if (imageId == null) {
        final uploaded = await api!.request(
          'POST',
          '/v1/images',
          bytes: packed,
        );
        if (uploaded['sha256'] != sha256.convert(packed!).toString()) {
          throw Exception('上传校验失败，请重试');
        }
        imageId = uploaded['image_id'] as String;
        final random = math.Random.secure();
        idem = List.generate(
          16,
          (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
        ).join();
      }
      if (job?['idem'] == idem &&
          ['succeeded', 'failed', 'uncertain'].contains(job?['state'])) {
        final random = math.Random.secure();
        idem = List.generate(
          16,
          (_) => random.nextInt(256).toRadixString(16).padLeft(2, '0'),
        ).join();
      }
      final created = await api!.request(
        'POST',
        '/v1/refresh-jobs',
        json: {'image_id': imageId, 'idempotency_key': idem},
      );
      if (mounted) {
        setState(() {
          job = created;
          message = null;
        });
      }
      await poll();
    } catch (e) {
      if (mounted) {
        setState(() => message = friendly(e));
      }
    } finally {
      if (mounted) {
        setState(() => working = false);
      }
    }
  }

  Future<void> settings() async {
    final url = TextEditingController(text: api?.baseUrl ?? 'https://');
    final token = TextEditingController(text: api?.token ?? '');
    final save = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('连接相框'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: url,
              keyboardType: TextInputType.url,
              decoration: const InputDecoration(labelText: '服务地址'),
            ),
            TextField(
              controller: token,
              obscureText: true,
              decoration: const InputDecoration(labelText: '访问令牌'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    final newUrl = url.text.trim(), newToken = token.text.trim();
    Future.delayed(const Duration(seconds: 1), () {
      url.dispose();
      token.dispose();
    });
    if (save != true || !mounted) {
      return;
    }
    try {
      final parsed = Uri.tryParse(newUrl);
      if (parsed == null ||
          parsed.scheme != 'https' ||
          parsed.host.isEmpty ||
          newToken.isEmpty) {
        throw Exception('请填写 HTTPS 地址和访问令牌');
      }
      await storage.write(key: 'url', value: newUrl);
      await storage.write(key: 'token', value: newToken);
      if (!mounted) {
        return;
      }
      api?.close();
      api = RelayApi(newUrl, newToken);
      setState(() {
        device = null;
        job = null;
        imageId = null;
        idem = null;
        message = null;
      });
      await poll();
    } catch (e) {
      if (mounted) {
        setState(() => message = friendly(e));
      }
    }
  }

  String get taskLabel {
    const labels = {
      'created': '已创建，等待下发',
      'dispatched': '已通知相框',
      'downloading': '相框正在接收画面',
      'refreshing': '墨水屏刷新中',
      'succeeded': '刷新完成',
      'failed': '刷新失败',
      'uncertain': '结果待确认，请查看屏幕',
    };
    return labels[job?['state']] ?? '选择一张喜欢的照片';
  }

  Widget editor() => LayoutBuilder(
    builder: (context, constraints) {
      final factor = constraints.maxWidth / 800;
      Offset focal(Offset p) => p / factor - const Offset(400, 240);
      return GestureDetector(
        onScaleStart: (details) {
          startScale = pose!.scale;
          startAngle = pose!.angle;
          final delta = focal(details.localFocalPoint) - pose!.center;
          anchor =
              Offset(
                math.cos(startAngle) * delta.dx +
                    math.sin(startAngle) * delta.dy,
                -math.sin(startAngle) * delta.dx +
                    math.cos(startAngle) * delta.dy,
              ) /
              startScale;
        },
        onScaleUpdate: (details) => setState(() {
          pose!.angle = startAngle + details.rotation;
          pose!.scale = startScale * details.scale;
          final angle = pose!.angle;
          pose!.center =
              focal(details.localFocalPoint) -
              Offset(
                    math.cos(angle) * anchor.dx - math.sin(angle) * anchor.dy,
                    math.sin(angle) * anchor.dx + math.cos(angle) * anchor.dy,
                  ) *
                  pose!.scale;
          pose!.constrain();
          invalidate();
        }),
        child: CropCanvas(image: source!, pose: pose!),
      );
    },
  );
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      backgroundColor: paper,
      title: const Text(
        '墨间',
        style: TextStyle(fontWeight: FontWeight.w700, letterSpacing: 4),
      ),
      actions: [
        IconButton(
          onPressed: working ? null : settings,
          tooltip: '连接设置',
          icon: const Icon(Icons.tune),
        ),
      ],
    ),
    body: SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(24, 14, 24, 28),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Container(
                  width: 7,
                  height: 7,
                  decoration: BoxDecoration(
                    color: device?['online'] == true
                        ? const Color(0xff608573)
                        : Colors.grey,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  api == null
                      ? '尚未连接相框'
                      : device == null
                      ? '连接云端中'
                      : device!['online'] == true
                      ? '我的相框 · 在线'
                      : '我的相框 · 离线',
                ),
                const Spacer(),
                const Text(
                  '800 × 480',
                  style: TextStyle(color: Colors.black45, fontSize: 12),
                ),
              ],
            ),
            const SizedBox(height: 28),
            Text(
              preview != null ? '看看它在纸上的样子' : '把一刻，留在眼前',
              style: const TextStyle(
                fontSize: 25,
                fontWeight: FontWeight.w600,
                color: ink,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              preview != null ? '六色抖动预览 · 构图与发送内容一致' : '选择照片，在固定画框内自由调整',
              style: const TextStyle(color: Colors.black54, fontSize: 13),
            ),
            const SizedBox(height: 26),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xffe7e1d5),
                borderRadius: BorderRadius.circular(6),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: .08),
                    blurRadius: 20,
                    offset: const Offset(0, 9),
                  ),
                ],
              ),
              child: AspectRatio(
                aspectRatio: 5 / 3,
                child: working
                    ? const ColoredBox(
                        color: Colors.white,
                        child: Center(
                          child: CircularProgressIndicator(color: ink),
                        ),
                      )
                    : preview != null
                    ? Image.memory(
                        preview!,
                        fit: BoxFit.fill,
                        gaplessPlayback: true,
                      )
                    : source != null
                    ? editor()
                    : ColoredBox(
                        color: const Color(0xfffffdf8),
                        child: InkWell(
                          onTap: pick,
                          child: const Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(
                                Icons.add_photo_alternate_outlined,
                                size: 38,
                                color: ink,
                              ),
                              SizedBox(height: 12),
                              Text('从相册选择照片', style: TextStyle(color: ink)),
                            ],
                          ),
                        ),
                      ),
              ),
            ),
            const SizedBox(height: 24),
            if (source != null && preview == null) ...[
              const Text(
                '双指缩放和旋转 · 拖动调整位置',
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.black54, fontSize: 12),
              ),
              Row(
                children: [
                  const Icon(Icons.rotate_left, size: 20),
                  Expanded(
                    child: Slider(
                      value: (pose!.angle * 180 / math.pi + 180) % 360 - 180,
                      min: -180,
                      max: 180,
                      onChanged: working
                          ? null
                          : (v) => setState(() {
                              pose!.angle = v * math.pi / 180;
                              pose!.constrain();
                              invalidate();
                            }),
                    ),
                  ),
                  SizedBox(
                    width: 50,
                    child: Text(
                      '${((pose!.angle * 180 / math.pi + 180) % 360 - 180).toStringAsFixed(1)}°',
                      style: const TextStyle(fontSize: 12),
                    ),
                  ),
                ],
              ),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  TextButton.icon(
                    onPressed: working
                        ? null
                        : () => setState(() {
                            pose!.angle += math.pi / 2;
                            pose!.constrain();
                            invalidate();
                          }),
                    icon: const Icon(Icons.rotate_90_degrees_cw),
                    label: const Text('旋转 90°'),
                  ),
                  TextButton(
                    onPressed: working
                        ? null
                        : () => setState(() {
                            pose!.reset();
                            invalidate();
                          }),
                    child: const Text('重置'),
                  ),
                ],
              ),
            ],
            if (preview != null)
              Text(
                '预览生成 ${(previewMs / 1000).toStringAsFixed(2)} 秒 · 实物颜色以面板为准',
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 11, color: Colors.black45),
              ),
            const SizedBox(height: 18),
            FilledButton.icon(
              style: FilledButton.styleFrom(
                backgroundColor: ink,
                padding: const EdgeInsets.symmetric(vertical: 16),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
              ),
              onPressed: working
                  ? null
                  : source == null
                  ? pick
                  : preview == null
                  ? generate
                  : active ||
                        api == null ||
                        device?['online'] != true ||
                        device?['busy'] == true
                  ? null
                  : send,
              icon: Icon(
                preview == null
                    ? Icons.auto_awesome_outlined
                    : Icons.send_outlined,
              ),
              label: Text(
                source == null
                    ? '选择照片'
                    : preview == null
                    ? '确定，生成预览'
                    : active
                    ? '正在刷新…'
                    : '刷新电子墨水屏',
              ),
            ),
            if (source != null)
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  TextButton(
                    onPressed: working ? null : pick,
                    child: const Text('换一张照片'),
                  ),
                  if (preview != null)
                    TextButton(
                      onPressed: working ? null : () => setState(invalidate),
                      child: const Text('返回编辑'),
                    ),
                ],
              ),
            const SizedBox(height: 22),
            if (job != null)
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: .7),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  children: [
                    Icon(
                      job!['state'] == 'succeeded'
                          ? Icons.check_circle_outline
                          : Icons.hourglass_empty,
                      color: ink,
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(taskLabel),
                          if (job!['error']?.toString().isNotEmpty == true)
                            Text(
                              job!['error'].toString(),
                              style: const TextStyle(
                                fontSize: 11,
                                color: Colors.black54,
                              ),
                            ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            if (message != null || networkError != null)
              Padding(
                padding: const EdgeInsets.only(top: 14),
                child: Text(
                  message ?? networkError!,
                  style: const TextStyle(
                    color: Color(0xff965c45),
                    fontSize: 13,
                  ),
                ),
              ),
          ],
        ),
      ),
    ),
  );
}
