# Telegram Skill Bot

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

**智能交互**
- Claude 输出的编号选项自动转为 Telegram 内联按钮 — 点击即选
- 响应中的文件路径（图片、PDF 等）自动作为照片或文档发送
- 每用户独立的 SDK 长连接 — 低延迟，支持并发消息（每用户最多 3 条）

**安全**
- 项目目录内的文件访问自动放行
- 访问项目外文件时触发 Telegram 内联按钮确认
- 通过 `ALLOWED_USER_IDS` 设置用户白名单
- 超过 20 分钟的过期消息自动丢弃

**运维**
- 守护进程模式，崩溃自动重启（60 秒内连续崩溃 5 次则停止）
- 一条命令安装 macOS launchd 开机自启（`--install`）
- 基于 MD5 的依赖缓存 — `requirements.txt` 未变则跳过安装
- 自动创建 venv、14 天日志自动清理、崩溃日志含退出码

## 前置条件

- **Python 3.11+**
- **Claude CLI** — 已安装并在 `$PATH` 中，或通过 `CLAUDE_CLI_PATH` 指定
- **Telegram Bot Token** — 从 [@BotFather](https://t.me/BotFather) 获取

## 快速开始

1. **配置环境：**

```bash
cd telegram_bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

2. **配置：**

```bash
cp .env.example .env
# 编辑 .env — 填入你的 TELEGRAM_BOT_TOKEN
```

3. **配置全局别名**（推荐）— 添加到 `~/.zshrc` 或 `~/.bashrc`：

```bash
alias tgbot='/absolute/path/to/telegram_bot/start.sh --path'
```

然后在任意项目目录下启动：

```bash
cd ~/my-project
tgbot .                # 以当前目录启动 Bot
tgbot . --debug        # 调试模式
tgbot . --status       # 查看运行状态
tgbot . --stop         # 停止
```

4. **或直接调用 `start.sh`：**

```bash
./start.sh --help                                # 显示帮助
./start.sh --path /path/to/project              # 前台运行（默认）
./start.sh --path /path/to/project -d           # 后台守护进程
./start.sh --path /path/to/project --debug       # 调试模式
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
tgbot ~/my-project --install

# 随时查看状态
tgbot ~/my-project --status
# 🟢 Bot is running (PID: 12345)

# 不需要时卸载
tgbot ~/my-project --uninstall
```

## 机器人命令

| 命令 | 说明 |
|---|---|
| `/start` | 开始对话 |
| `/new` | 开启新会话（清除当前连接） |
| `/model` | 切换模型（Sonnet / Opus / Haiku） |
| `/resume` | 浏览并恢复历史会话 |
| `/stop` | 终止当前运行的任务 |
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
| `LOG_LEVEL` | 否 | `INFO` | 日志级别 |
| `PROXY_URL` | 否 | — | HTTP 代理；自动配置 `http_proxy`/`https_proxy`/`all_proxy` |

## 安全

- `--path` 设定 `PROJECT_ROOT` — 所有文件操作的沙箱边界。
- `PROJECT_ROOT` 内的文件访问自动放行。外部访问需通过内联按钮确认。
- Bot 输出引用外部文件时，发送前需用户确认。
- 所有运行时数据都在 `PROJECT_ROOT/.telegram_bot/` 内。

## 生命周期管理

```bash
tgbot . --status       # 查看运行状态
tgbot . --stop         # 停止
tgbot . --install      # macOS launchd 开机自启
tgbot . --uninstall    # 移除开机自启
```

守护进程崩溃后自动重启，每次崩溃记录退出码和运行时间，60 秒内连续崩溃 5 次后停止重启。

## 调试

```bash
tgbot . --debug
# 或: BOT_DEBUG=1 python -m telegram_bot --path .
```

启用完整控制台日志、逐会话聊天记录和 SDK 工具调用追踪。

## 许可证

MIT
