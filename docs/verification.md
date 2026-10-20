# MVP 验证记录

更新：2026-10-20。范围：红米Android、iPhone iOS共用工程；本地Ubuntu与GitHub macOS构建。iPhone已连接、通过USB配对并成功签名安装，正在处理首次信任/开发者模式，真机运行及手机操作待验收。

## 已验证

| 项目 | 结果 |
| --- | --- |
| 方案落盘 | [MVP方案](mvp-plan.md)、[iPhone自测计划](ios-free-testing-plan.md) |
| 云端单元测试 | 鉴权、错误长度/色码、离线、忙、幂等、下载权限、状态不可倒退、错误摘要、超时，已通过 |
| Flutter静态检查 | 无问题 |
| Flutter测试 | 裁剪数学、Python抖动参考、完整图像及预览、选图/旋转/预览/返回编辑，已通过 |
| 裁剪覆盖 | 三种宽高、每种500组随机旋转/缩放/位移，四角均在源图内 |
| 算法参考 | 固定32×16 RGB输入，Burkes六色量化及打包与原Python逐字节一致 |
| 预览一致性 | 800×480、192000字节、全部色码合法，PNG像素来自同一打包数据 |
| Android构建 | 共享代码已同步构建个人签名release，30816383字节，Flutter运行时及AOT为ARM32/64，签名验证通过且证书保持一致 |
| iOS构建与安装 | GitHub Linux检查和macOS/Xcode26.2构建成功，arm64真机Release 0.1.0（1），已下载、注入私人配置并在Ubuntu免费签名安装；USB查询与实际描述文件核对通过 |
| iPhone USB | iPhone15Pro/iOS26.7.1已连接、信任并通过配对验证；读取到ProductType=iPhone16,1 |
| ESP构建/烧录 | ESP-IDF5.5.5通过，约889KB，4MiB factory分区；Wi-Fi连接成功 |
| 服务器服务 | SSH正常，systemd三服务active；内部API与MQTT连接正常；HTTPS私有CA验证通过 |
| 真实云端刷屏 | 临时SSH与最终公网直连均成功；公网任务34.77秒，UART整图CRC一致 |
| 目视核对 | 白天实拍的黄色圆形、绿色三角形、六色色块及边界与公网任务预览对应，面板物理竖放 |

## 2026-10-19：临时SSH链路记录

公网443/8883流量未到达服务器，故临时将本机LAN端口14443/18883通过SSH转发到腾讯云HTTPS/MQTTS。ESP连接该LAN入口，TLS名称仍验证腾讯云IP，证书验证未关闭。该验证覆盖实际云端服务及实际面板，不覆盖公网端口连通性。

原始硬件样本已归档至本地`artifacts/hardware-20261019/frame.bin`，与该目录的任务记录、实拍及manifest对应。任务`55a5f76991c8e7c98ad911d5e49de6ff`，创建到成功约33.47秒；整图CRC32 `b67519a0`。状态依次为created、downloading、refreshing、succeeded。公开测试fixture现已改为程序生成的色块/图案；当前`artifacts/sample-frame.bin`和`sample-preview.png`由新fixture生成，不代表这次历史硬件任务。

成功后重复发布同一MQTT命令，服务端结果仍为succeeded且完成时间不变，串口仍为done，未再次刷新。原始事件记录见 `artifacts/cloud-refresh-verification.jsonl`。

额外实机检查：

