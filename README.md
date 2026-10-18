# 🚀 Antigravity Telegram Bridge (Powerhouse Edition)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9+-yellow.svg)](https://python.org)
[![Telegram Bot API](https://img.shields.io/badge/Telegram-Bot%20API-blue?logo=telegram)](https://core.telegram.org/bots/api)
[![Platform: Linux | macOS | Windows](https://img.shields.io/badge/Platform-Linux%20|%20macOS%20|%20Windows-lightgrey.svg)]()
[![Cloudflare Tunnel](https://img.shields.io/badge/Preview-Cloudflare%20Tunnel-orange?logo=cloudflare)](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)

> **Control, monitor, and code with your autonomous Google Antigravity agent remotely from Telegram. Live step streaming, 1-tap option buttons, multi-project switching, encrypted web previews, and 100+ skill autocomplete.**

[العربية (Arabic README)](README.ar.md) | **English**

---

## 🌟 Overview

**Antigravity Telegram Bridge** turns your Telegram into a full-featured remote IDE and agent control room. Whether you are away from your desk, commuting, or on your phone, you can prompt your AI agent, watch its thought process in real-time, tap interactive multiple-choice buttons, switch between codebases, preview running web servers over secure HTTPS tunnels, and open GitHub Pull Requests with a single tap.

---

## ✨ Powerhouse Features

### 🔘 1-Tap Interactive Option Buttons (`pick_opt`)
- Automatically detects choices like `1) ... 2) ...` or `A) ... B) ...` in the agent's output.
- Generates **interactive Telegram inline buttons** so you can pick answers with your thumb without typing.
- Perfect for interactive alignment workflows like `/grill-me`, `/plan`, architecture reviews, and decision forks.
- Strictly enforces single-question pacing during interviews to eliminate walls of text.

### ⚡ Real-Time Live Streaming & Step Monitor
- Live, throttled progress updates directly from `transcript.jsonl`.
- Shows dynamic timer (`⏱️ 1m 24s`), active step counter (`🔄 Step #14`), currently executing tool (`🛠️ Viewing file`, `Running bash command`), and active session title.
- Keeps you informed of every command and file edit without hitting Telegram rate limits.

### 🎯 100+ Antigravity Skills Autocomplete
- Automatically discovers all registered skills and slash commands across your global customizations (`~/.gemini/config/skills`), workspace skills (`.agents/skills`), and installed plugins.
- Syncs them directly with Telegram Bot API's native command menu so typing `/` reveals instant autocompletion with rich descriptions!

### 📂 Multi-Project Studio & IDE Auto-Tracking
- `/projects`: Scans your `projects_root` and presents an interactive keyboard to switch project directories instantly.
- `/cd [path]`: Manually navigate or pin any local workspace.
- `/auto`: Automatically synchronizes your working directory with whichever project is currently focused in your desktop Antigravity IDE.

### 💬 Multi-Conversation Manager
- `/chats`: Interactive browser listing recent conversations with summaries and resumption buttons.
- `/new`: Spin up a fresh, pristine conversation session anytime.
- `/export`: Download full conversation transcripts or markdown summaries directly as documents to your device.

### 🔄 Multi-Account Switcher & Auto-Failover
- `/accounts`: Seamlessly switch between configured Google accounts or token profiles.
- `auto_failover`: Automatically detects quota limits or rate-limiting and fails over to backup accounts without interrupting your workflow.

### 🌐 Instant Encrypted Cloudflare Web Previews
- `/servers`: Detects running local development servers (Vite `5173`, Next.js `3000`, Flutter Web, Django, FastAPI, etc.).
- `/preview [port]`: Spins up a temporary, encrypted HTTPS tunnel via `cloudflared` (`*.trycloudflare.com`) on the fly, allowing you to test and interact with your web app live from your phone browser anywhere in the world!

### 🌿 Git Studio & 1-Click Pull Requests
- `/diff`: Colorized unified diff view and automatic delivery of modified files.
- `/git`: Branch status, ahead/behind tracking, and recent commits.
- `/commit [msg]`: Stage and commit working tree changes.
- `/push`: Push commits to remote branch.
- `/undo`: Revert or stash working changes safely.
- `/pr [title]`: Push branch and open a GitHub Pull Request via `gh` CLI with a direct link.

### 🎙️ Voice Notes & Multi-Modal Code Transfers
- Send voice notes in **English or Arabic**; the bridge automatically transcribes and feeds them as natural coding instructions to the agent.
- Upload any code or documentation file (`.py`, `.dart`, `.ts`, `.json`, `.md`); the agent inspects and integrates it directly into your codebase.
- Visual artifacts (generated UI diagrams, mockups, images) created by the agent are automatically delivered to your Telegram chat.

### 📸 Desktop Remote Eye & Shell Terminal
- `/screenshot`: Captures high-resolution desktop screenshots across Linux (Wayland `grim` / X11 `scrot`), macOS (`screencapture`), and Windows (PowerShell).
- `/sh [command]`: Direct terminal shell execution with live output streaming.
- `/stop`: Instant, clean cancellation of running tasks and subprocesses.

### 🛡️ Security & Housekeeping
- **First-Touch Secure Pairing:** Automatically locks onto the first Telegram user ID that messages the bot, completely blocking unauthorized access.
- **24h Media Cleanup Daemon:** Background worker automatically deletes old recordings and temporary files to keep your disk clean.

---

## ⚡ Quickstart (2-Minute Setup)

### 1. Clone the repository
```bash
git clone https://github.com/coach-nooreldean/antigravity-telegram-bridge.git
cd antigravity-telegram-bridge
```

### 2. Run the interactive installer
```bash
chmod +x install.sh
./install.sh
```

The interactive script will:
1. Detect Python 3.9+ and your `agy` CLI binary.
2. Prompt for your preferred language (**English** or **Arabic**).
3. Prompt for your Telegram Bot Token (from [@BotFather](https://t.me/BotFather)).
4. Set your `projects_root` (for the `/projects` switcher) and default workspace.
5. Check optional utilities (`cloudflared` for live previews, `ffmpeg` for audio).
6. Optionally configure a 24/7 background `systemd` user service.

### 3. Start coding!
Open your bot in Telegram and send `/start` or any natural language prompt!

---

## 📖 Command Reference

| Command | Description |
| :--- | :--- |
| **Workspace & Sessions** | |
| `/projects` | Scan and switch between local projects with 1 tap 📂 |
| `/cd [path]` | Change or pin active working directory 📍 |
| `/auto` | Auto-sync workspace with active Antigravity IDE window ⚡ |
| `/chats` | Browse and resume previous conversation sessions 💬 |
| `/new` | Start a fresh, clean conversation session ✨ |
| `/export` | Export conversation transcript as a document 📄 |
| **Model & Reasoning** | |
| `/model` | Switch active model (Claude Opus/Sonnet, Gemini, GPT) 🧠 |
| `/effort` | Set reasoning effort (Max / High / Medium / Low) ⚡ |
| `/accounts` | Switch Google Antigravity account profile 🔄 |
| `/goal [prompt]` | Run autonomous goal mode until 100% achieved 🎯 |
| **Live Previews & System** | |
| `/servers` | List active local development servers and ports 🔍 |
| `/preview [port]`| Create encrypted HTTPS Cloudflare tunnel for mobile testing 🌐 |
| `/screenshot` | Capture live desktop screen cross-platform 📸 |
| `/sh [command]` | Run direct bash/shell command on host machine ⚡ |
| `/stop` | Cleanly terminate currently running task 🛑 |
| **Git Studio** | |
| `/git` | Check branch status and latest commits 📊 |
| `/diff` | View unified diff and receive modified code files 📝 |
| `/commit [msg]` | Commit staged working tree changes 💾 |
| `/push` | Push commits to remote GitHub repository 🚀 |
| `/pr [title]` | Open a GitHub Pull Request via `gh` CLI 🌿 |
| `/undo` | Safely revert or stash uncommitted changes ↩️ |
| **Interface & Settings** | |
| `/menu` | Show the persistent mobile quick-action keyboard 📱 |
| `/lang` | Toggle interface language between English and العربية 🌐 |
| `/status` | View system status, CPU/RAM, and active configuration ⚙️ |

---

## ⚙️ Configuration (`config.json`)

The installer generates `config.json` automatically, but you can customize it at any time:

```json
{
  "bot_token": "YOUR_TELEGRAM_BOT_TOKEN_FROM_BOTFATHER",
  "allowed_user_id": null,
  "language": "en",
  "projects_root": "~/projects",
  "workspace_mode": "auto",
  "current_workspace": "~/projects/my-app",
  "current_model": "default",
  "current_effort": "default",
  "auto_failover": true,
  "task_timeout_seconds": 600,
  "sentry_url": "",
  "force_new": false,
  "agy_bin": "agy"
}
```

### Configuration Options
- `bot_token`: Telegram Bot API token obtained from [@BotFather](https://t.me/BotFather).
- `allowed_user_id`: Your Telegram numeric User ID. Set to `null` to automatically pair with the first user who sends `/start`.
- `language`: Interface language (`"en"` or `"ar"`). Can be toggled on the fly via `/lang`.
- `projects_root`: Directory containing your repositories for the `/projects` switcher.
- `workspace_mode`: `"auto"` (tracks active IDE window) or `"manual"` (fixed workspace).
- `auto_failover`: Automatically switch Google accounts if quota limits are encountered.
- `task_timeout_seconds`: Safety timeout for running agent tasks (default: `600`).
- `agy_bin`: Path to the `agy` CLI binary.

---

## 🛠️ Running 24/7 with Systemd (Linux)

To keep the bridge running continuously in the background:

```bash
# Enable and start user service
systemctl --user daemon-reload
systemctl --user enable antigravity-bridge.service
systemctl --user start antigravity-bridge.service

# View live logs
journalctl --user -u antigravity-bridge.service -f

# Check status
systemctl --user status antigravity-bridge.service
```

---

## 💡 Optional Dependencies

- **Cloudflare Tunnel (`cloudflared`)**: Enables the `/preview` command to expose local web apps (Vite, Next.js, Flutter) to the internet with free, secure HTTPS.
  - *Ubuntu/Debian:* `sudo apt install cloudflared` or download from [Cloudflare Releases](https://github.com/cloudflare/cloudflared/releases).
  - *Arch Linux:* `sudo pacman -S cloudflared`
  - *macOS:* `brew install cloudflared`
- **FFmpeg (`ffmpeg`)**: Required for audio transcoding of Telegram voice notes.
  - *Ubuntu/Debian:* `sudo apt install ffmpeg`
  - *macOS:* `brew install ffmpeg`
- **GitHub CLI (`gh`)**: Enables 1-click Pull Requests via `/pr`.
  - Install from [cli.github.com](https://cli.github.com/).

---

## 🤝 Contributing

Contributions, bug reports, and feature suggestions are warmly welcomed! Please feel free to open an issue or submit a Pull Request.

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.
