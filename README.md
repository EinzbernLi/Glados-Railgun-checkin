# GLaDOS / Railgun 自动签到

模块化、可测试的 GLaDOS 与 Railgun 多账号签到脚本。默认每天由 GitHub Actions 计划运行两次，同时保留旧 `python checkin.py` 入口和旧 Secret 名称。

> GitHub `schedule` 不保证准点。当前 cron `0 4,10 * * *` 对应香港/北京时间计划时刻 12:00、18:00，但实际启动可能延迟。

## 安全边界

- Cookie 只发送到经过校验的 HTTPS 签到域名。
- 通知服务永远不会收到 Cookie。
- 日志、`--dry-run` 和错误摘要不输出 Cookie、token、sendkey 或 chat ID。
- CI 不读取 Secrets，也不执行真实签到或通知。
- 普通代码 push 不触发签到 workflow。

## 环境变量

| 名称 | 必需 | 默认值 | 兼容/作用 |
|---|---:|---|---|
| `GLADOS_COOKIES` | 是 | 无 | 旧 Secret 保持兼容；多个 Cookie 用 `&` 分隔 |
| `GLADOS_DOMAINS` | 否 | `glados.cloud,railgun.info` | 逗号分隔的纯主机名 |
| `GLADOS_ALLOW_CUSTOM_DOMAINS` | 否 | `false` | 自定义域名的显式安全开关 |
| `GLADOS_EXCHANGE_PLAN` | 否 | `plan500` | 旧 Secret 保持兼容；可选 `plan100/plan200/plan500` |
| `GLADOS_ENABLE_EXCHANGE` | 否 | `true` | 是否在积分达到门槛时兑换 |
| `GLADOS_VERBOSE` | 否 | `false` | 旧 Secret 保持兼容 |
| `GLADOS_RETRY_MAX` | 否 | `2` | 重试次数，范围 0–5；最大尝试次数为该值 + 1 |
| `GLADOS_RETRY_BACKOFF` | 否 | `0.5` | 指数退避基数秒数，范围 0–10 |
| `GLADOS_CONNECT_TIMEOUT` | 否 | `5` | 连接超时，范围 1–30 秒 |
| `GLADOS_READ_TIMEOUT` | 否 | `15` | 读取超时，范围 1–60 秒 |
| `PUSHDEER_SENDKEY` | 否 | 无 | 旧 PushDeer Secret，存在即启用 |
| `PUSHPLUS_TOKEN` | 否 | 无 | 旧 PushPlus Secret，存在即启用 |
| `TG_BOT_TOKEN` | 否 | 无 | Telegram bot token |
| `TG_CHAT_ID` | 否 | 无 | Telegram chat ID；必须与 token 同时配置 |

空通知 Secret 等同未配置。多个渠道凭证同时存在时会逐个发送；任一已配置渠道失败会使程序返回非零，但不会阻止后续渠道尝试。完全不配置通知时，签到仍可成功。

### 多账号示例

Repository Secret `GLADOS_COOKIES` 使用：

```text
fake-cookie-account-1&fake-cookie-account-2
```

请不要把真实 Cookie 写入仓库、Issue、日志或测试。

### 自定义域名限制

默认只允许 `glados.cloud` 与 `railgun.info`。自定义值必须：

- 同时设置 `GLADOS_ALLOW_CUSTOM_DOMAINS=true`；
- 是纯 DNS 主机名；
- 不含协议、路径、userinfo、端口；
- 不是 IP 地址。

应用始终使用 HTTPS。

## 本地配置检查

安装运行依赖：

```powershell
python -m pip install -r requirements.txt
```

只使用虚假值验证配置，不进行任何网络请求：

```powershell
$env:GLADOS_COOKIES = "fake-cookie-a&fake-cookie-b"
$env:PUSHPLUS_TOKEN = "fake-token"
python checkin.py --dry-run
```

输出只包含账号数、域名、兑换计划、重试次数和渠道名称，不包含凭证。

## 退出码

- `0`：全部签到成功或今日已签到，且所有已配置渠道发送成功。
- `1`：至少一个签到任务失败，或至少一个已配置通知渠道失败。
- `2`：配置错误；未开始网络请求。

“今日已签到”是正常结果，不会制造失败。

## 重试与兑换

HTTP 仅有一层重试。连接错误、超时、429、500、502、503、504 可重试；401、403 和其他普通 4xx 不重试。支持 `Retry-After`，指数退避与最大等待均有上限。

状态查询失败后仍尝试签到。签到后可继续查询积分用于诊断。只有积分查询成功、兑换启用且积分达到门槛时才兑换；积分不足不会调用兑换接口。

## 测试

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q src tests checkin.py
```

所有测试使用 fake 凭证和注入的 HTTP 边界，不访问真实签到、兑换或通知服务。

## GitHub Actions

- `.github/workflows/ci.yml`：源码、测试、依赖或 workflow 变化时运行；无 Secrets。
- `.github/workflows/gladosCheck.yml`：仅 `schedule` 与 `workflow_dispatch`；cron 保持 `0 4,10 * * *`。
- 定时 job 使用单一 Python 3.12、`contents: read`、3 分钟超时，不运行 pytest、不升级 pip、无 matrix、keepalive 或历史运行删除。
- `actions/checkout@v6` 固定到 `d23441a48e516b6c34aea4fa41551a30e30af803`。
- `actions/setup-python@v6` 固定到 `ece7cb06caefa5fff74198d8649806c4678c61a1`。

## 人工上线顺序

1. 保留现有 Secrets，不要删除旧变量。
2. 提交代码后先观察无 Secret 的 CI。
3. 人工检查 workflow diff 和 `--dry-run` 输出。
4. 只有在明确授权后，才手动触发一次真实签到。
5. 核对两个默认域名、全部账号、兑换和所有渠道。
6. 再观察至少两个原定 cron 周期。

本次模块化改造本身不会修改 Secrets、启用 workflow 或触发真实签到。

## 回滚

远端升级前基线是 `4c00e5e2f542223021c69778c6e8b11212745fd3`。如需整体回滚，恢复到该 commit；旧 Secrets 与 cron 均保持不变。通知问题可先删除新增 Telegram Secrets，继续使用旧 PushDeer/PushPlus。

## 许可证与来源

本项目继续使用 [GNU GPL-3.0](LICENSE)。

- 原项目与主要来源：`EinzbernLi/Glados-Railgun-checkin`。
- 模块边界参考 GPL-3.0 项目：`EinzbernLi/Glados_checkin@f29e6e33ca16b319eca9ea810ead7cf53aed92a1`。
- 多渠道注册表思想参考 `yangmeng611/GLaDOS-CheckIn@0a8333409eeb4c8445ceacb3a4043aab7ab9b988`；该仓库无可识别许可证，本项目未复制其实质代码。

本次改造并非声称上述参考代码为原创；所有新增与改写代码继续按 GPL-3.0 发布。
