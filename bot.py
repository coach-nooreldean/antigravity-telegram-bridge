#!/usr/bin/env python3
"""
Antigravity Telegram Bridge
Open-source remote controller and mobile interface for Google Antigravity Agent.
Author: Nooreldean (https://github.com/coach-nooreldean)
License: MIT
"""

import base64
import datetime
import glob
import json
import os
import platform
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import threading
import urllib.parse
import requests

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    default_cfg = {
        "bot_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "allowed_user_id": None,
        "language": "en",
        "workspace_mode": "auto",
        "current_workspace": os.path.expanduser("~/"),
        "current_model": "default",
        "current_effort": "default",
        "agy_bin": shutil.which("agy") or os.path.expanduser("~/.local/bin/agy") or "agy",
        "auto_failover": True,
        "project_states": {}
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                default_cfg.update(loaded)
        except Exception as e:
            print(f"[Warning] Failed to parse config.json: {e}")
    return default_cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[Error] Failed to save config: {e}")

CONFIG = load_config()
BOT_TOKEN = CONFIG.get("bot_token")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Thread synchronization
active_task_lock = threading.Lock()
current_task_info = {"running": False, "process": None, "prompt": "", "start_time": 0}
active_question_state = {}
active_extracted_options = {}

# ==========================================
# Multi-Language Localization Engine (EN / AR)
# ==========================================
TRANSLATIONS = {
    "en": {
        "welcome": "🤖 <b>Welcome to Antigravity Telegram Bridge!</b>\n\nControl your Google Antigravity autonomous coding agent remotely right from your phone.",
        "project": "📁 <b>Active Project:</b>",
        "mode": "⚙️ <b>Mode:</b>",
        "model": "🧠 <b>Model:</b>",
        "effort": "⚡ <b>Effort:</b>",
        "lang_switched": "🌐 <b>Language switched to English!</b>",
        "pairing_success": "🔒 <b>Bot paired successfully to your Telegram account!</b> (User ID: {user_id})",
        "unauthorized": "⛔ Access denied. This bot is locked to its owner.",
        "task_started": "🚀 <b>Task started:</b>",
        "task_running_wait": "⚠️ Another task is already running. Please wait or use /stop.",
        "task_done": "✅ <b>Task completed successfully ({duration}s):</b>",
        "task_timeout": "⏱️ <b>Task stopped:</b> Timed out after {mins} minutes.",
        "btn_resume": "▶️ Resume task from here",
        "btn_tasks": "⚡ Tasks",
        "btn_where": "📍 Where am I?",
        "btn_screenshot": "📸 Screenshot",
        "btn_git": "📊 Git Status",
        "btn_diff": "📝 Diff Summary",
        "btn_projects": "📂 Projects",
        "btn_preview": "🌐 Live Preview",
        "btn_servers": "🔌 Active Ports",
        "btn_restart": "🔄 Restart Bot",
        "btn_commit": "💾 Commit",
        "btn_push": "🚀 Push",
        "btn_pr": "🌿 Pull Request",
        "btn_undo": "↩️ Undo",
        "btn_inspect": "🔍 Inspect File",
        "btn_summary": "📝 Summarize",
        "file_received": "📥 <b>File saved successfully!</b>\n\n📄 <b>Name:</b> <code>{name}</code>\n📦 <b>Size:</b> <code>{size} KB</code>\n📁 <b>Path:</b> <code>{path}</code>",
        "media_artifact": "🎨 <b>Generated Output / Media Artifact:</b>\n📁 <code>{name}</code>",
        "pr_success": "🎉 <b>Pull Request created successfully on GitHub!</b>\n\n📁 <b>Project:</b> <code>{project}</code>\n🌿 <b>Branch:</b> <code>{branch}</code>\n📝 <b>Title:</b> <code>{title}</code>\n\n🔗 <a href=\"{url}\">{url}</a>",
        "menu_shown": "📱 <b>Quick Action Bar pinned to your chat!</b>\nTap any button below for instant 1-tap mobile control.",
        "menu_hidden": "🙈 <b>Quick action keyboard hidden.</b> Type /menu anytime to restore."
    },
    "ar": {
        "welcome": "🤖 <b>أهلاً بك في جسر Antigravity Telegram Bridge!</b>\n\nتحكم بوكيلك الذكي Antigravity وطوّر مشاريعك البرمجية عن بُعد من شاشة موبايلك.",
        "project": "📁 <b>المشروع الحالي:</b>",
        "mode": "⚙️ <b>الوضع:</b>",
        "model": "🧠 <b>النموذج:</b>",
        "effort": "⚡ <b>الجهد:</b>",
        "lang_switched": "🌐 <b>تم تحويل لغة البوت بنجاح إلى العربية!</b>",
        "pairing_success": "🔒 <b>تم قفل واقتران البوت بحسابك بنجاح!</b> (User ID: {user_id})",
        "unauthorized": "⛔ عذراً، هذا البوت خاص ومقفل على المالك فقط.",
        "task_started": "🚀 <b>بدأ تنفيذ المهمة:</b>",
        "task_running_wait": "⚠️ هناك مهمة سابقة قيد التنفيذ حالياً، انتظر أو اكتب /stop.",
        "task_done": "✅ <b>تمت المهمة بنجاح ({duration}s):</b>",
        "task_timeout": "⏱️ <b>توقفت المهمة:</b> تخطت المهلة المحددة ({mins} دقيقة).",
        "btn_resume": "▶️ استكمال العمل من نفس النقطة",
        "btn_tasks": "⚡ المهام",
        "btn_where": "📍 أين أنا؟",
        "btn_screenshot": "📸 سكرين شوت",
        "btn_git": "📊 حالة Git",
        "btn_diff": "📝 التغييرات Diff",
        "btn_projects": "📂 المشاريع",
        "btn_preview": "🌐 نفق لايف",
        "btn_servers": "🔌 السيرفرات",
        "btn_restart": "🔄 تحديث/ريستارت",
        "btn_commit": "💾 Commit",
        "btn_push": "🚀 Push",
        "btn_pr": "🌿 عمل PR",
        "btn_undo": "↩️ تراجع Undo",
        "btn_inspect": "🔍 فحص وقراءة الملف",
        "btn_summary": "📝 تلخيص المحتوى",
        "file_received": "✅ <b>تم استلام وحفظ الملف بنجاح!</b>\n\n📄 <b>الاسم:</b> <code>{name}</code>\n📦 <b>الحجم:</b> <code>{size} KB</code>\n📁 <b>المسار:</b> <code>{path}</code>",
        "media_artifact": "🎨 <b>تصميم / صورة ناتجة من الأيجنت:</b>\n📁 <code>{name}</code>",
        "pr_success": "🎉 <b>تم إنشاء الـ Pull Request بنجاح على GitHub!</b>\n\n📁 <b>المشروع:</b> <code>{project}</code>\n🌿 <b>الفرع:</b> <code>{branch}</code>\n📝 <b>العنوان:</b> <code>{title}</code>\n\n🔗 <a href=\"{url}\">{url}</a>",
        "menu_shown": "📱 <b>لوحة التحكم السريعة مثبتة أسفل الشاشة!</b>\nاضغط على أي زر للوصول الفوري بنقرة واحدة من الموبايل.",
        "menu_hidden": "🙈 <b>تم إخفاء لوحة الأزرار.</b> اكتب /menu في أي وقت لإعادتها."
    }
}

def t(key, **kwargs):
    lang = CONFIG.get("language", "en")
    table = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
    template = table.get(key, TRANSLATIONS["en"].get(key, key))
    try:
        return template.format(**kwargs)
    except Exception:
        return template

def escape_html(text):
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

# ==========================================
# Telegram API Wrappers
# ==========================================
def send_message(chat_id, text, parse_mode="HTML", reply_markup=None):
    url = f"{API_URL}/sendMessage"
    chunk_size = 3800
    chunks = [text] if len(text) <= chunk_size else [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    first_msg_id = None
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup and i == len(chunks) - 1:
            payload["reply_markup"] = reply_markup
        try:
            res = requests.post(url, json=payload, timeout=15)
            if not res.ok and parse_mode:
                payload.pop("parse_mode", None)
                res = requests.post(url, json=payload, timeout=15)
            if res.ok and i == 0:
                first_msg_id = res.json().get("result", {}).get("message_id")
        except Exception as e:
            print(f"[Error] send_message: {e}")
    return first_msg_id

def edit_message_text(chat_id, message_id, text, parse_mode="HTML", reply_markup=None):
    url = f"{API_URL}/editMessageText"
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "disable_web_page_preview": True}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.ok
    except Exception:
        return False

def answer_callback_query(callback_query_id, text=None):
    url = f"{API_URL}/answerCallbackQuery"
    try:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

def send_photo(chat_id, photo_path, caption=None):
    url = f"{API_URL}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            res = requests.post(url, data=data, files=files, timeout=60)
            return res.ok
    except Exception as e:
        print(f"[Error] send_photo: {e}")
        return False

def send_document(chat_id, file_path, caption=None):
    url = f"{API_URL}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
                data["parse_mode"] = "HTML"
            res = requests.post(url, data=data, files=files, timeout=60)
            return res.ok
    except Exception as e:
        print(f"[Error] send_document: {e}")
        return False

def download_telegram_file(file_id, dest_path):
    get_file_url = f"{API_URL}/getFile"
    try:
        res = requests.get(get_file_url, params={"file_id": file_id}, timeout=15)
        if not res.ok:
            return False
        file_path = res.json().get("result", {}).get("file_path")
        if not file_path:
            return False
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        file_res = requests.get(download_url, timeout=60)
        if not file_res.ok:
            return False
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(file_res.content)
        return True
    except Exception as e:
        print(f"[Error] download_telegram_file: {e}")
        return False

# ==========================================
# Cross-Platform OS Utilities
# ==========================================
def take_desktop_screenshot(dest_path):
    """Captures desktop screen cross-platform (Wayland, X11, macOS, Windows)."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    sys_name = platform.system().lower()

    if sys_name == "darwin":  # macOS
        res = subprocess.run(["screencapture", "-x", dest_path], capture_output=True, timeout=10)
        return res.returncode == 0 and os.path.exists(dest_path)

    elif sys_name == "windows":
        ps_cmd = f"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('^'); $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds; $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height; $g = [System.Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size); $bmp.Save('{dest_path}');"
        res = subprocess.run(["powershell", "-command", ps_cmd], capture_output=True, timeout=10)
        return res.returncode == 0 and os.path.exists(dest_path)

    else:  # Linux
        # Try Wayland (grim)
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = env.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        if shutil.which("grim"):
            res = subprocess.run(["grim", dest_path], env=env, capture_output=True, timeout=10)
            if res.returncode == 0 and os.path.exists(dest_path):
                return True
        # Try scrot (X11)
        if shutil.which("scrot"):
            res = subprocess.run(["scrot", dest_path], env=env, capture_output=True, timeout=10)
            if res.returncode == 0 and os.path.exists(dest_path):
                return True
        # Try ImageMagick import
        if shutil.which("import"):
            res = subprocess.run(["import", "-window", "root", dest_path], env=env, capture_output=True, timeout=10)
            if res.returncode == 0 and os.path.exists(dest_path):
                return True
    return False

def lock_desktop_screen():
    """Locks workstation cross-platform."""
    sys_name = platform.system().lower()
    if sys_name == "darwin":
        return subprocess.run(["pmset", "displaysleepnow"], timeout=5).returncode == 0
    elif sys_name == "windows":
        return subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], timeout=5).returncode == 0
    else:  # Linux
        for cmd in [["hyprlock"], ["swaylock"], ["loginctl", "lock-session"], ["xdg-screensaver", "lock"]]:
            if shutil.which(cmd[0]):
                try:
                    subprocess.Popen(cmd)
                    return True
                except Exception:
                    pass
    return False

# ==========================================
# Navigation & Keyboards
# ==========================================
def get_main_reply_keyboard():
    """Persistent 3x3 mobile navigation grid in user language."""
    return {
        "keyboard": [
            [{"text": t("btn_tasks")}, {"text": t("btn_where")}, {"text": t("btn_screenshot")}],
            [{"text": t("btn_git")}, {"text": t("btn_diff")}, {"text": t("btn_projects")}],
            [{"text": t("btn_preview")}, {"text": t("btn_servers")}, {"text": t("btn_restart")}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def get_task_action_buttons(ws=None):
    """Dynamic inline buttons attached below task completion reports."""
    rows = [
        [
            {"text": t("btn_diff"), "callback_data": "act:diff"},
            {"text": t("btn_commit"), "callback_data": "act:commit"},
            {"text": t("btn_push"), "callback_data": "act:push"}
        ],
        [
            {"text": t("btn_pr"), "callback_data": "act:pr"},
            {"text": t("btn_preview"), "callback_data": "act:tunnel"},
            {"text": "🧪 Build / Test", "callback_data": "act:build"}
        ],
        [
            {"text": t("btn_screenshot"), "callback_data": "act:shot"},
            {"text": t("btn_undo"), "callback_data": "act:undo_prompt"},
            {"text": "➕ New Session", "callback_data": "conv:new"}
        ]
    ]
    return {"inline_keyboard": rows}

# ==========================================
# Artifacts, Media & Background Daemons
# ==========================================
def extract_interactive_options(text):
    """
    Parses questions and multiple-choice options from agent output text
    so they can be converted into interactive Telegram buttons.
    """
    if not text:
        return []
    options = []
    pattern = re.compile(r'^(?:(?:\d+|[A-Da-d])[\.\-\)]|\([0-9A-Za-z]\))\s+(.+)$', re.MULTILINE)
    matches = pattern.findall(text)
    if matches and len(matches) >= 2:
        for idx, m in enumerate(matches[:5]):
            clean_opt = re.sub(r'[*_`#]', '', m).strip()
            if ":" in clean_opt:
                short_title = clean_opt.split(":", 1)[0].strip()
            elif " - " in clean_opt:
                short_title = clean_opt.split(" - ", 1)[0].strip()
            else:
                short_title = clean_opt
            if len(short_title) > 35 and "(" in short_title:
                clean_short = re.sub(r'\(.*?\)', '', short_title).strip()
                if clean_short:
                    short_title = clean_short
            if len(short_title) > 35:
                short_title = short_title[:32] + "..."
            options.append({
                "index": idx + 1,
                "label": f"{idx + 1}️⃣ {short_title}",
                "full_text": clean_opt[:120]
            })
    return options

def find_newly_generated_media(workspace, start_time, max_files=4):
    """Auto-detects image and design files created/modified during agent execution."""
    media_exts = ('.png', '.jpg', '.jpeg', '.webp', '.svg')
    candidates = []
    exclude_dirs = {'.git', 'node_modules', '.bot', '.dart_tool', 'build', 'dist', '.venv', 'venv', '__pycache__', '.scratch'}
    try:
        for root, dirs, files in os.walk(workspace):
            dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
            for f in files:
                if f.lower().endswith(media_exts):
                    fpath = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(fpath)
                        if mtime >= start_time - 1.0:
                            candidates.append((fpath, mtime))
                    except Exception:
                        pass
    except Exception:
        pass

    brain_dir = os.path.expanduser("~/.gemini/antigravity-ide/brain")
    if os.path.isdir(brain_dir):
        try:
            for root, dirs, files in os.walk(brain_dir):
                for f in files:
                    if f.lower().endswith(media_exts):
                        fpath = os.path.join(root, f)
                        try:
                            mtime = os.path.getmtime(fpath)
                            if mtime >= start_time - 1.0:
                                candidates.append((fpath, mtime))
                        except Exception:
                            pass
        except Exception:
            pass

    candidates.sort(key=lambda x: x[1], reverse=True)
    seen = set()
    unique_files = []
    for fpath, _ in candidates:
        if fpath not in seen and os.path.isfile(fpath) and os.path.getsize(fpath) > 100:
            seen.add(fpath)
            unique_files.append(fpath)
            if len(unique_files) >= max_files:
                break
    return unique_files

def start_media_cleanup_daemon():
    """Background thread to clean temporary media older than 24h."""
    def _cleanup():
        while True:
            try:
                now = time.time()
                max_age = 86400
                del_count = 0
                media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
                if os.path.isdir(media_dir):
                    for f in os.listdir(media_dir):
                        fp = os.path.join(media_dir, f)
                        try:
                            if os.path.isfile(fp) and (now - os.path.getmtime(fp)) > max_age:
                                os.remove(fp)
                                del_count += 1
                        except Exception:
                            pass
                if del_count > 0:
                    print(f"[Cleanup] Removed {del_count} old temp files.")
            except Exception as e:
                print(f"[Cleanup Error] {e}")
            time.sleep(21600)  # Sweep every 6 hours

    threading.Thread(target=_cleanup, daemon=True).start()

# ==========================================
# Workspace & Project Management
# ==========================================
def get_effective_workspace():
    ws = CONFIG.get("current_workspace") or os.getcwd()
    ws = os.path.expanduser(ws)
    if not os.path.exists(ws):
        ws = os.getcwd()
    return ws, "Fixed"

def discover_all_projects():
    """Discovers git and code projects in current and parent directory hierarchies."""
    projects = []
    roots = [
        CONFIG.get("current_workspace"),
        os.path.expanduser("~/projects"),
        os.path.expanduser("~/Documents"),
        os.getcwd()
    ]
    seen = set()
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            for item in os.listdir(root):
                p_path = os.path.join(root, item)
                if os.path.isdir(p_path) and not item.startswith("."):
                    if os.path.isdir(os.path.join(p_path, ".git")) or os.path.isfile(os.path.join(p_path, "package.json")):
                        if p_path not in seen:
                            seen.add(p_path)
                            projects.append({"name": item, "path": p_path})
        except Exception:
            pass
    return projects

# ==========================================
# Git & GitHub CLI Integration
# ==========================================
def handle_pr_workflow(chat_id, ws, arg=""):
    """Creates or views a GitHub Pull Request using gh CLI."""
    if not os.path.isdir(os.path.join(ws, ".git")):
        send_message(chat_id, "❌ Current directory is not a Git repository.")
        return

    try:
        b_res = subprocess.run(["git", "branch", "--show-current"], cwd=ws, capture_output=True, text=True, timeout=5)
        branch_name = b_res.stdout.strip()
        if not branch_name:
            send_message(chat_id, "⚠️ Unable to detect branch name (Detached HEAD).")
            return

        st_res = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=5)
        if st_res.stdout.strip():
            send_message(
                chat_id,
                f"⚠️ <b>Uncommitted changes in <code>{escape_html(branch_name)}</code>.</b>\nPlease commit changes first before opening a PR.",
                reply_markup={"inline_keyboard": [[{"text": t("btn_commit"), "callback_data": "act:commit"}]]}
            )
            return

        if branch_name in ["main", "master"]:
            send_message(
                chat_id,
                f"⚠️ You are on default branch (<code>{escape_html(branch_name)}</code>).\nFor clean PRs, creating a feature branch is recommended.",
                reply_markup={"inline_keyboard": [[{"text": "🌿 Auto-create Feature Branch & PR", "callback_data": "act:create_pr_branch"}]]}
            )
            return

        send_message(chat_id, f"🚀 <i>Syncing branch <code>{escape_html(branch_name)}</code> with GitHub...</i>")
        subprocess.run(["git", "push", "-u", "origin", branch_name], cwd=ws, capture_output=True, text=True, timeout=60)

        # Check existing PR
        view_res = subprocess.run(["gh", "pr", "view", "--json", "url,title,state,number"], cwd=ws, capture_output=True, text=True, timeout=15)
        if view_res.returncode == 0:
            pr_data = json.loads(view_res.stdout)
            pr_url = pr_data.get("url")
            pr_num = pr_data.get("number")
            pr_title = pr_data.get("title")
            pr_state = pr_data.get("state", "OPEN")
            send_message(
                chat_id,
                f"ℹ️ <b>Pull Request already exists (#{pr_num}):</b>\n\n📝 <b>Title:</b> {escape_html(pr_title)}\n📊 <b>State:</b> <code>{escape_html(pr_state)}</code>\n🔗 <a href=\"{pr_url}\">{pr_url}</a>",
                reply_markup={"inline_keyboard": [[{"text": f"🔗 Open PR #{pr_num} on GitHub", "url": pr_url}]]}
            )
            return

        title = arg.strip() if arg.strip() else f"feat: updates from {branch_name}"
        body = f"### Automated Pull Request\n\n- **Project:** `{os.path.basename(ws)}`\n- **Branch:** `{branch_name}`\n- **Created via:** Antigravity Telegram Bridge\n"
        create_res = subprocess.run(["gh", "pr", "create", "--title", title, "--body", body, "--head", branch_name], cwd=ws, capture_output=True, text=True, timeout=40)

        if create_res.returncode == 0:
            urls = re.findall(r"https://github\.com/[^\s]+/pull/\d+", create_res.stdout)
            pr_url = urls[0] if urls else create_res.stdout.strip()
            msg = t("pr_success", project=os.path.basename(ws), branch=branch_name, title=title, url=pr_url)
            send_message(chat_id, msg, reply_markup={"inline_keyboard": [[{"text": "🔗 Open PR in Browser", "url": pr_url}]]})
        else:
            send_message(chat_id, f"❌ <b>Failed to create PR:</b>\n<pre>{escape_html((create_res.stdout + create_res.stderr).strip()[:800])}</pre>")
    except Exception as e:
        send_message(chat_id, f"❌ Error: {escape_html(str(e))}")

# ==========================================
# Core Antigravity Agent Execution Engine
# ==========================================
def kill_process_tree(proc):
    if not proc:
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(0.3)
        os.killpg(pgid, signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

def run_agent_task(chat_id, prompt, agent_name=None, extra_args=None, banner_title=None):
    global current_task_info
    workspace, _ = get_effective_workspace()
    agy_bin = CONFIG.get("agy_bin", "agy")

    with active_task_lock:
        if current_task_info["running"]:
            send_message(chat_id, t("task_running_wait"))
            return
        current_task_info["running"] = True
        current_task_info["prompt"] = prompt
        current_task_info["start_time"] = time.time()

    banner = banner_title if banner_title else f"🚀 <b>Task Started:</b>\n<code>{escape_html(prompt[:120])}</code>"
    status_msg_id = send_message(chat_id, banner)

    cmd = [agy_bin, "-c"]
    active_model = CONFIG.get("current_model", "default")
    if active_model != "default":
        cmd.extend(["-m", active_model])
    active_effort = CONFIG.get("current_effort", "default")
    if active_effort != "default":
        cmd.extend(["-e", active_effort])

    cmd.append(prompt)

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            bufsize=1,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None
        )
        current_task_info["process"] = proc

        stdout, stderr = proc.communicate(timeout=1800)
        duration = round(time.time() - current_task_info["start_time"], 1)

        result_text = stdout.strip() if stdout else (stderr.strip() if stderr else "Task executed without text output.")
        header = f"✅ <b>Done ({duration}s):</b>\n\n"
        detected_options = extract_interactive_options(result_text)
        action_markup = get_task_action_buttons(workspace)
        if detected_options:
            opt_buttons = []
            q_id = int(time.time())
            active_extracted_options[q_id] = detected_options
            for opt in detected_options:
                opt_buttons.append([{"text": f"👉 {opt['label']}", "callback_data": f"pick_opt:{q_id}:{opt['index']}"}])
            action_markup["inline_keyboard"] = opt_buttons + action_markup["inline_keyboard"]

        send_message(chat_id, header + f"<pre>{escape_html(result_text[:3500])}</pre>", reply_markup=action_markup)

        # Auto-deliver generated artifacts
        try:
            new_media = find_newly_generated_media(workspace, current_task_info["start_time"])
            for mpath in new_media:
                fname = os.path.basename(mpath)
                caption = t("media_artifact", name=fname)
                if mpath.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    if not send_photo(chat_id, mpath, caption=caption):
                        send_document(chat_id, mpath, caption=caption)
                else:
                    send_document(chat_id, mpath, caption=caption)
        except Exception as e:
            print(f"[Auto-deliver error] {e}")

    except subprocess.TimeoutExpired:
        if current_task_info["process"]:
            kill_process_tree(current_task_info["process"])
        send_message(chat_id, t("task_timeout", mins=30), reply_markup={"inline_keyboard": [[{"text": t("btn_resume"), "callback_data": "act:resume_task"}]]})
    except Exception as e:
        send_message(chat_id, f"❌ <b>Execution Error:</b>\n<code>{escape_html(str(e))}</code>")
    finally:
        with active_task_lock:
            current_task_info["running"] = False
            current_task_info["process"] = None
            current_task_info["prompt"] = ""
            current_task_info["start_time"] = 0

# ==========================================
# Command Dispatcher
# ==========================================
def handle_command(chat_id, user_id, text):
    ALIASES = {
        # Arabic button aliases
        "⚡ المهام": "/tasks", "📍 أين أنا؟": "/where", "📸 سكرين شوت": "/screenshot",
        "📊 حالة Git": "/git", "📊 حالة git": "/git", "📝 التغييرات Diff": "/diff",
        "📂 المشاريع": "/projects", "🌐 نفق لايف": "/preview", "🔌 السيرفرات": "/servers",
        "🔄 تحديث/ريستارت": "/restart", "قائمة": "/menu",
        # English button aliases
        "⚡ Tasks": "/tasks", "📍 Where am I?": "/where", "📸 Screenshot": "/screenshot",
        "📊 Git Status": "/git", "📝 Diff Summary": "/diff", "📂 Projects": "/projects",
        "🌐 Live Preview": "/preview", "🔌 Active Ports": "/servers", "🔄 Restart Bot": "/restart",
        "Menu": "/menu"
    }

    clean_text = text.strip()
    if clean_text in ALIASES:
        text = ALIASES[clean_text]

    parts = text.strip().split(maxsplit=1)
    raw_cmd = parts[0].lower().lstrip("/")
    cmd = "/" + raw_cmd
    arg = parts[1] if len(parts) > 1 else ""

    ws, _ = get_effective_workspace()

    if cmd in ["/start", "/help"]:
        active_model = CONFIG.get("current_model", "default")
        active_effort = CONFIG.get("current_effort", "default")
        msg = (
            f"{t('welcome')}\n\n"
            f"📁 <b>Workspace:</b> <code>{escape_html(ws)}</code>\n"
            f"🧠 <b>Model:</b> <code>{escape_html(active_model)}</code> | ⚡ <b>Effort:</b> <code>{escape_html(active_effort)}</code>\n\n"
            "<b>🎛️ Navigation & Control:</b>\n"
            "• <code>/menu</code> - Show persistent mobile action bar 📱\n"
            "• <code>/lang</code> - Toggle language between English and العربية 🌐\n"
            "• <code>/model</code> - Select AI model (Claude Sonnet / Opus, Gemini, GPT)\n"
            "• <code>/effort</code> - Reasoning depth (Max / High / Medium / Low)\n"
            "• <code>/goal [objective]</code> - 100% Autonomous execution mode\n"
            "• <code>/diff</code> - View git changes & download modified files\n"
            "• <code>/commit [msg]</code> - Commit changes to local git\n"
            "• <code>/push</code> - Push commits to GitHub origin\n"
            "• <code>/pr [title]</code> - Create or view GitHub Pull Request 🌿\n"
            "• <code>/screenshot</code> - Take a live desktop screenshot 📸\n"
            "• <code>/sh [command]</code> - Execute direct shell command\n"
            "• <code>/stop</code> - Terminate currently running task 🛑\n\n"
            "<i>💡 You can send any natural language prompt, voice note, photo, or document directly to this chat!</i>"
        )
        send_message(chat_id, msg, reply_markup=get_main_reply_keyboard())

    elif cmd in ["/lang", "/language"]:
        new_lang = "ar" if CONFIG.get("language", "en") == "en" else "en"
        CONFIG["language"] = new_lang
        save_config(CONFIG)
        send_message(chat_id, t("lang_switched"), reply_markup=get_main_reply_keyboard())

    elif cmd in ["/menu", "/keyboard"]:
        send_message(chat_id, t("menu_shown"), reply_markup=get_main_reply_keyboard())

    elif cmd in ["/hidemenu", "/closemenu"]:
        send_message(chat_id, t("menu_hidden"), reply_markup={"remove_keyboard": True})

    elif cmd in ["/pr", "/pullrequest"]:
        handle_pr_workflow(chat_id, ws, arg)

    elif cmd in ["/grill-me", "/grill_me", "/grill"]:
        topic = arg.strip() if arg.strip() else "Interview and grill me about the best architectural improvements and features to add to this project."
        grill_prompt = (
            f"Activate the grilling skill. Interview and grill the user about this topic, idea, or plan: '{topic}'.\n\n"
            f"STRICT INTERACTIVE RULES YOU MUST STRICTLY FOLLOW:\n"
            f"1. Ask exactly ONE single question at a time. NEVER dump multiple questions (like Q1, Q2, Q3) in one message.\n"
            f"2. For your question, provide 2 to 4 clear, numbered choices (1., 2., 3., 4.) with concise bold titles (e.g. 1. **Option Title**: description).\n"
            f"3. Mark your recommended choice with (Recommended).\n"
            f"4. STOP completely and wait for the user to pick an option before asking anything else.\n"
            f"5. Start by briefly reviewing the project, then ask Question 1 with its numbered options."
        )
        threading.Thread(target=run_agent_task, args=(chat_id, grill_prompt), daemon=True).start()

    elif cmd in ["/screenshot", "/shot"]:
        media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
        shot_path = os.path.join(media_dir, f"screen_{int(time.time())}.png")
        if take_desktop_screenshot(shot_path):
            send_photo(chat_id, shot_path, caption=f"📸 <b>Desktop Screenshot</b> - {datetime.datetime.now().strftime('%H:%M:%S')}")
        else:
            send_message(chat_id, "❌ Unable to capture screenshot on this operating system.")

    elif cmd in ["/git", "/status"]:
        try:
            res = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=5)
            b_res = subprocess.run(["git", "branch", "--show-current"], cwd=ws, capture_output=True, text=True, timeout=5)
            branch = b_res.stdout.strip() or "HEAD"
            stat = res.stdout.strip() or "Working tree is clean ✨"
            send_message(chat_id, f"📊 <b>Git Status ({os.path.basename(ws)}):</b>\n🌿 Branch: <code>{branch}</code>\n<pre>{escape_html(stat)}</pre>", reply_markup=get_task_action_buttons(ws))
        except Exception as e:
            send_message(chat_id, f"❌ Git error: {escape_html(str(e))}")

    elif cmd in ["/diff", "/changes"]:
        try:
            res = subprocess.run(["git", "diff", "--stat"], cwd=ws, capture_output=True, text=True, timeout=10)
            out = res.stdout.strip() or "No uncommitted modifications ✨"
            send_message(chat_id, f"📝 <b>Diff Summary:</b>\n<pre>{escape_html(out)}</pre>", reply_markup=get_task_action_buttons(ws))
        except Exception as e:
            send_message(chat_id, f"❌ Diff error: {escape_html(str(e))}")

    elif cmd in ["/stop", "/cancel"]:
        with active_task_lock:
            if current_task_info["running"] and current_task_info["process"]:
                kill_process_tree(current_task_info["process"])
                send_message(chat_id, "🛑 Task terminated.")
            else:
                send_message(chat_id, "No active task running.")

    elif cmd in ["/sh", "/cmd"]:
        if not arg:
            send_message(chat_id, "⚡ Usage: <code>/sh [command]</code> (e.g. <code>/sh free -h</code>)")
            return
        send_message(chat_id, f"⚡ <i>Running: {escape_html(arg[:60])}...</i>")
        try:
            res = subprocess.run(arg, shell=True, cwd=ws, capture_output=True, text=True, timeout=45)
            out = (res.stdout + "\n" + res.stderr).strip() or "Done (no output)."
            send_message(chat_id, f"⚡ <b>Terminal (Exit {res.returncode}):</b>\n<pre>{escape_html(out[-3000:])}</pre>")
        except Exception as e:
            send_message(chat_id, f"❌ Shell error: {escape_html(str(e))}")

    else:
        # Natural Language prompt for Antigravity
        threading.Thread(target=run_agent_task, args=(chat_id, text), daemon=True).start()

# ==========================================
# Main Bot Polling Loop
# ==========================================
def main():
    print("[+] Starting Antigravity Telegram Bridge...")
    start_media_cleanup_daemon()
    offset = None

    if CONFIG.get("allowed_user_id"):
        send_message(CONFIG["allowed_user_id"], "🟢 <b>Antigravity Telegram Bridge is online!</b>", reply_markup=get_main_reply_keyboard())

    while True:
        try:
            params = {"timeout": 30}
            if offset is not None:
                params["offset"] = offset

            resp = requests.get(f"{API_URL}/getUpdates", params=params, timeout=40)
            if not resp.ok:
                time.sleep(5)
                continue

            data = resp.json()
            for update in data.get("result", []):
                offset = update["update_id"] + 1

                # Handle Inline Button callbacks
                cb = update.get("callback_query")
                if cb:
                    cb_id = cb["id"]
                    user_id = cb["from"]["id"]
                    chat_id = cb["message"]["chat"]["id"]
                    cb_data = cb.get("data", "")

                    if user_id != CONFIG.get("allowed_user_id"):
                        answer_callback_query(cb_id, t("unauthorized"))
                        continue

                    if cb_data.startswith("act:"):
                        act = cb_data.split(":", 1)[1]
                        if act == "diff":
                            answer_callback_query(cb_id, "Diff")
                            handle_command(chat_id, user_id, "/diff")
                        elif act == "commit":
                            answer_callback_query(cb_id, "Commit")
                            handle_command(chat_id, user_id, "/commit")
                        elif act == "push":
                            answer_callback_query(cb_id, "Push")
                            handle_command(chat_id, user_id, "/push")
                        elif act == "pr":
                            answer_callback_query(cb_id, "PR")
                            handle_command(chat_id, user_id, "/pr")
                        elif act == "shot":
                            answer_callback_query(cb_id, "Screenshot")
                            handle_command(chat_id, user_id, "/screenshot")
                        elif act == "create_pr_branch":
                            answer_callback_query(cb_id, "Creating branch...")
                            ws, _ = get_effective_workspace()
                            new_b = f"feat/update-{int(time.time())}"
                            subprocess.run(["git", "checkout", "-b", new_b], cwd=ws, timeout=10)
                            handle_pr_workflow(chat_id, ws, "Auto-created feature PR")
                    continue

                msg = update.get("message")
                if not msg:
                    continue

                user_id = msg["from"]["id"]
                chat_id = msg["chat"]["id"]

                # First-touch pairing
                if CONFIG.get("allowed_user_id") is None:
                    CONFIG["allowed_user_id"] = user_id
                    save_config(CONFIG)
                    send_message(chat_id, t("pairing_success", user_id=user_id), reply_markup=get_main_reply_keyboard())

                if user_id != CONFIG.get("allowed_user_id"):
                    send_message(chat_id, t("unauthorized"))
                    continue

                # Voice Note handling
                if "voice" in msg or "audio" in msg:
                    v_obj = msg.get("voice") or msg.get("audio")
                    fid = v_obj.get("file_id")
                    if fid:
                        media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
                        os.makedirs(media_dir, exist_ok=True)
                        ts = int(time.time())
                        ogg_p = os.path.join(media_dir, f"voice_{ts}.ogg")
                        wav_p = os.path.join(media_dir, f"voice_{ts}.wav")
                        send_message(chat_id, "🎙️ <i>Audio received, converting and processing...</i>")
                        if download_telegram_file(fid, ogg_p):
                            subprocess.run(["ffmpeg", "-y", "-i", ogg_p, "-ar", "16000", "-ac", "1", wav_p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                            target_a = wav_p if os.path.exists(wav_p) else ogg_p
                            v_prompt = f"The user sent a voice note saved at: {target_a}. Inspect and transcribe it with view_file, and execute their request."
                            threading.Thread(target=run_agent_task, args=(chat_id, v_prompt), daemon=True).start()
                    continue

                # Photo / Screenshot handling
                if "photo" in msg:
                    fid = msg["photo"][-1]["file_id"]
                    cap = msg.get("caption", "Analyze this image/screenshot and execute any instructions depicted.")
                    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
                    img_p = os.path.join(media_dir, f"photo_{int(time.time())}.jpg")
                    send_message(chat_id, "📸 <i>Image received, analyzing...</i>")
                    if download_telegram_file(fid, img_p):
                        p_prompt = f"The user sent an image at {img_p}. View it with view_file tool, analyze it, and execute: {cap}"
                        threading.Thread(target=run_agent_task, args=(chat_id, p_prompt), daemon=True).start()
                    continue

                # Document / File upload handling
                if "document" in msg:
                    doc = msg["document"]
                    fid = doc.get("file_id")
                    fname = doc.get("file_name", f"file_{int(time.time())}")
                    cap = msg.get("caption", "").strip()
                    fsize = doc.get("file_size", 0)

                    if fid:
                        ws, _ = get_effective_workspace()
                        up_dir = os.path.join(ws, ".scratch", "uploads")
                        os.makedirs(up_dir, exist_ok=True)
                        dest_p = os.path.join(up_dir, fname)
                        if download_telegram_file(fid, dest_p):
                            rel_p = os.path.relpath(dest_p, ws)
                            size_kb = round(fsize / 1024, 1)
                            if cap:
                                d_prompt = f"The user sent a file saved at: {dest_p} (relative: {rel_p}). Inspect it with view_file and execute: {cap}"
                                threading.Thread(target=run_agent_task, args=(chat_id, d_prompt), daemon=True).start()
                            else:
                                send_message(chat_id, t("file_received", name=fname, size=size_kb, path=rel_p))
                    continue

                # Text messages
                if "text" in msg:
                    threading.Thread(target=handle_command, args=(chat_id, user_id, msg["text"]), daemon=True).start()

        except requests.exceptions.RequestException:
            time.sleep(5)
        except Exception as e:
            print(f"[Loop Exception] {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
