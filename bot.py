#!/usr/bin/env python3
"""
Antigravity Telegram Bridge
Allows controlling Antigravity Agent and coding projects remotely via Telegram.
"""

import base64
import datetime
import glob
import json
import os
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

try:
    import sre_engine
except ImportError:
    sre_engine = None

try:
    import analytics_engine
except ImportError:
    analytics_engine = None

try:
    import context_engine
except ImportError:
    context_engine = None

try:
    import terminal_hud
except ImportError:
    terminal_hud = None


CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "bot_token": "",
        "allowed_user_id": None,
        "workspace_mode": "auto",
        "current_workspace": "/mnt/data2/documents/githup/nooreldean-life-os",
        "current_model": "default",
        "current_effort": "default",
        "agy_bin": "/home/nooreldean/.local/bin/agy"
    }

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

CONFIG = load_config()
BOT_TOKEN = CONFIG.get("bot_token")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Thread lock for active task
active_task_lock = threading.Lock()
current_task_info = {"running": False, "process": None, "prompt": "", "start_time": 0}
active_question_state = {}
active_extracted_options = {}
ACTIVE_RUNNING_PROCESSES = []
PENDING_DISPATCH = {}
SESSION_TASK_QUEUE = []


def send_message(chat_id, text, parse_mode="HTML", reply_markup=None):
    url = f"{API_URL}/sendMessage"
    chunk_size = 3800
    if len(text) <= chunk_size:
        chunks = [text]
    else:
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    first_msg_id = None
    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True
        }
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
            print(f"[Error] Failed to send message: {e}")
    return first_msg_id

def edit_message_text(chat_id, message_id, text, parse_mode="HTML", reply_markup=None):
    url = f"{API_URL}/editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "disable_web_page_preview": True
    }
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

def send_chat_action(chat_id, action="typing"):
    url = f"{API_URL}/sendChatAction"
    try:
        requests.post(url, json={"chat_id": chat_id, "action": action}, timeout=5)
    except Exception:
        pass

def keep_typing(chat_id, stop_event):
    while not stop_event.is_set():
        send_chat_action(chat_id, "typing")
        stop_event.wait(4.0)

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
        print(f"[Error] download_telegram_file failed: {e}")
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
        print(f"[Error] send_document failed: {e}")
        return False

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
        print(f"[Error] send_photo failed: {e}")
        return False

def take_desktop_screenshot(dest_path):
    env = os.environ.copy()
    env["XDG_RUNTIME_DIR"] = "/run/user/1000"
    if "WAYLAND_DISPLAY" not in env:
        try:
            for f in os.listdir("/run/user/1000"):
                if f.startswith("wayland-"):
                    env["WAYLAND_DISPLAY"] = f
                    break
        except Exception:
            pass
    if "WAYLAND_DISPLAY" not in env:
        env["WAYLAND_DISPLAY"] = "wayland-1"
    
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    res = subprocess.run(["grim", dest_path], env=env, capture_output=True, text=True, timeout=10)
    return res.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0

def take_web_snapshot(url, dest_path):
    chrome_bin = "/home/nooreldean/.local/bin/google-chrome"
    if not os.path.isfile(chrome_bin):
        chrome_bin = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome_bin:
        return False
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    cmd = [
        chrome_bin,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        f"--screenshot={dest_path}",
        "--window-size=1280,800",
        url
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=15)
        return res.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0
    except Exception:
        return False

def get_modified_code_files(ws, limit=3):
    try:
        res = subprocess.run(["git", "status", "--porcelain"], cwd=ws, capture_output=True, text=True, timeout=5)
        files = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                fpath = parts[1].strip()
                full_p = os.path.join(ws, fpath)
                if os.path.isfile(full_p):
                    files.append(fpath)
        return files[:limit]
    except Exception:
        return []