- 创建专用测试图后故意修改云端文件，使下载内容与SHA-256不符；设备尝试下载后返回`download_or_integrity_failed`，屏幕未被覆盖，串口保留原成功CRC `b67519a0`。
- 随后正常图恢复任务`ea849dad927f701449087d0d4b398777`成功，约35.07秒，记录为`artifacts/cloud-recovery-verification.jsonl`。刷新期间另一个新请求得到HTTP409 `device_busy`。
- 正常结束后重启ESP，UART恢复为idle、RAM CRC归零；MQTT重新联网后仍回报同一已成功任务，云端成功时间保持不变，没有自动刷屏。证实NVS结果保留。
- 最终固件重新生成并恢复公网URL，临时LAN转发仅用于验证，不作为正式运行依赖。
- 最后重启时观察到单一SNTP时间源等候较久，已将固件改为三个备用时间源；本机分别验证三个服务均能返回时间。
- 最后补充云端占用权保持至结果确认，以防串口在屏幕刚完成时抢先改变共享状态。该修正与时间源修正已重新构建、烧录并打包；本节记录来自此前测试，修正后的最终二进制于2026-10-20完成下文的公网刷新。

实拍：`artifacts/screen-snapshot-044.jpg`。面板颜色比电脑预览柔和；本次只核对内容、构图和可见边缘，未做仪器色差测量。界面截图`artifacts/app-editor.png`和`artifacts/app-preview.png`来自Flutter测试环境，非手机截图。

桌面Flutter测试生成预览约0.7–0.8秒，不能代替红米性能测量。移动版锐化与Pillow内部取整不保证逐字节相同，但预览和发送二进制严格一致。

## 待验收

- 手机Wi-Fi/蜂窝网络及实际操作发起的刷新；公网脚本刷屏、UART与白天实物核对已通过。
- 红米安装、系统选图器、EXIF/透明/大图、多指手势、前后台恢复、真实耗时及App到屏幕全流程；当前`adb devices`为空。
- iPhone首次信任/开发者模式、独立启动、相册/HEIC、Keychain、TLS、手势、预览与实际刷屏；真机Release构建及签名安装已通过。
- 真正断电发生于刷屏中、面板BUSY故障等破坏性硬件场景未制造；当前依赖代码状态机与服务端异常测试，不声称已经实机覆盖。

后续变更与额外硬件检查结果补记于本文末尾，避免将模拟/中转验证描述为公网或手机验收。

## 2026-10-19：iPhone接线前准备

- 已实现空公共连接资源及私人安装包的自动加载、保存和覆盖更新；首次启动无需输入地址或令牌。Android原有构建参数仍可作为开发回退。
- 已实现macOS未签名Release构建工作流、IPA打包、按提交及SHA-256下载核验、本地配置注入和产物保留策略。尚待GitHub授权，未运行云端iOS构建，也没有可供签名的真实IPA。
- 已用临时`.app`归档测试打包/注入：只改变配置资源，原公开IPA不变，可执行权限/框架符号链接保留；错误摘要、版本元数据、路径、配置、输出目录会被拒绝。
- 本地15项Python测试（3项服务端、12项IPA流程）、8项Flutter测试通过，`flutter analyze`无问题。
- 已安装官方iloader2.3.10并核对发布资产SHA-256；usbmuxd、libimobiledevice及动态库就绪，服务正常启动。未连接iPhone，未验证配对、Apple登录、签名或安装。
- 公网复查：SSH和云内HTTPS健康检查正常，三服务active、443/8883监听，主机防火墙未限制这两个端口。办公室Ubuntu的TCP443连接建立后TLS仍超时，期间服务器抓包未看到对应443/8883流量；因此还需从实例防火墙/安全组及办公室中间路由定位，不能断言已打通或仅是服务器应用问题。
- 安装及续签步骤见[iOS构建与USB安装](ios-installation.md)。明日接线后再验收iPhone15Pro/iOS26.7.1的相册、HEIC、Keychain、TLS、手势和手机发起的摄像头闭环。

2026-10-20凌晨补记：仅从公开提交检出的干净工作区重跑15项Python测试、8项Flutter测试及静态检查，均通过；公开集合119个文件通过发布检查。iloader在当前Ubuntu桌面成功显示窗口，未进行Apple登录。首次GitHub设备码到期，当前仍未取得账号授权，仓库尚未推送、未生成真实iOS IPA；已请求用户方便时重新进行浏览器授权。

## 2026-10-20：GitHub授权和公网恢复

