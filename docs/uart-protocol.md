# 串口协议 v1

UART0：115200、8N1、无硬件流控。主机单连接、逐块请求确认；不允许多个发送方同时控制设备。

## 请求

所有整数为 little endian：

| 字段 | 长度 |
| --- | --- |
| Magic `EPD1` | 4 字节 |
| command | uint8 |
| sequence | uint32 |
| payload length | uint32 |
| CRC32 | uint32 |
| payload | 0～4100 字节 |

CRC32 使用 Python `zlib.crc32(command + sequence + length + payload)`，不包含 Magic 和 CRC 字段自身。固件使用 `esp_rom_crc32_le`。接收不足时等待 1.5 秒后重新寻找帧头。

| command | 含义 | payload |
| --- | --- | --- |
| 1 | STATUS | 空 |
| 2 | BEGIN | 总长度 uint32（必须 192000）+ 整图 CRC32 uint32 |
| 3 | DATA | offset uint32 + 最多 4096 字节图片 |
| 4 | COMMIT | 空；长度、整图 CRC 均正确后启动刷新 |

响应为 ASCII 行：`@EPD <sequence> OK <信息>\n` 或 `@EPD <sequence> ERR <错误>\n`。

STATUS 信息示例：`state=done received=192000 crc=12ab34cd version=1`。状态为 idle / receiving / refreshing / done / error。crc 表示本次开机以来最近成功刷新的图像；重启为 00000000。

错误包括 crc、size、offset、incomplete、image_crc、busy、command。长度错误或接收中断不触发屏幕刷新。上传闲置超过 30 秒，在处理下一条有效请求时清除上传状态；可以重新 BEGIN。刷新使用独立任务，因此主机仍可查询 STATUS。

主机每次请求最多尝试 3 次，每次响应等待 3 秒。重试沿用相同序号和内容；设备缓存最近一条有效请求的序号、CRC 和响应，避免重复 DATA 或 COMMIT 的副作用。该机制依赖逐块确认，不支持乱序流水线。开始新传输时重新 BEGIN，不支持断点续传。

COMMIT 应答只表示刷新任务已启动。主机继续查询 STATUS，必须同时满足 `state=done` 和整图 CRC 相同才报告成功；驱动 BUSY 超时返回 error。当前固件不进行图像识别，不能通过状态判断实物颜色或接线是否产生正确画面。

## 图像格式

800×480，按行从左到右、从上到下。每字节两个像素，高半字节为左像素。黑 0、白 1、黄 2、红 3、蓝 5、绿 6。整图 192000 字节。


## Station 状态扩展

STATUS v1 保持原字段，并追加 `wifi=disabled|starting|connecting|connected|disconnected|error ip=... rssi=... reason=...`。`reason` 为 ESP-IDF 断开原因代码，成功获取地址后清零。凭据不存在时为 disabled；SSID 和密码均不通过 STATUS 返回。

诊断命令 5：payload 为扫描结果索引 uint32，返回开机扫描缓存中的 `count`、`ssid_hex`、`rssi`、`channel`、`auth`。超出范围返回 `count=... end=1`。SSID 用 UTF-8 字节的十六进制表示，避免空格和特殊字符破坏响应行格式。扫描在后台启动阶段执行，最多缓存 32 个结果；没有新增用户侧扫描短命令。
