# Claude Telegram Bot Bridge

[English](README.md)

把你的 Telegram 变成远程 Claude Code 终端。随时随地与 Claude 对话、运行技能、编辑代码、搜索文件。

## 解决什么问题？

Claude Code 很强大，但它绑定在你的终端里。当你离开电脑 — 通勤、开会、或者只是躺在沙发上 — 你就失去了访问能力。没法快速看看构建结果、让 Claude 修个 bug、或者跑一个技能命令，得等回到桌前才行。

[OpenClaw](https://github.com/anthropics/openclaw) 这样的方案确实存在，但代价不小：需要部署和维护一整套 Web 服务栈，通过 Web 界面暴露开发环境有安全隐患，而且仅仅为了临时的移动办公需求去搭建一套重量级基础设施，实在是杀鸡用牛刀。

这个 Bot 走了一条不同的路 — **轻量、零基础设施、默认安全**。它把 Claude Code SDK 接入 Telegram Bot（一个你手机上已经有的应用），让你拥有一个持久化的、永远在线的 Claude Code 会话。不需要 Web 服务器、不需要暴露端口、不需要额外的认证层。为一个项目目录启动一次，它就作为守护进程在后台运行 — 崩溃自动重启、Mac 重启后自动启动、依赖自动管理。Telegram 本身负责认证、加密和推送通知。

## 功能特性

**核心能力**
- 在 Telegram 中直接与 Claude 对话，由 Claude Code SDK 驱动
- 远程调用任何 Claude Code 技能 (`/skill <name>`) 或斜杠命令 (`/command <cmd>`)
- 通过 `/model` 在 Sonnet、Opus、Haiku 之间随时切换
- 使用 `/resume` 恢复历史对话，浏览会话记录
- 使用 `/history` 查看最近对话历史 — 显示当前会话最近 5 条消息
- 使用 `/revert` 回退到任意历史消息 — 支持 5 种模式：完整恢复（代码+对话）、仅对话、仅代码、从此处总结、取消

**智能交互**
- 渐进式流式响应：AI 回复实时更新，边思考边显示，而非等待完成后才展示
- Claude 输出的编号选项自动转为 Telegram 内联按钮 — 点击即选
- 响应中的文件路径（图片、PDF 等）自动作为照片或文档发送
- 原生语音消息支持：自动下载、格式识别/转码（OGG/AMR → MP3）、Whisper 转写后继续交给 Claude 处理
- 每用户独立的 SDK 长连接 — 低延迟，支持并发消息（每用户最多 3 条）
- 优先级 `/stop` 命令：立即取消正在运行的任务和语音转写，即使消息队列已满
- 优先级 `/revert` 命令：绕过消息队列限制，取消活动操作，将对话状态恢复到任意历史点

**安全**
- 项目目录内的文件访问自动放行
- 访问项目外文件时触发 Telegram 内联按钮确认
- 通过 `ALLOWED_USER_IDS` 设置用户白名单
- 超过 20 分钟的过期消息自动丢弃

**运维**
- 守护进程模式，崩溃自动重启（60 秒内连续崩溃 5 次则停止）
- 一条命令安装 macOS launchd 开机自启（`--install`）
- 启动时自动检测更新 — 有新版本时提示
- 一条命令升级（`--upgrade`）— 拉取最新代码并重装依赖
- 基于 MD5 的依赖缓存 — `requirements.txt` 未变则跳过安装
- 自动创建 venv、14 天日志自动清理、崩溃日志含退出码

## 前置条件

- **Python 3.11+**
- **Claude CLI** — 已安装并在 `$PATH` 中，或通过 `CLAUDE_CLI_PATH` 指定
- **Telegram Bot Token** — 从 [@BotFather](https://t.me/BotFather) 获取
- **ffmpeg** — 语音格式转换必需
- **OpenAI API Key** — Whisper 转写必需（`OPENAI_API_KEY`）

## 快速开始

```bash
git clone https://github.com/terranc/claude-telegram-bot-bridge
cd claude-telegram-bot-bridge
claude
```

然后运行 `/setup`。Claude Code 会处理一切：系统检查、Bot Token 收集、依赖安装和配置。

> **注意：** 以 `/` 开头的命令（如 `/setup`）是 [Claude Code 技能](https://code.claude.com/docs/en/skills)。请在 `claude` CLI 提示符中输入，而非在普通终端中。

设置完成后，启动 Bot：

```bash
./start.sh --path /path/to/your/project
```

<details>
<summary>备选方案：直接运行安装脚本</summary>

如果你不想使用 Claude Code，可以直接运行安装脚本：

```bash
git clone https://github.com/terranc/claude-telegram-bot-bridge
cd claude-telegram-bot-bridge
./setup.sh
```

然后启动 Bot：

```bash
./start.sh --path /path/to/your/project
```

</details>

### 常用命令

```bash
./start.sh --path /path/to/project              # 启动（前台）
./start.sh --path /path/to/project -d           # 启动（后台守护进程）
./start.sh --path /path/to/project --debug      # 调试模式
./start.sh --path /path/to/project --status     # 查看状态
./start.sh --path /path/to/project --stop       # 停止
./start.sh --path /path/to/project --upgrade    # 更新到最新版本
./start.sh --path /path/to/project --install    # 安装为 macOS 开机自启服务
./start.sh --path /path/to/project --uninstall  # 移除开机自启服务
```

## 使用场景

### 手机上修 Bug

你不在电脑旁，队友报了个 bug。打开 Telegram：

```
你：     登录页在邮箱包含加号时崩溃了
Claude:  找到问题了，在 src/auth/validator.ts:42 — 正则没有转义 + 字符。
         已修复，测试通过。
```

### 远程运行技能

```
你：     /skill commit
Claude:  已创建提交: fix(auth): escape special characters in email validation
```

### 发送语音消息

```
你：     [发送 Telegram 语音消息]
Bot:     🎤 Voice: summarize yesterday's git diff
Claude:  下面是昨天代码变更的摘要...
```

### 恢复昨天的工作

```
你：     /resume
Bot:     1. 重构 auth 模块 — 2 小时前
         2. 添加暗色模式 — 昨天
         3. API 限流 — 3 天前

你：     1
Bot:     已切换到会话: 重构 auth 模块

你：     我们上次做到哪了？
Claude:  我们已经把 JWT 逻辑抽离到了独立的 service。
         还剩下：更新 middleware 使用新 service...
```

### 查看最近对话历史

```
你：     /history
Bot:     📜 Recent History (last 5 messages)

         🧑 User [2026-03-05 14:23:15]
         修复登录 bug

         🤖 Assistant [2026-03-05 14:23:18]
         找到问题了，在 src/auth/validator.ts:42...

         🧑 User [2026-03-05 14:25:30]
         给这个加个测试

         🤖 Assistant [2026-03-05 14:25:35]
         已在 tests/auth.test.ts 添加测试...
```

### 回退到历史对话状态

```
你：     /revert
Bot:     🔄 选择要回退到的消息：
         [显示最近 50 条消息的分页列表，带内联按钮]

你：     [点击某条消息]
Bot:     选择回退模式：
         1️⃣ 恢复代码和对话
         2️⃣ 仅恢复对话
         3️⃣ 仅恢复代码
         4️⃣ 从此处总结
         5️⃣ 取消

你：     [点击"恢复代码和对话"]
Bot:     ✅ 已回退到消息 #42。对话和代码状态已恢复。
```

### 对话中切换模型

```
你：     /model haiku
Bot:     已切换到 Claude Haiku

你：     总结 src/api/ 最近 3 次提交的变更
Claude:  ...
```

### 让 Bot 7x24 运行

```bash
# 安装为 macOS 开机自启服务 — 重启后自动恢复
./start.sh --path ~/my-project --install

# 随时查看状态
./start.sh --path ~/my-project --status
# 🟢 Bot is running (PID: 12345)

# 不需要时卸载
./start.sh --path ~/my-project --uninstall
```

## 机器人命令

| 命令 | 说明 |
|---|---|
| `/start` | 开始对话 |
| `/new` | 开启新会话（清除当前连接并取消正在进行的流式响应） |
| `/model` | 切换模型（Sonnet / Opus / Haiku） |
| `/resume` | 浏览并恢复历史会话（显示进度摘要及最后一条助手消息） |
| `/stop` | 立即中断执行（绕过队列限制，取消活动任务） |
| `/history` | 查看最近对话历史 |
| `/revert` | 回退到历史对话状态（浏览历史记录，选择消息，选择恢复模式） |
| `/skills` | 列出可用的 Claude Code 技能 |
| `/skill <name> [args]` | 执行技能命令 |
| `/command <cmd> [args]` | 执行 Claude Code 斜杠命令 |

未识别的 `/命令` 也会作为技能调用自动转发。

## 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | 是 | — | Telegram Bot API Token |
| `ALLOWED_USER_IDS` | 否 | *（允许所有人）* | 逗号分隔的用户 ID 白名单 |
| `CLAUDE_CLI_PATH` | 否 | *（自动检测）* | Claude CLI 绝对路径 |
| `CLAUDE_SETTINGS_PATH` | 否 | `~/.claude/settings.json` | Claude Code settings 文件路径 |
| `CLAUDE_PROCESS_TIMEOUT` | 否 | `600` | SDK 超时时间（秒） |
| `DRAFT_UPDATE_MIN_CHARS` | 否 | `150` | 流式响应草稿更新的最小字符数 |
| `DRAFT_UPDATE_INTERVAL` | 否 | `1.0` | 流式响应草稿更新的最小间隔（秒） |
| `TRANSCRIPTION_PROVIDER` | 否 | `whisper` | 语音转写渠道：`whisper` 或 `volcengine` |
| `OPENAI_API_KEY` | 语音功能必需 | — | Whisper 转写所需 OpenAI API Key |
| `OPENAI_BASE_URL` | 否 | *（官方 OpenAI API）* | OpenAI 兼容 Whisper 接口基础地址 |
| `WHISPER_MODEL` | 否 | `whisper-1` | Whisper 模型名称 |
| `VOLCENGINE_APP_ID` | 火山渠道必需 | — | 火山转写 `X-Api-App-Key` |
| `VOLCENGINE_TOKEN` | 火山渠道必需 | — | 火山转写 `X-Api-Access-Key` |
| `VOLCENGINE_ACCESS_KEY` | 火山渠道必需 | — | TOS Access Key |
| `VOLCENGINE_SECRET_ACCESS_KEY` | 火山渠道必需 | — | TOS Secret Access Key（在 `https://console.volcengine.com/iam/keymanage` 创建） |
| `VOLCENGINE_TOS_BUCKET_NAME` | 火山渠道必需 | — | 用于中转语音文件的 TOS Bucket 名称 |
| `VOLCENGINE_TOS_ENDPOINT` | 火山渠道必需 | — | TOS 节点地址（必须与你的 Bucket 区域匹配，如 `https://tos-cn-shanghai.volces.com`） |
| `VOLCENGINE_TOS_REGION` | 否 | `cn-beijing` | TOS SDK 使用的 region |
| `VOLCENGINE_RESOURCE_ID` | 否 | `volc.bigasr.auc` | 火山引擎 `X-Api-Resource-Id` |
| `VOLCENGINE_SUBMIT_ENDPOINT` | 否 | `https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit` | 火山转写 submit 接口地址 |
| `VOLCENGINE_QUERY_ENDPOINT` | 否 | `https://openspeech.bytedance.com/api/v3/auc/bigmodel/query` | 火山转写 query 接口地址 |
| `VOLCENGINE_MODEL_NAME` | 否 | `bigmodel` | 火山请求参数 `model_name` |
| `VOLCENGINE_TIMEOUT_SECONDS` | 否 | `20` | 火山请求超时（秒） |
| `VOLCENGINE_MAX_RETRIES` | 否 | `3` | 火山转写重试次数 |
| `VOLCENGINE_INITIAL_BACKOFF` | 否 | `1.0` | 火山转写初始重试退避时间（秒） |
| `MAX_VOICE_DURATION` | 否 | `300` | 允许的最大语音时长（秒） |
| `FFMPEG_PATH` | 否 | *（自动检测）* | ffmpeg 二进制绝对路径 |
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `PROXY_URL` | 否 | — | HTTP 代理；自动配置 `http_proxy`/`https_proxy`/`all_proxy` |

## 语音转写渠道

- 默认使用 `whisper`。
- 如需切换到火山引擎录音文件极速版，请设置：
  - `TRANSCRIPTION_PROVIDER=volcengine`
  - `VOLCENGINE_APP_ID`
  - `VOLCENGINE_TOKEN`
  - `VOLCENGINE_ACCESS_KEY`
  - `VOLCENGINE_SECRET_ACCESS_KEY`
  - `VOLCENGINE_TOS_BUCKET_NAME`
  - `VOLCENGINE_TOS_ENDPOINT`
- Secret Access Key 需要在火山 IAM 控制台创建：
  - `https://console.volcengine.com/iam/keymanage`
- 火山渠道下，Bot 现在走 `下载 Telegram 语音 -> 上传 TOS -> 传递签名 TOS URL -> ASR`。

## ffmpeg 安装

启用语音消息前请先安装 ffmpeg：

- macOS (Homebrew): `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt-get update && sudo apt-get install -y ffmpeg`
- Windows (winget): `winget install --id Gyan.FFmpeg -e`

安装后可验证：

```bash
ffmpeg -version
```

## Whisper 成本说明

语音转写使用 OpenAI Whisper API（`whisper-1`），按音频时长计费。
参考价格约为 **$0.006/分钟**，请以 OpenAI 最新价格页面为准。

## 安全

- `--path` 设定 `PROJECT_ROOT` — 所有文件操作的沙箱边界。
- `PROJECT_ROOT` 内的文件访问自动放行。外部访问需通过内联按钮确认。
- Bot 输出引用外部文件时，发送前需用户确认。
- 所有运行时数据都在 `PROJECT_ROOT/.telegram_bot/` 内。

## 生命周期管理

```bash
./start.sh --path /path/to/project --status       # 查看运行状态
./start.sh --path /path/to/project --stop         # 停止
./start.sh --path /path/to/project --install      # macOS launchd 开机自启
./start.sh --path /path/to/project --uninstall    # 移除开机自启
```

守护进程崩溃后自动重启，每次崩溃记录退出码和运行时间，60 秒内连续崩溃 5 次后停止重启。

## 调试

```bash
./start.sh --path /path/to/project --debug
# 或: BOT_DEBUG=1 python -m telegram_bot --path .
```

启用完整控制台日志、逐会话聊天记录和 SDK 工具调用追踪。

## 许可证

MIT

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=terranc/claude-telegram-bot-bridge&type=Date)](https://star-history.com/#terranc/claude-telegram-bot-bridge&Date)
