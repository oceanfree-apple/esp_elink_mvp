# iOS云端构建与Ubuntu USB安装

更新：2026-10-20。设备：iPhone 15 Pro / iOS 26.7.1。用户已授权先做所有不依赖接线的准备。

## 已完成与待完成

| 环节 | 当前状态 |
| --- | --- |
| Flutter自动连接 | 已实现并通过测试；私人安装包首次启动读取配置，写入Keychain；新包的有效配置可以覆盖旧配置 |
| 公开源码准备 | 已排除私有目录、Wi-Fi/设备凭据头文件和个人安装包；测试图片已换为程序生成的图案，已建立本地Git提交 |
| Actions工作流 | 已写入`.github/workflows/ios.yml`；Linux检查通过后在macos-15/Xcode26.2构建Flutter3.38.10 Release |
| IPA打包、下载、注入 | 已实现；通过归档内容、摘要、权限、符号链接、错误配置与篡改测试 |
| GitHub授权、发布、首次云端构建 | 首次浏览器授权码已过期，尚未获得授权；用户方便时重新生成短码。尚未推送或产出真实iOS IPA |
| Ubuntu安装环境 | 已安装官方iloader2.3.10、usbmuxd及libimobiledevice工具；动态库齐全；USB服务已启动 |
| iPhone安装、Keychain、HEIC、实际刷新 | 等待接线；当前没有连接iPhone，不能记为已通过 |
| 公网HTTPS/MQTTS | 服务内部正常；办公室Ubuntu直连443 TLS超时，尚待核实实例防火墙/安全组与办公室路由 |

## 接线前的构建与配置

以下命令在仓库根目录执行。GitHub登录时，用户在自己的浏览器中完成设备授权；不在终端参数或聊天中填写密码。

```bash
gh auth login --hostname github.com --web --scopes workflow
gh auth status
gh auth setup-git --hostname github.com
```

实际发布前核对登录用户是`oceanfree-apple`，检查目标仓库是否已有内容，再创建或复用公开仓库`oceanfree-apple/esp_elink_mvp`。执行`python3 tools/check_public.py`检查Git跟踪的发布集合；私有`.private/`不上传。

Actions对主分支相关代码更新或手动触发执行检查和构建；PR只运行检查。公开产物`ios-unsigned`包括未签名IPA、`build-info.json`、`SHA256SUMS`及工具链信息；里面的`assets/connection.json`必须为空。使用标准免费runner，产物3天过期、最多留两份，不使用付费runner或构建缓存。

构建成功后：

```bash
# 可用 --run 指定某次构建，避免下载其他提交。
python3 tools/fetch_ios.py --wait
python3 tools/prepare_ios.py
```

下载脚本只接受成功的工作流，核对提交、SHA-256及空配置。预处理脚本再核对Release/未签名标记、版本和Bundle ID，从本地`.private/settings.json`读取现有云端连接资料，生成：

- `artifacts/ios/mojian-unsigned.ipa`：保留的公开原包。
- `.private/ios/mojian-configured.ipa`：只在Ubuntu保留的自用包，等待签名。
- `.private/ios/mojian-configured.json`：原包/自用包摘要及构建提交，不含连接凭据。

自用IPA不能上传到公开仓库、Actions或公开下载区。预处理不使用Apple账号；必须完成注入后再签名。

## iPhone接线后的安装

1. 使用能传数据的USB线连接办公室Ubuntu，解锁手机，在手机上选择“信任此电脑”并输入手机锁屏密码。
2. 读取设备列表并验证配对；列表中的设备ID保留本地，不复制到公开记录。

   ```bash
   systemctl is-active usbmuxd
   idevice_id -l
   idevicepair validate
   # 若提示尚未配对，保持手机解锁后执行，再按手机提示信任。
   idevicepair pair
   ideviceinfo -k ProductType
   ideviceinfo -k ProductVersion
   ```

   无设备时先检查线材和USB口；服务未运行时用`sudo systemctl start usbmuxd`。今天没有iPhone，因此空列表属于预期情况，尚未验证配对。

3. 在Ubuntu桌面启动`iloader`。由用户在其窗口中登录Apple账号，完成必要的双重认证，不将账号密码或验证码放入项目、命令行或Actions。选择导入自己的IPA，文件为`.private/ios/mojian-configured.ipa`。工具处理个人证书、描述文件、框架签名与USB安装。
4. 按手机实际提示开启“设置 → 隐私与安全性 → 开发者模式”，可能需要重启；如出现开发者信任提示，在“设置 → 通用 → VPN与设备管理”完成信任。入口和提示以手机实际系统为准。
5. 在桌面独立打开“墨间”。首次启动不填写URL、令牌或项目账号；应能查询云端并显示相框状态。再验证相册JPEG/PNG/HEIC、EXIF方向、双指缩放/旋转、预览和前后台恢复。

同一Apple账号如已有开发证书，先核对再使用，避免为安装本项目随意撤销其他应用仍在使用的证书。当前仅验证了iloader可启动及依赖完整；Apple认证、免费签名和iOS26.7.1安装必须接线后实测。[官方说明支持导入任意IPA](https://github.com/nab138/iloader#features)。[2.3.10发布说明](https://github.com/nab138/iloader/releases/tag/v2.3.10)提到当周Apple认证不稳定并更新认证服务列表，实际错误需要保留脱敏日志后处理。

## 公网检查与真正的刷新验收

安装前或云端构建期间，先确认：

```bash
python3 tools/cloud_check.py
# 仅用于区分服务与公网路径故障，不能作为公网通过的证据。
python3 tools/cloud_check.py --ssh
```

如果普通检查TLS超时，而SSH检查正常，核查腾讯云实例入站TCP443/8883，以及办公室网络路径；不关闭TLS校验。手机用Wi-Fi、蜂窝网络各验证一次；ESP应独立通过公网MQTTS上线并能HTTPS下载。

完整验收必须由iPhone实际点击刷新：先拍屏幕基准图，手机选图/编辑/确认并记录预览，再点击刷新；记录该次任务ID和摘要，等待设备成功回报，随后通过C270取景与该预览核对。保存证据在本地`artifacts/`，记录到[验证记录](verification.md)。目前尚未完成这次手机闭环。

## 免费续签与覆盖安装

首次成功后记录实际签名Team、Bundle ID和到期时间到`.private/ios/`。保持同一Apple账号及签名应用标识，每5～6天USB连接Ubuntu，用同一份已配置IPA在iloader中重新签名并覆盖安装；无代码改动无需重新运行CI。不要先卸载应用。覆盖安装后验证独立启动、自动连接和Keychain仍正常，再记录新的到期时间。

公开Actions产物可能已过期，因此本地保留最新公开原包和已配置IPA。认证资料和工具日志位于用户本机；分享诊断前过滤密码、验证码、私钥、令牌及设备配对资料。

## 本轮验证命令

```bash
.venv/bin/python -m pytest server/tests tools/tests -q
cd mobile
flutter analyze
flutter test --reporter expanded
```

本地结果：15项Python测试、8项Flutter测试通过，静态检查无问题。另从仅包含公开提交的干净工作区重新执行以上检查，也全部通过；119个跟踪文件通过本机凭据扫描及发布路径检查。这些覆盖源码和本地打包流程，不代替macOS构建、iPhone签名安装或公网刷新验收。

iloader官方Deb下载摘要已与GitHub发布资产digest一致：`3a616475a619751336d2a1bf9762bf5050bbe984d121b5e414eab917515130b2`。重新安装工具时仍应从[官方发布页](https://github.com/nab138/iloader/releases/tag/v2.3.10)下载对应架构。