def get_main_reply_keyboard():
    """Persistent 3x3 reply keyboard for seamless mobile navigation."""
    return {
        "keyboard": [
            [{"text": "⚡ المهام"}, {"text": "📍 أين أنا؟"}, {"text": "📸 سكرين شوت"}],
            [{"text": "📊 حالة Git"}, {"text": "📝 التغييرات Diff"}, {"text": "📂 المشاريع"}],
            [{"text": "⚡ طاقة الـ PC"}, {"text": "🌐 نفق لايف"}, {"text": "🖥️ الـ HUD لايف"}]
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

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
    """Find media files (.png, .jpg, .jpeg, .webp, .svg) created or modified since start_time."""
    media_exts = ('.png', '.jpg', '.jpeg', '.webp', '.svg')
    candidates = []
    
    # 1. Search in workspace
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

    # 2. Search in Antigravity Brain artifacts
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
    """Background daemon thread to auto-delete temporary media older than 24 hours."""
    def _cleanup_loop():
        while True:
            try:
                now = time.time()
                max_age = 86400  # 24 hours
                del_count = 0

                # 1. Bot media folder
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

                # 2. Workspace scratch screenshots
                ws, _ = get_effective_workspace()
                scr_dir = os.path.join(ws, ".scratch", "screenshots")
                if os.path.isdir(scr_dir):
                    for f in os.listdir(scr_dir):
                        fp = os.path.join(scr_dir, f)
                        try:
                            if os.path.isfile(fp) and (now - os.path.getmtime(fp)) > max_age:
                                os.remove(fp)
                                del_count += 1
                        except Exception:
                            pass

                if del_count > 0:
                    print(f"[Media Cleanup Daemon] Removed {del_count} old media files (>24h).")
            except Exception as e:
                print(f"[Media Cleanup Daemon Error] {e}")

            time.sleep(21600)  # Sweep every 6 hours

    t = threading.Thread(target=_cleanup_loop, daemon=True)
    t.start()

tunnel_info = {
    "process": None,
    "http_server_process": None,
    "url": None,
    "port": None,
    "lock": threading.RLock()
}

def stop_active_tunnel():
    with tunnel_info["lock"]:
        if tunnel_info["process"]:
            try:
                tunnel_info["process"].terminate()
            except Exception:
                pass
            tunnel_info["process"] = None
        if tunnel_info["http_server_process"]:
            try:
                tunnel_info["http_server_process"].terminate()
            except Exception:
                pass
            tunnel_info["http_server_process"] = None
        old_url = tunnel_info["url"]
        tunnel_info["url"] = None
        tunnel_info["port"] = None
        return old_url

def is_port_listening(port):
    try:
        res = subprocess.run(["ss", "-tulpn"], capture_output=True, text=True, timeout=5)
        return f":{port}" in res.stdout
    except Exception:
        return False

def find_active_web_port():
    try:
        res = subprocess.run(["ss", "-tulpn"], capture_output=True, text=True, timeout=5)
        for p in [5173, 3000, 8080, 8000, 4200, 5000]:
            if f":{p}" in res.stdout:
                return p
    except Exception:
        pass
    return None

def list_active_servers():
    """Returns a list of actively listening ports and identified server processes."""
    try:
        res = subprocess.run(["ss", "-tulpn"], capture_output=True, text=True, timeout=5)
        lines = res.stdout.splitlines()
        found = []
        known_ports = {
            5173: "Vite Dev Server (Frontend)",
            3000: "React / Next.js Web App",
            8080: "Web Server / HTTP Proxy",
            8000: "Python / Django / FastAPI",
            4200: "Angular Dev Server",
            5000: "Flask / Express Server",
            54321: "Supabase Local API Gateway",
            54322: "Supabase Studio (Dashboard)",
            54323: "Supabase Local Postgres DB",
            5037: "Android ADB Bridge Daemon",
            22: "SSH Remote Server"
        }
        seen_ports = set()
        for line in lines:
            if "LISTEN" in line:
                m = re.search(r":(\d+)\s+", line)
                if m:
                    port = int(m.group(1))
                    if port in seen_ports:
                        continue
                    seen_ports.add(port)
                    proc = ""
                    pm = re.search(r'users:\(\(\"([^\"]+)\"', line)
                    if pm:
                        proc = pm.group(1)
                    desc = known_ports.get(port)
                    if desc or port in [5173, 3000, 8080, 8000, 4200, 5000, 54322] or "supabase" in proc.lower():
                        found.append({"port": port, "name": desc or f"خدمة {proc}", "proc": proc})
        return found
    except Exception:
        return []

def start_cloudflare_tunnel(port):
    with tunnel_info["lock"]:
        if tunnel_info["process"] and tunnel_info["url"] and tunnel_info["port"] == port:
            if tunnel_info["process"].poll() is None:
                return tunnel_info["url"], False
        stop_active_tunnel()

        ws, _ = get_effective_workspace()
        if not is_port_listening(port):
            try:
                p_http = subprocess.Popen(
                    ["python3", "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                    cwd=ws, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                tunnel_info["http_server_process"] = p_http
                time.sleep(0.5)
            except Exception as e:
                print(f"[Error] Failed to start http.server on {port}: {e}")

        cloudflared_bin = "/home/nooreldean/.local/bin/cloudflared"
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "cloudflared.log")
        if os.path.exists(log_path):
            try:
                os.remove(log_path)
            except Exception:
                pass

        log_file = open(log_path, "w")
        p = subprocess.Popen([cloudflared_bin, "tunnel", "--url", f"http://127.0.0.1:{port}"],
                             stdout=log_file, stderr=log_file)
        url = None
        start = time.time()
        while time.time() - start < 15:
            time.sleep(0.5)
            if os.path.exists(log_path):
                try:
                    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", content)
                    if m:
                        url = m.group(0)
                        break
                except Exception:
                    pass
        if url:
            tunnel_info["process"] = p
            tunnel_info["url"] = url
            tunnel_info["port"] = port
            return url, True
        else:
            try:
                p.terminate()
            except Exception:
                pass
            return None, False

def get_task_action_buttons(ws=None):
    if not ws:
        ws, _ = get_effective_workspace()

    rows = [
        [
            {"text": "📊 ملخص Diff", "callback_data": "act:diff"},
            {"text": "💾 Commit", "callback_data": "act:commit"},
            {"text": "🚀 Push", "callback_data": "act:push"}
        ],
        [
            {"text": "🖥️ شاشة الـ HUD", "callback_data": "hud:open"},
            {"text": "🌿 عمل PR", "callback_data": "act:pr"},
            {"text": "🧪 فحص Build", "callback_data": "act:build"}
        ],
        [
            {"text": "📸 شاشة الكمبيوتر", "callback_data": "act:shot"},
            {"text": "↩️ تراجع (Undo)", "callback_data": "act:undo_prompt"},
            {"text": "🚀 Deploy (Vercel)", "callback_data": "act:deploy"}
        ]
    ]

    # One-click file download buttons for modified files
    mod_files = get_modified_code_files(ws, limit=2)
    if mod_files:
        file_btns = []
        for f in mod_files:
            fname = os.path.basename(f)
            file_btns.append({"text": f"📥 تحميل {fname}", "callback_data": f"file_get:{f}"})
        rows.append(file_btns)

    rows.append([
        {"text": "🧠 مؤشر الذاكرة", "callback_data": "ctx:refresh"},
        {"text": "🗜️ ضغط السياق", "callback_data": "ctx:compact"}
    ])
    rows.append([
        {"text": "➕ جلسة جديدة", "callback_data": "conv:new"},
        {"text": "💬 الجلسات", "callback_data": "conv:list"}
    ])

    return {"inline_keyboard": rows}

CONV_DB_PATH = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")

def kill_process_tree(proc):
    """Cleanly terminates the entire process group without leaving orphan background jobs."""
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

def mark_conversation_idle(conv_id=None):
    """Resets not_fully_idle flag in conversation_summaries.db so session is never marked stuck."""
    if not conv_id:
        conv_id = CONFIG.get("current_conversation_id")
    if not conv_id or not os.path.exists(CONV_DB_PATH):
        return
    try:
        conn = sqlite3.connect(CONV_DB_PATH)
        cur = conn.cursor()
        cur.execute("UPDATE conversation_summaries SET not_fully_idle = 0 WHERE conversation_id = ?", (conv_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

def list_recent_conversations(limit=8):
    if not os.path.exists(CONV_DB_PATH):
        return []
    try:
        conn = sqlite3.connect(CONV_DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            SELECT conversation_id, title, preview, step_count, last_modified_time, workspace_uris
            FROM conversation_summaries
            ORDER BY last_modified_time DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
        conn.close()
        res = []
        for r in rows:
            ws_name = ""
            if r[5]:
                try:
                    uris = json.loads(r[5])
                    if uris and isinstance(uris, list):
                        clean_path = uris[0].replace("file://", "").strip().rstrip("/")
                        ws_name = os.path.basename(clean_path)
                except Exception:
                    pass
            res.append({
                "id": r[0],
                "title": r[1] or "محادثة بدون عنوان",
                "preview": r[2] or "",
                "steps": r[3] or 0,
                "last_modified": r[4],
                "workspace": ws_name
            })
        return res
    except Exception as e:
        print(f"[Error] list_recent_conversations: {e}")
        return []

def get_conversation_by_id(conv_id):
    if not os.path.exists(CONV_DB_PATH) or not conv_id:
        return None
    try:
        conn = sqlite3.connect(CONV_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT conversation_id, title, step_count FROM conversation_summaries WHERE conversation_id = ?", (conv_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {"id": row[0], "title": row[1] or "محادثة بدون عنوان", "steps": row[2] or 0}
    except Exception:
        pass
    return None

def get_conversation_details(conv_id):
    """
    Returns deep context for a conversation:
    Workspace project, step count, last tool action, last agent thought, and activity time.
    """
    if not conv_id:
        return None
    info = {
        "id": conv_id,
        "title": "محادثة",
        "workspace": "",
        "steps": 0,
        "last_action": "",
        "last_thought": "",
        "last_user_prompt": "",
        "last_time": ""
    }
    
    if os.path.exists(CONV_DB_PATH):
        try:
            conn = sqlite3.connect(CONV_DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT title, step_count, last_modified_time, workspace_uris 
                FROM conversation_summaries 
                WHERE conversation_id = ?
            """, (conv_id,))
            row = cur.fetchone()
            conn.close()
            if row:
                info["title"] = row[0] or "محادثة بدون عنوان"
                info["steps"] = row[1] or 0
                if row[2]:
                    try:
                        raw_dt = str(row[2]).split(".")[0].strip()
                        dt_obj = datetime.datetime.fromisoformat(raw_dt)
                        info["last_time"] = dt_obj.strftime("%I:%M %p")
                    except Exception:
                        info["last_time"] = str(row[2])[:16]
                if row[3]:
                    try:
                        uris = json.loads(row[3])
                        if uris and isinstance(uris, list):
                            clean_p = uris[0].replace("file://", "").strip().rstrip("/")
                            info["workspace"] = os.path.basename(clean_p)
                    except Exception:
                        pass
        except Exception:
            pass

    # Read transcript for deep details (actual workspace, last action, last thought, last user prompt)
    paths = [
        os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript.jsonl"),
        os.path.expanduser(f"~/.gemini/antigravity-ide/brain/{conv_id}/.system_generated/logs/transcript.jsonl"),
        os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript_full.jsonl")
    ]
    for p in paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            try:
                with open(p, "rb") as f:
                    f.seek(max(0, os.path.getsize(p) - 32768))
                    chunk = f.read().decode("utf-8", errors="ignore")
                lines = [l.strip() for l in chunk.split("\n") if l.strip()]
                for l in reversed(lines):
                    try:
                        d = json.loads(l)
                        if not info["last_action"] and d.get("tool_calls"):
                            tc = d["tool_calls"][0]
                            args = tc.get("args") or tc.get("arguments") or {}
                            act = args.get("toolAction") or args.get("toolSummary") or args.get("Description")
                            if not act:
                                if tc.get("name") == "run_command":
                                    cmd = str(args.get("CommandLine", "")).strip().replace("\n", " ")
                                    act = f"تشغيل: {cmd[:50]}..." if len(cmd) > 50 else f"تشغيل: {cmd}"
                                elif args.get("TargetFile") or args.get("AbsolutePath"):
                                    f_path = (args.get("TargetFile") or args.get("AbsolutePath")).strip("\"'")
                                    act = f"{tc.get('name')} على {os.path.basename(f_path)}"
                                else:
                                    act = tc.get("name")
                            info["last_action"] = str(act).strip("\"'")

                            raw_args = str(args)
                            if "nooreldean-super-app" in raw_args:
                                info["workspace"] = "nooreldean-super-app"
                            elif "content-dashboard" in raw_args:
                                info["workspace"] = "content-dashboard"

                        if not info["last_thought"] and d.get("type") == "PLANNER_RESPONSE" and d.get("content"):
                            c_text = d.get("content").strip()
                            clean_c = c_text.replace("\n", " ")
                            if len(clean_c) > 130:
                                clean_c = clean_c[:130] + "..."
                            info["last_thought"] = clean_c

                        if not info["last_user_prompt"] and d.get("type") == "USER_INPUT" and d.get("content"):
                            u_text = d.get("content").strip()
                            if "<USER_REQUEST>" in u_text:
                                u_text = u_text.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
                            clean_u = u_text.replace("\n", " ")
                            if len(clean_u) > 90:
                                clean_u = clean_u[:90] + "..."
                            info["last_user_prompt"] = clean_u

                        if info["last_action"] and info["last_thought"]:
                            break
                    except Exception:
                        continue
                if info["last_action"] or info["last_thought"]:
                    break
            except Exception:
                pass

    return info

def get_latest_conversation_id():
    if not os.path.exists(CONV_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(CONV_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT conversation_id FROM conversation_summaries ORDER BY last_modified_time DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
    return None

def get_latest_conversation_for_workspace(workspace=None):
    """Retrieves the most recent conversation_id for the given workspace, or the overall latest."""
    if not os.path.exists(CONV_DB_PATH):
        return None
    try:
        conn = sqlite3.connect(CONV_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT conversation_id, title, workspace_uris, last_modified_time FROM conversation_summaries ORDER BY last_modified_time DESC LIMIT 30")
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return None
        if not workspace:
            return rows[0][0]

        target_norm = os.path.abspath(workspace).rstrip("/").lower()
        for cid, title, uris_raw, _ in rows:
            try:
                uris = json.loads(uris_raw) if uris_raw else []
                for u in uris:
                    raw_path = u.replace("file://", "")
                    decoded_path = urllib.parse.unquote(raw_path)
                    if os.path.abspath(decoded_path).rstrip("/").lower() == target_norm:
                        return cid
            except Exception:
                pass
        return rows[0][0]
    except Exception:
        pass
    return None


def auto_rename_session_smartly(conv_id, prompt, workspace):
    """
    Renames the session in conversation_summaries.db from generic placeholders
    like 'Connection Test Ping' to a meaningful, concise title.
    """
    if not conv_id or not os.path.exists(CONV_DB_PATH):
        return
    try:
        conn = sqlite3.connect(CONV_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT title FROM conversation_summaries WHERE conversation_id = ?", (conv_id,))
        row = cur.fetchone()
        curr_title = row[0] if row else ""

        generic_titles = [
            "connection test ping", "network connection test", "casual greeting",
            "new conversation", "untitled", "greeting", "hello", "where are you located"
        ]
        
        # If title is generic or starts with generic prefix
        if not curr_title or any(g in curr_title.lower() for g in generic_titles) or curr_title == prompt:
            proj_name = os.path.basename(workspace.rstrip("/"))
            clean_prompt = prompt.strip().replace("\n", " ")
            if "<USER_REQUEST>" in clean_prompt:
                clean_prompt = clean_prompt.split("<USER_REQUEST>")[1].split("</USER_REQUEST>")[0].strip()
            # Remove filler Arabic words
            clean_prompt = re.sub(r'^(ممكن|عاوز|يا ريت|لو سمحت|من فضلك|اعمل|ضيف|حل)\s+', '', clean_prompt).strip()
            if len(clean_prompt) > 28:
                clean_prompt = clean_prompt[:28].rstrip() + "..."
            
            new_title = f"{proj_name}: {clean_prompt}" if clean_prompt else f"{proj_name}: مهمة برمجية"
            cur.execute("UPDATE conversation_summaries SET title = ? WHERE conversation_id = ?", (new_title, conv_id))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Error] auto_rename_session_smartly: {e}")

def get_latest_live_action(conv_id=None):
    """
    Extracts the latest tool action or step description directly from the conversation transcripts
    to provide real-time granular updates in Telegram.
    """
    try:
        candidates = []
        if conv_id:
            candidates.append(os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript.jsonl"))
            candidates.append(os.path.expanduser(f"~/.gemini/antigravity-ide/brain/{conv_id}/.system_generated/logs/transcript.jsonl"))
            candidates.append(os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript_full.jsonl"))
        else:
            brain_dirs = [
                os.path.expanduser("~/.gemini/antigravity-cli/brain"),
                os.path.expanduser("~/.gemini/antigravity-ide/brain")
            ]
            for b_dir in brain_dirs:
                if os.path.exists(b_dir):
                    subdirs = glob.glob(os.path.join(b_dir, "*/.system_generated/logs/transcript.jsonl"))
                    if subdirs:
                        candidates.extend(subdirs)
            if candidates:
                candidates.sort(key=os.path.getmtime, reverse=True)

        for p in candidates:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                with open(p, "rb") as f:
                    # Seek close to end of file for blazing fast read
                    f.seek(max(0, os.path.getsize(p) - 16384))
                    chunk = f.read().decode("utf-8", errors="ignore")
                lines = [l.strip() for l in chunk.split("\n") if l.strip()]
                for l in reversed(lines):
                    try:
                        data = json.loads(l)
                        tool_calls = data.get("tool_calls")
                        if tool_calls:
                            tc = tool_calls[0]
                            name = tc.get("name", "أمر")
                            args = tc.get("args") or tc.get("arguments") or {}
                            action = args.get("toolAction") or args.get("toolSummary") or args.get("Description")
                            if not action:
                                if name == "run_command":
                                    cmd = args.get("CommandLine", "")
                                    clean_cmd = cmd.strip().replace("\n", " ")
                                    if len(clean_cmd) > 60:
                                        clean_cmd = clean_cmd[:60] + "..."
                                    action = f"تشغيل: {clean_cmd}"
                                elif name in ("view_file", "replace_file_content", "multi_replace_file_content", "write_to_file"):
                                    target = args.get("TargetFile") or args.get("AbsolutePath") or ""
                                    fname = os.path.basename(target.strip("\"'"))
                                    action = f"{name} ({fname})"
                                elif name == "grep_search":
                                    q = str(args.get("Query", ""))[:30]
                                    action = f"بحث: {q}"
                                elif name == "ask_question":
                                    action = "سؤال واستفسار"
                                else:
                                    action = name
                            
                            is_question = False
                            q_text = ""
                            opts = []
                            if name == "ask_question":
                                is_question = True
                                q_list = args.get("questions")
                                if q_list and isinstance(q_list, list) and len(q_list) > 0:
                                    q_obj = q_list[0]
                                    q_text = q_obj.get("question", "")
                                    opts = q_obj.get("options", [])
                                action = f"سؤال الأيجنت: {q_text[:70]}"

                            action = str(action).strip("\"'")
                            return {
                                "step": data.get("step_index"),
                                "tool": name,
                                "action": action,
                                "is_question": is_question,
                                "question": q_text,
                                "options": opts
                            }
                    except Exception:
                        continue
    except Exception:
        pass
    return None

def get_pc_health_report():
    uptime_out = ""
    try:
        res = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=5)
        uptime_out = res.stdout.strip()
    except Exception:
        pass

    ram_out = ""
    try:
        res = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.splitlines():
            if line.startswith("Mem:"):
                parts = line.split()
                ram_out = f"{parts[2]} مستخدم من {parts[1]} (متاح: {parts[6]})"
                break
    except Exception:
        pass

    disk_out = ""
    try:
        res = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = res.stdout.strip().splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            disk_out = f"{parts[3]} متاح من {parts[1]} ({parts[4]} مستخدم)"
    except Exception:
        pass

    gpu_out = ""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            g_parts = [p.strip() for p in res.stdout.strip().split(",")]
            gpu_out = f"{g_parts[0]} (حرارة: {g_parts[1]}°C | ضغط: {g_parts[2]}% | VRAM: {g_parts[3]}MB / {g_parts[4]}MB)"
    except Exception:
        pass

    cpu_temp = ""
    try:
        res = subprocess.run("sensors 2>/dev/null | grep -E 'Package id 0|Core 0|Tctl' | head -n 1", shell=True, capture_output=True, text=True, timeout=5)
        if res.stdout.strip():
            clean_temp = re.search(r'\+?[0-9.]+°C', res.stdout)
            if clean_temp:
                cpu_temp = clean_temp.group(0)
    except Exception:
        pass

    msg = (
        "🖥️ <b>تقرير صحة وحالة الكمبيوتر (Desktop PC Status):</b>\n\n"
        f"⏱️ <b>مدة التشغيل (Uptime):</b> <code>{escape_html(uptime_out or 'غير معروف')}</code>\n"
        f"🧠 <b>الذاكرة العشوائية (RAM):</b> <code>{escape_html(ram_out or 'غير معروف')}</code>\n"
        f"💾 <b>مساحة الهارد (Disk /):</b> <code>{escape_html(disk_out or 'غير معروف')}</code>\n"
    )
    if cpu_temp:
        msg += f"🌡️ <b>حرارة المعالج (CPU Temp):</b> <code>{escape_html(cpu_temp)}</code>\n"
    if gpu_out:
        msg += f"🎮 <b>كارت الشاشة (GPU):</b> <code>{escape_html(gpu_out)}</code>\n"
    else:
        msg += "🎮 <b>كارت الشاشة:</b> مدمج / معطل\n"

    msg += "\n💡 <i>أوامر الشاشة والحماية: <code>/screen off</code> أو <code>/screen on</code> أو <code>/lock</code></i>"
    return msg

SCHEDULES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedules.json")

def get_life_os_now():
    now_dt = datetime.datetime.now()
    cur_time = now_dt.strftime("%H:%M")
    cur_day = now_dt.strftime("%A")

    day_map = {
        "Saturday": ("saturday_college", "السبت (كلية نظري + طلبات مسائي)"),
        "Wednesday": ("wednesday", "الأربعاء (كلية عملي + تصوير ومونتاج شورتس)"),
        "Friday": ("friday", "الجمعة (إجازة + صلاة الجمعة + مراجعة أسبوعية)"),
        "Sunday": ("live_study", "الأحد (لايف Study With Me - 12 ساعة)"),
        "Tuesday": ("live_study", "الثلاثاء (لايف Study With Me - 12 ساعة)"),
        "Monday": ("talabat_full", "الإثنين (شيفت طلبات كامل)"),
        "Thursday": ("talabat_full", "الخميس (شيفت طلبات كامل)")
    }

    sched_id, day_label = day_map.get(cur_day, ("talabat_full", "يوم عادي"))

    schedules_data = {}
    if os.path.exists(SCHEDULES_FILE):
        try:
            with open(SCHEDULES_FILE, "r", encoding="utf-8") as f:
                schedules_data = json.load(f)
        except Exception:
            pass

    sched = schedules_data.get(sched_id, {})
    blocks = sched.get("blocks", [])

    cur_block = None
    next_block = None

    for i, b in enumerate(blocks):
        if b["start"] <= cur_time < b["end"]:
            cur_block = b
            if i + 1 < len(blocks):
                next_block = blocks[i + 1]
            break

    if not cur_block and blocks:
        for b in blocks:
            if b["start"] > b["end"]:
                if cur_time >= b["start"] or cur_time < b["end"]:
                    cur_block = b
                    break
        if not cur_block:
            cur_block = blocks[0]

    out = (
        f"📅 <b>Nooreldean Life OS (المحطة اليومية):</b>\n"
        f"• <b>اليوم:</b> {day_label}\n"
        f"• <b>الوقت الآن:</b> <code>{cur_time}</code>\n\n"
    )
    if cur_block:
        out += (
            f"📍 <b>المحطة الحالية:</b>\n"
            f"{cur_block.get('icon', '📌')} <b>{escape_html(cur_block['title'])}</b>\n"
            f"⏱️ <i>من {cur_block['start']} إلى {cur_block['end']}</i>\n"
            f"📝 {escape_html(cur_block.get('desc', ''))}\n\n"
        )
    if next_block:
        out += (
            f"⏭️ <b>المحطة القادمة ({next_block['start']}):</b>\n"
            f"{next_block.get('icon', '📌')} <b>{escape_html(next_block['title'])}</b>\n"
        )
    return out

def get_briefing_report():
    now_dt = datetime.datetime.now()
    now_str = now_dt.strftime("%A, %d %B %Y - %I:%M %p")
    schedule_text = get_life_os_now()
    pc_report = get_pc_health_report()
    ws, mode_desc = get_effective_workspace()
    
    git_summary = ""
    try:
        st_res = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=5)
        branch_res = subprocess.run(["git", "branch", "--show-current"], cwd=ws, capture_output=True, text=True, timeout=5)
        log_res = subprocess.run(["git", "log", "-n", "1", "--oneline"], cwd=ws, capture_output=True, text=True, timeout=5)
        
        branch = branch_res.stdout.strip() or "main"
        last_commit = log_res.stdout.strip() or "N/A"
        modified_count = len(st_res.stdout.strip().splitlines()) if st_res.stdout.strip() else 0
        
        git_summary = (
            f"• <b>المشروع الحالي:</b> <code>{escape_html(os.path.basename(ws))}</code> ({mode_desc})\n"
            f"• <b>الفرع (Branch):</b> <code>{escape_html(branch)}</code> | 📝 <b>تعديلات معلقة:</b> {modified_count}\n"
            f"• <b>آخر Commit:</b> <code>{escape_html(last_commit)}</code>\n"
        )
    except Exception:
        git_summary = f"• <b>المشروع:</b> <code>{escape_html(ws)}</code>\n"

    active_model = CONFIG.get("current_model", "default")
    active_email = get_email_from_token_file(ACTIVE_TOKEN_PATH)

    report = (
        f"🌅 <b>التقرير الصباحي الشامل وموجز اليوم (Daily Briefing):</b>\n"
        f"⏰ <i>{escape_html(now_str)}</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>1️⃣ محطة وروتين Life OS:</b>\n"
        f"{schedule_text}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>2️⃣ حالة مشروع البرمجة النشط:</b>\n"
        f"{git_summary}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>3️⃣ صحة عتاد الكمبيوتر:</b>\n"
        f"{pc_report}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>الوكيل الذكي:</b> <code>{escape_html(active_model)}</code> | 👤 <code>{escape_html(active_email or 'Google Active')}</code>\n"
        f"<i>الجهاز جاهز ومستعد لأي مهمة من موبايلك طوال اليوم!</i>"
    )
    return report

def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def get_active_ide_workspace():
    pattern = os.path.expanduser('~/.config/Antigravity IDE/User/workspaceStorage/*/workspace.json')
    files = glob.glob(pattern)
    if not files:
        return None
    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
                folder_uri = data.get('folder')
                if folder_uri and folder_uri.startswith('file://'):
                    path = urllib.parse.unquote(folder_uri[7:])
                    if os.path.isdir(path):
                        return path
        except Exception:
            continue
    return None

ACCOUNTS_DIR = os.path.expanduser("~/.gemini/accounts")
ACTIVE_TOKEN_PATH = os.path.expanduser("~/.gemini/jetski-standalone-oauth-token")

def get_email_from_token_file(path=ACTIVE_TOKEN_PATH):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        id_token = data.get("id_token")
        if id_token:
            parts = id_token.split(".")
            if len(parts) >= 2:
                padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(padded))
                return decoded.get("email")
    except Exception:
        pass
    return None

CLI_TOKEN_PATH = os.path.expanduser("~/.gemini/antigravity-cli/antigravity-oauth-token")

def save_current_account_profile():
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    email = get_email_from_token_file(ACTIVE_TOKEN_PATH)
    token_src = ACTIVE_TOKEN_PATH
    if not email:
        email = get_email_from_token_file(CLI_TOKEN_PATH)
        token_src = CLI_TOKEN_PATH

    if email and os.path.isfile(token_src):
        profile_dir = os.path.join(ACCOUNTS_DIR, email)
        os.makedirs(profile_dir, exist_ok=True)
        shutil.copy2(token_src, os.path.join(profile_dir, "jetski-standalone-oauth-token"))
    return email

def list_saved_accounts():
    os.makedirs(ACCOUNTS_DIR, exist_ok=True)
    save_current_account_profile()
    active_email = get_email_from_token_file(ACTIVE_TOKEN_PATH) or get_email_from_token_file(CLI_TOKEN_PATH)
    accounts = []
    for d in os.listdir(ACCOUNTS_DIR):
        token_file = os.path.join(ACCOUNTS_DIR, d, "jetski-standalone-oauth-token")
        if os.path.isfile(token_file):
            accounts.append({
                "email": d,
                "is_active": (d == active_email)
            })
    accounts.sort(key=lambda x: (not x["is_active"], x["email"]))
    return accounts, active_email

def switch_to_account(email):
    profile_token = os.path.join(ACCOUNTS_DIR, email, "jetski-standalone-oauth-token")
    if os.path.isfile(profile_token):
        save_current_account_profile()
        shutil.copy2(profile_token, ACTIVE_TOKEN_PATH)
        try:
            os.makedirs(os.path.dirname(CLI_TOKEN_PATH), exist_ok=True)
            shutil.copy2(profile_token, CLI_TOKEN_PATH)
        except Exception:
            pass
        return True
    return False

def get_next_account(current_email=None):
    accounts, active_email = list_saved_accounts()
    if not accounts:
        return None
    if not current_email:
        current_email = active_email
    emails = [a["email"] for a in accounts]
    try:
        idx = emails.index(current_email)
        next_email = emails[(idx + 1) % len(emails)]
    except ValueError:
        next_email = emails[0]
    return next_email

def is_quota_or_rate_limit_error(text):
    if not text:
        return False
    lower = text.lower()
    patterns = [
        "resource_exhausted",
        "quota exceeded",
        "quota limit",
        "rate limit",
        "ratelimit",
        "too many requests",
        "429",
        "insufficient quota",
        "exceeded your current quota",
        "daily limit exceeded",
        "user rate limit exceeded",
        "credit limit reached",
        "credits exhausted",
        "free tier limit",
        "billing not enabled"
    ]
    return any(p in lower for p in patterns)

def scan_skills():
    skill_dirs = [
        os.path.expanduser('~/.gemini/config/skills/*'),
        os.path.expanduser('~/.gemini/config/plugins/*/skills/*'),
        os.path.expanduser('~/.gemini/antigravity-ide/builtin/skills/*')
    ]
    skills = {}
    for pattern in skill_dirs:
        for path in glob.glob(pattern):
            skill_md = os.path.join(path, 'SKILL.md')
            if os.path.isfile(skill_md):
                name = os.path.basename(path)
                desc = ''
                try:
                    with open(skill_md, 'r', encoding='utf-8') as f:
                        for line in f:
                            sline = line.strip()
                            if sline.startswith('description:'):
                                desc = sline.replace('description:', '').strip().strip("'\"")
                                break
                except Exception:
                    pass
                skills[name] = desc
    return skills

CACHED_SKILLS = scan_skills()

def sync_telegram_commands():
    """Register top 100 commands & skills with Telegram Bot API for autocomplete upon typing '/'"""
    try:
        core_cmds = [
            ("start", "🤖 تشغيل البوت وعرض لوحة التحكم"),
            ("model", "🧠 اختيار نموذج الذكاء الاصطناعي"),
            ("effort", "⚡ تحديد عمق ومستوى التفكير"),
            ("accounts", "👤 إدارة وتبديل حسابات جوجل / Antigravity"),
            ("autofailover", "🛡️ تبديل الكوتا التلقائي عند انتهاء الرصيد"),
            ("chats", "💬 استعراض وتبديل جلسات العمل والمحادثات"),
            ("where", "📍 أين يقف الأيجنت والمشروع والملف الحالي"),
            ("new", "✨ بدء محادثة وجلسة عمل جديدة نظيفة"),
            ("pc", "🖥️ تقرير صحة ومواصفات الكمبيوتر والـ GPU"),
            ("file", "📄 إرسال ملف كود إلى تيليجرام كـ Document"),
            ("screen", "🖥️ إطفاء أو تشغيل الشاشات عن بُعد"),
            ("hud", "🖥️ التحكم في تيرمينال العرض الحي ملء الشاشة"),
            ("lock", "🔒 قفل شاشة الكمبيوتر عن بُعد"),

            ("goal", "🎯 تنفيذ هدف كامل بدون توقف (100% Autonomous)"),
            ("grill_me", "🔥 استجواب واختبار الفكرة وسد الثغرات المعمارية"),
            ("plan", "📋 وضع خطة معمارية للمشروع قبل البدء"),
            ("skills", "🔍 مكتبة المهارات والتصنيفات والبحث"),
            ("status", "💻 فحص حالة الجهاز والمشروع النشط"),
            ("auto", "🔄 تتبع مشروع Antigravity IDE تلقائياً"),
            ("projects", "📂 استعراض مشاريعك في githup"),
            ("git", "📊 فحص حالة Git وآخر Commits"),
            ("commit", "💾 حفظ وتثبيت التعديلات الحالية في Git"),
            ("push", "🚀 رفع الكود على فرع GitHub الحالي"),
            ("deploy", "🚀 رفع الكود على GitHub و Vercel"),
            ("screenshot", "📸 التقاط لقطة شاشة حية لشاشات الكمبيوتر"),
            ("preview", "🌐 فتح رابط معاينة لايف مشفر للمشروع"),
            ("undo", "↩️ تراجع فوري عن تعديلات الكود"),
            ("briefing", "🌅 تقرير صباحي شامل لليوم والمشاريع"),
            ("sh", "⚡ تنفيذ أمر شل/ترمينال مباشر"),
            ("sentry", "🛡️ لوحة أخطاء ومشاكل Sentry"),
            ("incidents", "🚨 سجل الإصلاح التلقائي للأعطال SRE"),
            ("analytics", "📊 التقرير الأسبوعي وهندسة الاستقرار"),
            ("test", "🧪 توليد وفحص اختبارات Unit Tests مؤتمتة"),
            ("servers", "🌐 فحص السيرفرات والخدمات المفتوحة (Ports)"),
            ("diff", "📝 ملخص التغييرات في الكود غير المحفوظة"),
            ("tasks", "⚡ مراقبة العمليات واستهلاك المعالج والرام"),
            ("export", "📄 تصدير سجل الشات الحالي كملف Markdown"),
            ("logs", "📋 عرض آخر أسطر من سجل خدمة البوت"),
            ("restart", "🔄 إعادة تشغيل خدمة البوت عن بُعد"),
            ("pr", "🌿 إنشاء أو فحص Pull Request على GitHub"),
            ("menu", "📱 إظهار لوحة الأزرار السريعة المثبتة"),
            ("context", "🧠 سعة الذاكرة ومؤشر سياق المحادثة"),
            ("compact", "🗜️ ضغط الذاكرة الفوري وتكثيف السياق"),
            ("db_scan", "🗄️ فحص شامل لأمان وأداء قواعد البيانات"),
            ("power", "⚡ لوحة التحكم في طاقة وإيقاف تشغيل الكمبيوتر"),
            ("pc", "💻 التحكم في إيقاف وتشغيل وإسبات الكمبيوتر"),
            ("stop", "🛑 إيقاف المهمة الجارية حالياً")
        ]
        
        commands = [{"command": c, "description": d} for c, d in core_cmds]
        seen = set(c["command"] for c in commands)
        
        priority_skills = [
            "clean-code-guard", "code-review", "tdd", "test-guard", "security-audit",
            "impeccable", "modern-web-guidance", "chrome-devtools",
            "super-app-chat-messenger", "coachdrift-sync-architect", "coachdrift-rls-guard",
            "coachdrift-feature-scaffold", "coachdrift-video", "nooreldean-coaching-video",
            "video-use", "youtube-thumbnail", "reels-scripting", "post-writer",
            "post-formatter", "post-scorer", "hook-generator", "content-matrix",
            "firestore-rules-creation", "flutter-apply-architecture-best-practices",
            "flutter-build-responsive-layout", "flutter-fix-layout-issues",
            "flutter-add-widget-test", "flutter-setup-declarative-routing",
            "dart-run-static-analysis", "diagnosing-bugs", "gemini-carousel", "gemini-infographic"
        ]
        
        def format_desc(text, default):
            if not text:
                return default[:60]
            clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
            clean = clean.replace('`', '').replace('"', '').replace("'", '').strip()
            first_sentence = clean.split('.')[0].strip()
            if len(first_sentence) > 75:
                first_sentence = first_sentence[:72] + '...'
            return first_sentence if first_sentence else default[:60]

        for s in priority_skills:
            if s in CACHED_SKILLS and len(commands) < 100:
                cname = s.replace("-", "_")[:32].lower()
                if cname not in seen and re.match(r'^[a-z0-9_]{1,32}$', cname):
                    commands.append({"command": cname, "description": format_desc(CACHED_SKILLS[s], s)})
                    seen.add(cname)
                    
        for s in sorted(CACHED_SKILLS.keys()):
            if len(commands) >= 100:
                break
            cname = s.replace("-", "_")[:32].lower()
            if re.match(r'^[a-z0-9_]{1,32}$', cname) and cname not in seen:
                commands.append({"command": cname, "description": format_desc(CACHED_SKILLS[s], s)})
                seen.add(cname)

        url = f"{API_URL}/setMyCommands"
        res = requests.post(url, json={"commands": commands}, timeout=10)
        if res.ok:
            print(f"[+] Successfully synced {len(commands)} commands to Telegram Autocomplete Menu!")
        else:
            print(f"[-] Failed to sync commands: {res.text}")
    except Exception as e:
        print(f"[-] Error syncing commands: {e}")

def get_effective_workspace():
    mode = CONFIG.get("workspace_mode", "auto")
    if mode == "auto":
        ide_ws = get_active_ide_workspace()
        if ide_ws:
            return ide_ws, "🔄 تتبع تلقائي للـ IDE"
    manual_ws = CONFIG.get("current_workspace", "/mnt/data2/documents/githup/nooreldean-life-os")
    return manual_ws, "📌 مجلد مثبت يدوياً"

def discover_all_projects():
    """Scans /mnt/data2/documents/githup up to depth 3 for git repositories."""
    base_dir = "/mnt/data2/documents/githup"
    projects = []
    if not os.path.exists(base_dir):
        return projects
    try:
        res = subprocess.run(
            ["find", base_dir, "-maxdepth", "3", "-type", "d", "-name", ".git"],
            capture_output=True, text=True, timeout=5
        )
        for line in res.stdout.splitlines():
            git_dir = line.strip()
            if git_dir:
                p_dir = os.path.dirname(git_dir)
                rel_name = os.path.relpath(p_dir, base_dir)
                bname = os.path.basename(p_dir)
                projects.append({
                    "path": p_dir,
                    "name": bname,
                    "rel_name": rel_name
                })
    except Exception:
        pass
    projects.sort(key=lambda x: x["name"].lower())
    return projects

def find_project_by_query(query):
    query = query.strip().lower()
    projects = discover_all_projects()
    # 1. Exact match
    for p in projects:
        if p["name"].lower() == query or p["rel_name"].lower() == query:
            return p
    # 2. Substring match
    for p in projects:
        if query in p["name"].lower() or query in p["rel_name"].lower():
            return p
    # 3. Direct path
    target = os.path.expanduser(query)
    if os.path.isdir(target):
        return {"path": target, "name": os.path.basename(target), "rel_name": os.path.basename(target)}
    return None

def get_project_state_summary(ws_path):
    """Gathers git branch, last modified file, uncommitted changes, and associated session."""
    info = {
        "branch": "غير متوفر",
        "modified_count": 0,
        "last_file": None,
        "conversation_id": None,
        "conversation_title": None,
        "conversation_steps": 0
    }
    if not os.path.isdir(ws_path):
        return info

    try:
        b_res = subprocess.run(["git", "branch", "--show-current"], cwd=ws_path, capture_output=True, text=True, timeout=3)
        info["branch"] = b_res.stdout.strip() or "HEAD"
        s_res = subprocess.run(["git", "status", "-s"], cwd=ws_path, capture_output=True, text=True, timeout=3)
        lines = [l for l in s_res.stdout.splitlines() if l.strip()]
        info["modified_count"] = len(lines)
        if lines:
            info["last_file"] = lines[0].split()[-1]
    except Exception:
        pass

    p_states = CONFIG.get("project_states", {})
    saved_cid = p_states.get(ws_path, {}).get("conversation_id")

    if not saved_cid and os.path.exists(CONV_DB_PATH):
        try:
            conn = sqlite3.connect(CONV_DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT conversation_id, title, step_count
                FROM conversation_summaries
                WHERE workspace_uris LIKE ?
                ORDER BY last_modified_time DESC LIMIT 1
            """, (f"%{os.path.basename(ws_path)}%",))
            row = cur.fetchone()
            conn.close()
            if row:
                saved_cid = row[0]
                info["conversation_title"] = row[1]
                info["conversation_steps"] = row[2]
        except Exception:
            pass

    if saved_cid:
        info["conversation_id"] = saved_cid
        if not info["conversation_title"]:
            c_det = get_conversation_details(saved_cid)
            if c_det:
                info["conversation_title"] = c_det.get("title")
                info["conversation_steps"] = c_det.get("steps", 0)

    return info

def switch_to_workspace(ws_path):
    """
    Switches to a workspace, saves current project's session,
    restores target project's session, and returns (success, summary_dict).
    """
    if not os.path.isdir(ws_path):
        return False, None

    current_ws, _ = get_effective_workspace()
    current_cid = CONFIG.get("current_conversation_id")
    
    if "project_states" not in CONFIG:
        CONFIG["project_states"] = {}
    if current_ws and current_cid:
        if current_ws not in CONFIG["project_states"]:
            CONFIG["project_states"][current_ws] = {}
        CONFIG["project_states"][current_ws]["conversation_id"] = current_cid
        CONFIG["project_states"][current_ws]["last_active_time"] = datetime.datetime.now().isoformat()

    CONFIG["workspace_mode"] = "manual"
    CONFIG["current_workspace"] = ws_path
    
    summary = get_project_state_summary(ws_path)
    target_cid = summary.get("conversation_id")
    if target_cid:
        CONFIG["current_conversation_id"] = target_cid
        CONFIG["force_new"] = False
    else:
        CONFIG["current_conversation_id"] = None
        CONFIG["force_new"] = True

    if ws_path not in CONFIG["project_states"]:
        CONFIG["project_states"][ws_path] = {}
    if target_cid:
        CONFIG["project_states"][ws_path]["conversation_id"] = target_cid

    save_config(CONFIG)
    return True, summary

def format_project_card(ws_path, summary):
    bname = os.path.basename(ws_path)
    branch = summary.get("branch", "HEAD")
    mod_count = summary.get("modified_count", 0)
    c_title = summary.get("conversation_title")
    steps = summary.get("conversation_steps", 0)
    cid = summary.get("conversation_id")
    
    status_icon = "🧹 نظيف (Clean)" if mod_count == 0 else f"⚠️ {mod_count} ملفات معدلة غير محفوظة"
    
    session_line = ""
    if cid and c_title:
        session_line = (
            f"💬 <b>الجلسة المستعادة:</b> <code>{escape_html(c_title[:45])}</code> 🟢\n"
            f"   ↳ <i>#{steps} خطوة سابقة محفوظة (تتذكر كامل السياق والملفات)</i>\n"
        )
    else:
        session_line = "💬 <b>الجلسة:</b> <i>جلسة جديدة ستتصل مع أول طلب لك ✨</i>\n"

    last_f_line = ""
    if summary.get("last_file"):
        last_f_line = f"📄 <b>آخر ملف معدل:</b> <code>{escape_html(summary['last_file'])}</code>\n"

    msg = (
        f"📂 <b>تم الانتقال وتثبيت سياق المشروع بنجاح!</b>\n\n"
        f"📁 <b>المشروع:</b> <code>{escape_html(bname)}</code>\n"
        f"🌿 <b>فرع Git:</b> <code>{escape_html(branch)}</code>\n"
        f"📊 <b>حالة الكود:</b> {status_icon}\n"
        f"{last_f_line}"
        f"{session_line}\n"
        f"💡 <i>أنت الآن في هذه النقطة تماماً! أي طلب أو فويس نوت ستعمل على هذا المشروع فوراً.</i>"
    )
    
    kb = {
        "inline_keyboard": [
            [
                {"text": "📊 فحص Git", "callback_data": "act:git"},
                {"text": "🧪 فحص Build", "callback_data": "act:build"},
                {"text": "🌐 نفق لايف", "callback_data": "act:tunnel"}
            ],
            [
                {"text": "💬 جلسات المشروع", "callback_data": "conv:list"},
                {"text": "📂 تبديل المشروع", "callback_data": "proj:list"}
            ]
        ]
    }
    return msg, kb

def send_projects_menu(chat_id):
    projects = discover_all_projects()
    current_ws, mode_desc = get_effective_workspace()
    
    if not projects:
        send_message(chat_id, "❌ لم يتم العثور على أي مشاريع في <code>/mnt/data2/documents/githup</code>")
        return

    curr_bname = os.path.basename(current_ws)
    msg = (
        f"📂 <b>مشاريع العمل المتاحة ({len(projects)} مشروع):</b>\n\n"
        f"📍 <b>المشروع الحالي:</b> <code>{escape_html(curr_bname)}</code> ({mode_desc})\n\n"
        f"اضغط على أي مشروع للتبديل إليه مباشرة واستعادة كامل سياقه وملفاته المحفوظة:"
    )

    keyboard_rows = []
    auto_active = (CONFIG.get("workspace_mode") == "auto")
    auto_label = "🟢 🔄 تتبع الـ IDE تلقائياً (نشط)" if auto_active else "🔄 تتبع الـ IDE تلقائياً (Auto)"
    keyboard_rows.append([
        {"text": auto_label, "callback_data": "proj:auto"}
    ])

    row = []
    for idx, p in enumerate(projects):
        try:
            is_curr = (os.path.realpath(p["path"]) == os.path.realpath(current_ws))
        except Exception:
            is_curr = (p["path"] == current_ws)
        icon = "🟢 " if is_curr else "📁 "
        display_name = p["name"]
        btn_text = f"{icon}{display_name}"
        row.append({"text": btn_text, "callback_data": f"proj_set:{idx}"})
        if len(row) == 2:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)

    keyboard_rows.append([
        {"text": "🔄 تحديث القائمة", "callback_data": "proj:refresh"}
    ])

    send_message(chat_id, msg, reply_markup={"inline_keyboard": keyboard_rows})

def run_agent_task(chat_id, prompt, agent_name=None, extra_args=None, banner_title=None, override_workspace=None, force_new_chat=False, allow_parallel=False):
    global current_task_info
    workspace, mode_desc = (override_workspace, "مخصص") if override_workspace else get_effective_workspace()
    agy_bin = CONFIG.get("agy_bin", "/home/nooreldean/.local/bin/agy")
    
    if context_engine and not force_new_chat:
        prompt = context_engine.prepare_prompt_with_context(prompt, workspace)
    
    with active_task_lock:
        if current_task_info["running"] and not allow_parallel:
            send_message(chat_id, "⚠️ هناك مهمة سابقة قيد التنفيذ حالياً، انتظر حتى تنتهي أو اكتب /stop لإيقافها.")
            return
        if not allow_parallel:
            current_task_info["running"] = True
            current_task_info["prompt"] = prompt
            current_task_info["start_time"] = time.time()

    # Detect if prompt invokes a known skill or special banner
    first_word = prompt.strip().split()[0].lstrip("/") if prompt.strip() else ""
    skill_banner = ""
    if banner_title:
        skill_banner = f"{banner_title}\n"
    elif first_word in CACHED_SKILLS:
        skill_desc = CACHED_SKILLS[first_word]
        skill_banner = f"🎯 <b>مهارة نشطة:</b> <code>{first_word}</code>\n"
        if skill_desc:
            skill_banner += f"<i>{escape_html(skill_desc[:120])}...</i>\n"

    agent_banner = f"🤖 <b>وكيل مخصص:</b> <code>{agent_name}</code>\n" if agent_name else ""

    current_conv_id = None if force_new_chat else CONFIG.get("current_conversation_id")
    if not current_conv_id and not CONFIG.get("force_new", False) and not force_new_chat:
        current_conv_id = get_latest_conversation_for_workspace(workspace)

    force_new = CONFIG.get("force_new", False) or force_new_chat
    conv_banner = ""
    if current_conv_id and not force_new:
        c_info = get_conversation_by_id(current_conv_id)
        c_title = c_info["title"] if c_info else current_conv_id[:12]
        short_id = current_conv_id[:8]
        conv_banner = (
            f"💬 <b>الجلسة:</b> <code>{escape_html(c_title[:45])}</code> 🟢\n"
            f"🆔 <b>رقم الشات:</b> <code>{short_id}</code> | 💻 <code>agy --conversation {current_conv_id}</code>\n"
        )
    elif not force_new:
        conv_banner = "💬 <b>الجلسة:</b> <i>استمرار تلقائي للمحادثة (-c)</i> 🟢\n"
    else:
        conv_banner = "💬 <b>الجلسة:</b> <i>محادثة جديدة نظيفة (New)</i> ✨\n"

    active_model = CONFIG.get("current_model", "default")
    active_effort = CONFIG.get("current_effort", "default")

    model_effort_tags = []
    if active_model != "default":
        model_effort_tags.append(f"🧠 {escape_html(active_model)}")
    if active_effort != "default":
        model_effort_tags.append(f"⚡ {escape_html(active_effort)}")
    config_banner = f"<i>{' | '.join(model_effort_tags)}</i>\n" if model_effort_tags else ""

    task_markup = {
        "inline_keyboard": [
            [
                {"text": "🖥️ اعرضه في شاشة الـ HUD لايف", "callback_data": f"hud:open:{current_conv_id or ''}"},
                {"text": "🛑 إيقاف المهمة", "callback_data": "act:stop_task"}
            ]
        ]
    }

    status_msg_id = send_message(
        chat_id,
        f"🚀 <b>بدأ تنفيذ المهمة:</b>\n"
        f"{skill_banner}{agent_banner}{conv_banner}{config_banner}"
        f"<code>{escape_html(prompt[:180])}</code>\n\n"
        f"📁 <i>المسار ({mode_desc}):</i>\n<code>{escape_html(workspace)}</code>",
        reply_markup=task_markup
    )

    if terminal_hud:
        eff_m = active_model if active_model != "default" else "Claude Opus / Gemini Flash"
        eff_e = active_effort if active_effort != "default" else "high"
        terminal_hud.start_terminal_hud(prompt, workspace, model=eff_m, effort=eff_e)

    stop_typing = threading.Event()

    typing_thread = threading.Thread(target=keep_typing, args=(chat_id, stop_typing), daemon=True)
    typing_thread.start()

    stop_progress = threading.Event()

    def live_progress_tracker():
        spinners = ["⏳", "⚡", "🔍", "🛠️", "⚙️", "🧪"]
        idx = 0
        next_milestone = 300  # Send proactive ping every 5 minutes
        asked_questions = set()
        timeout_warned = False
        while not stop_progress.wait(3.5):
            try:
                idx += 1
                elapsed = int(time.time() - start_time)
                spinner = spinners[idx % len(spinners)]
                
                if elapsed < 60:
                    elapsed_str = f"{elapsed} ثانية"
                else:
                    elapsed_str = f"{elapsed // 60} دقيقة و {elapsed % 60} ثانية"

                target_cid = current_conv_id or CONFIG.get("current_conversation_id") or get_latest_conversation_id()
                latest_action_info = get_latest_live_action(target_cid)
                
                step_line = ""
                action_line = ""
                if latest_action_info:
                    st = latest_action_info.get("step")
                    act = latest_action_info.get("action")
                    if st is not None:
                        step_line = f" | 🔄 الخطوة: #{st}"
                    if act:
                        action_line = f"\n🛠️ <b>الإجراء الحالي:</b> <code>{escape_html(act[:110])}</code>"
                else:
                    try:
                        if target_cid and os.path.exists(CONV_DB_PATH):
                            conn = sqlite3.connect(CONV_DB_PATH)
                            cur = conn.cursor()
                            cur.execute("SELECT step_count FROM conversation_summaries WHERE conversation_id = ?", (target_cid,))
                            row = cur.fetchone()
                            conn.close()
                            if row and row[0] is not None:
                                step_line = f" | 🔄 الخطوة: #{row[0]}"
                    except Exception:
                        pass

                ctx_meter = ""
                if context_engine:
                    try:
                        ctx_meter = f"\n{context_engine.format_live_context_badge(target_cid)}"
                    except Exception:
                        pass

                if terminal_hud:
                    try:
                        st_val = latest_action_info.get("step") if latest_action_info else None
                        act_val = latest_action_info.get("action") if latest_action_info else None
                        ctx_val = None
                        if context_engine and hasattr(context_engine, "get_conversation_step_count"):
                            ctx_val = context_engine.get_conversation_step_count(target_cid)
                        terminal_hud.update_terminal_hud_action(step=st_val, action=act_val, activity_item=act_val, context_steps=ctx_val)
                    except Exception:
                        pass


                cid_tag = ""
                if target_cid and "رقم الشات" not in conv_banner:
                    short_id = target_cid[:8]
                    cid_tag = f"🆔 <b>رقم الشات:</b> <code>{short_id}</code> | 💻 <code>agy --conversation {target_cid}</code>\n"

                if status_msg_id:
                    progress_text = (
                        f"{spinner} <b>جاري التنفيذ المباشر...</b>\n"
                        f"{skill_banner}{agent_banner}{conv_banner}{cid_tag}"
                        f"<code>{escape_html(prompt[:140])}</code>\n\n"
                        f"⏱️ <b>الوقت المنقضي:</b> {elapsed_str}{step_line}"
                        f"{ctx_meter}"
                        f"{action_line}\n"
                        f"📁 <i>المسار ({mode_desc}):</i> <code>{escape_html(workspace)}</code>"
                    )
                    stop_markup = {
                        "inline_keyboard": [
                            [
                                {"text": "🖥️ اعرضه في شاشة الـ HUD لايف", "callback_data": f"hud:open:{target_cid or ''}"},
                                {"text": "🛑 إيقاف المهمة", "callback_data": "act:stop_task"}
                            ]
                        ]
                    }
                    edit_message_text(chat_id, status_msg_id, progress_text, reply_markup=stop_markup)

                # Interactive decision prompt if agent asks a question with options
                if latest_action_info and latest_action_info.get("is_question") and latest_action_info.get("options"):
                    st_idx = latest_action_info.get("step")
                    if st_idx not in asked_questions:
                        asked_questions.add(st_idx)
                        q_text = latest_action_info.get("question") or "يحتاج الأيجنت لقرارك للمتابعة:"
                        opts = latest_action_info.get("options", [])
                        active_question_state[st_idx] = opts
                        q_rows = []
                        for o_idx, opt in enumerate(opts):
                            q_rows.append([{"text": f"👉 {opt[:32]}", "callback_data": f"ans_q:{st_idx}:{o_idx}"}])
                        send_message(
                            chat_id,
                            f"❓ <b>سؤال الأيجنت للمتابعة (الخطوة #{st_idx}):</b>\n\n"
                            f"<code>{escape_html(q_text)}</code>\n\n"
                            f"<i>اختر من الأزرار التالية ليتم إرسال إجابتك للأيجنت فوراً:</i>",
                            reply_markup={"inline_keyboard": q_rows}
                        )

                # Proactive progress ping every 5 minutes
                if elapsed >= next_milestone:
                    next_milestone += 300
                    mins = elapsed // 60
                    act_str = latest_action_info.get("action") if latest_action_info else ""
                    act_ping = f"\n🛠️ <code>{escape_html(act_str[:100])}</code>" if act_str else ""
                    st_ping = latest_action_info.get("step") if latest_action_info else "?"
                    send_message(
                        chat_id,
                        f"⏱️ <b>تنبيه تقدم ({mins} دقائق مضت):</b>\n"
                        f"المهمة مستمرة بنشاط... (الخطوة #{st_ping}){act_ping}"
                    )

                # Proactive warning: only if a positive finite timeout is configured
                curr_timeout = current_task_info.get("task_timeout", 0)
                if curr_timeout and curr_timeout > 0:
                    if not timeout_warned and elapsed >= (curr_timeout - 300) and elapsed < curr_timeout:
                        timeout_warned = True
                        rem_mins = max(1, int((curr_timeout - elapsed) // 60))
                        warn_kb = {
                            "inline_keyboard": [
                                [{"text": "⏳ تمديد المهلة +30 دقيقة إضافية", "callback_data": "act:extend_timeout"}],
                                [{"text": "🛑 إيقاف المهمة الآن", "callback_data": "act:stop_task"}]
                            ]
                        }
                        send_message(
                            chat_id,
                            f"⚠️ <b>تنبيه اقتراب انتهاء المهلة:</b>\n"
                            f"المهمة مستمرة منذ {int(elapsed // 60)} دقيقة (متبقي حوالي {rem_mins} دقائق على انتهاء مهلة الـ {int(curr_timeout // 60)} دقيقة).\n\n"
                            f"<i>إذا كانت المهمة ضخمة وترغب في استمرارها بدون مقاطعة، اضغط على زر التمديد:</i>",
                            reply_markup=warn_kb
                        )
            except Exception as loop_err:
                pass

    progress_thread = threading.Thread(target=live_progress_tracker, daemon=True)
    progress_thread.start()

    start_time = time.time()
    try:
        # Determine effective model and effort to avoid conflicts
        eff_model = active_model if active_model != "default" else None
        eff_effort = active_effort if active_effort != "default" else None

        # If model has baked-in effort (e.g. -low, -medium, -high), don't pass a conflicting --effort flag
        if eff_model:
            for suffix in ["low", "medium", "high"]:
                if eff_model.endswith(f"-{suffix}"):
                    if eff_effort and eff_effort != suffix:
                        eff_effort = None
                    break

        cmd = [agy_bin]
        if agent_name:
            cmd.extend(["--agent", agent_name])
        if eff_model:
            cmd.extend(["--model", eff_model])
        if extra_args:
            cmd.extend(extra_args)
        elif eff_effort:
            cmd.extend(["--effort", eff_effort])

        if not extra_args:
            if current_conv_id and not force_new:
                cmd.extend(["--conversation", current_conv_id])
            elif not force_new:
                cmd.append("-c")

        cmd.extend(["-p", prompt, "--dangerously-skip-permissions"])

        max_attempts = len(list_saved_accounts()[0]) if CONFIG.get("auto_failover", True) else 1
        max_attempts = max(1, min(max_attempts, 6))
        attempt = 0
        stdout, stderr = "", ""
        task_timeout = CONFIG.get("task_timeout_seconds", 0)  # 0 = Unlimited execution mode
        timeout_arg = None if (not task_timeout or task_timeout <= 0) else task_timeout

        while attempt < max_attempts:
            attempt += 1
            process = subprocess.Popen(
                cmd,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True
            )
            with active_task_lock:
                if not allow_parallel:
                    current_task_info["process"] = process
                    current_task_info["task_timeout"] = task_timeout
                ACTIVE_RUNNING_PROCESSES.append(process)
            stdout, stderr = process.communicate(timeout=timeout_arg)
            duration = round(time.time() - start_time, 1)

            # Fallback auto-retry if model/effort conflict occurred
            if stderr and ("conflicts with --effort" in stderr or "--effort is not supported" in stderr) and "--effort" in cmd:
                effort_idx = cmd.index("--effort")
                cmd = [c for i, c in enumerate(cmd) if i != effort_idx and i != effort_idx + 1]
                continue

            # Auto-Failover to next account if quota/rate limit error occurred
            full_out = f"{stdout or ''}\n{stderr or ''}"
            if (process.returncode != 0 or not stdout) and is_quota_or_rate_limit_error(full_out) and CONFIG.get("auto_failover", True):
                current_acc = get_email_from_token_file(ACTIVE_TOKEN_PATH) or get_email_from_token_file(CLI_TOKEN_PATH)
                next_acc = get_next_account(current_acc)
                if next_acc and next_acc != current_acc and attempt < max_attempts:
                    switch_to_account(next_acc)
                    send_message(
                        chat_id,
                        f"⚠️ <b>تنبيه كوتا (Rate Limit / Quota Exceeded):</b>\n"
                        f"الحساب <code>{escape_html(current_acc or 'الحالي')}</code> استنفد الكوتا.\n\n"
                        f"🔄 <b>تم التبديل تلقائياً إلى:</b>\n"
                        f"👉 <code>{escape_html(next_acc)}</code> 🟢\n\n"
                        f"<i>جاري استكمال المهمة تلقائياً دون انقطاع...</i>"
                    )
                    time.sleep(1)
                    continue

            break

        # Automatically capture active conversation ID for seamless follow-up
        try:
            latest_id = get_latest_conversation_id()
            if latest_id:
                CONFIG["current_conversation_id"] = latest_id
                CONFIG["force_new"] = False
                if "project_states" not in CONFIG:
                    CONFIG["project_states"] = {}
                if workspace not in CONFIG["project_states"]:
                    CONFIG["project_states"][workspace] = {}
                CONFIG["project_states"][workspace]["conversation_id"] = latest_id
                CONFIG["project_states"][workspace]["last_active_time"] = datetime.datetime.now().isoformat()
                save_config(CONFIG)
                auto_rename_session_smartly(latest_id, prompt, workspace)
        except Exception:
            pass

        result_text = stdout.strip() if stdout else ""
        if stderr and not result_text:
            result_text = f"Errors:\n{stderr.strip()}"

        if not result_text:
            result_text = "تمت المهمة بدون مخرجات نصية."

        cid = CONFIG.get("current_conversation_id") or get_latest_conversation_for_workspace(workspace)
        active_conv = get_conversation_by_id(cid)
        conv_label = ""
        if active_conv:
            short_id = cid[:8] if cid else ""
            conv_label = (
                f"\n💬 <b>الجلسة:</b> <code>{escape_html(active_conv['title'])}</code>\n"
                f"🆔 <b>رقم الشات:</b> <code>{short_id}</code> | 💻 <code>agy --conversation {cid}</code>"
            )
        elif cid:
            conv_label = f"\n🆔 <b>رقم الشات:</b> <code>{cid[:8]}</code> | 💻 <code>agy --conversation {cid}</code>"
        header = f"✅ <b>تمت المهمة بنجاح ({duration}s):</b>{conv_label}\n\n"

        if terminal_hud:
            try:
                mod_f = get_modified_code_files(workspace)
                terminal_hud.finish_terminal_hud(duration=duration, summary=result_text[:400], modified_files=mod_f)
            except Exception as he:
                print(f"[HUD finish error] {he}")

        # Check if output contains interactive multiple-choice options (e.g. from grill-me or questions)
        detected_options = extract_interactive_options(result_text)
        action_markup = get_task_action_buttons(workspace)
        if detected_options:
            opt_buttons = []
            q_id = int(time.time())
            active_extracted_options[q_id] = detected_options
            for opt in detected_options:
                opt_buttons.append([{"text": f"👉 {opt['label']}", "callback_data": f"pick_opt:{q_id}:{opt['index']}"}])
            action_markup["inline_keyboard"] = opt_buttons + action_markup["inline_keyboard"]

        # Continuous Context Compaction & Hard Cap Check after every message
        ctx_footer = ""
        did_rollover = False
        rollover_notice = ""
        if context_engine:
            try:
                did_rollover, rollover_notice, ctx_stats = context_engine.compress_after_message(
                    CONFIG.get("current_conversation_id"),
                    workspace,
                    prompt,
                    result_text
                )
                ctx_footer = f"\n\n{ctx_stats['meter_badge']} | 🗜️ <i>تم ضغط السياق</i>"
            except Exception as ce:
                print(f"[ContextEngine error] {ce}")

        send_message(chat_id, header + f"<pre>{escape_html(result_text)}</pre>" + ctx_footer, reply_markup=action_markup)

        if did_rollover and rollover_notice:
            send_message(chat_id, rollover_notice)

        # Auto-deliver newly generated media / artifacts
        try:
            start_t = current_task_info.get("start_time") or (time.time() - duration)
            new_media = find_newly_generated_media(workspace, start_t)
            for media_path in new_media:
                fname = os.path.basename(media_path)
                caption = f"🎨 <b>تصميم / صورة ناتجة من الأيجنت:</b>\n📁 <code>{escape_html(fname)}</code>"
                if media_path.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    if not send_photo(chat_id, media_path, caption=caption):
                        send_document(chat_id, media_path, caption=caption)
                else:
                    send_document(chat_id, media_path, caption=caption)
        except Exception as e:
            print(f"[Auto-deliver media error] {e}")

    except subprocess.TimeoutExpired:
        if current_task_info["process"]:
            kill_process_tree(current_task_info["process"])
        mark_conversation_idle()
        if terminal_hud:
            terminal_hud.finish_terminal_hud(duration=current_task_info.get("task_timeout", 1800), summary="Task reached timeout limit.", modified_files=[])
        timeout_mins = int(current_task_info.get("task_timeout", 1800) / 60)
        resume_markup = {
            "inline_keyboard": [
                [{"text": "▶️ استكمال العمل من نفس النقطة", "callback_data": "act:resume_task"}]
            ]
        }
        send_message(
            chat_id,
            f"⏱️ <b>توقفت المهمة:</b> تخطت المهلة المحددة ({timeout_mins} دقيقة).\n\n"
            f"💡 <b>ملاحظة:</b> تم حفظ كل الخطوات والملفات المعدلة في الجلسة وتنظيف العمليات بالكامل.\n"
            f"اضغط على الزر أدناه للاستكمال فوراً دون الحاجة للكتابة:",
            reply_markup=resume_markup
        )
    except Exception as e:
        if terminal_hud:
            terminal_hud.finish_terminal_hud(duration=0, summary=f"Task error: {str(e)}", modified_files=[])
        send_message(chat_id, f"❌ <b>حدث خطأ أثناء التشغيل:</b>\n<code>{escape_html(str(e))}</code>")

    finally:
        stop_progress.set()
        stop_typing.set()
        mark_conversation_idle()
        with active_task_lock:
            if not allow_parallel:
                current_task_info["running"] = False
                current_task_info["process"] = None
                current_task_info["prompt"] = ""
                current_task_info["start_time"] = 0
            if 'process' in locals() and process in ACTIVE_RUNNING_PROCESSES:
                try:
                    ACTIVE_RUNNING_PROCESSES.remove(process)
                except ValueError:
                    pass

        # Automatically pop and trigger next queued task for this session
        if not allow_parallel and SESSION_TASK_QUEUE:
            next_task = SESSION_TASK_QUEUE.pop(0)
            ws_target = next_task.get("workspace") or workspace
            send_message(
                chat_id,
                f"🔄 <b>انتهت المهمة السابقة، جاري بدء المهمة المنتظرة تلقائياً:</b>\n"
                f"📋 <code>{escape_html(next_task['prompt'][:140])}</code>"
            )
            threading.Thread(
                target=run_agent_task,
                args=(chat_id, next_task["prompt"]),
                kwargs={
                    "agent_name": next_task.get("agent_name"),
                    "extra_args": next_task.get("extra_args"),
                    "banner_title": next_task.get("banner_title"),
                    "override_workspace": ws_target
                },
                daemon=True
            ).start()

MODELS_MAP = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6-thinking",
    "flash": "gemini-3.8-flash-high",
    "flash_low": "gemini-3.8-flash-low",
    "flash_med": "gemini-3.8-flash-medium",
    "gpt": "gpt-oss-120b-medium",
    "claude-sonnet-4-6": "claude-sonnet-4-6",
    "claude-opus-4-6-thinking": "claude-opus-4-6-thinking",
    "gemini-3.8-flash-high": "gemini-3.8-flash-high",
    "gemini-3.8-flash-medium": "gemini-3.8-flash-medium",
    "gemini-3.8-flash-low": "gemini-3.8-flash-low",
    "gpt-oss-120b-medium": "gpt-oss-120b-medium",
    "default": "default"
}

EFFORT_MAP = {
    "max": "max",
    "xhigh": "xhigh",
    "high": "high",
    "medium": "medium",
    "med": "medium",
    "low": "low",
    "default": "default"
}

def send_diff_summary(chat_id, ws=None):
    if not ws:
        ws, _ = get_effective_workspace()
    try:
        res_stat = subprocess.run(["git", "diff", "--stat"], cwd=ws, capture_output=True, text=True, timeout=10)
        stat_out = res_stat.stdout.strip()
        if not stat_out:
            res_staged = subprocess.run(["git", "diff", "--staged", "--stat"], cwd=ws, capture_output=True, text=True, timeout=10)
            stat_out = res_staged.stdout.strip()

        bname = os.path.basename(ws)
        if not stat_out:
            send_message(chat_id, f"📝 <b>ملخص التعديلات ({escape_html(bname)}):</b>\nلا توجد أي تعديلات غير محفوظة (Working tree clean) ✨")
            return

        diff_buttons = []
        mod_files = get_modified_code_files(ws, limit=4)
        for f in mod_files:
            diff_buttons.append([{"text": f"📥 تحميل {os.path.basename(f)}", "callback_data": f"file_get:{f}"}])
        
        diff_buttons.append([
            {"text": "💾 Commit التعديلات", "callback_data": "act:commit"},
            {"text": "↩️ تراجع Undo", "callback_data": "act:undo"}
        ])

        diff_msg = (
            f"📝 <b>ملخص التغييرات في الكود ({escape_html(bname)}):</b>\n"
            f"<pre>{escape_html(stat_out)}</pre>\n\n"
            f"<i>اضغط على زر أي ملف لتحميله ومراجعته مباشرة في تيليجرام.</i>"
        )
        send_message(chat_id, diff_msg, reply_markup={"inline_keyboard": diff_buttons})
    except Exception as e:
        send_message(chat_id, f"❌ خطأ فحص Diff: {escape_html(str(e))}")

def handle_pr_workflow(chat_id, ws, arg=""):
    """Creates or views a GitHub Pull Request using gh CLI."""
    if not os.path.isdir(os.path.join(ws, ".git")):
        send_message(chat_id, "❌ هذا المجلد ليس مستودع Git.")
        return

    try:
        b_res = subprocess.run(["git", "branch", "--show-current"], cwd=ws, capture_output=True, text=True, timeout=5)
        branch_name = b_res.stdout.strip()
        if not branch_name:
            send_message(chat_id, "⚠️ لا يمكن تحديد اسم الفرع الحالي (Detached HEAD).")
            return

        st_res = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=5)
        uncommitted = st_res.stdout.strip()
        if uncommitted:
            send_message(
                chat_id,
                f"⚠️ <b>هناك تعديلات غير محفوظة في فرع <code>{escape_html(branch_name)}</code>:</b>\n\n"
                f"يُرجى عمل <code>/commit</code> لحفظ التعديلات أولاً، أو الضغط على زر Commit أدناه:",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "💾 عمل Commit الآن", "callback_data": "act:commit"}],
                        [{"text": "📊 عرض التغييرات (Diff)", "callback_data": "act:diff"}]
                    ]
                }
            )
            return

        if branch_name in ["main", "master"]:
            send_message(
                chat_id,
                f"⚠️ <b>أنت تقف حالياً على الفرع الرئيسي (<code>{escape_html(branch_name)}</code>):</b>\n\n"
                f"لإنشاء Pull Request نظيف ومطابق لمعايير GitHub، يُفضل العمل على فرع ميزات منفصل.\n"
                f"هل تود إنشاء فرع تلقائي وعمل الـ PR عليه مباشرة؟",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "🌿 إنشاء فرع وعمل PR تلقائياً", "callback_data": "act:create_pr_branch"}],
                        [{"text": "❌ إلغاء", "callback_data": "act:undo_cancel"}]
                    ]
                }
            )
            return

        send_message(chat_id, f"🚀 <i>جاري التحقق من فرع <code>{escape_html(branch_name)}</code> ومزامنته مع GitHub...</i>")

        # Push branch to origin
        subprocess.run(["git", "push", "-u", "origin", branch_name], cwd=ws, capture_output=True, text=True, timeout=60)

        # Check if PR already exists
        view_res = subprocess.run(["gh", "pr", "view", "--json", "url,title,state,number"], cwd=ws, capture_output=True, text=True, timeout=15)
        if view_res.returncode == 0:
            try:
                pr_data = json.loads(view_res.stdout)
                pr_url = pr_data.get("url")
                pr_num = pr_data.get("number")
                pr_title = pr_data.get("title")
                pr_state = pr_data.get("state", "OPEN")
                send_message(
                    chat_id,
                    f"ℹ️ <b>يوجد بالفعل Pull Request مفتوح لهذا الفرع (#{pr_num}):</b>\n\n"
                    f"📁 <b>المشروع:</b> <code>{escape_html(os.path.basename(ws))}</code>\n"
                    f"🌿 <b>الفرع:</b> <code>{escape_html(branch_name)}</code>\n"
                    f"📝 <b>العنوان:</b> {escape_html(pr_title)}\n"
                    f"📊 <b>الحالة:</b> <code>{escape_html(pr_state)}</code>\n\n"
                    f"🔗 <b>الرابط:</b> <a href=\"{pr_url}\">{pr_url}</a>",
                    reply_markup={
                        "inline_keyboard": [
                            [{"text": f"🔗 فتح PR #{pr_num} على GitHub", "url": pr_url}],
                            [{"text": "📊 فحص حالة Git", "callback_data": "act:git"}]
                        ]
                    }
                )
                return
            except Exception:
                pass

        # Create PR using gh pr create
        title = arg.strip() if arg.strip() else f"feat: updates from {branch_name}"
        body = (
            f"### Automated Pull Request\n\n"
            f"- **Project:** `{os.path.basename(ws)}`\n"
            f"- **Branch:** `{branch_name}`\n"
            f"- **Created via:** Antigravity Mobile Telegram Bot\n"
        )
        create_res = subprocess.run(
            ["gh", "pr", "create", "--title", title, "--body", body, "--head", branch_name],
            cwd=ws, capture_output=True, text=True, timeout=40
        )

        if create_res.returncode == 0:
            pr_out = create_res.stdout.strip()
            urls = re.findall(r"https://github\.com/[^\s]+/pull/\d+", pr_out)
            final_url = urls[0] if urls else pr_out
            send_message(
                chat_id,
                f"🎉 <b>تم إنشاء الـ Pull Request بنجاح على GitHub!</b>\n\n"
                f"📁 <b>المشروع:</b> <code>{escape_html(os.path.basename(ws))}</code>\n"
                f"🌿 <b>الفرع:</b> <code>{escape_html(branch_name)}</code>\n"
                f"📝 <b>العنوان:</b> <code>{escape_html(title)}</code>\n\n"
                f"🔗 <b>الرابط المباشر:</b>\n<a href=\"{final_url}\">{final_url}</a>",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "🔗 فتح الـ PR في المتصفح", "url": final_url}],
                        [{"text": "📊 فحص حالة Git", "callback_data": "act:git"}]
                    ]
                }
            )
        else:
            send_message(
                chat_id,
                f"❌ <b>فشل إنشاء الـ Pull Request:</b>\n<pre>{escape_html((create_res.stdout + create_res.stderr).strip()[:800])}</pre>"
            )

    except Exception as e:
        send_message(chat_id, f"❌ خطأ أثناء معالجة PR: {escape_html(str(e))}")

