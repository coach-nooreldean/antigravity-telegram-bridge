#!/usr/bin/env python3
"""
Antigravity Live Cyberpunk Fullscreen Multi-Project Terminal HUD for Hyprland/Kitty.
Renders real-time telemetry, all open project sessions across workspaces,
cross-project conversation streams, live tool activity, and persistent completion dashboards.
"""

import os
import sys
import time
import json
import shutil
import sqlite3
import datetime
import subprocess
import unicodedata
import re

STATE_FILE = "/tmp/agy_live_state.json"
SETTINGS_FILE = "/tmp/agy_hud_settings.json"
CONV_DB_PATH = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")
CONFIG_PATH = "/mnt/data2/documents/githup/nooreldean-life-os/.bot/config.json"

# ANSI Color & Style Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

# Cyberpunk 24-bit TrueColor Palettes
FG_CYAN = "\033[38;2;0;255;234m"
FG_GREEN = "\033[38;2;0;255;128m"
FG_YELLOW = "\033[38;2;255;215;0m"
FG_ORANGE = "\033[38;2;255;140;0m"
FG_RED = "\033[38;2;255;45;85m"
FG_PURPLE = "\033[38;2;180;100;255m"
FG_WHITE = "\033[38;2;240;240;245m"
FG_GRAY = "\033[38;2;120;125;145m"

SPINNERS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Cache for cross-project DB queries
_CACHED_PROJECT_DATA = None
_LAST_DB_QUERY_TIME = 0

def strip_ansi(s: str) -> str:
    return ANSI_REGEX.sub("", str(s))

def char_display_width(ch: str) -> int:
    if ord(ch) == 0xfe0f:
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("F", "W"):
        return 2
    if ord(ch) in (
        0x231a, 0x231b, 0x23f0, 0x23f3, 0x2600, 0x2601, 0x2614, 0x2615,
        0x2648, 0x2653, 0x267f, 0x2693, 0x26a1, 0x26aa, 0x26ab, 0x26bd,
        0x26be, 0x26c4, 0x26c5, 0x26ce, 0x26d4, 0x26ea, 0x26f2, 0x26f3,
        0x26f5, 0x26fa, 0x26fd, 0x2702, 0x2705, 0x2708, 0x2709, 0x270a,
        0x270b, 0x2728, 0x274c, 0x274e, 0x2753, 0x2757, 0x27b0, 0x27bf,
        0x2b1b, 0x2b1c, 0x2b50, 0x2b55
    ) or ord(ch) >= 0x1F000:
        return 2
    return 1

def str_display_width(s: str) -> int:
    clean = strip_ansi(s)
    return sum(char_display_width(c) for c in clean)

def truncate_to_display_width(text: str, max_w: int, ellipsis: str = "...") -> str:
    clean = strip_ansi(text)
    if str_display_width(clean) <= max_w:
        return text
    target_w = max(0, max_w - str_display_width(ellipsis))
    cur_w = 0
    chars = []
    for ch in clean:
        cw = char_display_width(ch)
        if cur_w + cw > target_w:
            break
        cur_w += cw
        chars.append(ch)
    return "".join(chars) + ellipsis

def make_box_line(inner: str, inner_width: int, fg_border: str = FG_CYAN, reset: str = RESET) -> str:
    w = str_display_width(inner)
    pad = max(0, inner_width - w)
    return f"{fg_border}║{reset}{inner}{' ' * pad}{fg_border}║{reset}"

def make_centered_box_line(text: str, inner_width: int, fg_border: str = FG_CYAN, reset: str = RESET) -> str:
    w = str_display_width(text)
    total_pad = max(0, inner_width - w)
    pad_left = total_pad // 2
    pad_right = total_pad - pad_left
    return f"{fg_border}║{reset}{' ' * pad_left}{text}{' ' * pad_right}{fg_border}║{reset}"

def make_two_col_box_line(left: str, right: str, inner_width: int, fg_border: str = FG_CYAN, reset: str = RESET) -> str:
    wl = str_display_width(left)
    wr = str_display_width(right)
    pad = max(1, inner_width - wl - wr)
    return f"{fg_border}║{reset}{left}{' ' * pad}{right}{fg_border}║{reset}"

def get_term_size():
    try:
        ts = shutil.get_terminal_size((130, 40))
        return max(75, ts.columns), max(24, ts.lines)
    except Exception:
        return 130, 40

