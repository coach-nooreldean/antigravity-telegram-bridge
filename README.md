# 🚀 Antigravity Telegram Bridge

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.9+](https://img.shields.io/badge/Python-3.9+-yellow.svg)](https://python.org)
[![Telegram Bot API](https://img.shields.io/badge/Telegram-Bot%20API-blue?logo=telegram)](https://core.telegram.org/bots/api)
[![Platform: Linux | macOS | Windows](https://img.shields.io/badge/Platform-Linux%20|%20macOS%20|%20Windows-lightgrey.svg)]()

> **Control, inspect, and code with your Google Antigravity agent remotely from Telegram with zero latency.**

[العربية (Arabic README)](README.ar.md) | **English**

---

## ✨ Features

- **🤖 Full Autonomous Agent Control:** Direct remote bridge to Google Antigravity (`agy` CLI) supporting continuous conversation sessions (`-c`) and fresh sessions (`-n`).
- **🧠 Model & Thinking Depth Selection:** Switch seamlessly between Claude (Sonnet / Opus Thinking), Gemini, and GPT models on the fly (`/model`), and configure reasoning depth (`/effort`).
- **📱 Persistent Mobile Action Bar:** 3x3 interactive reply keyboard pinned to your phone's screen for 1-tap git, diff, task monitor, and screenshot access.
- **📸 Cross-Platform Desktop Screenshots:** Snap live screen captures anywhere (Linux Wayland `grim`, Linux X11 `scrot`, macOS `screencapture`, and Windows PowerShell).
- **🎙️ Voice Note Execution:** Send voice notes in English or Arabic; the agent transcribes, analyzes, and executes the requested code changes directly.
- **📥 Two-Way File & Document Transfers:** Upload `.py`, `.dart`, `.ts`, `.json` code files or docs. The agent inspects, summarizes, or integrates them into your codebase.
- **🎨 Auto-Delivered Visual Artifacts:** Newly generated charts, diagrams, mockups, or UI screenshots are delivered directly to your Telegram chat upon task completion.
- **🌿 1-Click GitHub Pull Requests:** Built-in integration with `gh` CLI (`/pr`) to push branches and open pull requests with direct browser links.
- **🌐 Dual-Language Support:** Instant bilingual switching between English and Arabic (`/lang`).
- **🔒 First-Touch Secure Pairing:** Locks immediately to the first Telegram account that contacts the bot.
- **🧹 Automated Media Cleanup:** Background daemon sweeps temporary recordings and screenshots older than 24 hours.

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
*The installer will prompt you for your Telegram Bot Token (obtained from [@BotFather](https://t.me/BotFather)), detect your `agy` binary, and optionally set up a 24/7 background systemd service.*

### 3. Start chatting!
Open your bot in Telegram and send `/start` or any natural language coding prompt!

---

## 📖 Command Reference

| Command | Description |
| :--- | :--- |
| `/menu` | Show the persistent mobile quick-action keyboard 📱 |
| `/lang` | Toggle interface language between English and العربية 🌐 |
| `/model` | Change active AI model (Claude / Gemini / GPT) 🧠 |
| `/effort` | Set reasoning effort (Max / High / Medium / Low) ⚡ |
| `/goal [prompt]` | Run autonomous goal mode until 100% completed 🎯 |
| `/diff` | View uncommitted code changes & download modified files 📝 |
| `/git` | Check git branch status and recent commits 📊 |
| `/commit [msg]` | Commit working tree modifications 💾 |
| `/push` | Push commits to remote GitHub branch 🚀 |
| `/pr [title]` | Create or inspect GitHub Pull Request via `gh` CLI 🌿 |
| `/screenshot` | Capture live desktop screen cross-platform 📸 |
| `/sh [command]` | Run direct shell terminal command on host machine ⚡ |
| `/stop` | Cleanly terminate the currently running task 🛑 |

---

## ⚙️ Configuration (`config.json`)

```json
{
  "bot_token": "YOUR_BOT_TOKEN_HERE",
  "allowed_user_id": null,
  "language": "en",
  "workspace_mode": "auto",
  "current_workspace": "~/projects/my-app",
  "current_model": "default",
  "current_effort": "default",
  "agy_bin": "agy"
}
```

---

## 🛠️ Running 24/7 with Systemd (Linux)

To run the bridge continuously as a user service:
```bash
systemctl --user enable antigravity-bridge.service
systemctl --user start antigravity-bridge.service
systemctl --user status antigravity-bridge.service
```

---

## 🤝 Contributing

Contributions, bug reports, and feature suggestions are welcome! Feel free to open an issue or submit a Pull Request.

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for details.
