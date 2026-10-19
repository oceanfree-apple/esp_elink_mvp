# 接口与运维

## 链路及配置

App → HTTPS443 → Nginx → FastAPI（127.0.0.1:8000）→ Mosquitto（内部127.0.0.1:1883）→ MQTTS8883 → ESP。ESP 从 HTTPS 下载原始打包图。App 前台每秒查询设备及最新任务，后台暂停，回到前台恢复。

`ssh tencent` 当前指向 `42.194.237.249`。服务器配置在 `/etc/elink/`，代码及 venv 在 `/opt/elink/`，SQLite 与图像在 `/var/lib/elink/`。服务为 `elink-api`、`mosquitto`、`nginx`。凭据文件600权限，MQTT密钥仅对所需服务组可读。

已从实例元数据确认这是广州地域CVM，实例`ins-jn8457i8`；控制台应修改实例绑定的安全组入站规则。逐步操作见[公网端口设置](cloud-access.md)。

本地私有配置 `.private/settings.json` 是生成与部署源；CA私钥、服务端私钥、Android签名密钥及密码也在 `.private/`。CA公钥证书位于 `mobile/assets/cloud_ca.pem` 与 `firmware/main/cloud_ca.pem`，服务器证书含公网IP SAN，ESP使用SNTP校时并校验名称、证书链及有效期。

SNTP配置了腾讯、阿里与pool.ntp.org三个时间源，避免单个时间服务失效时一直等候。未获得可信证书校验所需时间前显示`cloud=waiting_time`，不会跳过TLS时间校验。

## HTTP

除 `/health` 外必须使用 `Authorization: Bearer <token>`。App令牌与设备下载令牌不同。

| 接口 | 请求与返回 |
| --- | --- |
| `GET /health` | 进程与MQTT连接状态，无凭据 |
| `GET /v1/device` | App；规格、online、busy、last_seen、state、latest_job |
| `POST /v1/images` | App；application/octet-stream，192000字节；返回image_id、sha256、size |
| `POST /v1/refresh-jobs` | App；JSON image_id、idempotency_key；返回任务记录 |
| `GET /v1/refresh-jobs/{id}` | App；返回任务状态、error及时间戳 |
| `GET /v1/device/images/{id}` | 设备；返回打包图和X-Image-SHA256 |

色码仅允许0/1/2/3/5/6，每字节高半字节为左像素；宽800、高480，按行扫描，服务端及固件都校验。上传返回摘要必须与App本地SHA-256一致。

401表示凭据错误，404表示资源不存在，409表示设备离线/忙或幂等键冲突，422表示输入或图像非法，503表示broker不可用。同一个幂等键+图像返回原任务，避免HTTP丢响应后重复刷屏。用户明确再次点击已结束任务的刷新按钮会生成新幂等键。

任务状态：`created → dispatched → downloading → refreshing → succeeded`；失败为`failed`；4分钟未获最终回报为`uncertain`，可在迟到的正确成功回报后收敛。`succeeded`只接受对应图片摘要，不能把MQTT PUBACK或HTTP上传成功当作刷屏成功。

## MQTT与固件

主题前缀：`elink/v1/frame-001/`。

- `command`：API发布，设备订阅；QoS1，不retain；JSON含v、job_id、image_id、sha256、size、expires_at、issued_at_us。API在有效期60秒内重发未开始任务。
- `events`：设备发布，API订阅；QoS1，不retain；boot_id、job_id、sha256、state、error。空闲/刷新时约10秒心跳。
- `presence`：设备连接声明online=true，遗嘱online=false，retain；服务器不把历史retain在线消息当作新心跳。45秒无新事件视为离线。

设备在NVS记录最近任务ID、顺序和结果，重复任务只回报，早于最近任务的指令不执行。每次下载最多3次、总预算45秒，完整下载并核验SHA-256及色码后才刷屏。刷新期间仍发送心跳、响应串口状态。重启发现未完成任务返回uncertain，不自动重刷。

串口与云端共享互斥状态；UART接收超时30秒后可重新接收云任务。屏幕BUSY超时保持启用。当前状态指驱动结果，无法单凭软件状态证明实际颜色，应结合实物。

云任务持有整段下载、刷新和结果确认期间的独占权，结果确认后再释放给串口，避免仅凭屏幕任务短暂进入done就接收下一张图。

## 部署、诊断、备份

```bash
python3 tools/provision.py
python3 tools/deploy.py
python3 tools/cloud_check.py
# 公网未放通时可用SSH检查服务，仍验证真实TLS证书
python3 tools/cloud_check.py --ssh
# 以下会实际覆盖屏幕画面
python3 tools/cloud_check.py --send artifacts/sample-frame.bin
ssh tencent 'sudo systemctl status elink-api mosquitto nginx --no-pager'
ssh tencent 'sudo journalctl -u elink-api -n 50 --no-pager'
```

部署需要服务器已安装 python3-venv、mosquitto、mosquitto-clients、nginx。更新时同步本地代码，`tools/deploy.py`安装依赖、更新配置并重启服务；不会删除任务数据库或图像。个人服务不做无中断滚动发布，应等当前刷新结束再部署。

备份时先停止`elink-api`以冻结SQLite，再用root备份`/var/lib/elink`及`/etc/elink`，完成后启动服务；本地另行离线备份整个`.private/`。备份包含秘密，应限制权限和访问。恢复到相同IP、相同CA和签名密钥时可继续使用现有App/固件；IP或CA改变需要重发服务器证书并更新客户端配置/信任。

图像7天后自动清理，执行中的任务文件受保护，任务元数据留存SQLite。无持久图像缓存的ESP重启后屏幕可保持画面，但UART RAM CRC变为0。

公网失败时先检查腾讯云实例防火墙/安全组TCP443/8883，再检查主机监听与防火墙。`cloud=offline cloud_error=32794`表示ESP TLS握手失败，需结合服务端抓包判断网络或证书原因；不得直接关闭校验绕过。`waiting_time`表示尚未获得可用于证书校验的网络时间。