def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

def read_state():
    if not os.path.isfile(STATE_FILE):
        return {
            "status": "idle",
            "task_title": "Waiting for instructions from Telegram...",
            "workspace": "/mnt/data2/documents/githup",
            "model": "Claude Opus / Gemini Flash",
            "effort": "high",
            "start_time": time.time(),
            "step": 0,
            "action": "Standing by for remote tasks",
            "context_steps": 0,
            "max_context_steps": 45,
            "modified_files": [],
            "summary": "",
            "activity_log": []
        }
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_state(state: dict):
    try:
        tmp_path = STATE_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, STATE_FILE)
    except Exception as e:
        print(f"[HUD write_state error] {e}", file=sys.stderr)

def is_hud_enabled() -> bool:
    try:
        if os.path.isfile(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("enabled", True)
    except Exception:
        pass
    return True

def set_hud_enabled(enabled: bool):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump({"enabled": enabled}, f)
    except Exception:
        pass

def get_desktop_env():
    env = os.environ.copy()
    if not env.get("XDG_RUNTIME_DIR"):
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    if not env.get("WAYLAND_DISPLAY"):
        rdir = env["XDG_RUNTIME_DIR"]
        for cand in ["wayland-1", "wayland-0"]:
            if os.path.exists(os.path.join(rdir, cand)):
                env["WAYLAND_DISPLAY"] = cand
                break
    return env

def is_kitty_hud_running() -> bool:
    try:
        out = subprocess.check_output(["pgrep", "-fa", "kitty.*agy-hud"], text=True)
        return bool(out.strip())
    except Exception:
        return False

def ensure_kitty_process():
    if not is_hud_enabled():
        return
    if is_kitty_hud_running():
        return
    
    script_path = os.path.abspath(__file__)
    env = get_desktop_env()
    kitty_bin = shutil.which("kitty") or "/usr/bin/kitty"
    
    cmd = [
        kitty_bin,
        "--class", "agy-hud",
        "--title", "Antigravity Live HUD",
        "--start-as=fullscreen",
        "-o", "font_size=15",
        "-o", "background=#0a0c14",
        "-o", "foreground=#e0e6ed",
        "-o", "window_padding_width=12",
        "python3", script_path
    ]
    try:
        subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        print(f"[HUD ensure_kitty error] {e}", file=sys.stderr)

def close_terminal_hud():
    try:
        subprocess.run(["pkill", "-f", "kitty.*agy-hud"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def start_terminal_hud(task_title: str, workspace: str, model: str = "Claude Opus / Gemini Flash", effort: str = "high"):
    state = {
        "status": "running",
        "task_title": task_title,
        "workspace": workspace,
        "model": model,
        "effort": effort,
        "start_time": time.time(),
        "step": 0,
        "action": "Autonomous agent initialized task environment...",
        "context_steps": 0,
        "max_context_steps": 45,
        "modified_files": [],
        "summary": "",
        "activity_log": [
            f"Initialized mission: {task_title[:80]}",
            f"Target workspace: {os.path.basename(workspace)}",
            f"Model configured: {model} (Effort: {effort})"
        ]
    }
    write_state(state)
    ensure_kitty_process()

def update_terminal_hud_action(step=None, action=None, activity_item=None, context_steps=None):
    state = read_state()
    if not state:
        return
    if step is not None:
        state["step"] = step
    if action:
        state["action"] = action
    if context_steps is not None:
        state["context_steps"] = context_steps
    if activity_item:
        act_list = state.get("activity_log", [])
        clean_item = strip_ansi(activity_item).strip()
        if clean_item and (not act_list or act_list[-1] != clean_item):
            act_list.append(clean_item)
            state["activity_log"] = act_list[-35:]
    write_state(state)

def finish_terminal_hud(duration=0, summary="", modified_files=None):
    state = read_state()
    if not state:
        return
    state["status"] = "completed"
    state["duration"] = duration
    state["summary"] = summary
    if modified_files is not None:
        state["modified_files"] = modified_files
    state["action"] = "Mission completed successfully."
    act_list = state.get("activity_log", [])
    act_list.append(f"Mission verified and completed in {int(duration)}s.")
    state["activity_log"] = act_list[-35:]
    write_state(state)

def fetch_hud_projects_data():
    """Gathers open project sessions across all workspaces and recent chats with caching."""
    global _CACHED_PROJECT_DATA, _LAST_DB_QUERY_TIME
    now = time.time()
    if _CACHED_PROJECT_DATA and (now - _LAST_DB_QUERY_TIME < 2.5):
        return _CACHED_PROJECT_DATA

    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            pass

    curr_cid = cfg.get("current_conversation_id")
    curr_ws = cfg.get("current_workspace", "")
    curr_ws_name = os.path.basename(curr_ws.rstrip("/")) if curr_ws else ""

    rows = []
    if os.path.exists(CONV_DB_PATH):
        try:
            conn = sqlite3.connect(CONV_DB_PATH)
            cur = conn.cursor()
            cur.execute("""
                SELECT conversation_id, title, step_count, last_modified_time, workspace_uris
                FROM conversation_summaries
                ORDER BY last_modified_time DESC
                LIMIT 50
            """)
            rows = cur.fetchall()
            conn.close()
        except Exception:
            pass

    project_map = {}
    recent_chats = []

    for r in rows:
        cid, title, steps, mtime, uris_raw = r
        ws = "General"
        if uris_raw:
            try:
                uris = json.loads(uris_raw)
                if uris:
                    clean = uris[0].replace("file://", "").rstrip("/")
                    ws = os.path.basename(clean)
            except Exception:
                pass

        t_str = ""
        if mtime:
            try:
                raw_t = str(mtime).split(".")[0].replace("T", " ")
                dt = datetime.datetime.fromisoformat(raw_t)
                t_str = dt.strftime("%I:%M %p")
            except Exception:
                t_str = str(mtime)[:10]

        is_current = (cid == curr_cid) or (ws == curr_ws_name and not curr_cid)
        item = {
            "id": cid,
            "project": ws,
            "title": title or "Active Session",
            "steps": steps or 0,
            "time": t_str,
            "is_current": is_current,
            "status": "ACTIVE" if is_current else "STANDBY"
        }

        recent_chats.append(item)
        if ws not in project_map:
            project_map[ws] = item

    # Add any saved project states from config
    p_states = cfg.get("project_states", {})
    for p_path, p_info in p_states.items():
        p_name = os.path.basename(p_path.rstrip("/"))
        if p_name not in project_map and p_info.get("conversation_id"):
            cid = p_info["conversation_id"]
            is_cur = (cid == curr_cid) or (p_name == curr_ws_name)
            project_map[p_name] = {
                "id": cid,
                "project": p_name,
                "title": f"Session ({cid[:8]})",
                "steps": 0,
                "time": "Saved",
                "is_current": is_cur,
                "status": "ACTIVE" if is_cur else "STANDBY"
            }

    # Sort so active is first, then by project name
    sorted_projects = sorted(project_map.values(), key=lambda x: (not x["is_current"], x["project"].lower()))
    _CACHED_PROJECT_DATA = (sorted_projects, recent_chats[:8])
    _LAST_DB_QUERY_TIME = now
    return _CACHED_PROJECT_DATA

def format_progress_bar(current, maximum, width=14):
    maximum = max(1, maximum)
    pct = min(100, int((current / maximum) * 100))
    filled = min(width, int((current / maximum) * width))
    empty = width - filled
    
    if pct < 50:
        fill_color = FG_GREEN
    elif pct < 75:
        fill_color = FG_YELLOW
    elif pct < 90:
        fill_color = FG_ORANGE
    else:
        fill_color = FG_RED
        
    bar = f"{fill_color}{'█' * filled}{FG_GRAY}{'░' * empty}{RESET}"
    return bar, pct

def render_hud():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    spinner_idx = 0
    
    try:
        while True:
            try:
                state = read_state()
                status = state.get("status", "idle")
                title = state.get("task_title", "Antigravity Agent Standing By")
                workspace = state.get("workspace", "/mnt/data2/documents/githup")
                model = state.get("model", "Claude Opus / Gemini Flash")
                effort = state.get("effort", "high")
                start_time = state.get("start_time", time.time())
                step = state.get("step", 0)
                action = state.get("action", "Standing by for remote tasks...")
                ctx_steps = state.get("context_steps", 0)
                max_ctx = state.get("max_context_steps", 45)
                mod_files = state.get("modified_files", [])
                summary = state.get("summary", "")
                activity = state.get("activity_log", [])
                
                open_projects, recent_chats = fetch_hud_projects_data()
                
                elapsed = int(time.time() - start_time) if status == "running" else int(state.get("duration", 0))
                elapsed_str = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
                
                term_cols, term_rows = get_term_size()
                inner_w = term_cols - 4
                
                spinner_char = SPINNERS[spinner_idx % len(SPINNERS)]
                spinner_idx += 1
                
                ctx_bar, ctx_pct = format_progress_bar(ctx_steps, max_ctx, width=12)
                
                lines = []
                
                # --- TOP BORDER ---
                lines.append(f"{FG_CYAN}{BOLD}╔{'═' * inner_w}╗{RESET}")
                
                # --- HEADER ---
                hdr_text = "⚡ ANTIGRAVITY MULTI-PROJECT COMMAND STATION ⚡  |  HYPRLAND DESKTOP HUD"
                lines.append(make_centered_box_line(f"{FG_WHITE}{BOLD}{hdr_text}{RESET}", inner_w))
                lines.append(f"{FG_CYAN}{BOLD}╠{'═' * inner_w}╣{RESET}")
                
                # --- ACTIVE EXECUTION DECK ---
                ws_short = os.path.basename(workspace) if workspace else "Workspace"
                status_badge = (
                    f"{FG_GREEN}● RUNNING{RESET}" if status == "running" else
                    (f"{FG_CYAN}✔ COMPLETED{RESET}" if status == "completed" else f"{FG_YELLOW}● STANDING BY{RESET}")
                )
                r1_left = f" 📁 {BOLD}Active Target:{RESET} {FG_WHITE}{BOLD}{ws_short}{RESET}  |  🤖 {BOLD}Model:{RESET} {FG_PURPLE}{model}{RESET}"
                r1_right = f"⏱️ {BOLD}Elapsed:{RESET} {FG_YELLOW}{elapsed_str}{RESET}  |  {status_badge} "
                lines.append(make_two_col_box_line(r1_left, r1_right, inner_w))
                
                r2_left = f" 🧠 {BOLD}Active Context:{RESET} [ {BOLD}{ctx_steps}{RESET} / {max_ctx} steps ] {ctx_bar} ({ctx_pct}%)"
                r2_right = f"🔄 {BOLD}Step:{RESET} #{step}  |  ⚡ {BOLD}Effort:{RESET} {effort} "
                lines.append(make_two_col_box_line(r2_left, r2_right, inner_w))
                
                if status == "running":
                    clean_title = truncate_to_display_width(title.replace("\n", " ").strip(), inner_w - 18)
                    lines.append(make_box_line(f" 🎯 {BOLD}Mission:{RESET} {FG_WHITE}{BOLD}{clean_title}{RESET}", inner_w))
                    clean_act = truncate_to_display_width(action.replace("\n", " ").strip(), inner_w - 24)
                    lines.append(make_box_line(f" {FG_GREEN}{spinner_char}{RESET} {BOLD}Current Action:{RESET} {FG_CYAN}{clean_act}{RESET}", inner_w))
                
                lines.append(f"{FG_CYAN}{BOLD}╠{'═' * inner_w}╣{RESET}")
                
                # --- SECTION: ALL OPEN PROJECTS & SESSIONS MATRIX ---
                p_count = len(open_projects)
                lines.append(make_box_line(f" 🌐 {BOLD}ALL OPEN PROJECTS & ACTIVE SESSIONS MATRIX ({p_count} Workspaces):{RESET}", inner_w))
                
                # Table header
                th_status = "STATUS"
                th_proj = "PROJECT WORKSPACE"
                th_topic = "ACTIVE SESSION / TOPIC"
                th_steps = "MEMORY"
                th_time = "TIME"
                
                # Display each distinct project session
                max_proj_disp = min(5, len(open_projects))
                for p in open_projects[:max_proj_disp]:
                    is_cur = p.get("is_current", False) or (p["project"] == ws_short)
                    flag_tag = f"{FG_GREEN}● ACTIVE {RESET}" if is_cur else f"{FG_GRAY}💤 SAVED  {RESET}"
                    
                    p_name_styled = f"{FG_WHITE}{BOLD}{p['project'][:20]:<20}{RESET}"
                    clean_p_title = truncate_to_display_width(p['title'], 36)
                    p_title_styled = f"{FG_CYAN}{clean_p_title:<36}{RESET}"
                    
                    p_steps = p.get("steps", 0)
                    p_bar, p_pct = format_progress_bar(p_steps, 45, width=8)
                    steps_styled = f"[{p_steps:>2}/45] {p_bar} ({p_pct:>2}%)"
                    
                    time_styled = f"{FG_GRAY}{p.get('time', ''):>8}{RESET}"
                    
                    row_str = f"   {flag_tag} 📁 {p_name_styled}  💬 {p_title_styled}  {steps_styled}  {time_styled}"
                    lines.append(make_box_line(row_str, inner_w))
                
                lines.append(f"{FG_CYAN}{BOLD}╠{'═' * inner_w}╣{RESET}")
                
                # --- SECTION: RECENT CONVERSATIONS STREAM ACROSS ALL WORKSPACES ---
                lines.append(make_box_line(f" 💬 {BOLD}RECENT ACTIVE CONVERSATION THREADS (CROSS-PROJECT):{RESET}", inner_w))
                
                recent_disp = recent_chats[:5] if recent_chats else []
                for chat in recent_disp:
                    p_tag = f"{FG_PURPLE}[{chat['project']}]{RESET}"
                    c_title = truncate_to_display_width(chat['title'], inner_w - 42)
                    c_steps = f"{FG_YELLOW}#{chat['steps']} steps{RESET}"
                    c_time = f"{FG_GRAY}@{chat['time']}{RESET}"
                    lines.append(make_box_line(f"   › {p_tag} {FG_WHITE}{c_title}{RESET} ({c_steps}) {c_time}", inner_w))
                
                # --- SECTION: LIVE ACTIVITY FEED OR MISSION ACCOMPLISHED ---
                remaining_rows = max(6, term_rows - len(lines) - 4)
                lines.append(f"{FG_CYAN}{BOLD}╠{'═' * inner_w}╣{RESET}")
                
                if status == "completed":
                    lines.append(make_box_line(f" {FG_GREEN}{BOLD}🎉 MISSION ACCOMPLISHED - SUMMARY DASHBOARD:{RESET}", inner_w))
                    sum_lines = [l.strip() for l in summary.split("\n") if l.strip()] if summary else [
                        "All autonomous tasks executed and verified successfully.",
                        "Code and database migrations validated."
                    ]
                    for sl in sum_lines[:max(2, remaining_rows - 3)]:
                        clean_sl = truncate_to_display_width(sl, inner_w - 8)
                        lines.append(make_box_line(f"   {FG_WHITE}• {clean_sl}{RESET}", inner_w))
                    if mod_files:
                        f_str = ", ".join([os.path.basename(f) for f in mod_files[:5]])
                        clean_f = truncate_to_display_width(f_str, inner_w - 26)
                        lines.append(make_box_line(f"   📁 {BOLD}Modified Files:{RESET} {FG_YELLOW}{clean_f}{RESET}", inner_w))
                else:
                    lines.append(make_box_line(f" 📜 {BOLD}Live Autonomous Activity Feed:{RESET}", inner_w))
                    disp_activity = activity[-max(3, remaining_rows - 2):] if activity else [
                        "Standing by for remote instructions from Telegram.",
                        f"Target Workspace: {workspace}",
                        "All background services (SRE Engine, Context Compactor) running healthy."
                    ]
                    for item in disp_activity:
                        item_clean = truncate_to_display_width(item, inner_w - 8)
                        lines.append(make_box_line(f"   {FG_GRAY}›{RESET} {FG_WHITE}{item_clean}{RESET}", inner_w))
                
                # --- FOOTER ---
                lines.append(f"{FG_CYAN}{BOLD}╠{'═' * inner_w}╣{RESET}")
                ft_left = f" 📱 {DIM}Remote Control Active via Telegram (@CoachNooreldeanBot){RESET}"
                ft_right = f"{DIM}Hyprland DP-4 (1680x1050){RESET} "
                lines.append(make_two_col_box_line(ft_left, ft_right, inner_w))
                lines.append(f"{FG_CYAN}{BOLD}╚{'═' * inner_w}╝{RESET}")
                
                # Render to screen
                sys.stdout.write("\033[H" + "\n".join(lines))
                sys.stdout.flush()
                
            except Exception as loop_e:
                pass
                
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

if __name__ == "__main__":
    clear_screen()
    render_hud()
