# MVP 验证记录

日期：2026-10-19。范围：红米Android、iPhone iOS共用工程；本轮未连接手机、无Mac。

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
| Android构建 | debug和个人密钥签名release APK已构建；release约30.8MB，ARM32/64 |
| ESP构建/烧录 | ESP-IDF5.5.5通过，约889KB，4MiB factory分区；Wi-Fi连接成功 |
| 服务器服务 | SSH正常，systemd三服务active；内部API与MQTT连接正常；HTTPS私有CA验证通过 |
| 真实云端刷屏 | 下述SSH转发路径成功；已收到任务成功回报及UART整图CRC |
| 目视核对 | 摄像头照片与发送预览中的人物、肩部、长发、樱花对应；面板竖放，因此需按物理方向理解画面 |

## 硬件链路记录

公网443/8883流量未到达服务器，故临时将本机LAN端口14443/18883通过SSH转发到腾讯云HTTPS/MQTTS。ESP连接该LAN入口，TLS名称仍验证腾讯云IP，证书验证未关闭。该验证覆盖实际云端服务及实际面板，不覆盖公网端口连通性。

原始硬件样本已归档至本地`artifacts/hardware-20261019/frame.bin`，与该目录的任务记录、实拍及manifest对应。任务`55a5f76991c8e7c98ad911d5e49de6ff`，创建到成功约33.47秒；整图CRC32 `b67519a0`。状态依次为created、downloading、refreshing、succeeded。公开测试fixture现已改为程序生成的色块/图案；当前`artifacts/sample-frame.bin`和`sample-preview.png`由新fixture生成，不代表这次历史硬件任务。

成功后重复发布同一MQTT命令，服务端结果仍为succeeded且完成时间不变，串口仍为done，未再次刷新。原始事件记录见 `artifacts/cloud-refresh-verification.jsonl`。

额外实机检查：

- 创建专用测试图后故意修改云端文件，使下载内容与SHA-256不符；设备尝试下载后返回`download_or_integrity_failed`，屏幕未被覆盖，串口保留原成功CRC `b67519a0`。
- 随后正常图恢复任务`ea849dad927f701449087d0d4b398777`成功，约35.07秒，记录为`artifacts/cloud-recovery-verification.jsonl`。刷新期间另一个新请求得到HTTP409 `device_busy`。
- 正常结束后重启ESP，UART恢复为idle、RAM CRC归零；MQTT重新联网后仍回报同一已成功任务，云端成功时间保持不变，没有自动刷屏。证实NVS结果保留。
- 最终固件重新生成并恢复公网URL，临时LAN转发仅用于验证，不作为正式运行依赖。
- 最后重启时观察到单一SNTP时间源等候较久，已将固件改为三个备用时间源；本机分别验证三个服务均能返回时间。
- 最后补充云端占用权保持至结果确认，以防串口在屏幕刚完成时抢先改变共享状态。该修正与时间源修正已重新构建、烧录并打包；以上完整刷屏记录来自此前测试，最终二进制未另做一次完整刷屏。

实拍：`artifacts/screen-snapshot-044.jpg`。面板颜色比电脑预览柔和；本次只核对内容、构图和可见边缘，未做仪器色差测量。界面截图`artifacts/app-editor.png`和`artifacts/app-preview.png`来自Flutter测试环境，非手机截图。

桌面Flutter测试生成预览约0.7–0.8秒，不能代替红米性能测量。移动版锐化与Pillow内部取整不保证逐字节相同，但预览和发送二进制严格一致。

## 待验收

- 腾讯云入站TCP443/8883放通后的公网直连（包括ESP独立重连、手机蜂窝网络）。
- 红米安装、系统选图器、EXIF/透明/大图、多指手势、前后台恢复、真实耗时及App到屏幕全流程；当前`adb devices`为空。
- macOS/Xcode构建签名、iPhone相册/HEIC、Keychain、TLS、手势、预览与实际刷屏。
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
