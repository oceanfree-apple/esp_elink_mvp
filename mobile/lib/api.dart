import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:http/io_client.dart';

class RelayApi {
  RelayApi(this.baseUrl, this.token);
  final String baseUrl, token;
  IOClient? _client;
  Future<IOClient> _getClient() async {
    if (_client != null) {
      return _client!;
    }
    final ca = await rootBundle.load('assets/cloud_ca.pem');
    final context = SecurityContext(withTrustedRoots: false);
    context.setTrustedCertificatesBytes(ca.buffer.asUint8List());
    return _client = IOClient(
      HttpClient(context: context)
        ..connectionTimeout = const Duration(seconds: 10),
    );
  }

  Future<Map<String, dynamic>> request(
    String method,
    String path, {
    Object? json,
    Uint8List? bytes,
  }) async {
    final base = Uri.parse(baseUrl);
    if (base.scheme != 'https' ||
        base.host.isEmpty ||
        base.userInfo.isNotEmpty ||
        base.query.isNotEmpty ||
        base.fragment.isNotEmpty) {
      throw Exception('请输入有效的 HTTPS 服务地址');
    }
    final client = await _getClient();
    final headers = {
      'Authorization': 'Bearer $token',
      'Content-Type': bytes != null
          ? 'application/octet-stream'
          : 'application/json',
    };
    final url = base.resolve(path);
    final response =
        await (method == 'GET'
                ? client.get(url, headers: headers)
                : client.post(
                    url,
                    headers: headers,
                    body: bytes ?? jsonEncode(json),
                  ))
            .timeout(const Duration(seconds: 30));
    final body =
        jsonDecode(utf8.decode(response.bodyBytes)) as Map<String, dynamic>;
    if (response.statusCode >= 400) {
      final code = body['detail'].toString();
      const messages = {
        'device_offline': '墨水屏离线，请检查供电和 Wi-Fi',
        'device_busy': '墨水屏正在处理任务，请稍后再试',
        'unauthorized': '访问令牌不正确',
        'broker_unavailable': '云端消息服务暂不可用',
      };
      throw Exception(messages[code] ?? '请求失败：$code');
    }
    return body;
  }

  void close() {
    _client?.close();
  }
}
