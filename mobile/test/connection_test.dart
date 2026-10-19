import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:elink_frame/connection.dart';

void main() {
  Future<ConnectionConfig?> load(
    Map<String, String> store,
    Map<String, Object> asset, {
    String fallbackUrl = '',
    String fallbackToken = '',
  }) => loadConnection(
    read: (key) async => store[key],
    write: (key, value) async {
      store[key] = value;
    },
    loadAsset: () async => jsonEncode(asset),
    fallbackUrl: fallbackUrl,
    fallbackToken: fallbackToken,
  );
  const empty = {'version': 1, 'base_url': '', 'app_token': ''};
  const personal = {
    'version': 1,
    'base_url': 'https://192.0.2.1',
    'app_token': 'local-test-token',
  };

  test('first launch uses injected configuration without user input', () async {
    final store = <String, String>{};
    final config = await load(store, personal);
    expect(config!.baseUrl, personal['base_url']);
    expect(config.token, personal['app_token']);
    expect(store, {
      'url': personal['base_url'],
      'token': personal['app_token'],
    });
  });
  test(
    'an updated personal IPA replaces outdated stored credentials',
    () async {
      final store = {'url': 'https://192.0.2.2', 'token': 'old-test-token'};
      final config = await load(store, personal);
      expect(config!.token, 'local-test-token');
      expect(store['url'], 'https://192.0.2.1');
      expect(store['token'], 'local-test-token');
    },
  );
  test(
    'public IPA is unconfigured but preserves saved developer settings',
    () async {
      expect(await load({}, empty), isNull);
      final config = await load({
        'url': 'https://192.0.2.3',
        'token': 'saved-test-token',
      }, empty);
      expect(config!.token, 'saved-test-token');
      final fallback = await load(
        {},
        empty,
        fallbackUrl: 'https://192.0.2.4',
        fallbackToken: 'android-test-token',
      );
      expect(fallback!.token, 'android-test-token');
    },
  );
  test(
    'invalid package configuration fails without exposing its secret',
    () async {
      for (final body in [
        {...personal, 'base_url': 'http://192.0.2.1'},
        {...personal, 'base_url': 'https://username:password@192.0.2.1'},
        {...personal, 'base_url': ''},
        {...personal, 'version': 2},
        {...personal, 'app_token': 'secret\nheader'},
      ]) {
        try {
          await load({}, body);
          fail('Invalid bootstrap accepted');
        } on FormatException catch (e) {
          expect(e.toString(), isNot(contains(body['app_token'].toString())));
        }
      }
    },
  );
}