def export_conversation_to_markdown(conv_id, ws_path):
    """Parses transcript.jsonl or SQLite conversation and returns exported markdown filepath."""
    cli_brain = os.path.expanduser(f"~/.gemini/antigravity-cli/brain/{conv_id}/.system_generated/logs/transcript.jsonl")
    ide_brain = os.path.expanduser(f"~/.gemini/antigravity-ide/brain/{conv_id}/.system_generated/logs/transcript.jsonl")
    
    trans_path = cli_brain if os.path.exists(cli_brain) else (ide_brain if os.path.exists(ide_brain) else None)
    
    bname = os.path.basename(ws_path)
    export_dir = os.path.join(ws_path, ".scratch", "chats")
    os.makedirs(export_dir, exist_ok=True)
    ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(export_dir, f"chat_{conv_id[:8]}_{ts_str}.md")

    lines_out = [
        f"# 💬 سجل محادثة Antigravity",
        f"- **معرف الجلسة:** `{conv_id}`",
        f"- **المشروع:** `{bname}`",
        f"- **تاريخ التصدير:** `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`",
        f"\n---\n"
    ]

    if trans_path and os.path.exists(trans_path):
        turn_num = 0
        try:
            with open(trans_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    
                    t = data.get("type")
                    content = data.get("content", "").strip()
                    created_at = data.get("created_at", "")

                    if t == "USER_INPUT":
                        turn_num += 1
                        m = re.search(r"<USER_REQUEST>(.*?)</USER_REQUEST>", content, re.DOTALL)
                        req = m.group(1).strip() if m else content
                        lines_out.append(f"\n### 👤 المستخدم (طلب #{turn_num}) - {created_at}\n\n{req}\n")
                        lines_out.append("\n---\n")
                    elif t == "PLANNER_RESPONSE":
                        if content == "..." or not content:
                            continue
                        lines_out.append(f"\n### 🤖 رد الوكيل (Agent Response)\n\n{content}\n")
                        lines_out.append("\n---\n")
        except Exception as e:
            lines_out.append(f"\n*خطأ أثناء قراءة السجل: {str(e)}*\n")
    else:
        det = get_conversation_details(conv_id)
        if det:
            lines_out.append(f"### 📌 ملخص الجلسة:\n- **العنوان:** {det.get('title')}\n- **الخطوات:** #{det.get('steps')}\n- **آخر إجراء:** {det.get('last_action')}\n- **آخر فكرة:** {det.get('last_thought')}\n")
        else:
            lines_out.append(f"لا يوجد سجل تفصيلي محفوظ لهذه الجلسة.")

    with open(out_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out))

    return out_file

