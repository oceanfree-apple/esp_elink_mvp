# 墨间 · 手机电子墨水相框 MVP

Flutter App 选图、缩放/拖动/任意角度旋转、固定 5:3 裁剪，点击确定后在手机本地生成六色 Burkes 预览，再经腾讯云刷新 ESP32-S3 + GDEP073E01（800×480）。预览从最终的 192000 字节数据反解，上传与预览使用同一份像素。

## 当前交付

- Android：`artifacts/mojian-android.apk`，个人密钥签名的 release 包，支持 ARM32/ARM64、Android 7/API24 及以上；已预置本人的云端地址和访问令牌，**只供私人分发**。红米尚未连接，本次不能声称已在红米实测。
- iOS：与安卓共用代码；已实现首次启动自动连接、GitHub Actions未签名Release构建、本地IPA下载核验及私有配置注入。GitHub浏览器授权已成功，公开仓库已创建，开始首次云端构建；iPhone未接线，签名安装和真机测试尚未完成。
- 云端：已通过 `ssh tencent` 部署 HTTPS API、MQTTS、SQLite 和服务自启动。2026-10-20放通安全组后，公网443/8883、ESP在线及公网脚本刷屏均通过，耗时约35秒、串口CRC一致；摄像头当前画面全黑，实物核对和手机操作仍待验收。
- 硬件：通过临时 SSH 转发完成了真实“上传 → MQTT → HTTPS 下载 → 完整性校验 → 刷新 → 成功回报”，约33秒；已用摄像头核对画面。该路径不代表公网直连已验收。

确认方案见[MVP方案](docs/mvp-plan.md)及[iPhone免费自测计划](docs/ios-free-testing-plan.md)。实际操作见[iOS构建与USB安装](docs/ios-installation.md)，实测与未验证项见[验证记录](docs/verification.md)，接口及部署见[接口与运维](docs/operations.md)。

公开仓库：[oceanfree-apple/esp_elink_mvp](https://github.com/oceanfree-apple/esp_elink_mvp)。构建进度及公共未签名IPA见[GitHub Actions](https://github.com/oceanfree-apple/esp_elink_mvp/actions/workflows/ios.yml)。

## 使用

1. 确认实例入站TCP443/8883及公网连接正常，运行`python3 tools/cloud_check.py`检查。
2. 保持当前板子供电并接入已配置的 Wi-Fi；生产固件上电自动联网。
3. iPhone按[iOS安装说明](docs/ios-installation.md)通过Ubuntu USB签名安装；红米安装本地私人APK，需要电脑安装时开启USB调试并授权，执行`adb install -r artifacts/mojian-android.apk`。
4. 打开“墨间”，确认相框在线。选图后双指缩放、旋转，拖动构图，滑条微调角度；确定生成预览，再点刷新。刷新完成依赖设备成功回报，通常需要数十秒。

自用安装包首次打开自动连接，不要求用户填写地址或令牌。公开IPA的连接资源为空，Ubuntu签名前从本机`.private/settings.json`自动注入；App保存在Android安全存储/iOS Keychain。右上角保留开发诊断设置。App只信任项目CA，不要求在手机系统安装CA。不要上传`.private/`、已配置IPA/APK或私人固件。

## 开发与构建

当前验证工具链：Flutter3.38.10 / Dart3.10.9、JDK17、Android SDK36、ESP-IDF5.5.5。Dart 依赖锁定于 `mobile/pubspec.lock`，服务依赖见 `server/requirements.txt`。

```bash
# 本机 Flutter 已安装在 ~/software/flutter
export PATH="$HOME/software/flutter/bin:$PATH"
python3 -m venv .venv
.venv/bin/pip install -r server/requirements.txt
.venv/bin/python -m pytest server/tests tools/tests -q
cd mobile
flutter pub get
flutter analyze
flutter test
cd ..
python3 tools/build_android.py
```

个人签名密钥由构建脚本首次生成，保存在 `.private/`，请备份；后续更新必须继续用同一密钥。测试调试包与正式个人签名不同，若先装过调试包，需卸载调试包后再安装 release。

首次新环境需要 `python3 tools/provision.py` 生成配置和证书；**现有环境不要删除 `.private/` 后重新生成 CA**，否则云端、固件和 App 的信任链会改变。现有 Wi-Fi 私有头文件从串口工程复制，未提交。

```bash
source /home/oceanfree/software/esp-idf-v5.5.5/export.sh
idf.py -C firmware build
idf.py -C firmware -p /dev/ttyUSB0 flash
python3 tools/package_firmware.py
```

串口权限不足时重新登录以继承 `dialout` 组，或由管理员为该设备配置 ACL。保留串口 v1 日常诊断能力，`epd status` 新增 `cloud` 与 `cloud_error`；网络与串口共用忙锁。4MiB factory 分区无 OTA，图像仅在 PSRAM 中，NVS 仅记录最近任务信息。

`artifacts/esp-elink-firmware.tar.gz`包含已构建bootloader、分区表和应用。解压进入firmware目录后可用`python -m esptool --chip esp32s3 -p /dev/ttyUSB0 write_flash @flash_args`烧录。固件同样包含个人设备凭据，应私下保管。

日常iOS开发在Ubuntu修改并推送到公开GitHub仓库，由`.github/workflows/ios.yml`在标准macos-15/Xcode26.2上构建Flutter3.38.10。首次授权和发布后：

```bash
python3 tools/fetch_ios.py --wait
python3 tools/prepare_ios.py
# iPhone连接、解锁并信任Ubuntu后，在桌面工具中导入.private/ios/mojian-configured.ipa
iloader
```

Apple账号只在Ubuntu的iloader窗口登录，不提供给Actions。免费签名按每5～6天USB续签安排；相册JPEG/PNG/HEIC、EXIF、手势、预览性能、Keychain、TLS和真实刷新需要接线后逐项验收。

## 算法约定

`burkes-mobile-v1` 沿用旧工程调色板、颜色增强参数和蛇形 Burkes 核；锐化采用固定 Gaussian 实现，Pillow 内部锐化的取整结果不作为跨平台逐字节契约。独立 Burkes/打包参考样本已与原 Python 实现逐字节比对。预览和发送数据严格一致，实际面板颜色以实物为准。

暂无手机配网、账户系统、多屏、云端图库、轮播和 OTA。
