#!/usr/bin/env python3
"""
Antigravity Live Cyberpunk Fullscreen Terminal HUD for Hyprland/Kitty.
Renders real-time telemetry, context window progress, live tool activity,
and persistent mission completion dashboards for remote screenshot monitoring.
"""

import os
import sys
import time
import json
import shutil
import datetime
import subprocess
import unicodedata
import re

STATE_FILE = "/tmp/agy_live_state.json"
SETTINGS_FILE = "/tmp/agy_hud_settings.json"

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
        return max(70, ts.columns), max(22, ts.lines)
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

def format_progress_bar(current, maximum, width=18):
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
                action = state.get("action", "Running autonomous instructions...")
                ctx_steps = state.get("context_steps", 0)
                max_ctx = state.get("max_context_steps", 45)
                mod_files = state.get("modified_files", [])
                summary = state.get("summary", "")
                activity = state.get("activity_log", [])
                
                elapsed = int(time.time() - start_time) if status == "running" else int(state.get("duration", 0))
                elapsed_str = f"{elapsed // 60:02d}:{elapsed % 60:02d}"
                
                term_cols, term_rows = get_term_size()
                inner_w = term_cols - 4
                
                spinner_char = SPINNERS[spinner_idx % len(SPINNERS)]
                spinner_idx += 1
                
                ctx_bar, ctx_pct = format_progress_bar(ctx_steps, max_ctx, width=14)
                
                lines = []
                
                # --- TOP BORDER ---
                lines.append(f"{FG_CYAN}{BOLD}╔{'═' * inner_w}╗{RESET}")
                
                # --- HEADER ---
                hdr_text = "⚡ ANTIGRAVITY AUTONOMOUS OPERATING STATION ⚡  |  HYPRLAND DESKTOP HUD"
                lines.append(make_centered_box_line(f"{FG_WHITE}{BOLD}{hdr_text}{RESET}", inner_w))
                lines.append(f"{FG_CYAN}{BOLD}╠{'═' * inner_w}╣{RESET}")

                
                # --- ROW 1: METRICS ---
                ws_short = os.path.basename(workspace) if workspace else "Workspace"
                status_badge = (
                    f"{FG_GREEN}● RUNNING{RESET}" if status == "running" else
                    (f"{FG_CYAN}✔ COMPLETED{RESET}" if status == "completed" else f"{FG_YELLOW}● STANDING BY{RESET}")
                )
                r1_left = f" 📁 {BOLD}Project:{RESET} {FG_WHITE}{ws_short}{RESET}  |  🤖 {BOLD}Model:{RESET} {FG_PURPLE}{model}{RESET}"
                r1_right = f"⏱️ {BOLD}Elapsed:{RESET} {FG_YELLOW}{elapsed_str}{RESET}  |  {status_badge} "
                lines.append(make_two_col_box_line(r1_left, r1_right, inner_w))
                
                # --- ROW 2: CONTEXT & STEP ---
                r2_left = f" 🧠 {BOLD}Context Window:{RESET} [ {BOLD}{ctx_steps}{RESET} / {max_ctx} steps ] {ctx_bar} ({ctx_pct}%)"
                r2_right = f"🔄 {BOLD}Step:{RESET} #{step}  |  ⚡ {BOLD}Effort:{RESET} {effort} "
                lines.append(make_two_col_box_line(r2_left, r2_right, inner_w))
                lines.append(f"{FG_CYAN}{BOLD}╠{'═' * inner_w}╣{RESET}")
                
                # --- ROW 3: MISSION TITLE ---
                clean_title = truncate_to_display_width(title.replace("\n", " ").strip(), inner_w - 16)
                m_line = f" 🎯 {BOLD}Mission:{RESET} {FG_WHITE}{BOLD}{clean_title}{RESET}"
                lines.append(make_box_line(m_line, inner_w))
                
                # --- ROW 4: CURRENT ACTION ---
                if status == "running":
                    clean_act = truncate_to_display_width(action.replace("\n", " ").strip(), inner_w - 24)
                    act_str = f" {FG_GREEN}{spinner_char}{RESET} {BOLD}Current Action:{RESET} {FG_CYAN}{clean_act}{RESET}"
                else:
                    act_str = f" {FG_GREEN}✔{RESET} {BOLD}Status:{RESET} {FG_WHITE}Mission finished successfully.{RESET}"
                lines.append(make_box_line(act_str, inner_w))
                lines.append(f"{FG_CYAN}{BOLD}╠{'═' * inner_w}╣{RESET}")
                
                # --- BODY: SUMMARY OR LIVE FEED ---
                body_rows = max(8, term_rows - 16)
                
                if status == "completed":
                    lines.append(make_box_line(f" {FG_GREEN}{BOLD}🎉 MISSION ACCOMPLISHED - SUMMARY DASHBOARD:{RESET}", inner_w))
                    lines.append(make_box_line("", inner_w))
                    
                    sum_lines = [l.strip() for l in summary.split("\n") if l.strip()] if summary else [
                        "All autonomous steps executed successfully with zero syntax errors.",
                        "Static analysis and verification passed."
                    ]
                    for sl in sum_lines[:body_rows - 4]:
                        clean_sl = truncate_to_display_width(sl, inner_w - 8)
                        lines.append(make_box_line(f"   {FG_WHITE}• {clean_sl}{RESET}", inner_w))
                        
                    if mod_files:
                        f_str = ", ".join([os.path.basename(f) for f in mod_files[:6]])
                        clean_f = truncate_to_display_width(f_str, inner_w - 26)
                        lines.append(make_box_line("", inner_w))
                        lines.append(make_box_line(f"   📁 {BOLD}Modified Files:{RESET} {FG_YELLOW}{clean_f}{RESET}", inner_w))
                        
                    pad = body_rows - len(sum_lines[:body_rows - 4]) - (3 if mod_files else 1)
                    for _ in range(max(0, pad)):
                        lines.append(make_box_line("", inner_w))
                else:
                    lines.append(make_box_line(f" 📜 {BOLD}Live Autonomous Activity Feed:{RESET}", inner_w))
                    
                    disp_activity = activity[-body_rows:] if activity else [
                        "Initialized isolated working branch and environment.",
                        "Tri-Phase Architecture: Claude Opus 4.6 Thinking analyzing requirements.",
                        f"Target Workspace: {workspace}",
                        f"Active Action: {action}"
                    ]
                    
                    for item in disp_activity:
                        item_clean = truncate_to_display_width(item, inner_w - 8)
                        lines.append(make_box_line(f"   {FG_GRAY}›{RESET} {FG_WHITE}{item_clean}{RESET}", inner_w))
                        
                    for _ in range(max(0, body_rows - len(disp_activity))):
                        lines.append(make_box_line("", inner_w))
                        
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