def get_task_status_card():
    with active_task_lock:
        is_running = current_task_info["running"]
        prompt = current_task_info.get("prompt", "")
        proc = current_task_info.get("process")
        start_t = current_task_info.get("start_time", 0)

    ws, mode_desc = get_effective_workspace()
    servers = list_active_servers()
    
    tunnel_url = None
    tunnel_p = None
    with tunnel_info["lock"]:
        if tunnel_info["process"] and tunnel_info["url"]:
            tunnel_url = tunnel_info["url"]
            tunnel_p = tunnel_info.get("port")

    if is_running and proc:
        pid = proc.pid
        cpu_usage = "0%"
        mem_usage = "0MB"
        try:
            p_res = subprocess.run(["ps", "-p", str(pid), "-o", "%cpu,%mem,rss"], capture_output=True, text=True, timeout=3)
            lines = [l.strip() for l in p_res.stdout.splitlines() if l.strip()]
            if len(lines) > 1:
                parts = lines[1].split()
                cpu_usage = f"{parts[0]}%"
                rss_kb = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
                mem_usage = f"{round(rss_kb / 1024, 1)}MB"
        except Exception:
            pass

        target_cid = CONFIG.get("current_conversation_id")
        action_info = get_latest_live_action(target_cid) if target_cid else None
        act_str = action_info.get("action") if action_info else "جاري معالجة الكود..."
        step_num = action_info.get("step") if action_info else "?"
        
        elapsed_sec = int(time.time() - start_t) if start_t else 0
        if elapsed_sec < 60:
            dur_str = f"{elapsed_sec} ثانية"
        else:
            dur_str = f"{elapsed_sec // 60} دقيقة و {elapsed_sec % 60} ثانية"

        msg = (
            f"⚡ <b>لوحة مراقبة المهام والعمليات (Tasks Monitor):</b>\n\n"
            f"🟢 <b>حالة الوكيل:</b> يعمل بنشاط الآن (PID: <code>{pid}</code>)\n"
            f"• <b>المهمة:</b> <code>{escape_html(prompt[:120])}</code>\n"
            f"• <b>المدة:</b> {dur_str}\n"
            f"• <b>المعالج (CPU):</b> <code>{cpu_usage}</code> | <b>الذاكرة (RAM):</b> <code>{mem_usage}</code>\n"
            f"• <b>الخطوة الحالية:</b> #{step_num}\n"
            f"• <b>الإجراء:</b> <code>{escape_html(act_str[:100])}</code>\n"
            f"• <b>المشروع:</b> <code>{escape_html(os.path.basename(ws))}</code>\n"
        )
    else:
        msg = (
            f"⚡ <b>لوحة مراقبة المهام والعمليات (Tasks Monitor):</b>\n\n"
            f"🟢 <b>حالة الوكيل:</b> خامل ومستعد لاستقبال الأوامر (Idle)\n"
            f"• <b>المشروع النشط:</b> <code>{escape_html(os.path.basename(ws))}</code> ({mode_desc})\n"
        )

    if tunnel_url:
        msg += f"\n🌐 <b>النفق النشط (Tunnel):</b> <code>{escape_html(tunnel_url)}</code> (Port: {tunnel_p})\n"

    if servers:
        msg += f"\n🔌 <b>السيرفرات المحلية النشطة:</b> {len(servers)} سيرفر يعمل (اكتب /servers)\n"

    kb = {
        "inline_keyboard": [
            [{"text": "🔄 تحديث", "callback_data": "act:tasks_refresh"},
             {"text": "🛑 إيقاف المهمة", "callback_data": "act:stop_task"} if is_running else {"text": "📋 سجل Logs", "callback_data": "act:logs_refresh"}],
            [{"text": "📊 فحص Git", "callback_data": "act:git"},
             {"text": "📝 ملخص Diff", "callback_data": "act:diff"}]
        ]
    }
    return msg, kb

def prompt_task_dispatch(chat_id, prompt_text, banner_title=None, extra_args=None, agent_name=None):
    """
    Prompts the user to decide how to execute a new request:
      1. Continue in the current session (queues if busy, or runs immediately)
      2. Start in a new session (prompts for project workspace, then executes in parallel)
      3. Cancel
    """
    task_id = str(int(time.time() * 1000))[-6:]
    PENDING_DISPATCH[task_id] = {
        "task_id": task_id,
        "chat_id": chat_id,
        "prompt": prompt_text,
        "banner_title": banner_title,
        "extra_args": extra_args,
        "agent_name": agent_name,
        "created_at": time.time()
    }

    ws, mode_desc = get_effective_workspace()
    curr_pname = os.path.basename(ws.rstrip("/"))
    cid = CONFIG.get("current_conversation_id") or get_latest_conversation_for_workspace(ws)
    c_info = get_conversation_by_id(cid) if cid else None
    c_title = c_info["title"] if c_info else (cid[:8] if cid else "جديدة")

    is_busy = current_task_info.get("running", False) or bool(ACTIVE_RUNNING_PROCESSES)
    busy_status = "⏳ <i>(توجد مهمة تعمل حالياً في هذا المشروع)</i>\n" if is_busy else "🟢 <i>(النظام متاح للتنفيذ الفوري)</i>\n"

    msg = (
        f"📥 <b>استلمت طلبك الجديد:</b>\n"
        f"<code>{escape_html(prompt_text[:160])}</code>\n\n"
        f"📍 <b>المشروع الحالي:</b> <code>{escape_html(curr_pname)}</code>\n"
        f"💬 <b>الجلسة الحالية:</b> <code>{escape_html(c_title[:35])}</code>\n"
        f"{busy_status}\n"
        f"<b>كيف تود تنفيذ هذا الطلب؟</b>"
    )

    same_label = "💬 في نفس الشات" + (" (انتظار الدور ⏳)" if is_busy else " (تنفيذ فوري ⚡)")
    kb = {
        "inline_keyboard": [
            [
                {"text": same_label, "callback_data": f"dsp:same:{task_id}"}
            ],
            [
                {"text": "✨ في شات جديد (اختيار المشروع 📁)", "callback_data": f"dsp:new:{task_id}"}
            ],
            [
                {"text": "❌ إلغاء الطلب", "callback_data": f"dsp:cancel:{task_id}"}
            ]
        ]
    }
    send_message(chat_id, msg, reply_markup=kb)