GitHub设备授权完成，并以`GET /user`确认登录为`oceanfree-apple`；已创建公开仓库`oceanfree-apple/esp_elink_mvp`，开始首次CI构建。Apple凭据不参与该流程。

腾讯云实例元数据确认为广州CVM `ins-jn8457i8`。用户保存443/8883入站安全组规则后，Ubuntu直接访问公网IP，`/health`返回`ok=true,mqtt_connected=true`，App鉴权查询返回`online=true,busy=false`；8883通过项目CA及主机名验证、建立TLS1.3。以上未使用SSH转发，表明安全组修改后的公网服务连接与ESP在线已恢复。实际图像下载刷屏及手机闭环尚待单独测试。

随后完成一次公网脚本刷新，使用程序生成的合成图案：

| 项目 | 结果 |
| --- | --- |
| 任务 | 09738f8f3bbce986adb2c63fcb20e6e3 |
| 图像 | 6783d30a0135dbefb7216ddb39ba8410，192000字节 |
| SHA-256 | e75ad68686e2d52b643b0b4b78a63c5ce389b4d04d8f3763bca291e7c751ac82 |
| 状态与耗时 | created → dispatched → refreshing → succeeded，34.77秒 |
| UART | state=done，received=192000，crc=d06c94f7，cloud=connected，cloud_error=0 |
| 传输 | 公网直连，无SSH/LAN转发；最终公网固件成功执行 |
| 摄像头 | 前后照片均几乎全黑，延长采集等待后仍无法识别面板内容，不能判定实际画面对应 |

本地证据：`artifacts/public-20261020/`包含frame.bin、preview.png、refresh.jsonl、uart-status.txt、manifest.json、before.jpg和after.jpg。后续恢复照明/取景后再核对屏幕，并由iPhone实际发起另一任务验收。

