import 'dart:convert';
import 'package:flutter/services.dart';

class ConnectionConfig {
  const ConnectionConfig(this.baseUrl, this.token);
  final String baseUrl, token;

  static ConnectionConfig? parse(String url, String token) {
    if (url.isEmpty && token.isEmpty) return null;
    final uri = Uri.tryParse(url);
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.query.isNotEmpty ||
        uri.fragment.isNotEmpty ||
        (uri.path.isNotEmpty && uri.path != '/') ||
        token.isEmpty ||
        RegExp(r'\s').hasMatch(token)) {
      throw const FormatException('安装连接配置无效，请重新准备安装包');
    }
    return ConnectionConfig(url, token);
  }

  static ConnectionConfig? fromAsset(String source) {
    try {
      final body = jsonDecode(source);
      if (body is! Map<String, dynamic> ||
          body['version'] != 1 ||
          body['base_url'] is! String ||
          body['app_token'] is! String) {
        throw const FormatException();
      }
      return parse(body['base_url'] as String, body['app_token'] as String);
    } on FormatException {
      // Do not include input JSON, URLs or credentials in error messages.
      throw const FormatException('安装连接配置无效，请重新准备安装包');
    }
  }
}

/// A personal IPA's injected configuration wins on both first install and
/// update. Public builds contain an empty asset and keep the existing developer
/// settings / Android build-define behavior.
Future<ConnectionConfig?> loadConnection({
  required Future<String?> Function(String key) read,
  required Future<void> Function(String key, String value) write,
  Future<String> Function()? loadAsset,
  String fallbackUrl = const String.fromEnvironment('ELINK_URL'),
  String fallbackToken = const String.fromEnvironment('ELINK_TOKEN'),
}) async {
  final source =
      await (loadAsset?.call() ??
          rootBundle.loadString('assets/connection.json'));
  final bundled = ConnectionConfig.fromAsset(source);
  if (bundled != null) {
    if (await read('url') != bundled.baseUrl) {
      await write('url', bundled.baseUrl);
    }
    if (await read('token') != bundled.token) {
      await write('token', bundled.token);
    }
    return bundled;
  }
  final savedUrl = await read('url') ?? '';
  final savedToken = await read('token') ?? '';
  return ConnectionConfig.parse(savedUrl, savedToken) ??
      ConnectionConfig.parse(fallbackUrl, fallbackToken);
}