def handle_command(chat_id, user_id, text):
    TEXT_COMMAND_ALIASES = {
        "⚡ المهام": "/tasks",
        "📍 أين أنا؟": "/where",
        "📸 سكرين شوت": "/screenshot",
        "📊 حالة git": "/git",
        "📊 حالة Git": "/git",
        "📝 التغييرات diff": "/diff",
        "📝 التغييرات Diff": "/diff",
        "📂 المشاريع": "/projects",
        "🌐 نفق لايف": "/preview",
        "🔌 السيرفرات": "/servers",
        "🔄 تحديث/ريستارت": "/restart",
        "⚡ طاقة الـ PC": "/pc",
        "طاقة": "/pc",
        "الباور": "/pc",
        "🖥️ الـ HUD لايف": "/hud",
        "قفل الكمبيوتر": "/lock",
        "قائمة": "/menu",
        "مينيو": "/menu",
        "المينيو": "/menu"
    }

    clean_text = text.strip()
    if clean_text in TEXT_COMMAND_ALIASES:
        text = TEXT_COMMAND_ALIASES[clean_text]

    parts = text.strip().split(maxsplit=1)
    raw_cmd = parts[0].lower().lstrip("/")
    cmd = "/" + raw_cmd
    arg = parts[1] if len(parts) > 1 else ""

    # Check if this command corresponds to a skill (either exact or with underscores -> hyphens)
    hyphen_skill = raw_cmd.replace("_", "-")
    core_commands = [
        "start", "help", "model", "effort", "goal", "grill_me", "grill-me", "grill",
        "plan", "skills", "agent", "auto", "status", "where", "servers", "sentry", "incidents", "analytics", "weekly", "test", "test_gen", "test-gen", "sre",
        "commit", "push", "cd", "projects", "git", "deploy", "stop",
        "diff", "restart", "logs", "log", "errors", "export", "transcript", "dump", "tasks", "top", "ps", "jobs",
        "pr", "pullrequest", "menu", "hidemenu", "hud", "pc", "power", "shutdown", "poweroff", "suspend", "sleep", "reboot"
    ]
    
    if raw_cmd not in core_commands and (raw_cmd in CACHED_SKILLS or hyphen_skill in CACHED_SKILLS):
        skill_name = raw_cmd if raw_cmd in CACHED_SKILLS else hyphen_skill
        skill_desc = CACHED_SKILLS.get(skill_name, "")
        skill_prompt = f"/{skill_name} {arg}".strip() if arg else f"Activate the {skill_name} skill and report capabilities or status."
        threading.Thread(
            target=run_agent_task,
            args=(chat_id, skill_prompt),
            kwargs={
                "banner_title": f"🎯 <b>مهارة نشطة:</b> <code>{skill_name}</code>\n<i>{escape_html(skill_desc[:120])}...</i>"
            },
            daemon=True
        ).start()
        return

    if cmd in ["/start", "/help"]:
        ws, mode_desc = get_effective_workspace()
        active_model = CONFIG.get("current_model", "default")
        active_effort = CONFIG.get("current_effort", "default")
        msg = (
            "🤖 <b>أهلاً بك في بوت Antigravity الشخصي!</b>\n\n"
            "أنت الآن متصل بالوكيل الذكي Antigravity مع كامل التحكم في النماذج ومستويات التفكير والتخصيصات.\n\n"
            f"📁 <b>المشروع الحالي:</b> <code>{escape_html(ws)}</code>\n"
            f"⚙️ <b>الوضع:</b> {mode_desc}\n"
            f"🧠 <b>النموذج:</b> <code>{escape_html(active_model)}</code> | ⚡ <b>الجهد:</b> <code>{escape_html(active_effort)}</code>\n\n"
            "<b>🎛️ ضبط الذكاء والنماذج والحسابات:</b>\n"
            "• <code>/accounts</code> - التبديل الفوري بين حسابات جوجل المسجلة وإضافة حسابات جديدة\n"
            "• <code>/model</code> - اختيار وتغيير نموذج الذكاء الاصطناعي (Claude / Gemini / GPT)\n"
            "• <code>/effort</code> - تحديد مستوى وعمق التفكير (Max / High / Medium / Low)\n\n"
            "<b>🚀 الأوضاع المتقدمة:</b>\n"
            "• <code>/goal [هدفك]</code> - وضع الهدف المستقل (ينفذ مهمة كاملة ولا يتوقف حتى يكتمل الهدف بنسبة 100% بأقصى ذكاء)\n"
            "• <code>/grill-me [فكرتك]</code> - وضع الاستجواب الصارم (يختبر فرضياتك ويكشف الثغرات المعمارية سؤالاً بسؤال)\n"
            "• <code>/plan [الميزة]</code> - وضع التخطيط المعماري وهندسة الخطوات\n"
            "• <code>/skills</code> - مكتبة التخصيصات والـ Skills المتاحة (124 مهارة)\n\n"
            "<b>⚡ الترمينال والتحكم المباشر والمراقبة:</b>\n"
            "• <code>/tasks</code> - لوحة مراقبة العمليات واستهلاك المعالج والرام للمهمة الجارية ⚡\n"
            "• <code>/export</code> - تصدير سجل الشات الحالي كاملاً كملف Markdown على تيليجرام 📄\n"
            "• <code>/diff</code> - ملخص التغييرات في الكود مع أزرار التحميل والتراجع 📝\n"
            "• <code>/logs</code> - فحص آخر 25 سطر من سجل خدمة البوت في النظام 📋\n"
            "• <code>/restart</code> - إعادة تشغيل خدمة البوت عن بُعد عبر Systemd 🔄\n"
            "• <code>/screenshot</code> - لقطة شاشة حية لشاشات الكمبيوتر لايف وأنت في أي مكان 📸\n"
            "• <code>/preview</code> - فتح رابط معاينة لايف للمشروع على الموبايل عبر نفق مشفر 🌐\n"
            "• <code>/servers</code> - لوحة الخوادم والمنافذ النشطة (Vite/Supabase/React) مع زر لفتح كل نفق 🔌\n"
            "• <code>/sentry</code> - مراقبة أخطاء وكراشات Sentry في السوبر آب والبوت 🛡️\n"
            "• <code>/undo</code> - التراجع الفوري عن تعديلات الكود واستعادة النسخة السابقة ↩️\n"
            "• <code>/briefing</code> - تقرير صباحي شامل: جدول اليوم + حالة المشاريع + صحة العتاد 🌅\n"
            "• <code>/chats</code> - استعراض والتبديل بين جلسات المحادثة السابقة 💬\n"
            "• <code>/new</code> - بدء جلسة ومحادثة جديدة نظيفة تماماً ✨\n"
            "• <code>/pc</code> - تقرير عتاد الكمبيوتر وحرارة المعالج وكارت الشاشة 🖥️\n"
            "• <code>/screen off|on</code> - إطفاء أو تشغيل شاشات الكمبيوتر عن بُعد 🌑\n"
            "• <code>/lock</code> - قفل الكمبيوتر (Hyprlock) عن بُعد 🔒\n"
            "• <code>/sh [أمر]</code> - تشغيل أي أمر ترمينال مباشر (مثال: <code>/sh free -h</code>)\n"
            "• <code>/file [مسار]</code> - إرسال أي ملف كود من جهازك إلى تيليجرام 📄\n"
            "• <code>/now</code> - فحص محطة وجدول اليوم الحالية في Nooreldean Life OS 📅\n\n"
            "<b>🎙️ وسائط وتفاعل خارق:</b>\n"
            "• 🎙️ <b>فويس نوت (Voice Note):</b> ابعت رسالة صوتية بأي طلب وهيتم الاستماع ليها وتنفيذها فوراً في الكود!\n"
            "• 📸 <b>سكرين شوت (Screenshot):</b> ابعت صورة لأي خطأ أو تصميم مع شرح وهيتم تحليله وحله!\n"
            "• 📥 <b>رفع المستندات والملفات (Files):</b> ابعت أي ملف كود أو داتا وهيتم حفظه وفحصه فوراً بالأيجنت!\n"
            "• 🎨 <b>تسليم المخرجات تلقائياً:</b> أي صور أو تصاميم ينشئها الأيجنت هتوصلك تيليجرام فور انتهاء المهمة!\n"
            "• 📡 <b>بث حي للخطوات:</b> تحديث حي ومباشر بالثواني لخطوات التنفيذ أثناء عمل الوكيل!\n"
            "• 🔘 <b>أزرار سريعة:</b> أزرار جاهزة تحت كل مهمة: Commit 💾، و Push 🚀، و PR 🌿، و Diff 📝، و Undo ↩️، ومعاينة لايف 🌐!\n\n"
            "<b>⚙️ إدارة المشاريع والنظام:</b>\n"
            "• <code>/auto</code> - تتبع المشروع المفتوح في Antigravity IDE تلقائياً\n"
            "• <code>/projects</code> - استعراض المشاريع واختيار مشروع بنقرة واحدة\n"
            "• <code>/cd [اسم أو مسار]</code> - تثبيت مجلد العمل يدوياً\n"
            "• <code>/status</code> - فحص حالة النظام والمشروع النشط\n"
            "• <code>/where</code> - بطاقة سياق المشروع والموقع الحالي وفرع Git\n"
            "• <code>/git</code> - حالة Git والـ commits الأخيرة\n"
            "• <code>/commit [رسالة]</code> - حفظ وتثبيت التعديلات الحالية في Git محلياً 💾\n"
            "• <code>/push</code> - رفع الكوميتات على فرع GitHub الحالي مباشرة 🚀\n"
            "• <code>/pr [عنوان]</code> - إنشاء أو متابعة Pull Request مباشرة على GitHub 🌿\n"
            "• <code>/menu</code> - إظهار وتثبيت لوحة الأزرار السريعة أسفل الشاشة 📱\n"
            "• <code>/hidemenu</code> - إخفاء لوحة الأزرار السريعة 🙈\n"
            "• <code>/deploy</code> - رفع أحدث كود على Vercel و GitHub\n"
            "• <code>/stop</code> - إيقاف المهمة الجارية لو علقت"
        )
        send_message(chat_id, msg, reply_markup=get_main_reply_keyboard())

    elif cmd == "/model":
        if not arg:
            curr = CONFIG.get("current_model", "default")
            msg = (
                f"🧠 <b>إعدادات نموذج الذكاء الاصطناعي (Model):</b>\n"
                f"• النموذج النشط حالياً: <code>{escape_html(curr)}</code>\n\n"
                "اختر النموذج المطلوب من الأزرار بنقرة واحدة، أو اكتب: <code>/model [الاسم]</code>"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "⚡ Claude Sonnet 4.6", "callback_data": "model:claude-sonnet-4-6"},
                     {"text": "🧠 Claude Opus 4.6", "callback_data": "model:claude-opus-4-6-thinking"}],
                    [{"text": "🚀 Gemini 3.8 Flash (High)", "callback_data": "model:gemini-3.8-flash-high"},
                     {"text": "⚡ Gemini 3.8 Flash (Low)", "callback_data": "model:gemini-3.8-flash-low"}],
                    [{"text": "🤖 GPT-OSS 120B", "callback_data": "model:gpt-oss-120b-medium"},
                     {"text": "🔄 الافتراضي (Default)", "callback_data": "model:default"}]
                ]
            }
            send_message(chat_id, msg, reply_markup=keyboard)
            return

        choice = arg.strip().lower()
        if choice in MODELS_MAP:
            target_model = MODELS_MAP[choice]
            CONFIG["current_model"] = target_model
            save_config(CONFIG)
            send_message(chat_id, f"✅ <b>تم تغيير نموذج الذكاء الاصطناعي إلى:</b>\n<code>{escape_html(target_model)}</code>")
        else:
            send_message(chat_id, f"❌ نموذج غير معروف: <code>{escape_html(arg)}</code>\nالخيارات المتاحة:\n• sonnet\n• opus\n• flash\n• gpt\n• default")

    elif cmd in ["/effort", "/reasoning"]:
        if not arg:
            curr = CONFIG.get("current_effort", "default")
            msg = (
                f"⚡ <b>مستوى عمق التفكير (Reasoning Effort):</b>\n"
                f"• المستوى النشط حالياً: <code>{escape_html(curr)}</code>\n\n"
                "اختر المستوى المطلوب من الأزرار بنقرة واحدة، أو اكتب: <code>/effort [max/high/medium/low]</code>"
            )
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🔥 Max (أقصى عمق وتفكير)", "callback_data": "effort:max"},
                     {"text": "⚡ X-High (تفكير فائق)", "callback_data": "effort:xhigh"}],
                    [{"text": "🧠 High (عالي - ممتاز للـ Goal)", "callback_data": "effort:high"},
                     {"text": "⚖️ Medium (متوازن وسريع)", "callback_data": "effort:medium"}],
                    [{"text": "💨 Low (سريع ومباشر)", "callback_data": "effort:low"},
                     {"text": "🔄 الافتراضي", "callback_data": "effort:default"}]
                ]
            }
            send_message(chat_id, msg, reply_markup=keyboard)
            return

        choice = arg.strip().lower()
        if choice in EFFORT_MAP:
            target_effort = EFFORT_MAP[choice]
            CONFIG["current_effort"] = target_effort
            save_config(CONFIG)
            send_message(chat_id, f"✅ <b>تم ضبط مستوى عمق التفكير على:</b>\n<code>{escape_html(target_effort)}</code>")
        else:
            send_message(chat_id, f"❌ خيار غير معروف: <code>{escape_html(arg)}</code>\nالخيارات المتاحة:\n• max\n• xhigh\n• high\n• medium\n• low\n• default")

    elif cmd in ["/accounts", "/account"]:
        accounts, active_email = list_saved_accounts()
        if arg:
            target_email = arg.strip()
            found = [a for a in accounts if a["email"].lower() == target_email.lower()]
            if found:
                target_email = found[0]["email"]
                if switch_to_account(target_email):
                    send_message(chat_id, f"✅ <b>تم التبديل بنجاح إلى الحساب:</b>\n<code>{escape_html(target_email)}</code>\n\nجميع المهام والأوامر القادمة ستعمل الآن من خلال كوتا هذا الحساب.")
                    return
                else:
                    send_message(chat_id, f"❌ فشل التبديل إلى الحساب: {escape_html(target_email)}")
                    return
            else:
                send_message(chat_id, f"❌ الحساب <code>{escape_html(target_email)}</code> غير موجود في القائمة المسجلة.\nاكتب <code>/accounts</code> لعرض الحسابات المتاحة.")
                return

        auto_failover = CONFIG.get("auto_failover", True)
        msg = (
            "👤 <b>إدارة وتبديل حسابات جوجل / Antigravity:</b>\n\n"
            f"• <b>الحساب النشط حالياً:</b>\n"
            f"👉 <code>{escape_html(active_email or 'غير معروف')}</code> 🟢\n"
            f"• <b>التبديل التلقائي للكوتا (Auto-Failover):</b> {'🟢 مفعل (آمن)' if auto_failover else '🔴 معطل'}\n\n"
            f"<b>الحسابات المسجلة ({len(accounts)}):</b>\n"
        )
        buttons = []
        for a in accounts:
            status_icon = "🟢 (نشط)" if a["is_active"] else "⚪"
            msg += f"• <code>{escape_html(a['email'])}</code> {status_icon}\n"
            btn_text = f"{'🟢 ' if a['is_active'] else ''}{a['email']}"
            buttons.append([{"text": btn_text, "callback_data": f"account:{a['email']}"}])

        failover_btn = f"🛡️ تبديل الكوتا التلقائي: {'🟢 مفعل' if auto_failover else '🔴 معطل'}"
        buttons.append([{"text": failover_btn, "callback_data": "account:toggle_failover"}])
        buttons.append([{"text": "➕ كيفية إضافة حساب جديد", "callback_data": "account:add_info"}])
        keyboard = {"inline_keyboard": buttons}
        send_message(chat_id, msg, reply_markup=keyboard)

    elif cmd in ["/autofailover", "/auto_switch", "/failover"]:
        new_val = not CONFIG.get("auto_failover", True)
        CONFIG["auto_failover"] = new_val
        save_config(CONFIG)
        state_str = "مفعل 🟢" if new_val else "معطل 🔴"
        send_message(
            chat_id,
            f"🛡️ <b>نظام التبديل التلقائي عند انتهاء الكوتا (Auto-Failover):</b>\n"
            f"الحالة الآن: <b>{state_str}</b>\n\n"
            f"<i>{'عندما يستنفد أي حساب كوتا الاستخدام، سيقوم البوت تلقائياً بالتبديل للحساب التالي واستكمال المهمة.' if new_val else 'تم التعطيل، سيبقى البوت على الحساب المحدد يدوياً فقط.'}</i>"
        )

    elif cmd == "/goal":
        if not arg:
            msg = (
                "🎯 <b>وضع الهدف المستقل (/goal):</b>\n\n"
                "هذا الوضع مخصص للمهام الكبيرة التي تحتاج عملاً مستمراً ودقيقاً بدون توقف حتى يكتمل الهدف بنسبة 100% (مثالي وأنت في شفت طلبات أو وقت النوم).\n\n"
                "<b>طريقة الاستخدام:</b>\n"
                "<code>/goal [هدفك التفصيلي]</code>\n\n"
                "<b>أمثلة:</b>\n"
                "• <code>/goal اعمل refactor كامل للـ state management واختبر كل الشاشات</code>\n"
                "• <code>/goal صلح كل أخطاء الـ build واعمل deploy وتأكد إن الموقع شغال بدون مشاكل</code>"
            )
            send_message(chat_id, msg)
            return
        
        def run_tri_goal():
            ws, _ = get_effective_workspace()
            try:
                import tri_phase_engine
                res = tri_phase_engine.run_tri_phase_pipeline(
                    task_title=arg,
                    requirement_prompt=arg,
                    workspace=ws,
                    chat_id=chat_id,
                    send_message_func=send_message,
                    edit_message_text_func=edit_message_text,
                    agy_bin=CONFIG.get("agy_bin", "agy"),
                    is_sre=False
                )
                summary = res.get("review_summary") or "تم إنجاز الهدف واعتماده بنجاح."
                ctx_append = ""
                if context_engine:
                    try:
                        did_roll, roll_msg, ctx_st = context_engine.compress_after_message(
                            CONFIG.get("current_conversation_id"),
                            ws,
                            arg,
                            summary
                        )
                        ctx_append = f"\n\n{ctx_st['meter_badge']} | 🗜️ <i>تم ضغط السياق</i>"
                        if did_roll and roll_msg:
                            send_message(chat_id, roll_msg)
                    except Exception as ce:
                        print(f"[ContextEngine error in tri_goal] {ce}")

                msg_out = (
                    "🎉 <b>اكتمل الهدف بنجاح عبر خط الإنتاج الثلاثي!</b>\n\n"
                    f"📋 <b>الهدف:</b> <code>{escape_html(arg)}</code>\n\n"
                    "🛡️ <b>تقرير الاعتماد النهائي (Claude Opus Thinking):</b>\n"
                    f"<i>{escape_html(summary)}</i>"
                    f"{ctx_append}"
                )
                send_message(chat_id, msg_out)
            except Exception as e:
                goal_prompt = (
                    f"You are running in autonomous /goal mode. "
                    f"Be extra thorough, break down the problem, execute end-to-end, test and verify every step, "
                    f"do not stop until this goal is fully achieved and working without errors: {arg}"
                )
                run_agent_task(chat_id, goal_prompt, banner_title="🎯 <b>وضع الهدف المستقل (Goal Mode)</b>", extra_args=["--effort", "high"])

        threading.Thread(target=run_tri_goal, daemon=True).start()

    elif cmd in ["/resume", "/continue"]:
        conv_target = arg.strip() if arg.strip() else (CONFIG.get("current_conversation_id") or get_latest_conversation_id())
        if not conv_target:
            send_message(chat_id, "⚠️ لا توجد جلسة سابقة لاستئنافها.")
            return
        short_cid = conv_target[:8]
        send_message(chat_id, f"🔄 <b>جاري استئناف الجلسة:</b> <code>{short_cid}</code>...\n\n<i>الأيجنت هيكمل من النقطة اللي وقف عندها بالضبط! 🚀</i>")
        threading.Thread(
            target=run_agent_task,
            args=(chat_id, "Continue and complete the task from where you were interrupted. Ensure thorough inspection, test/verification, and provide a clear Arabic summary."),
            kwargs={
                "banner_title": f"🔄 <b>استئناف الجلسة:</b> <code>{short_cid}</code>",
                "extra_args": ["--conversation", conv_target]
            },
            daemon=True
        ).start()

    elif cmd in ["/grill-me", "/grill_me", "/grill"]:
        topic = arg.strip() if arg.strip() else "استجوبني واختبرني في ما هي أفضل الإضافات والتحسينات المعمارية والتطويرية لهذا المشروع؟"
        grill_prompt = (
            f"Activate the grilling skill. Interview and grill the user about this topic, idea, or plan: '{topic}'.\n\n"
            f"CRITICAL RULES YOU MUST STRICTLY FOLLOW:\n"
            f"1. Ask exactly ONE single question at a time. NEVER dump multiple questions (like Q1, Q2, Q3) in one message.\n"
            f"2. For your question, provide 2 to 4 clear, numbered choices (1., 2., 3., 4.) with concise bold titles (e.g. 1. **Option Title**: description).\n"
            f"3. Mark your recommended choice with (موصى به / Recommended).\n"
            f"4. STOP completely and wait for the user to pick an option before asking anything else.\n"
            f"5. Start by briefly reviewing the project, then ask Question 1 with its numbered options."
        )
        threading.Thread(
            target=run_agent_task,
            args=(chat_id, grill_prompt),
            kwargs={
                "banner_title": "🔥 <b>وضع الاستجواب الصارم (Grill-Me Mode)</b>"
            },
            daemon=True
        ).start()

    elif cmd == "/plan":
        if not arg:
            send_message(chat_id, "📋 <b>وضع التخطيط المعماري (/plan):</b>\n<code>/plan [الميزة المطلوبة]</code>\n\nيقوم الإيجينت بوضع خارطة طريق وهندسة معمارية خطوة بخطوة قبل التنفيذ.")
            return
        plan_prompt = f"Create a comprehensive step-by-step technical plan and architectural specification for: {arg}"
        threading.Thread(
            target=run_agent_task,
            args=(chat_id, plan_prompt),
            kwargs={
                "extra_args": ["--mode", "plan"],
                "banner_title": "📋 <b>وضع التخطيط المعماري (Plan Mode)</b>"
            },
            daemon=True
        ).start()

    elif cmd == "/skills":
        if not arg:
            msg = (
                f"🎯 <b>مكتبة المهارات والتخصيصات ({len(CACHED_SKILLS)} مهارة مثبتة):</b>\n\n"
                "💡 <b>كيف تستدعي أي مهارة؟</b>\n"
                "• اكتب: <code>/اسم-المهارة [طلبك]</code>\n"
                "• أو اكتب طلبك بالعربي عادي والإيجينت هيستدعي المهارة المناسبة تلقائياً!\n\n"
                "<b>🔍 تصفح حسب المجال:</b>\n"
                "• <code>/skills code</code> - فحص وجودة الكود (Clean code, Review, TDD)\n"
                "• <code>/skills flutter</code> - فلاتر والموبايل (Clean Arch, Widgets, BLoC)\n"
                "• <code>/skills web</code> - الويب والواجهات (Impeccable, modern-web)\n"
                "• <code>/skills sync</code> - الداتابيز ومزامنة Coachdrift\n"
                "• <code>/skills video</code> - مونتاج وصناعة الفيديو واليوتيوب\n"
                "• <code>/skills firebase</code> - قواعد بيانات وأمان Firebase\n"
                "• <code>/skills super</code> - مهارات السوبر آب ومراسلة العملاء\n\n"
                "<i>أو ابحث عن أي كلمة: <code>/skills اسم_التقنية</code></i>"
            )
            send_message(chat_id, msg)
            return

        query = arg.strip().lower()
        matched = {}
        for sname, sdesc in CACHED_SKILLS.items():
            if query in sname.lower() or query in sdesc.lower():
                matched[sname] = sdesc

        if not matched:
            send_message(chat_id, f"❌ لم يتم العثور على مهارات تطابق: <code>{escape_html(arg)}</code>\nاكتب <code>/skills</code> لعرض الفئات.")
            return

        msg = f"🔍 <b>المهارات المطابقة لـ ({escape_html(arg)}) [{len(matched)}]:</b>\n\n"
        for sname in sorted(matched.keys())[:15]:
            desc_short = matched[sname][:75] + "..." if matched[sname] else "مهارة متخصصة"
            msg += f"• <code>/{sname}</code>\n  <i>{escape_html(desc_short)}</i>\n\n"
        
        if len(matched) > 15:
            msg += f"<i>...وهناك {len(matched) - 15} مهارة أخرى. حدد كلمة البحث لعرضها.</i>"

        send_message(chat_id, msg)

    elif cmd == "/agent":
        if not arg:
            send_message(chat_id, "🤖 <b>استخدام الوكلاء المخصصين:</b>\n<code>/agent [اسم_الوكيل] [المهمة]</code>\n\nالوكلاء المتاحين:\n• <code>/agent firestore-rules-author راجع قواعد الأمان</code>\n• <code>/agent flutter_a11y_agent افحص إمكانية الوصول</code>")
            return
        agent_parts = arg.split(maxsplit=1)
        target_agent = agent_parts[0]
        agent_prompt = agent_parts[1] if len(agent_parts) > 1 else ""
        if not agent_prompt:
            send_message(chat_id, f"⚠️ برجاء كتابة المهمة المطلوب من الوكيل <code>{target_agent}</code> تنفيذها.")
            return
        threading.Thread(target=run_agent_task, args=(chat_id, agent_prompt, target_agent), daemon=True).start()

    elif cmd == "/auto":
        CONFIG["workspace_mode"] = "auto"
        save_config(CONFIG)
        ide_ws = get_active_ide_workspace()
        if ide_ws:
            send_message(chat_id, f"🔄 <b>تم تفعيل الوضع التلقائي:</b>\nالبوت يتبع الآن نافذة Antigravity IDE المفتوحة على:\n<code>{escape_html(ide_ws)}</code>")
        else:
            send_message(chat_id, "🔄 <b>تم تفعيل الوضع التلقائي:</b>\n(بمجرد فتح أي مشروع في Antigravity IDE سيعمل البوت عليه مباشرة).")

    elif cmd == "/status":
        ws, mode_desc = get_effective_workspace()
        is_running = current_task_info["running"]
        ide_ws = get_active_ide_workspace()
        active_model = CONFIG.get("current_model", "default")
        active_effort = CONFIG.get("current_effort", "default")
        active_email = get_email_from_token_file(ACTIVE_TOKEN_PATH)
        accounts_list, _ = list_saved_accounts()
        status_msg = (
            f"💻 <b>حالة النظام:</b>\n"
            f"• <b>الحساب النشط (Google):</b> <code>{escape_html(active_email or 'غير معروف')}</code> ({len(accounts_list)} حسابات مسجلة)\n"
            f"• <b>تبديل الكوتا التلقائي:</b> {'🟢 شغال (Auto-Failover)' if CONFIG.get('auto_failover', True) else '🔴 معطل'}\n"
            f"• <b>المشروع النشط:</b> <code>{escape_html(ws)}</code>\n"
            f"• <b>نظام التحديد:</b> {mode_desc}\n"
            f"• <b>مشروع الـ IDE المفتوح:</b> <code>{escape_html(ide_ws or 'لا يوجد مشروع مفتوح')}</code>\n"
            f"• <b>النموذج (Model):</b> <code>{escape_html(active_model)}</code>\n"
            f"• <b>مستوى التفكير (Effort):</b> <code>{escape_html(active_effort)}</code>\n"
            f"• <b>حالة الإيجينت:</b> {'⏳ يعمل على مهمة الآن' if is_running else '🟢 جاهز لاستقبال الأوامر'}\n"
        )
        if is_running:
            status_msg += f"• <b>المهمة:</b> <code>{escape_html(current_task_info['prompt'][:100])}</code>\n"
        send_message(chat_id, status_msg)

    elif cmd == "/cd":
        if not arg:
            send_projects_menu(chat_id)
            return
        
        found = find_project_by_query(arg)
        if found:
            ok, summary = switch_to_workspace(found["path"])
            if ok:
                msg, kb = format_project_card(found["path"], summary)
                send_message(chat_id, msg, reply_markup=kb)
            else:
                send_message(chat_id, f"❌ تعذر فتح مسار المشروع:\n<code>{escape_html(found['path'])}</code>")
        else:
            projects = discover_all_projects()
            names_hint = "، ".join([f"<code>{p['name']}</code>" for p in projects[:6]])
            send_message(
                chat_id,
                f"❌ لم يتم العثور على مشروع مطابق لـ <code>{escape_html(arg)}</code>.\n\n"
                f"💡 <b>أمثلة للمشاريع المتاحة:</b>\n{names_hint}...\n\n"
                f"أو اكتب <code>/projects</code> للاختيار مباشرة بنقرة واحدة."
            )

    elif cmd in ["/projects", "/switch", "/workspaces", "/repos"]:
        send_projects_menu(chat_id)

    elif cmd == "/git":
        ws, _ = get_effective_workspace()
        try:
            res = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=10)
            res2 = subprocess.run(["git", "log", "-n", "3", "--oneline"], cwd=ws, capture_output=True, text=True, timeout=10)
            out = f"📊 <b>Git Status ({os.path.basename(ws)}):</b>\n"
            out += f"<code>{escape_html(res.stdout.strip() or 'شجرة العمل نظيفة (Clean)')}</code>\n\n"
            out += f"<b>آخر 3 Commits:</b>\n<code>{escape_html(res2.stdout.strip())}</code>"
            send_message(chat_id, out)
        except Exception as e:
            send_message(chat_id, f"❌ خطأ Git: {escape_html(str(e))}")

    elif cmd in ["/diff", "/changes"]:
        send_diff_summary(chat_id)

    elif cmd == "/deploy":
        ws, _ = get_effective_workspace()
        send_message(chat_id, f"🚀 جاري الرفع على GitHub و Vercel لمشروع {os.path.basename(ws)}...")
        try:
            subprocess.run(["git", "push"], cwd=ws, capture_output=True, text=True, timeout=30)
            res = subprocess.run(["npx", "-y", "vercel", "--prod", "--yes"], cwd=ws, capture_output=True, text=True, timeout=60)
            send_message(chat_id, f"✅ <b>تم النشر بنجاح!</b>\n<pre>{escape_html(res.stdout[-300:])}</pre>")
        except Exception as e:
            send_message(chat_id, f"❌ خطأ النشر: {escape_html(str(e))}")

    elif cmd in ["/sh", "/cmd", "/run", "/terminal"]:
        if not arg:
            send_message(chat_id, "⚡ <b>أوامر الترمينال المباشرة:</b>\n<code>/sh [أمر الترمينال]</code>\n\nأمثلة:\n• <code>/sh git status</code>\n• <code>/sh npm run build</code>\n• <code>/sh free -h</code>\n• <code>/sh docker ps</code>")
            return
        ws, _ = get_effective_workspace()
        send_message(chat_id, f"⚡ <i>جاري تشغيل: {escape_html(arg[:60])}...</i>")
        try:
            res = subprocess.run(arg, shell=True, cwd=ws, capture_output=True, text=True, timeout=45)
            out = res.stdout or ""
            err = res.stderr or ""
            comb = (out + ("\nErrors:\n" + err if err else "")).strip() or "تم تنفيذ الأمر بنجاح بدون مخرجات."
            if len(comb) > 3500:
                comb = comb[-3500:]
            status_emoji = "✅" if res.returncode == 0 else "⚠️"
            send_message(chat_id, f"{status_emoji} <b>مخرجات الترمينال (Exit: {res.returncode}):</b>\n<pre>{escape_html(comb)}</pre>", reply_markup=get_task_action_buttons())
        except subprocess.TimeoutExpired:
            send_message(chat_id, "⏱️ تخطى الأمر مهلة 45 ثانية.")
        except Exception as e:
            send_message(chat_id, f"❌ خطأ: {escape_html(str(e))}")

    elif cmd in ["/now", "/today", "/schedule", "/routine"]:
        send_message(chat_id, get_life_os_now())

    elif cmd == "/stop":
        stopped_count = 0
        with active_task_lock:
            for p in list(ACTIVE_RUNNING_PROCESSES):
                try:
                    kill_process_tree(p)
                    stopped_count += 1
                except Exception:
                    pass
            ACTIVE_RUNNING_PROCESSES.clear()
            if current_task_info.get("process"):
                try:
                    kill_process_tree(current_task_info["process"])
                    stopped_count += 1
                except Exception:
                    pass
                current_task_info["process"] = None
            current_task_info["running"] = False
            SESSION_TASK_QUEUE.clear()
        if stopped_count > 0:
            send_message(chat_id, f"🛑 <b>تم إيقاف كافة المهام الجارية بنجاح ({stopped_count} عملية) ومسح طابور الانتظار.</b>")
        else:
            send_message(chat_id, "لا توجد مهام قيد التشغيل حالياً.")

    elif cmd in ["/tasks", "/top", "/ps", "/jobs"]:
        msg, kb = get_task_status_card()
        send_message(chat_id, msg, reply_markup=kb)

    elif cmd in ["/restart", "/reboot_bot", "/reload"]:
        send_message(chat_id, "🔄 <b>جاري إعادة تشغيل خدمة البوت الآن (Systemd Service)...</b>\nسيعود البوت للعمل خلال 2-3 ثوانٍ تلقائياً.")
        def _do_restart():
            time.sleep(1)
            subprocess.run(["systemctl", "--user", "restart", "agy-bot.service"])
        threading.Thread(target=_do_restart, daemon=True).start()

    elif cmd in ["/logs", "/log", "/errors"]:
        try:
            res = subprocess.run(
                ["journalctl", "--user", "-u", "agy-bot.service", "-n", "25", "--no-pager"],
                capture_output=True, text=True, timeout=8
            )
            logs = res.stdout.strip() or "لا توجد سجلات متاحة حالياً."
            if len(logs) > 3500:
                logs = logs[-3500:]
            send_message(
                chat_id,
                f"📋 <b>آخر 25 سطر من سجل خدمة البوت (Logs):</b>\n<pre>{escape_html(logs)}</pre>",
                reply_markup={
                    "inline_keyboard": [
                        [{"text": "🔄 تحديث السجل", "callback_data": "act:logs_refresh"},
                         {"text": "🔄 ريستارت للبوت", "callback_data": "act:restart_bot"}]
                    ]
                }
            )
        except Exception as e:
            send_message(chat_id, f"❌ خطأ جلب السجلات: {escape_html(str(e))}")

    elif cmd in ["/export", "/transcript", "/dump"]:
        ws, _ = get_effective_workspace()
        target_cid = arg.strip() if arg.strip() else (CONFIG.get("current_conversation_id") or get_latest_conversation_id())
        if not target_cid:
            send_message(chat_id, "⚠️ <b>لا توجد جلسة نشطة لتصديرها حالياً.</b>\nابدأ محادثة أولاً أو اكتب <code>/chats</code> لاختيار جلسة.")
        else:
            send_message(chat_id, f"⏳ <i>جاري تجميع وتصدير سجل المحادثة <code>{target_cid[:10]}...</code></i>")
            try:
                exp_file = export_conversation_to_markdown(target_cid, ws)
                if exp_file and os.path.isfile(exp_file):
                    rel_p = os.path.relpath(exp_file, ws)
                    caption = (
                        f"📄 <b>تم تصدير سجل المحادثة بنجاح!</b>\n"
                        f"📁 <code>{escape_html(rel_p)}</code>\n\n"
                        f"<i>يمكنك فتح وقراءة هذا الملف مباشرة داخل Antigravity IDE أو مشاركته.</i>"
                    )
                    if not send_document(chat_id, exp_file, caption=caption):
                        send_message(chat_id, f"✅ <b>تم حفظ ملف السجل في مشروعك:</b>\n<code>{escape_html(exp_file)}</code>")
                else:
                    send_message(chat_id, "❌ تعذر إنشاء ملف التصدير.")
            except Exception as e:
                send_message(chat_id, f"❌ خطأ أثناء التصدير: {escape_html(str(e))}")

    elif cmd in ["/where", "/loc", "/location", "/whereami"]:
        ws, mode_desc = get_effective_workspace()
        summary = get_project_state_summary(ws)
        curr_id = CONFIG.get("current_conversation_id")
        details = get_conversation_details(curr_id) if curr_id else None

        bname = os.path.basename(ws)
        branch = summary.get("branch", "HEAD")
        mod_count = summary.get("modified_count", 0)
        status_icon = "🧹 شجرة العمل نظيفة (Clean)" if mod_count == 0 else f"⚠️ {mod_count} ملفات معدلة غير محفوظة"
        
        last_f_line = ""
        if summary.get("last_file"):
            last_f_line = f"📄 <b>آخر ملف معدل:</b> <code>{escape_html(summary['last_file'])}</code>\n"

        if details:
            last_act = details.get("last_action") or "لا توجد أدوات مستدعاة مؤخراً"
            thought = details.get("last_thought") or "لا توجد تفاصيل إضافية"
            time_str = details.get("last_time") or "غير متوفر"
            msg = (
                f"📍 <b>موقع وسياق العمل الحالي:</b>\n\n"
                f"📁 <b>المشروع:</b> <code>{escape_html(bname)}</code>\n"
                f"📂 <b>المسار الكامل:</b> <code>{escape_html(ws)}</code> ({mode_desc})\n"
                f"🌿 <b>فرع Git:</b> <code>{escape_html(branch)}</code>\n"
                f"📊 <b>حالة الكود:</b> {status_icon}\n"
                f"{last_f_line}"
                f"💬 <b>الجلسة النشطة:</b> <code>{escape_html(details['title'])}</code> 🟢\n"
                f"🔄 <b>الخطوات المنجزة:</b> #{details['steps']}\n"
                f"🛠️ <b>آخر إجراء نفذه الأيجنت:</b>\n<code>{escape_html(last_act[:120])}</code>\n"
                f"💭 <b>سياق آخر فكرة:</b>\n<i>{escape_html(thought[:140])}</i>\n"
                f"⏰ <b>آخر نشاط:</b> {time_str}\n\n"
                f"💡 <i>أي أمر أو رسالة ترسلها الآن ستكمل على نفس هذا المشروع والملف مباشرة دون أن تفقد مكانك.</i>"
            )
        else:
            msg = (
                f"📍 <b>موقع وسياق العمل الحالي:</b>\n\n"
                f"📁 <b>المشروع:</b> <code>{escape_html(bname)}</code>\n"
                f"📂 <b>المسار الكامل:</b> <code>{escape_html(ws)}</code> ({mode_desc})\n"
                f"🌿 <b>فرع Git:</b> <code>{escape_html(branch)}</code>\n"
                f"📊 <b>حالة الكود:</b> {status_icon}\n"
                f"{last_f_line}"
                f"💬 <b>الجلسة:</b> <i>جلسة جديدة ستتصل تلقائياً مع أول رسالة</i> ✨"
            )
        
        kb = {
            "inline_keyboard": [
                [
                    {"text": "📊 فحص Git", "callback_data": "act:git"},
                    {"text": "🧪 فحص Build", "callback_data": "act:build"},
                    {"text": "🌐 نفق لايف", "callback_data": "act:tunnel"}
                ],
                [
                    {"text": "💬 جلسات المشروع", "callback_data": "conv:list"},
                    {"text": "📂 تبديل المشروع", "callback_data": "proj:list"}
                ]
            ]
        }
        send_message(chat_id, msg, reply_markup=kb)

    elif cmd in ["/chats", "/conversations", "/history"]:
        convs = list_recent_conversations(8)
        curr_id = CONFIG.get("current_conversation_id")
        curr_det = get_conversation_details(curr_id) if curr_id else None

        active_block = ""
        if curr_det:
            ws_tag = f"📍 <b>المشروع:</b> <code>{escape_html(curr_det['workspace'])}</code>\n" if curr_det.get("workspace") else ""
            act_tag = f"🛠️ <b>آخر إجراء وصل له:</b> <code>{escape_html(curr_det['last_action'][:100])}</code>\n" if curr_det.get("last_action") else ""
            thought_tag = f"💭 <b>آخر رد/سياق:</b>\n<i>{escape_html(curr_det['last_thought'][:120])}</i>\n" if curr_det.get("last_thought") else ""
            time_tag = f"⏰ <code>{curr_det['last_time']}</code> | " if curr_det.get("last_time") else ""
            active_block = (
                f"• <b>الجلسة النشطة حالياً:</b>\n"
                f"👉 <b>{escape_html(curr_det['title'])}</b> 🟢\n"
                f"({time_tag}#{curr_det['steps']} خطوة)\n"
                f"{ws_tag}{act_tag}{thought_tag}\n"
            )
        else:
            active_block = "• <b>الجلسة النشطة:</b> <i>محادثة جديدة تلقائياً</i> ✨\n\n"

        msg = (
            "💬 <b>إدارة جلسات ومحادثات Antigravity:</b>\n\n"
            f"{active_block}"
            f"<b>آخر {len(convs)} جلسات مسجلة:</b>\n"
        )
        buttons = []
        for c in convs:
            is_act = (c["id"] == curr_id)
            status_icon = "🟢 (نشطة)" if is_act else "⚪"
            ws_str = f"[{c['workspace']}] " if c.get("workspace") else ""
            msg += f"• <b>{escape_html(c['title'])}</b> {status_icon}\n  ↳ <i>{escape_html(ws_str)}{c['steps']} خطوة</i>\n"
            btn_label = f"{'🟢 ' if is_act else ''}{ws_str}{c['title'][:24]}"
            buttons.append([{"text": btn_label, "callback_data": f"conv:set:{c['id']}"}])

        buttons.append([{"text": "➕ بدء محادثة جديدة (/new)", "callback_data": "conv:new"}])
        keyboard = {"inline_keyboard": buttons}
        send_message(chat_id, msg, reply_markup=keyboard)

    elif cmd == "/new":
        CONFIG["current_conversation_id"] = None
        save_config(CONFIG)
        send_message(
            chat_id,
            "✨ <b>تم بدء جلسة عمل جديدة ونظيفة!</b>\n\n"
            "أي رسالة أو فويس نوت أو طلب قادم سيبدأ في محادثة مستقلة من البداية بدون التأثر بالسياق السابق."
        )

    elif cmd in ["/pc", "/health", "/laptop", "/specs"]:
        send_message(chat_id, get_pc_health_report())

    elif cmd in ["/file", "/get"]:
        if not arg:
            send_message(chat_id, "📄 <b>تحميل وإرسال ملف:</b>\n<code>/file [مسار_الملف]</code>\n\nمثال:\n• <code>/file app.js</code>\n• <code>/file styles.css</code>")
            return
        ws, _ = get_effective_workspace()
        target = os.path.expanduser(arg.strip())
        if not os.path.isabs(target):
            target = os.path.join(ws, target)
        if os.path.isfile(target):
            send_message(chat_id, f"📤 <i>جاري إرسال الملف {os.path.basename(target)}...</i>")
            if not send_document(chat_id, target, caption=f"📄 {os.path.basename(target)}"):
                send_message(chat_id, "❌ فشل إرسال الملف (قد يكون حجمه كبيراً جداً).")
        else:
            send_message(chat_id, f"❌ الملف غير موجود:\n<code>{escape_html(target)}</code>")

    elif cmd == "/cat":
        if not arg:
            send_message(chat_id, "📄 <b>استعراض كود الملف:</b>\n<code>/cat [مسار_الملف]</code>")
            return
        ws, _ = get_effective_workspace()
        target = os.path.expanduser(arg.strip())
        if not os.path.isabs(target):
            target = os.path.join(ws, target)
        if os.path.isfile(target):
            try:
                with open(target, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read(3500)
                send_message(chat_id, f"📄 <b>{os.path.basename(target)}:</b>\n<pre>{escape_html(content)}</pre>")
            except Exception as e:
                send_message(chat_id, f"❌ تعذر قراءة الملف: {escape_html(str(e))}")
        else:
            send_message(chat_id, f"❌ الملف غير موجود:\n<code>{escape_html(target)}</code>")

    elif cmd == "/lock":
        try:
            subprocess.Popen(["hyprlock"])
            send_message(chat_id, "🔒 <b>تم قفل شاشة الكمبيوتر بنجاح!</b>")
        except Exception:
            try:
                subprocess.run(["loginctl", "lock-session"], timeout=5)
                send_message(chat_id, "🔒 <b>تم قفل الجلسة بنجاح!</b>")
            except Exception as e:
                send_message(chat_id, f"❌ تعذر القفل: {escape_html(str(e))}")

    elif cmd == "/screen":
        sub = arg.strip().lower()
        if sub == "off":
            try:
                subprocess.run("hyprctl dispatch dpms off 2>/dev/null || xset dpms force off 2>/dev/null", shell=True, timeout=5)
                send_message(chat_id, "🌑 <b>تم إطفاء شاشات الكمبيوتر لتوفير الطاقة.</b>\nالجهاز والبوت مستمران في العمل بالخلفية 24/7!")
            except Exception as e:
                send_message(chat_id, f"❌ خطأ: {escape_html(str(e))}")
        elif sub == "on":
            try:
                subprocess.run("hyprctl dispatch dpms on 2>/dev/null || xset dpms force on 2>/dev/null", shell=True, timeout=5)
                send_message(chat_id, "💡 <b>تم تشغيل شاشات الكمبيوتر!</b>")
            except Exception as e:
                send_message(chat_id, f"❌ خطأ: {escape_html(str(e))}")
        else:
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🌑 إطفاء الشاشة (DPMS Off)", "callback_data": "screen:off"},
                     {"text": "💡 تشغيل الشاشة (DPMS On)", "callback_data": "screen:on"}],
                    [{"text": "🔒 قفل الكمبيوتر (Lock)", "callback_data": "screen:lock"}]
                ]
            }
            send_message(chat_id, "🖥️ <b>التحكم في شاشة الكمبيوتر عن بُعد:</b>\nاختر الإجراء المطلوب من الأزرار:", reply_markup=keyboard)

    elif cmd in ["/pc", "/power", "/shutdown", "/poweroff", "/suspend", "/sleep", "/reboot"]:
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "🛑 إيقاف التشغيل الكامل (Power Off)", "callback_data": "pc_pwr:confirm_off"},
                    {"text": "💤 وضع السكون (Suspend / Sleep)", "callback_data": "pc_pwr:confirm_suspend"}
                ],
                [
                    {"text": "🔄 إعادة تشغيل (Reboot)", "callback_data": "pc_pwr:confirm_reboot"},
                    {"text": "💡 إطفاء/تشغيل الشاشات", "callback_data": "pc_pwr:screens_menu"}
                ],
                [
                    {"text": "📡 دليل فتح الجهاز عن بُعد (Wake-on-LAN)", "callback_data": "pc_pwr:wol_guide"}
                ]
            ]
        }
        power_msg = (
            "⚡ <b>لوحة التحكم في طاقة الكمبيوتر (PC Power Management):</b>\n\n"
            "• <b>حالة النظام:</b> يعمل الآن 🟢\n"
            "• <b>IP الشبكة المحلية:</b> <code>192.168.1.14</code>\n"
            "• <b>MAC Address (WoL):</b> <code>c4:34:6b:58:c6:d2</code>\n"
            "• <b>واجهة الشبكة:</b> <code>eno1</code> (Wake-on-LAN مفعّل ومضبوط)\n\n"
            "<i>اختر الإجراء المطلوب لجهازك من الأزرار التفاعلية أدناه:</i>"
        )
        send_message(chat_id, power_msg, reply_markup=keyboard)

    elif cmd in ["/screenshot", "/shot", "/screen_shot"]:
        media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
        os.makedirs(media_dir, exist_ok=True)
        shot_path = os.path.join(media_dir, f"screen_{int(time.time())}.png")
        send_message(chat_id, "📸 <i>جاري التقاط صورة لشاشات الكمبيوتر لايف...</i>")
        if take_desktop_screenshot(shot_path):
            now_t = datetime.datetime.now().strftime("%I:%M:%S %p")
            caption = f"📸 <b>لقطة حية لشاشات الكمبيوتر:</b>\n⏰ <code>{now_t}</code> | 🖥️ Hyprland Workspace"
            if not send_photo(chat_id, shot_path, caption=caption):
                send_document(chat_id, shot_path, caption=caption)
        else:
            send_message(chat_id, "❌ تعذر التقاط الشاشة (تأكد من تفعيل بيئة الـ Display).")

    elif cmd in ["/preview", "/tunnel"]:
        if arg.strip().lower() == "stop":
            old_u = stop_active_tunnel()
            if old_u:
                send_message(chat_id, f"🛑 <b>تم إغلاق نفق المعاينة بنجاح:</b>\n<code>{escape_html(old_u)}</code>")
            else:
                send_message(chat_id, "ℹ️ لا يوجد نفق معاينة قيد التشغيل حالياً.")
            return

        port = None
        if arg.strip().isdigit():
            port = int(arg.strip())
        else:
            port = find_active_web_port()
        
        ws, _ = get_effective_workspace()
        if not port:
            port = 8080

        send_message(chat_id, f"🌐 <i>جاري تشغيل نفق Cloudflare المشفر للمنفذ {port}...</i>")
        url, is_new = start_cloudflare_tunnel(port)
        if url:
            keyboard = {
                "inline_keyboard": [
                    [{"text": "🌐 فتح الموقع الآن (Live Preview)", "url": url}],
                    [{"text": "🛑 إغلاق النفق", "callback_data": "act:tunnel_stop"}]
                ]
            }
            send_message(
                chat_id,
                f"🚀 <b>رابط المعاينة لايف جاهز على موبايلك!</b>\n\n"
                f"🔗 <b>الرابط:</b> <code>{escape_html(url)}</code>\n"
                f"🔌 <b>المنفذ المحلي:</b> <code>http://127.0.0.1:{port}</code>\n"
                f"📁 <b>المشروع:</b> <code>{escape_html(os.path.basename(ws))}</code>\n\n"
                f"<i>الرابط مشفر بـ HTTPS وآمن، يمكنك فتحه وتجربة وتصفح الموقع مباشرة من متصفح الموبايل!</i>",
                reply_markup=keyboard
            )
        else:
            send_message(chat_id, "❌ تعذر تشغيل نفق Cloudflare. تأكد من اتصال الإنترنت.")

    elif cmd in ["/undo", "/revert"]:
        ws, _ = get_effective_workspace()
        if arg.strip().lower() in ["force", "yes", "confirm"]:
            try:
                st = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=5)
                if not st.stdout.strip():
                    send_message(chat_id, f"ℹ️ لا توجد تعديلات للتراجع عنها، مشروع <b>{escape_html(os.path.basename(ws))}</b> نظيف تماماً.")
                else:
                    subprocess.run(["git", "restore", "."], cwd=ws, timeout=10)
                    subprocess.run(["git", "clean", "-fd"], cwd=ws, timeout=10)
                    send_message(chat_id, f"↩️ <b>تم التراجع بنجاح!</b>\nتمت استعادة حالة كود مشروع <b>{escape_html(os.path.basename(ws))}</b> ومسح جميع التعديلات.")
            except Exception as e:
                send_message(chat_id, f"❌ خطأ أثناء التراجع: {escape_html(str(e))}")
        else:
            undo_kb = {
                "inline_keyboard": [
                    [
                        {"text": "⚠️ نعم، احذف التعديلات نهائياً (تأكيد)", "callback_data": "act:undo_confirm"},
                        {"text": "❌ إلغاء وتراجع", "callback_data": "act:undo_cancel"}
                    ]
                ]
            }
            send_message(
                chat_id,
                f"⚠️ <b>تحذير أمان - التراجع عن تعديلات الكود:</b>\n\n"
                f"مشروع: <b>{escape_html(os.path.basename(ws))}</b>\n"
                f"هل أنت متأكد من مسح كافة التعديلات غير المحفوظة في المشروع والعودة لآخر Commit نظيف؟\n\n"
                f"<i>(اضغط تأكيد للحذف أو إلغاء للحفاظ على كودك)</i>",
                reply_markup=undo_kb
            )

    elif cmd == "/commit":
        ws, _ = get_effective_workspace()
        try:
            st = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=10)
            if not st.stdout.strip():
                send_message(chat_id, f"ℹ️ لا توجد أي تعديلات في مشروع <b>{escape_html(os.path.basename(ws))}</b> لعمل Commit عليها.")
            else:
                commit_msg = arg.strip()
                if not commit_msg:
                    mod_lines = [l.strip() for l in st.stdout.strip().splitlines() if l.strip()]
                    files_short = ", ".join([os.path.basename(l.split()[-1]) for l in mod_lines[:3]])
                    if len(mod_lines) > 3:
                        files_short += f" (+{len(mod_lines)-3} files)"
                    commit_msg = f"chore: update {files_short}"

                subprocess.run(["git", "add", "-A"], cwd=ws, capture_output=True, text=True, timeout=15)
                c_res = subprocess.run(["git", "commit", "-m", commit_msg], cwd=ws, capture_output=True, text=True, timeout=20)
                if c_res.returncode == 0:
                    b_res = subprocess.run(["git", "branch", "--show-current"], cwd=ws, capture_output=True, text=True, timeout=5)
                    branch_name = b_res.stdout.strip() or "HEAD"
                    push_btn = {
                        "inline_keyboard": [
                            [{"text": f"🚀 Push إلى {branch_name} على GitHub", "callback_data": "act:push"}]
                        ]
                    }
                    send_message(
                        chat_id,
                        f"💾 <b>تم عمل Commit بنجاح!</b>\n\n"
                        f"📁 <b>المشروع:</b> <code>{escape_html(os.path.basename(ws))}</code>\n"
                        f"🌿 <b>الفرع:</b> <code>{escape_html(branch_name)}</code>\n"
                        f"📝 <b>الرسالة:</b> <code>{escape_html(commit_msg)}</code>\n\n"
                        f"<pre>{escape_html(c_res.stdout.strip()[:600])}</pre>",
                        reply_markup=push_btn
                    )
                else:
                    send_message(chat_id, f"❌ خطأ أثناء الـ Commit:\n<pre>{escape_html((c_res.stdout + c_res.stderr).strip()[:800])}</pre>")
        except Exception as e:
            send_message(chat_id, f"❌ خطأ: {escape_html(str(e))}")

    elif cmd == "/push":
        ws, _ = get_effective_workspace()
        try:
            b_res = subprocess.run(["git", "branch", "--show-current"], cwd=ws, capture_output=True, text=True, timeout=5)
            branch_name = b_res.stdout.strip() or "HEAD"
            send_message(chat_id, f"🚀 <i>جاري الرفع على فرع {branch_name} في GitHub لمشروع {os.path.basename(ws)}...</i>")
            p_res = subprocess.run(["git", "push", "origin", branch_name], cwd=ws, capture_output=True, text=True, timeout=60)
            if p_res.returncode == 0:
                send_message(
                    chat_id,
                    f"✅ <b>تم الـ Push بنجاح إلى GitHub!</b>\n"
                    f"📁 مشروع: <b>{escape_html(os.path.basename(ws))}</b>\n"
                    f"🌿 الفرع: <code>{escape_html(branch_name)}</code>\n\n"
                    f"<pre>{escape_html((p_res.stdout + p_res.stderr).strip()[:600]) or 'Everything up-to-date'}</pre>"
                )
            else:
                send_message(
                    chat_id,
                    f"❌ <b>فشل الـ Push:</b>\n"
                    f"<pre>{escape_html((p_res.stdout + p_res.stderr).strip()[:800])}</pre>"
                )
        except Exception as e:
            send_message(chat_id, f"❌ خطأ: {escape_html(str(e))}")

    elif cmd in ["/pr", "/pullrequest"]:
        ws, _ = get_effective_workspace()
        handle_pr_workflow(chat_id, ws, arg)

    elif cmd in ["/menu", "/keyboard", "/buttons"]:
        send_message(
            chat_id,
            "📱 <b>لوحة التحكم السريعة (Quick Action Bar):</b>\n\n"
            "تم تثبيت شريط الأزرار السريعة أسفل شاشة المحادثة للوصول الفوري بنقرة واحدة من الموبايل! 🚀\n\n"
            "<i>(لإخفاء الأزرار في أي وقت اكتب <code>/hidemenu</code>)</i>",
            reply_markup=get_main_reply_keyboard()
        )

    elif cmd in ["/hidemenu", "/closemenu"]:
        send_message(
            chat_id,
            "🙈 <b>تم إخفاء لوحة الأزرار السريعة.</b>\nلإعادتها في أي وقت اكتب <code>/menu</code>.",
            reply_markup={"remove_keyboard": True}
        )

    elif cmd in ["/servers", "/ports"]:
        servers = list_active_servers()
        if not servers:
            send_message(
                chat_id,
                "ℹ️ <b>لا توجد خوادم ويب أو خدمات محلية تعمل حالياً.</b>\n"
                "يمكنك بدء تشغيل أي سيرفر في مشاريعك (مثل <code>npm run dev</code> أو <code>flutter run</code>) وسيكتشفه البوت تلقائياً!"
            )
        else:
            lines = [f"🖥️ <b>لوحة الخوادم والمنافذ النشطة ({len(servers)} خوادم):</b>\n"]
            btns = []
            for srv in servers:
                p = srv["port"]
                nm = srv["name"]
                pr = srv.get("proc", "")
                pr_str = f" ({pr})" if pr else ""
                lines.append(f"🔌 <b>منفذ {p}:</b> {escape_html(nm)}<code>{escape_html(pr_str)}</code>")
                if p in [5173, 3000, 8080, 8000, 4200, 5000, 54322] or "vite" in pr.lower() or "node" in pr.lower() or "python" in pr.lower():
                    btns.append([{"text": f"🌐 فتح نفق للمنفذ {p} ({nm[:16]})", "callback_data": f"tunnel_port:{p}"}])
            
            btns.append([{"text": "🔄 تحديث الخوادم", "callback_data": "act:refresh_servers"}, {"text": "🛑 إغلاق النفق النشط", "callback_data": "act:tunnel_stop"}])
            send_message(chat_id, "\n".join(lines), reply_markup={"inline_keyboard": btns})

    elif cmd in ["/analytics", "/weekly"]:
        if analytics_engine:
            threading.Thread(target=analytics_engine.send_weekly_digest, args=(chat_id,), daemon=True).start()
        else:
            send_message(chat_id, "⚠️ محرك التحليلات غير متصل حالياً.")

    elif cmd in ["/test", "/tests", "/test_gen", "/test-gen"]:
        ws, _ = get_effective_workspace()
        if analytics_engine:
            threading.Thread(target=analytics_engine.generate_automated_tests, args=(ws, chat_id, arg), daemon=True).start()
        else:
            send_message(chat_id, "⚠️ محرك توليد الاختبارات غير متصل حالياً.")

    elif cmd in ["/context", "/memory", "/ctx"]:
        if context_engine:
            card_text, card_markup = context_engine.get_context_card_markup()
            send_message(chat_id, card_text, reply_markup=card_markup)
        else:
            send_message(chat_id, "⚠️ محرك تتبع الذاكرة غير متصل.")

    elif cmd in ["/compact", "/compress"]:
        if context_engine:
            _, msg = context_engine.force_immediate_compaction()
            send_message(chat_id, msg)
        else:
            send_message(chat_id, "⚠️ محرك ضغط السياق غير متصل.")

    elif cmd in ["/db_scan", "/db_health", "/db"]:
        if sre_engine:
            send_message(chat_id, "🔍 <i>جاري فحص سلامة وأمان وأداء قواعد البيانات (Advisors & Security Scan)...</i>")
            threading.Thread(target=sre_engine.scan_all_databases_health, args=(chat_id,), daemon=True).start()
        else:
            send_message(chat_id, "⚠️ محرك SRE غير متصل.")

    elif cmd in ["/incidents", "/sre"]:
        if sre_engine:
            headers = sre_engine.get_supabase_headers()
            url = f"{sre_engine.get_supabase_url()}/rest/v1/incident_queue?order=created_at.desc&limit=5"
            try:
                res = requests.get(url, headers=headers, timeout=10)
                rows = res.json() if res.status_code == 200 else []
                if not rows:
                    send_message(chat_id, "✅ <b>لا توجد أي أعطال أو حوادث مسجلة حالياً!</b> النظام سليم ومستقر 100%.")
                else:
                    lines = ["📋 <b>سجل الأعطال وحالات الإصلاح التلقائي (Autonomous SRE):</b>\n"]
                    for r in rows:
                        st_icon = "⏳" if r["status"] == "pending" else "🛠️" if r["status"] == "in_progress" else "🌿" if r["status"] == "pr_opened" else "✅" if r["status"] == "merged" else "⚠️"
                        lines.append(f"{st_icon} <b>{r['source'].upper()}</b> | <code>{escape_html(r['project_slug'])}</code>")
                        lines.append(f"💥 {escape_html(r['issue_title'][:60])}")
                        lines.append(f"الحالة: <code>{r['status']}</code>")
                        if r.get("pr_url"):
                            lines.append(f"🔗 <a href='{r['pr_url']}'>عرض الـ Pull Request</a>")
                        lines.append("")
                    send_message(chat_id, "\n".join(lines))
            except Exception as e:
                send_message(chat_id, f"❌ تعذر استعلام الأعطال: {e}")
        else:
            send_message(chat_id, "⚠️ محرك SRE غير متصل حالياً.")

    elif cmd in ["/hud", "/terminal_hud", "/live_hud"]:
        parts = text.strip().split()
        if len(parts) > 1:
            arg = parts[1].lower()
            if arg in ["on", "enable", "1", "true", "start"]:
                if terminal_hud:
                    terminal_hud.set_hud_enabled(True)
                    terminal_hud.ensure_kitty_process()
                send_message(chat_id, "🖥️ <b>تم تفعيل تيرمينال العرض الحي (Fullscreen Live HUD):</b> 🟢\nسيعمل التيرمينال ملء الشاشة تلقائياً مع كل مهمة.")
                return
            elif arg in ["off", "disable", "0", "false", "stop", "close"]:
                if terminal_hud:
                    terminal_hud.set_hud_enabled(False)
                    terminal_hud.close_terminal_hud()
                send_message(chat_id, "🖥️ <b>تم إيقاف تيرمينال العرض الحي:</b> 🔴\nتم إغلاق نافذة العرض ولن تفتح تلقائياً حتى تعيد تفعيلها.")
                return

        is_on = terminal_hud.is_hud_enabled() if terminal_hud else False
        is_running = terminal_hud.is_kitty_hud_running() if terminal_hud else False
        status_text = "🟢 مفعّل (Enabled)" if is_on else "🔴 متوقف (Disabled)"
        proc_text = "🖥️ النافذة نشطة وملء الشاشة" if is_running else "💤 النافذة مغلقة حالياً"
        
        hud_markup = {
            "inline_keyboard": [
                [
                    {"text": "🔴 إيقاف الـ HUD" if is_on else "🟢 تشغيل الـ HUD", "callback_data": "hud:toggle"},
                    {"text": "📸 سكرين شوت حي", "callback_data": "act:screen"}
                ],
                [
                    {"text": "🔄 إعادة فتح النافذة", "callback_data": "hud:reopen"},
                    {"text": "❌ إغلاق النافذة", "callback_data": "hud:close"}
                ]
            ]
        }
        send_message(
            chat_id,
            f"🖥️ <b>لوحة تحكم تيرمينال العرض الحي (Fullscreen Live HUD):</b>\n\n"
            f"• <b>الحالة:</b> {status_text}\n"
            f"• <b>حالة النافذة:</b> {proc_text}\n"
            f"• <b>دقة الشاشة:</b> Hyprland DP-4 (1680x1050 Fullscreen)\n"
            f"• <b>حجم الخط:</b> 15pt (واضح ومقروء من لقطات الشاشة البعيدة)\n\n"
            f"<i>يمكنك أيضاً الكتابة مباشرة: <code>/hud on</code> أو <code>/hud off</code></i>",
            reply_markup=hud_markup
        )


    elif cmd == "/sentry":
        ws, _ = get_effective_workspace()
        sentry_url = "https://nooreldean-coaching.sentry.io/issues/?project=4511983519858688"
        
        recent_errors = []
        try:
            j_res = subprocess.run(
                ["journalctl", "--user", "-u", "agy-bot.service", "-n", "30", "--no-pager"],
                capture_output=True, text=True, timeout=5
            )
            for l in j_res.stdout.splitlines():
                if any(k in l for k in ["ERROR", "Exception", "Sentry", "Crash", "FATAL"]):
                    recent_errors.append(l.strip())
        except Exception:
            pass

        err_preview = ""
        if recent_errors:
            err_preview = "\n\n⚠️ <b>آخر سجلات وتنبيهات مسجلة:</b>\n<pre>" + escape_html("\n".join(recent_errors[-3:])) + "</pre>"
        
        keyboard = {
            "inline_keyboard": [
                [{"text": "🛡️ فتح لوحة أخطاء Sentry Dashboard", "url": sentry_url}],
                [{"text": "🧪 فحص سلامة كود المشروع (Build/Analyze)", "callback_data": "act:build"}],
                [{"text": "🔄 استعلام الأيجنت عن مشاكل الكراش الأخيرة", "callback_data": "act:ask_agent_sentry"}]
            ]
        }
        send_message(
            chat_id,
            f"🛡️ <b>لوحة فحص الأخطاء والكراشات (Sentry Diagnostics):</b>\n\n"
            f"📁 <b>المشروع الحالي:</b> <code>{escape_html(os.path.basename(ws))}</code>\n"
            f"🔗 <b>اللوحة:</b> <code>nooreldean-coaching.sentry.io</code>\n"
            f"📊 <b>المشروع المرتبط:</b> <code>nooreldean-super-app (Flutter & Web)</code>"
            f"{err_preview}\n\n"
            f"<i>اضغط على الزر أدناه لفتح لوحة تحكم Sentry المباشرة أو لفحص التطبيق.</i>",
            reply_markup=keyboard
        )

    elif cmd in ["/briefing", "/morning", "/daily", "/summary"]:
        send_message(chat_id, get_briefing_report())

    else:
        # Natural Language prompt for Antigravity (Route through session / new chat chooser)
        prompt_task_dispatch(chat_id, text)