首次iOS云端构建：[39284834109](https://github.com/oceanfree-apple/esp_elink_mvp/actions/runs/39284834109)，对应源码提交`d4a854ea9e70053d3a33d6bbaca9f18ec43fe914`。触发后处于queued，尚无运行器和构建产物；[GitHub官方状态页](https://www.githubstatus.com/)同时报告Actions、Pages和Webhooks服务降级（事件始于2026-10-19 15:49 UTC，北京时间23:49），可能导致本次排队延迟。该状态不代表检查或macOS构建已通过。

## 2026-10-20白天：真实IPA及实物核对

工作流现为completed/success，Linux检查、Xcode选择、Flutter编译、IPA打包和产物上传步骤全部成功。实际工具链为Xcode26.2（17C52）、Flutter3.38.10、Dart3.10.9。Ubuntu昨晚的等待进程未完成下载，白天已实际下载、核验并生成私人配置包。

| 项目 | 结果 |
| --- | --- |
| 版本与平台 | 0.1.0（1），dev.elink.elinkFrame，arm64，iPhoneOS，最低iOS13.0，SDK iPhoneOS26.2 |
| 公开IPA | 6834406字节，SHA-256为1ac04b7fd4b05555755bdf8587d8d71ba7aeea34847803232d2bdda2fac3f057 |
| 产物ZIP | GitHub artifact 12202807285；SHA-256与GitHub提供的81984c01b47bae101d28482e2430eed3470a5624f297fd4454040f3fd4ca09c2一致 |
| 公共配置 | 注册的connection.json为空；无embedded.mobileprovision，尚未个人签名 |
| 自用IPA | 本地.private/ios/mojian-configured.ipa，6834472字节，权限600；连接资料与现有私人配置一致 |
| 归档一致性 | SHA、ZIP CRC、文件列表、可执行权限全部校验；仅连接资源改变，其余文件内容逐项相同 |
| 真机安装 | iPhone暂未连接，未进行Apple登录、签名、安装或独立启动验证 |

详细本地记录：`artifacts/ios/local-verification.json`、`artifact-verification.json`及`toolchain.txt`。公开源IPA和私人配置包均已落盘，不依赖Actions产物保留期。

白天补拍`artifacts/public-20261020/daylight.jpg`，屏幕完整进入画面；对照同目录preview.png，黄色圆形、绿色三角形、六色色块顺序和边界均对应。面板物理竖放，内容相对源预览转过90度。用户确认夜间无照明，因此保留黑色夜间照片作为当时记录，以白天实拍补充目视核对。本次照片核对的是昨晚公网脚本任务`09738f8f3bbce986adb2c63fcb20e6e3`，未声称手机已发起刷新。

上述为早上未接线时的记录；当日后续已开始USB安装，见本文下一节。实际流程见[iOS安装说明](ios-installation.md)。

红米APK同步更新到与iOS构建相同的mobile源码树`390a864a96d509bbbea93c941c30f20c0ae1f5b5`，版本0.1.0（1）、API24起、Flutter运行时和AOT包含armeabi-v7a/arm64-v8a。`apksigner verify`通过，前后签名证书SHA-256一致；新版30816383字节，SHA-256为`64a6d866674a9eab38faff1f9e2bc377069275d1adf97029235079106f68f0cb`。本地`artifacts/SHA256SUMS`与`android-verification.json`已更新，旧APK备份保存在`.private/android/previous.apk`。红米实际安装、运行和刷新仍待手机连接后验证。

## 2026-10-20：iPhone配对与首次签名尝试

手机USB连接、解锁并信任Ubuntu。此前usbmuxd虽显示active，但本地socket队列阻塞，设备列表查询失败；恢复服务后`idevicepair validate`成功，读取到ProductType=iPhone16,1、ProductVersion=26.7.1。设备标识仅保留在本机私有目录。

iloader2.3.10已在桌面运行，用户在本机窗口登录Apple账号后导入已配置IPA。首次尝试在列举开发者团队时失败：`Failed to get anisette headers`，`new.ani.sidestore.io/v3/get_headers`返回HTTP502。此时查询未发现本项目已安装，不能记为签名或安装成功。

已核对该版本官方备用服务，并从Ubuntu进行不带账号的基础探测；三个Mac服务均有HTTP响应，空headers请求返回缺少identifier的预期错误，尚未验证完整签名。已请用户先切换`Jkcoxson (Mac)`重试，同类502时再试`StikStore (Mac)`。未删除配对或撤销证书。Apple密码与验证码不经过聊天、命令行或仓库。

用户随后报告同类502，报错网址仍为`new.ani.sidestore.io/v3/client_info`；本机只读取非敏感服务偏好，确认已保存为`ani3.stikstore.app`。核对官方账号源码后确认服务在登录时绑定，而签名复用原会话，因此更正操作为切换后退出、重新登录再导入IPA。此时尚不能说备用服务的完整认证也已尝试失败。

随后针对相同的`/v3/client_info`接口匿名复查：Jkcoxson (Mac)及StikStore (Mac)均返回HTTP200和`client_info`、`user_agent`字段；旧SideStore地址出现连接错误。脱敏探测结果保存在本机`.private/ios/anisette-probe.json`，完整登录、签名和安装仍待重试结果。

安装前公网复查仍为API正常、MQTT已连接、ESP在线且空闲，最近任务仍是此前脚本成功任务。已保存本次手机测试前的摄像头基准图`artifacts/iphone-20261020/before.jpg`；真正手机选图、刷新及之后的实拍尚待安装完成。

切换StikStore (Mac)并重新登录后，用户报告安装成功并看到墨间图标；USB查询独立确认应用版本0.1.0、构建1已安装。只复制本项目的签名描述文件并解码，实际application-identifier与已安装Bundle ID匹配。有效期实测7天，2026-10-27 20:35（北京时间）到期，建议10月25日续签。Team、改写后的Bundle ID、描述文件和到期时间保存在本机`.private/ios/signing-record.json`及profiles目录，未公开。

手机首次打开提示开发者信任或开发者模式，已提供对应设置路径；独立运行和手机发起的刷新仍未记为通过。