def main():
    print("[+] Starting Antigravity Telegram Bot...")
    sync_telegram_commands()
    start_media_cleanup_daemon()
    if sre_engine:
        sre_engine.init_sre_engine(CONFIG, send_message, edit_message_text, answer_callback_query, run_agent_task)
    if analytics_engine:
        analytics_engine.init_analytics_engine(CONFIG, send_message, edit_message_text)
    if context_engine:
        context_engine.init_context_engine(CONFIG, send_message, edit_message_text, answer_callback_query, save_config)
    offset = None
    
    # Send online notification if user id already exists
    if CONFIG.get("allowed_user_id"):
        send_message(
            CONFIG["allowed_user_id"],
            "🟢 <b>بوت Antigravity متصل وجاهز للعمل من الموبايل!</b>",
            reply_markup=get_main_reply_keyboard()
        )

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

                # Handle Inline Button clicks for Model / Effort selection
                cb = update.get("callback_query")
                if cb:
                    cb_id = cb["id"]
                    user_id = cb["from"]["id"]
                    chat_id = cb["message"]["chat"]["id"]
                    cb_data = cb.get("data", "")
                    message_id = cb.get("message", {}).get("message_id")

                    if user_id != CONFIG.get("allowed_user_id"):
                        answer_callback_query(cb_id, "⛔ غير مصرح لك")
                        continue

                    if cb_data.startswith("sre_"):
                        if sre_engine and sre_engine.handle_sre_callback(cb_data, chat_id, cb.get("message", {}).get("message_id"), user_id):
                            continue

                    if cb_data.startswith("ctx:"):
                        if context_engine and context_engine.handle_context_callback(chat_id, cb.get("message", {}).get("message_id"), cb_data):
                            continue

                    if cb_data.startswith("model:"):
                        chosen = cb_data.split(":", 1)[1]
                        CONFIG["current_model"] = chosen
                        save_config(CONFIG)
                        answer_callback_query(cb_id, f"تم اختيار النموذج: {chosen}")
                        send_message(chat_id, f"🧠 <b>تم تغيير نموذج الذكاء الاصطناعي بنجاح إلى:</b>\n<code>{escape_html(chosen)}</code>")

                    elif cb_data.startswith("effort:"):
                        chosen = cb_data.split(":", 1)[1]
                        CONFIG["current_effort"] = chosen
                        save_config(CONFIG)
                        answer_callback_query(cb_id, f"تم ضبط الجهد: {chosen}")
                        send_message(chat_id, f"⚡ <b>تم ضبط مستوى عمق التفكير بنجاح إلى:</b>\n<code>{escape_html(chosen)}</code>")

                    elif cb_data.startswith("account:"):
                        chosen = cb_data.split(":", 1)[1]
                        if chosen == "toggle_failover":
                            new_val = not CONFIG.get("auto_failover", True)
                            CONFIG["auto_failover"] = new_val
                            save_config(CONFIG)
                            state_str = "مفعل 🟢" if new_val else "معطل 🔴"
                            answer_callback_query(cb_id, f"التبديل التلقائي: {state_str}")
                            send_message(
                                chat_id,
                                f"🛡️ <b>تم تحديث نظام التبديل التلقائي عند انتهاء الكوتا:</b>\n"
                                f"الحالة الآن: <b>{state_str}</b>\n\n"
                                f"<i>{'عندما يواجه أي حساب حد الكوتا، سيتم التبديل تلقائياً للحساب التالي واستئناف المهمة.' if new_val else 'تم التعطيل، سيبقى البوت على الحساب المحدد يدوياً فقط.'}</i>"
                            )
                        elif chosen == "add_info":
                            answer_callback_query(cb_id, "تعليمات إضافة حساب")
                            info_msg = (
                                "➕ <b>طريقة إضافة حساب جوجل / Antigravity جديد:</b>\n\n"
                                "1. افتح شاشة Terminal في جهازك (أو في Antigravity IDE).\n"
                                "2. شغّل الأمر التالي:\n"
                                "<code>agy-add-account</code>\n\n"
                                "3. سيفتح لك المتصفح لتسجيل الدخول بحساب Google الجديد.\n"
                                "4. بمجرد تسجيل الدخول بنجاح، سيتم حفظ الحساب تلقائياً هنا في البوت وستتمكن من التبديل بينهما بنقرة زر واحدة في أي وقت!"
                            )
                            send_message(chat_id, info_msg)
                        else:
                            success = switch_to_account(chosen)
                            if success:
                                answer_callback_query(cb_id, f"تم التبديل إلى: {chosen}")
                                send_message(chat_id, f"✅ <b>تم التبديل بنجاح إلى الحساب:</b>\n<code>{escape_html(chosen)}</code>\n\nجميع المهام القادمة ستعمل الآن من خلال كوتا هذا الحساب.")
                            else:
                                answer_callback_query(cb_id, "فشل التبديل")
                                send_message(chat_id, f"❌ تعذر التبديل إلى: {escape_html(chosen)}")

                    elif cb_data.startswith("act:"):
                        action = cb_data.split(":", 1)[1]
                        ws, _ = get_effective_workspace()

                        if action == "deploy":
                            answer_callback_query(cb_id, "جاري الرفع...")
                            send_message(chat_id, f"🚀 <i>جاري الرفع على GitHub و Vercel لمشروع {os.path.basename(ws)}...</i>")
                            try:
                                subprocess.run(["git", "push"], cwd=ws, capture_output=True, text=True, timeout=30)
                                res = subprocess.run(["npx", "-y", "vercel", "--prod", "--yes"], cwd=ws, capture_output=True, text=True, timeout=60)
                                send_message(chat_id, f"✅ <b>تم النشر بنجاح!</b>\n<pre>{escape_html(res.stdout[-300:])}</pre>")
                            except Exception as e:
                                send_message(chat_id, f"❌ خطأ النشر: {escape_html(str(e))}")

                        elif action == "git":
                            answer_callback_query(cb_id, "فحص Git...")
                            try:
                                res = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=10)
                                out = res.stdout.strip() or "شجرة العمل نظيفة (Clean)"
                                send_message(chat_id, f"📊 <b>Git Status ({os.path.basename(ws)}):</b>\n<code>{escape_html(out)}</code>")
                            except Exception as e:
                                send_message(chat_id, f"❌ خطأ: {escape_html(str(e))}")

                        elif action == "diff":
                            answer_callback_query(cb_id, "عرض ملخص التغييرات...")
                            send_diff_summary(chat_id, ws)

                        elif action == "logs_refresh":
                            answer_callback_query(cb_id, "تحديث السجل...")
                            handle_command(chat_id, user_id, "/logs")

                        elif action == "restart_bot":
                            answer_callback_query(cb_id, "إعادة تشغيل البوت...")
                            handle_command(chat_id, user_id, "/restart")

                        elif action == "tasks_refresh":
                            answer_callback_query(cb_id, "تحديث المهام...")
                            handle_command(chat_id, user_id, "/tasks")

                        elif action == "build":
                            answer_callback_query(cb_id, "جاري فحص الـ Build...")
                            send_message(chat_id, f"🧪 <i>جاري فحص واختبار المشروع ({os.path.basename(ws)})...</i>")
                            try:
                                if os.path.exists(os.path.join(ws, "package.json")):
                                    b_cmd = ["npm", "run", "build"]
                                elif os.path.exists(os.path.join(ws, "pubspec.yaml")):
                                    b_cmd = ["flutter", "analyze"]
                                else:
                                    b_cmd = ["python3", "-m", "py_compile", "bot.py"]
                                res = subprocess.run(b_cmd, cwd=ws, capture_output=True, text=True, timeout=60)
                                out = (res.stdout + "\n" + res.stderr).strip()[-2500:]
                                status_emoji = "✅" if res.returncode == 0 else "❌"
                                send_message(chat_id, f"{status_emoji} <b>نتيجة الفحص (Exit {res.returncode}):</b>\n<pre>{escape_html(out)}</pre>")
                            except Exception as e:
                                send_message(chat_id, f"❌ خطأ الفحص: {escape_html(str(e))}")

                        elif action in ["undo", "undo_prompt"]:
                            answer_callback_query(cb_id, "تأكيد التراجع")
                            undo_kb = {
                                "inline_keyboard": [
                                    [
                                        {"text": "⚠️ نعم، احذف التعديلات نهائياً (تأكيد)", "callback_data": "act:undo_confirm"},
                                        {"text": "❌ إلغاء وتراجع", "callback_data": "act:undo_cancel"}
                                    ]
                                ]
                            }
                            send_message(
                                chat_id,
                                f"⚠️ <b>تحذير أمان - التراجع عن تعديلات الكود:</b>\n"
                                f"مشروع: <b>{escape_html(os.path.basename(ws))}</b>\n\n"
                                f"هل أنت متأكد من مسح جميع التعديلات غير المحفوظة نهائياً والعودة لآخر Commit نظيف؟",
                                reply_markup=undo_kb
                            )

                        elif action == "undo_confirm":
                            answer_callback_query(cb_id, "جاري استعادة النسخة النظيفة...")
                            try:
                                st = subprocess.run(["git", "status", "-s"], cwd=ws, capture_output=True, text=True, timeout=5)
                                if not st.stdout.strip():
                                    send_message(chat_id, f"ℹ️ لا توجد تعديلات للتراجع عنها، مشروع <b>{escape_html(os.path.basename(ws))}</b> نظيف تماماً.")
                                else:
                                    subprocess.run(["git", "restore", "."], cwd=ws, timeout=10)
                                    subprocess.run(["git", "clean", "-fd"], cwd=ws, timeout=10)
                                    send_message(chat_id, f"↩️ <b>تم التراجع بنجاح!</b>\nتمت استعادة حالة كود مشروع <b>{escape_html(os.path.basename(ws))}</b> النظيفة ومسح كافة التعديلات.")
                            except Exception as e:
                                send_message(chat_id, f"❌ خطأ أثناء التراجع: {escape_html(str(e))}")

                        elif action == "undo_cancel":
                            answer_callback_query(cb_id, "تم إلغاء التراجع")
                            send_message(chat_id, "🛡️ <b>تم إلغاء التراجع:</b> كود وتعديلات مشروعك آمنة تماماً كما هي.")

                        elif action == "commit":
                            answer_callback_query(cb_id, "جاري عمل Commit...")
                            handle_command(chat_id, user_id, "/commit")

                        elif action == "push":
                            answer_callback_query(cb_id, "جاري عمل Push...")
                            handle_command(chat_id, user_id, "/push")

                        elif action == "pr":
                            answer_callback_query(cb_id, "جاري فحص وإنشاء الـ PR...")
                            handle_command(chat_id, user_id, "/pr")

                        elif action == "create_pr_branch":
                            answer_callback_query(cb_id, "جاري إنشاء فرع ميزات جديد...")
                            ws, _ = get_effective_workspace()
                            ts_str = datetime.datetime.now().strftime("%m%d-%H%M")
                            new_branch = f"feat/update-{ts_str}"
                            b_res = subprocess.run(["git", "checkout", "-b", new_branch], cwd=ws, capture_output=True, text=True, timeout=10)
                            if b_res.returncode == 0:
                                send_message(chat_id, f"🌿 <b>تم إنشاء والتفرع إلى فرع جديد بنجاح:</b> <code>{new_branch}</code>")
                                handle_pr_workflow(chat_id, ws, f"Feature update ({ts_str})")
                            else:
                                send_message(chat_id, f"❌ فشل إنشاء الفرع:\n<code>{escape_html((b_res.stdout + b_res.stderr).strip())}</code>")

                        elif action == "extend_timeout":
                            current_task_info["task_timeout"] = current_task_info.get("task_timeout", 1800) + 900
                            answer_callback_query(cb_id, "تم تمديد المهلة 15 دقيقة إضافية!")
                            send_message(chat_id, "⏳ <b>تم تمديد مهلة تنفيذ المهمة بنجاح بمقدار 15 دقيقة إضافية!</b>")

                        elif action in ["shot", "screen", "screenshot"]:
                            answer_callback_query(cb_id, "جاري التقاط الشاشة...")

                            media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
                            os.makedirs(media_dir, exist_ok=True)
                            shot_path = os.path.join(media_dir, f"screen_{int(time.time())}.png")
                            if take_desktop_screenshot(shot_path):
                                now_t = datetime.datetime.now().strftime("%I:%M:%S %p")
                                caption = f"📸 <b>لقطة حية لشاشات الكمبيوتر:</b>\n⏰ <code>{now_t}</code> | 🖥️ Hyprland Workspace"
                                if not send_photo(chat_id, shot_path, caption=caption):
                                    send_document(chat_id, shot_path, caption=caption)
                            else:
                                send_message(chat_id, "❌ تعذر التقاط الشاشة.")

                        elif action == "web_shot":
                            answer_callback_query(cb_id, "جاري التقاط لقطة الويب...")
                            media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
                            os.makedirs(media_dir, exist_ok=True)
                            web_shot_path = os.path.join(media_dir, f"web_{int(time.time())}.png")

                            target_url = None
                            active_port = find_active_web_port()
                            if active_port:
                                target_url = f"http://127.0.0.1:{active_port}"
                            elif os.path.isfile(os.path.join(ws, "index.html")):
                                target_url = f"file://{os.path.join(ws, 'index.html')}"
                            elif os.path.isfile(os.path.join(ws, "public", "index.html")):
                                target_url = f"file://{os.path.join(ws, 'public', 'index.html')}"

                            if target_url and take_web_snapshot(target_url, web_shot_path):
                                now_t = datetime.datetime.now().strftime("%I:%M:%S %p")
                                caption = (
                                    f"🌐 <b>معاينة واجهة الويب (Headless UI Snapshot):</b>\n"
                                    f"📁 مشروع: <b>{escape_html(os.path.basename(ws))}</b>\n"
                                    f"🔗 المصدر: <code>{escape_html(target_url)}</code>\n"
                                    f"⏰ <code>{now_t}</code> | 🖥️ 1280x800"
                                )
                                if not send_photo(chat_id, web_shot_path, caption=caption):
                                    send_document(chat_id, web_shot_path, caption=caption)
                            else:
                                send_message(chat_id, f"ℹ️ لم يتم العثور على خادم ويب نشط أو ملف index.html في مشروع <b>{escape_html(os.path.basename(ws))}</b>.")

                        elif action == "tunnel":
                            answer_callback_query(cb_id, "جاري تجهيز رابط المعاينة...")
                            handle_command(chat_id, user_id, "/preview")

                        elif action == "tunnel_stop":
                            answer_callback_query(cb_id, "تم إغلاق النفق")
                            old_u = stop_active_tunnel()
                            if old_u:
                                send_message(chat_id, f"🛑 <b>تم إغلاق نفق المعاينة بنجاح:</b>\n<code>{escape_html(old_u)}</code>")
                            else:
                                send_message(chat_id, "ℹ️ لا يوجد نفق قيد التشغيل.")

                        elif action == "stop_task":
                            with active_task_lock:
                                if current_task_info["running"] and current_task_info["process"]:
                                    kill_process_tree(current_task_info["process"])
                                    mark_conversation_idle()
                                    answer_callback_query(cb_id, "تم إيقاف المهمة وتنظيف العمليات")
                                    resume_btn = {"inline_keyboard": [[{"text": "▶️ استكمال العمل من نفس النقطة", "callback_data": "act:resume_task"}]]}
                                    send_message(chat_id, "🛑 <b>تم إيقاف المهمة الحالية بنجاح وتنظيف كافة العمليات التابعة لها</b>.\nيمكنك استكمالها في أي وقت بضغطة زر واحدة أدناه:", reply_markup=resume_btn)
                                else:
                                    answer_callback_query(cb_id, "لا توجد مهمة قيد التشغيل حالياً")

                        elif action == "resume_task":
                            answer_callback_query(cb_id, "جاري استكمال المهمة...")
                            send_message(chat_id, "▶️ <b>جاري استكمال العمل فوراً من نفس النقطة والملفات...</b>")
                            threading.Thread(
                                target=run_agent_task,
                                args=(chat_id, "كمّل العمل من مكان ما وقفت وافحص لو كل حاجة تمام ونظيفة"),
                                daemon=True
                            ).start()

                        elif action == "refresh_servers":
                            answer_callback_query(cb_id, "جاري تحديث الخوادم...")
                            handle_command(chat_id, user_id, "/servers")

                        elif action == "ask_agent_sentry":
                            answer_callback_query(cb_id, "جاري فحص أخطاء Sentry...")
                            threading.Thread(
                                target=run_agent_task,
                                args=(chat_id, "افحص أخطاء وكراشات Sentry الأخيرة في المشروع وحللها واقترح حلولاً جذرية لها"),
                                daemon=True
                            ).start()

                    elif cb_data.startswith("file_get:"):
                        rel_path = cb_data.split(":", 1)[1]
                        ws, _ = get_effective_workspace()
                        full_p = os.path.join(ws, rel_path)
                        if os.path.isfile(full_p):
                            answer_callback_query(cb_id, f"جاري إرسال {os.path.basename(rel_path)}...")
                            caption = f"📄 <b>{escape_html(os.path.basename(rel_path))}</b>\n📁 <code>{escape_html(rel_path)}</code>"
                            if not send_document(chat_id, full_p, caption=caption):
                                send_message(chat_id, f"❌ تعذر إرسال الملف (قد يكون حجمه كبيراً جداً).")
                        else:
                            answer_callback_query(cb_id, "الملف غير موجود")
                            send_message(chat_id, f"❌ الملف غير موجود:\n<code>{escape_html(full_p)}</code>")

                    elif cb_data.startswith("conv:"):
                        c_action = cb_data.split(":", 1)[1]
                        if c_action == "new":
                            CONFIG["current_conversation_id"] = None
                            CONFIG["force_new"] = True
                            save_config(CONFIG)
                            answer_callback_query(cb_id, "جلسة جديدة")
                            send_message(
                                chat_id,
                                "✨ <b>تم بدء جلسة محادثة جديدة كلياً!</b>\n\n"
                                "أي رسالة ترسلها الآن ستبدأ شات نظيف جديد بدون التأثر بالسياق السابق."
                            )
                        elif c_action == "list":
                            answer_callback_query(cb_id, "قائمة الجلسات")
                            handle_command(chat_id, user_id, "/chats")
                        elif c_action.startswith("set:"):
                            chosen_conv = c_action.split(":", 1)[1]
                            CONFIG["current_conversation_id"] = chosen_conv
                            CONFIG["force_new"] = False
                            save_config(CONFIG)
                            det = get_conversation_details(chosen_conv)
                            title = det["title"] if det else chosen_conv
                            steps = det["steps"] if det else 0
                            ws = det.get("workspace", "") if det else ""
                            last_act = det.get("last_action", "") if det else ""
                            last_thought = det.get("last_thought", "") if det else ""
                            last_time = det.get("last_time", "") if det else ""

                            ws_line = f"📍 <b>المشروع الحالي:</b> <code>{escape_html(ws)}</code>\n" if ws else ""
                            act_line = f"🛠️ <b>آخر إجراء وصل له:</b>\n<code>{escape_html(last_act[:110])}</code>\n" if last_act else ""
                            thought_line = f"💭 <b>آخر فكرة/رد:</b>\n<i>{escape_html(last_thought[:130])}</i>\n" if last_thought else ""
                            time_line = f"⏰ <code>{last_time}</code> | " if last_time else ""

                            answer_callback_query(cb_id, "تم استئناف الشات")
                            send_message(
                                chat_id,
                                f"🔗 <b>تم استئناف الشات بنجاح:</b>\n"
                                f"👉 <b>{escape_html(title)}</b> 🟢\n"
                                f"({time_line}{steps} خطوة سابقة | ID: <code>{escape_html(chosen_conv[:12])}...</code>)\n\n"
                                f"{ws_line}{act_line}{thought_line}\n"
                                f"💡 <b>أنت الآن في نفس النقطة تماماً!</b> كل رسائلك وأوامرك القادمة ستتذكر وتكمل على نفس هذا المشروع والملف مباشرة."
                            )

                    elif cb_data.startswith("proj:"):
                        p_action = cb_data.split(":", 1)[1]
                        if p_action in ["list", "refresh"]:
                            answer_callback_query(cb_id, "قائمة المشاريع")
                            send_projects_menu(chat_id)
                        elif p_action == "auto":
                            CONFIG["workspace_mode"] = "auto"
                            save_config(CONFIG)
                            answer_callback_query(cb_id, "تتبع تلقائي للـ IDE")
                            ws, mode = get_effective_workspace()
                            send_message(
                                chat_id,
                                f"🔄 <b>تم تفعيل التتبع التلقائي للـ IDE!</b>\n"
                                f"📍 <b>المشروع المكتشف:</b> <code>{escape_html(ws)}</code> ({mode})\n\n"
                                f"<i>أي ملف تفتحه في الـ IDE سيتحول البوت إليه تلقائياً.</i>"
                            )

                    elif cb_data.startswith("proj_set:"):
                        try:
                            p_idx = int(cb_data.split(":", 1)[1])
                            projects = discover_all_projects()
                            if 0 <= p_idx < len(projects):
                                target_p = projects[p_idx]
                                answer_callback_query(cb_id, f"الانتقال إلى {target_p['name']}")
                                ok, summary = switch_to_workspace(target_p["path"])
                                if ok:
                                    msg, kb = format_project_card(target_p["path"], summary)
                                    send_message(chat_id, msg, reply_markup=kb)
                                else:
                                    send_message(chat_id, f"❌ تعذر فتح مسار المشروع:\n<code>{escape_html(target_p['path'])}</code>")
                            else:
                                answer_callback_query(cb_id, "مشروع غير موجود")
                        except Exception as e:
                            answer_callback_query(cb_id, "خطأ")
                            send_message(chat_id, f"❌ خطأ التبديل: {escape_html(str(e))}")

                    elif cb_data.startswith("hud:"):
                        hud_act = cb_data.split(":", 1)[1]
                        if hud_act == "toggle":
                            curr = terminal_hud.is_hud_enabled() if terminal_hud else True
                            new_st = not curr
                            if terminal_hud:
                                terminal_hud.set_hud_enabled(new_st)
                                if new_st:
                                    terminal_hud.ensure_kitty_process()
                                else:
                                    terminal_hud.close_terminal_hud()
                            answer_callback_query(cb_id, f"تم التغيير: {'مفعّل 🟢' if new_st else 'معطّل 🔴'}")
                            handle_command(chat_id, user_id, "/hud")
                        elif hud_act == "reopen":
                            if terminal_hud:
                                terminal_hud.close_terminal_hud()
                                time.sleep(0.3)
                                terminal_hud.ensure_kitty_process()
                            answer_callback_query(cb_id, "تم إعادة فتح النافذة 🖥️")
                            handle_command(chat_id, user_id, "/hud")
                        elif hud_act == "close":
                            if terminal_hud:
                                terminal_hud.close_terminal_hud()
                            answer_callback_query(cb_id, "تم إغلاق النافذة ❌")
                            handle_command(chat_id, user_id, "/hud")
                        elif hud_act.startswith("open"):
                            if terminal_hud:
                                terminal_hud.set_hud_enabled(True)
                                terminal_hud.ensure_kitty_process()
                                try:
                                    subprocess.run(["hyprctl", "eval", "return hl.dispatch(hl.dsp.focus({ window = 'class:agy-hud' }))"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                except Exception:
                                    pass
                            answer_callback_query(cb_id, "تم فتح شاشة الـ HUD على شاشة الكمبيوتر 🖥️")

                    elif cb_data.startswith("dsp:"):
                        parts = cb_data.split(":")
                        action = parts[1]
                        task_id = parts[2]
                        task = PENDING_DISPATCH.get(task_id)

                        if action == "cancel":
                            PENDING_DISPATCH.pop(task_id, None)
                            answer_callback_query(cb_id, "تم إلغاء الطلب")
                            if message_id:
                                edit_message_text(chat_id, message_id, "❌ <i>تم إلغاء الطلب.</i>")

                        elif action == "same":
                            task = PENDING_DISPATCH.pop(task_id, None)
                            if not task:
                                answer_callback_query(cb_id, "انتهت صلاحية هذا الطلب")
                                if message_id:
                                    edit_message_text(chat_id, message_id, "⚠️ <i>انتهت صلاحية هذا الطلب، يرجى إرساله مجدداً.</i>")
                            else:
                                is_busy = current_task_info.get("running", False) or bool(ACTIVE_RUNNING_PROCESSES)
                                ws, _ = get_effective_workspace()
                                curr_pname = os.path.basename(ws.rstrip("/"))
                                if is_busy:
                                    task["workspace"] = ws
                                    SESSION_TASK_QUEUE.append(task)
                                    q_pos = len(SESSION_TASK_QUEUE)
                                    answer_callback_query(cb_id, f"تمت الإضافة لطابور الانتظار (#{q_pos})")
                                    if message_id:
                                        edit_message_text(
                                            chat_id,
                                            message_id,
                                            f"⏳ <b>تمت إضافة طلبك إلى قائمة الانتظار لهذا الشات!</b> (الترتيب: #{q_pos})\n\n"
                                            f"📋 <b>المهمة:</b> <code>{escape_html(task['prompt'][:140])}</code>\n"
                                            f"📁 <b>المشروع:</b> <code>{escape_html(curr_pname)}</code>\n\n"
                                            f"<i>سيبدأ تنفيذه تلقائياً فور اكتمال المهمة الجارية دون مقاطعتها.</i>",
                                            reply_markup={
                                                "inline_keyboard": [
                                                    [{"text": "❌ إلغاء من طابور الانتظار", "callback_data": f"q:cancel:{task_id}"}]
                                                ]
                                            }
                                        )
                                else:
                                    answer_callback_query(cb_id, "جاري البدء فوراً ⚡")
                                    if message_id:
                                        edit_message_text(chat_id, message_id, "⚡ <i>جاري بدء المهمة في نفس الشات...</i>")
                                    threading.Thread(
                                        target=run_agent_task,
                                        args=(chat_id, task["prompt"]),
                                        kwargs={
                                            "banner_title": task.get("banner_title"),
                                            "extra_args": task.get("extra_args"),
                                            "agent_name": task.get("agent_name"),
                                            "override_workspace": ws
                                        },
                                        daemon=True
                                    ).start()

                        elif action == "new":
                            if not task:
                                answer_callback_query(cb_id, "انتهت صلاحية هذا الطلب")
                                if message_id:
                                    edit_message_text(chat_id, message_id, "⚠️ <i>انتهت صلاحية هذا الطلب، يرجى إرساله مجدداً.</i>")
                            else:
                                answer_callback_query(cb_id, "اختر المشروع للتشغيل")
                                projects = discover_all_projects()
                                curr_ws, _ = get_effective_workspace()
                                curr_pname = os.path.basename(curr_ws.rstrip("/"))

                                kb_rows = [
                                    [{"text": f"📍 نفس المشروع ({curr_pname}) - شات جديد ✨", "callback_data": f"dsp:exec:{task_id}:curr"}]
                                ]

                                row = []
                                for idx, p in enumerate(projects):
                                    try:
                                        if os.path.realpath(p["path"]) == os.path.realpath(curr_ws):
                                            continue
                                    except Exception:
                                        pass
                                    row.append({"text": f"📁 {p['name']}", "callback_data": f"dsp:exec:{task_id}:{idx}"})
                                    if len(row) == 2:
                                        kb_rows.append(row)
                                        row = []
                                if row:
                                    kb_rows.append(row)

                                kb_rows.append([{"text": "❌ إلغاء", "callback_data": f"dsp:cancel:{task_id}"}])

                                if message_id:
                                    edit_message_text(
                                        chat_id,
                                        message_id,
                                        f"✨ <b>فتح شات جديد:</b>\n"
                                        f"📋 <b>المهمة:</b> <code>{escape_html(task['prompt'][:100])}</code>\n\n"
                                        f"اختر المشروع الذي تود فتح الشات الجديد فيه:",
                                        reply_markup={"inline_keyboard": kb_rows}
                                    )

                        elif action == "exec":
                            task = PENDING_DISPATCH.pop(task_id, None)
                            if not task:
                                answer_callback_query(cb_id, "انتهت صلاحية هذا الطلب")
                                if message_id:
                                    edit_message_text(chat_id, message_id, "⚠️ <i>انتهت صلاحية هذا الطلب، يرجى إرساله مجدداً.</i>")
                            else:
                                target_proj = parts[3]
                                if target_proj == "curr":
                                    target_ws, _ = get_effective_workspace()
                                else:
                                    p_idx = int(target_proj)
                                    projects = discover_all_projects()
                                    target_ws = projects[p_idx]["path"] if (0 <= p_idx < len(projects)) else get_effective_workspace()[0]

                                target_pname = os.path.basename(target_ws.rstrip("/"))
                                answer_callback_query(cb_id, f"بدء شات جديد في {target_pname} 🚀")
                                if message_id:
                                    edit_message_text(
                                        chat_id,
                                        message_id,
                                        f"🚀 <b>جاري تشغيل شات جديد بالتوازي في:</b>\n<code>{escape_html(target_pname)}</code>..."
                                    )
                                threading.Thread(
                                    target=run_agent_task,
                                    args=(chat_id, task["prompt"]),
                                    kwargs={
                                        "banner_title": task.get("banner_title"),
                                        "extra_args": task.get("extra_args"),
                                        "agent_name": task.get("agent_name"),
                                        "override_workspace": target_ws,
                                        "force_new_chat": True,
                                        "allow_parallel": True
                                    },
                                    daemon=True
                                ).start()

                    elif cb_data.startswith("q:"):
                        parts = cb_data.split(":")
                        action = parts[1]
                        task_id = parts[2]
                        if action == "cancel":
                            SESSION_TASK_QUEUE = [item for item in SESSION_TASK_QUEUE if item.get("task_id") != task_id]
                            answer_callback_query(cb_id, "تم إلغاء الطلب من قائمة الانتظار 🗑️")
                            if message_id:
                                edit_message_text(chat_id, message_id, "❌ <i>تم إلغاء هذا الطلب من طابور الانتظار بنجاح.</i>")

                    elif cb_data.startswith("screen:"):

                        s_action = cb_data.split(":", 1)[1]
                        if s_action == "off":
                            try:
                                subprocess.run("hyprctl dispatch dpms off 2>/dev/null || xset dpms force off 2>/dev/null", shell=True, timeout=5)
                                answer_callback_query(cb_id, "تم إطفاء الشاشة")
                                send_message(chat_id, "🌑 <b>تم إطفاء شاشات الكمبيوتر لتوفير الطاقة (DPMS Off).</b>\nالجهاز والبوت مستمران بالعمل في الخلفية.")
                            except Exception as e:
                                answer_callback_query(cb_id, "خطأ")
                                send_message(chat_id, f"❌ خطأ: {escape_html(str(e))}")
                        elif s_action == "on":
                            try:
                                subprocess.run("hyprctl dispatch dpms on 2>/dev/null || xset dpms force on 2>/dev/null", shell=True, timeout=5)
                                answer_callback_query(cb_id, "تم تشغيل الشاشة")
                                send_message(chat_id, "💡 <b>تم تشغيل شاشات الكمبيوتر (DPMS On).</b>")
                            except Exception as e:
                                answer_callback_query(cb_id, "خطأ")
                                send_message(chat_id, f"❌ خطأ: {escape_html(str(e))}")
                        elif s_action == "lock":
                            try:
                                subprocess.Popen(["hyprlock"])
                                answer_callback_query(cb_id, "تم قفل الشاشة")
                                send_message(chat_id, "🔒 <b>تم قفل شاشة الكمبيوتر (Hyprlock Activated).</b>")
                            except Exception:
                                try:
                                    subprocess.run(["loginctl", "lock-session"], timeout=5)
                                    answer_callback_query(cb_id, "تم قفل الجلسة")
                                    send_message(chat_id, "🔒 <b>تم قفل الجلسة بنجاح!</b>")
                                except Exception as e:
                                    answer_callback_query(cb_id, "خطأ")
                                    send_message(chat_id, f"❌ تعذر القفل: {escape_html(str(e))}")

                    elif cb_data.startswith("pc_pwr:"):
                        p_act = cb_data.split(":", 1)[1]
                        
                        if p_act == "confirm_off":
                            kb = {
                                "inline_keyboard": [
                                    [
                                        {"text": "🛑 نعم، أطفئ الكمبيوتر الآن", "callback_data": "pc_pwr:do_poweroff"},
                                        {"text": "❌ تراجع وإلغاء", "callback_data": "pc_pwr:cancel"}
                                    ]
                                ]
                            }
                            edit_message_text(
                                chat_id, message_id,
                                "⚠️ <b>تأكيد إيقاف تشغيل الكمبيوتر:</b>\n\n"
                                "هل أنت متأكد من رغبتك في إيقاف تشغيل الجهاز بالكامل؟\n"
                                "<i>(سيتوقف البوت عن الاستجابة حتى يتم إعادة تشغيل الكمبيوتر مجدداً)</i>",
                                reply_markup=kb
                            )
                            answer_callback_query(cb_id, "تأكيد إيقاف التشغيل")

                        elif p_act == "confirm_suspend":
                            kb = {
                                "inline_keyboard": [
                                    [
                                        {"text": "💤 نعم، أدخل الجهاز في وضع السكون", "callback_data": "pc_pwr:do_suspend"},
                                        {"text": "❌ تراجع وإلغاء", "callback_data": "pc_pwr:cancel"}
                                    ]
                                ]
                            }
                            edit_message_text(
                                chat_id, message_id,
                                "💤 <b>تأكيد وضع السكون (Suspend to RAM):</b>\n\n"
                                "الجهاز سيوقف المراوح ويقلل استهلاك الطاقة للحد الأدنى (1-2W).\n"
                                "يمكنك إيقاظه بسهولة عبر Magic Packet من الموبايل أو لوحة المفاتيح.",
                                reply_markup=kb
                            )
                            answer_callback_query(cb_id, "تأكيد وضع السكون")

                        elif p_act == "confirm_reboot":
                            kb = {
                                "inline_keyboard": [
                                    [
                                        {"text": "🔄 نعم، أعد تشغيل الجهاز الآن", "callback_data": "pc_pwr:do_reboot"},
                                        {"text": "❌ تراجع وإلغاء", "callback_data": "pc_pwr:cancel"}
                                    ]
                                ]
                            }
                            edit_message_text(
                                chat_id, message_id,
                                "🔄 <b>تأكيد إعادة تشغيل الكمبيوتر (Reboot):</b>\n\n"
                                "سيتم إعادة تشغيل النظام بالكامل، وسيعود البوت للعمل تلقائياً فور الإقلاع.",
                                reply_markup=kb
                            )
                            answer_callback_query(cb_id, "تأكيد إعادة التشغيل")

                        elif p_act == "cancel":
                            answer_callback_query(cb_id, "تم الإلغاء")
                            handle_command(chat_id, user_id, "/pc")

                        elif p_act == "screens_menu":
                            answer_callback_query(cb_id, "شاشات الكمبيوتر")
                            handle_command(chat_id, user_id, "/screen")

                        elif p_act == "wol_guide":
                            answer_callback_query(cb_id, "دليل تشغيل الجهاز")
                            guide_text = (
                                "📡 <b>دليل تشغيل الكمبيوتر عن بُعد (Power ON):</b>\n\n"
                                "بما أن الكمبيوتر عندما يكون مغلقاً بالكامل لا تعمل عليه برامج أو اتصال بالإنترنت، هناك طريقتان لتشغيله من الموبايل:\n\n"
                                "<b>1️⃣ الطريقة الأولى: من الموبايل داخل البيت (Wake-on-LAN):</b>\n"
                                "• كارت الشبكة <code>eno1</code> في جهازك يدعم الـ WoL ومفعّل بالفعل ومضبوط على <code>magic</code>.\n"
                                "• نزّل على موبايلك تطبيق مجاني زي <b>WolOn</b> أو <b>Wake On Lan</b>.\n"
                                "• أضف جهازك بالإعدادات التالية:\n"
                                "  - <b>MAC Address:</b> <code>c4:34:6b:58:c6:d2</code>\n"
                                "  - <b>IP Address:</b> <code>192.168.1.14</code> (أو Broadcast: <code>192.168.1.255</code>)\n"
                                "  - <b>Port:</b> <code>9</code>\n"
                                "• بضغطة واحدة من موبايلك وأنت على الواي فاي، الكمبيوتر هيفتح في ثانية!\n\n"
                                "<b>2️⃣ الطريقة الثانية: من أي مكان في العالم خارج البيت (Smart Plug):</b>\n"
                                "• في إعدادات الـ BIOS في المازربورد، فعّل خيار: <code>Restore on AC Power Loss: Power ON</code>.\n"
                                "• وصّل فيشة الكمبيوتر بفيشة ذكية (Smart Plug زي Tuya / Sonoff / Tapo).\n"
                                "• من تطبيق الفيشة من أي مكان في العالم، أطفئ الفيشة وشغلها، الجهاز هيقوم فوراً ويبوت والبوت هيبعتلك رسالة إنه جاهز!"
                            )
                            edit_message_text(chat_id, message_id, guide_text, reply_markup={
                                "inline_keyboard": [[{"text": "🔙 عودة للوحة الطاقة", "callback_data": "pc_pwr:cancel"}]]
                            })

                        elif p_act == "do_poweroff":
                            answer_callback_query(cb_id, "جاري إيقاف التشغيل...")
                            edit_message_text(
                                chat_id, message_id,
                                "🛑 <b>جاري إيقاف تشغيل الكمبيوتر بالكامل الآن...</b>\n\n"
                                "👋 مع السلامة يا كوتش! سيتوقف البوت عن العمل حالاً."
                            )
                            def _do_off():
                                time.sleep(1.5)
                                subprocess.run("systemctl poweroff 2>/dev/null || loginctl poweroff", shell=True)
                            threading.Thread(target=_do_off, daemon=True).start()

                        elif p_act == "do_suspend":
                            answer_callback_query(cb_id, "جاري إدخال الجهاز في وضع السكون...")
                            edit_message_text(
                                chat_id, message_id,
                                "💤 <b>جاري إدخال الكمبيوتر في وضع السكون (Suspend to RAM)...</b>\n\n"
                                "تم حفظ حالة كل البرامج والشاشات. يمكنك إيقاظ الجهاز عبر Wake-on-LAN أو الضغط على الكيبورد."
                            )
                            def _do_susp():
                                time.sleep(1.5)
                                subprocess.run("systemctl suspend 2>/dev/null || loginctl suspend", shell=True)
                            threading.Thread(target=_do_susp, daemon=True).start()

                        elif p_act == "do_reboot":
                            answer_callback_query(cb_id, "جاري إعادة التشغيل...")
                            edit_message_text(
                                chat_id, message_id,
                                "🔄 <b>جاري إعادة تشغيل الكمبيوتر (Rebooting)...</b>\n\n"
                                "سيعود البوت للعمل تلقائياً بمجرد إقلاع النظام."
                            )
                            def _do_reb():
                                time.sleep(1.5)
                                subprocess.run("systemctl reboot 2>/dev/null || loginctl reboot", shell=True)
                            threading.Thread(target=_do_reb, daemon=True).start()

                    elif cb_data.startswith("tunnel_port:"):
                        p_str = cb_data.split(":", 1)[1]
                        if p_str.isdigit():
                            p_val = int(p_str)
                            answer_callback_query(cb_id, f"جاري تشغيل النفق للمنفذ {p_val}...")
                            send_message(chat_id, f"🌐 <i>جاري تشغيل نفق Cloudflare المشفر للمنفذ {p_val}...</i>")
                            url, is_new = start_cloudflare_tunnel(p_val)
                            if url:
                                keyboard = {
                                    "inline_keyboard": [
                                        [{"text": f"🌐 فتح المنفذ {p_val} لايف (HTTPS)", "url": url}],
                                        [{"text": "🛑 إغلاق النفق", "callback_data": "act:tunnel_stop"}]
                                    ]
                                }
                                send_message(
                                    chat_id,
                                    f"🚀 <b>تم فتح نفق Cloudflare المشفر للمنفذ {p_val}!</b>\n\n"
                                    f"🔗 <b>الرابط:</b> <code>{escape_html(url)}</code>\n"
                                    f"🔌 <b>المنفذ المحلي:</b> <code>http://127.0.0.1:{p_val}</code>\n\n"
                                    f"<i>يمكنك تصفح واختبار المشروع مباشرة من شاشة موبايلك!</i>",
                                    reply_markup=keyboard
                                )
                            else:
                                send_message(chat_id, f"❌ تعذر فتح نفق للمنفذ {p_val}.")

                    elif cb_data.startswith("ans_q:"):
                        parts = cb_data.split(":")
                        if len(parts) >= 3:
                            try:
                                st_idx = int(parts[1])
                            except ValueError:
                                st_idx = parts[1]
                            try:
                                o_idx = int(parts[2])
                            except ValueError:
                                o_idx = 0
                            
                            opts = active_question_state.get(st_idx, [])
                            chosen_text = opts[o_idx] if o_idx < len(opts) else "نعم"
                            answer_callback_query(cb_id, f"تم اختيار: {chosen_text[:20]}")
                            
                            sent_stdin = False
                            with active_task_lock:
                                if current_task_info["running"] and current_task_info["process"] and current_task_info["process"].stdin:
                                    try:
                                        current_task_info["process"].stdin.write(f"{chosen_text}\n")
                                        current_task_info["process"].stdin.flush()
                                        sent_stdin = True
                                    except Exception:
                                        pass
                            
                            if sent_stdin:
                                send_message(chat_id, f"✅ <b>تم إرسال قرارك للأيجنت فوراً:</b>\n👉 <code>{escape_html(chosen_text)}</code>")
                            else:
                                send_message(chat_id, f"ℹ️ <b>تم حفظ اختيارك:</b> <code>{escape_html(chosen_text)}</code>\n(المهمة جارية أو تجاوزت خطوة السؤال).")

                    elif cb_data.startswith("doc_inspect:"):
                        fname = cb_data.split(":", 1)[1]
                        ws, _ = get_effective_workspace()
                        dest_path = os.path.join(ws, ".scratch", "uploads", fname)
                        answer_callback_query(cb_id, "جاري فحص الملف...")
                        prompt = f"The user requested inspecting the uploaded file at: {dest_path}. Use your view_file tool to read and analyze its structure and content."
                        threading.Thread(
                            target=run_agent_task,
                            args=(chat_id, prompt),
                            kwargs={"banner_title": f"🔍 <b>فحص وتحليل ملف مستلم:</b> <code>{escape_html(fname)}</code>"},
                            daemon=True
                        ).start()

                    elif cb_data.startswith("doc_summary:"):
                        fname = cb_data.split(":", 1)[1]
                        ws, _ = get_effective_workspace()
                        dest_path = os.path.join(ws, ".scratch", "uploads", fname)
                        answer_callback_query(cb_id, "جاري تلخيص الملف...")
                        prompt = f"The user requested a summary of the uploaded file at: {dest_path}. Read its content using view_file and provide a clear Arabic summary of what this file contains."
                        threading.Thread(
                            target=run_agent_task,
                            args=(chat_id, prompt),
                            kwargs={"banner_title": f"📝 <b>تلخيص ملف مستلم:</b> <code>{escape_html(fname)}</code>"},
                            daemon=True
                        ).start()

                    elif cb_data.startswith("pick_opt:"):
                        parts = cb_data.split(":")
                        q_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                        o_idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
                        
                        opts = active_extracted_options.get(q_id, [])
                        chosen = None
                        for o in opts:
                            if o["index"] == o_idx:
                                chosen = o
                                break
                        
                        label = chosen["label"] if chosen else f"الخيار {o_idx}"
                        full_text = chosen["full_text"] if chosen else label
                        
                        answer_callback_query(cb_id, f"تم اختيار: {label[:25]}")
                        send_message(
                            chat_id,
                            f"👉 <b>تم اختيارك:</b> <code>{escape_html(label)}</code>\n\n"
                            f"<i>جاري إرسال قرارك للأيجنت ومتابعة الاستجواب فوراً... 🚀</i>"
                        )
                        
                        followup_prompt = (
                            f"The user selected: Option {o_idx} ({full_text}).\n\n"
                            f"Proceed immediately with the next step or next question. "
                            f"Remember: Ask ONE single question at a time with 2-4 clearly numbered choices so they render as interactive buttons."
                        )
                        threading.Thread(
                            target=run_agent_task,
                            args=(chat_id, followup_prompt),
                            kwargs={"banner_title": f"🎯 <b>متابعة الاستجواب:</b> <code>{escape_html(label)}</code>"},
                            daemon=True
                        ).start()

                    continue

                msg = update.get("message")
                if not msg:
                    continue

                user_id = msg["from"]["id"]
                chat_id = msg["chat"]["id"]

                # First time pairing: lock bot to first user who contacts it
                if CONFIG.get("allowed_user_id") is None:
                    CONFIG["allowed_user_id"] = user_id
                    save_config(CONFIG)
                    send_message(chat_id, f"🔒 <b>تم قفل البوت بنجاح وربطه بحسابك!</b> (User ID: {user_id})")

                # Security check
                if user_id != CONFIG.get("allowed_user_id"):
                    send_message(chat_id, "⛔ عذراً، هذا بوت خاص ومغلق على المالك فقط.")
                    continue

                # Voice Note handling
                if "voice" in msg or "audio" in msg:
                    voice_obj = msg.get("voice") or msg.get("audio")
                    file_id = voice_obj.get("file_id")
                    if file_id:
                        media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
                        os.makedirs(media_dir, exist_ok=True)
                        ts = int(time.time())
                        ogg_path = os.path.join(media_dir, f"voice_{ts}.ogg")
                        wav_path = os.path.join(media_dir, f"voice_{ts}.wav")
                        send_message(chat_id, "🎙️ <i>تم استلام رسالتك الصوتية، جاري التحويل والمعالجة...</i>")
                        if download_telegram_file(file_id, ogg_path):
                            subprocess.run(["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                            target_audio = wav_path if os.path.exists(wav_path) else ogg_path
                            voice_prompt = (
                                f"The user sent an Arabic/English voice note saved at: {target_audio}. "
                                f"First inspect and transcribe this audio using your view_file tool, understand their exact spoken request, "
                                f"and execute it in the workspace."
                            )
                            prompt_task_dispatch(chat_id, voice_prompt, banner_title="🎙️ <b>معالجة رسالة صوتية (Voice Note)</b>")
                        else:
                            send_message(chat_id, "❌ تعذر تحميل الرسالة الصوتية.")
                    continue

                # Photo / Screenshot handling
                if "photo" in msg:
                    photos = msg["photo"]
                    file_id = photos[-1]["file_id"]
                    caption = msg.get("caption", "حلل هذه الصورة واشرحها أو نفذ المطلوب فيها برمجياً في المشروع")
                    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")
                    os.makedirs(media_dir, exist_ok=True)
                    img_path = os.path.join(media_dir, f"photo_{int(time.time())}.jpg")
                    send_message(chat_id, "📸 <i>تم استلام لقطة الشاشة / الصورة، جاري التحليل...</i>")
                    if download_telegram_file(file_id, img_path):
                        photo_prompt = (
                            f"The user sent an image/screenshot saved at: {img_path}. "
                            f"View this image using your view_file tool, analyze the UI/error/code depicted in it, "
                            f"and execute the user request: {caption}"
                        )
                        prompt_task_dispatch(chat_id, photo_prompt, banner_title="📸 <b>تحليل صورة / لقطة شاشة (Screenshot Analysis)</b>")
                    else:
                        send_message(chat_id, "❌ تعذر تحميل الصورة.")
                    continue

                # Document / File upload handling
                if "document" in msg:
                    doc = msg["document"]
                    file_id = doc.get("file_id")
                    file_name = doc.get("file_name", f"file_{int(time.time())}")
                    caption = msg.get("caption", "").strip()
                    file_size = doc.get("file_size", 0)

                    if file_id:
                        ws, _ = get_effective_workspace()
                        upload_dir = os.path.join(ws, ".scratch", "uploads")
                        os.makedirs(upload_dir, exist_ok=True)
                        dest_path = os.path.join(upload_dir, file_name)

                        send_message(chat_id, f"📥 <i>تم استلام الملف <code>{escape_html(file_name)}</code>، جاري التنزيل والمعالجة...</i>")
                        if download_telegram_file(file_id, dest_path):
                            rel_p = os.path.relpath(dest_path, ws)
                            size_kb = round(file_size / 1024, 1)
                            if caption:
                                file_prompt = (
                                    f"The user sent a document/file saved at: {dest_path} (relative path: {rel_p}, size: {size_kb} KB).\n"
                                    f"Inspect this file using your view_file tool, understand its content, and execute the user's instructions: {caption}"
                                )
                                prompt_task_dispatch(chat_id, file_prompt, banner_title=f"📥 <b>معالجة ملف مستلم:</b> <code>{escape_html(file_name)}</code> ({size_kb} KB)")
                            else:
                                file_kb = {
                                    "inline_keyboard": [
                                        [{"text": "🔍 فحص وقراءة الملف بالأيجنت", "callback_data": f"doc_inspect:{file_name}"}],
                                        [{"text": "📝 تلخيص محتوى الملف", "callback_data": f"doc_summary:{file_name}"}]
                                    ]
                                }
                                send_message(
                                    chat_id,
                                    f"✅ <b>تم استلام وحفظ الملف بنجاح!</b>\n\n"
                                    f"📄 <b>الاسم:</b> <code>{escape_html(file_name)}</code>\n"
                                    f"📦 <b>الحجم:</b> <code>{size_kb} KB</code>\n"
                                    f"📁 <b>المسار:</b> <code>{escape_html(rel_p)}</code>\n\n"
                                    f"💡 <i>اكتب أي تعليمات تريد للأيجنت تنفيذها على هذا الملف، أو اضغط زر فحص/تلخيص أدناه:</i>",
                                    reply_markup=file_kb
                                )
                        else:
                            send_message(chat_id, f"❌ تعذر تنزيل الملف <code>{escape_html(file_name)}</code>.")
                    continue

                if "text" in msg:
                    text_content = msg["text"].strip()
                    if sre_engine and sre_engine.check_and_handle_refine_input(chat_id, text_content):
                        continue
                    threading.Thread(target=handle_command, args=(chat_id, user_id, msg["text"]), daemon=True).start()

        except requests.exceptions.RequestException:
            time.sleep(5)
        except Exception as e:
            print(f"[Error in loop] {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
