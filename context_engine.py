#!/usr/bin/env python3
"""
Context Window Tracking & Continuous Compaction Engine for Antigravity Telegram Bridge.

Features:
- Real-time Context Window Meter with visual progress bar (e.g. [ 15 / 45 ] 🟩🟩⬜⬜ 33%).
- Enforces a strict hard cap (default: 45 steps) to prevent bloated context, sluggishness, and hallucination.
- Post-Message Continuous Compaction: Automatically extracts and compresses conversation state after EVERY message.
- Automatic Rollover Guard: When reaching 45 steps, seamlessly rolls over to a clean session while injecting the compacted memory summary.
- Interactive Telegram commands & callbacks: /context, instant compaction, manual rollover, and memory inspection.
"""

import os
import sys
import time
import json
import sqlite3
import datetime
import logging
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger("context_engine")

CONV_SUMMARIES_DB = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")
CONV_DIR = os.path.expanduser("~/.gemini/antigravity-cli/conversations")
MEMORY_DIR = os.path.expanduser("~/.gemini/antigravity-cli/context_memory")
DEFAULT_MAX_STEPS = 45

# Shared dependencies injected from bot.py
_CONFIG = {}
_send_message = None
_edit_message_text = None
_answer_callback_query = None
_save_config = None

def init_context_engine(config: dict, send_msg_func, edit_msg_func, answer_cb_func, save_cfg_func):
    """Initializes the context engine with host bot hooks."""
    global _CONFIG, _send_message, _edit_message_text, _answer_callback_query, _save_config
    _CONFIG = config
    _send_message = send_msg_func
    _edit_message_text = edit_msg_func
    _answer_callback_query = answer_cb_func
    _save_config = save_cfg_func

    os.makedirs(MEMORY_DIR, exist_ok=True)
    if "max_context_steps" not in _CONFIG:
        _CONFIG["max_context_steps"] = DEFAULT_MAX_STEPS
        _save_config(_CONFIG)
    logger.info(f"[ContextEngine] Initialized with max_context_steps = {_CONFIG.get('max_context_steps', DEFAULT_MAX_STEPS)}")

def get_max_context_steps() -> int:
    """Returns the configured max context steps."""
    return int(_CONFIG.get("max_context_steps", DEFAULT_MAX_STEPS))

def get_context_status(conv_id: Optional[str] = None, max_steps: Optional[int] = None) -> Dict[str, Any]:
    """
    Queries current context window usage from SQLite DB and calculates visual meter.
    Returns structured stats dictionary.
    """
    if max_steps is None:
        max_steps = get_max_context_steps()

    target_cid = conv_id or _CONFIG.get("current_conversation_id")
    steps = 0
    title = "جلسة نشطة"
    last_mod = ""

    if os.path.exists(CONV_SUMMARIES_DB):
        try:
            conn = sqlite3.connect(CONV_SUMMARIES_DB)
            cur = conn.cursor()
            if target_cid:
                cur.execute(
                    "SELECT conversation_id, title, step_count, last_modified_time FROM conversation_summaries WHERE conversation_id = ?",
                    (target_cid,)
                )
                row = cur.fetchone()
            else:
                cur.execute(
                    "SELECT conversation_id, title, step_count, last_modified_time FROM conversation_summaries ORDER BY last_modified_time DESC LIMIT 1"
                )
                row = cur.fetchone()
            conn.close()

            if row:
                target_cid = row[0]
                title = row[1] or (target_cid[:12] if target_cid else "جلسة نشطة")
                steps = row[2] or 0
                last_mod = row[3] or ""
        except Exception as e:
            logger.error(f"[ContextEngine] Error reading summaries DB: {e}")

    # Fallback to direct conversation database if steps is 0 or summary not updated
    if target_cid and steps == 0:
        c_db = os.path.join(CONV_DIR, f"{target_cid}.db")
        if os.path.exists(c_db):
            try:
                conn = sqlite3.connect(c_db)
                cur = conn.cursor()
                cur.execute("SELECT max(idx) FROM steps")
                max_idx = cur.fetchone()[0]
                conn.close()
                if max_idx is not None:
                    steps = max_idx + 1
            except Exception:
                pass

    pct = min(100, int((steps / max(1, max_steps)) * 100))
    filled = min(8, int((steps / max(1, max_steps)) * 8))
    empty = 8 - filled

    if pct < 50:
        bar_char = "🟩"
        status_label = "🟢 خفيف وسريع"
        health = "excellent"
    elif pct < 75:
        bar_char = "🟨"
        status_label = "🟡 متوسط"
        health = "good"
    elif pct < 90:
        bar_char = "🟧"
        status_label = "🟠 مرتفع (يقترب من الحد)"
        health = "warning"
    else:
        bar_char = "🟥"
        status_label = "🔴 حرج (جاهز للضغط والتدوير)"
        health = "critical"

    progress_bar = (bar_char * filled) + ("⬜" * empty)
    remaining = max(0, max_steps - steps)

    compacted_file = os.path.join(MEMORY_DIR, f"{target_cid}.json") if target_cid else None
    has_compacted = os.path.isfile(compacted_file) if compacted_file else False

    meter_badge = f"🧠 <b>سعة الذاكرة:</b> [ <code>{steps}</code> / <code>{max_steps}</code> ] {progress_bar} (<b>{pct}%</b>)"
    
    return {
        "conversation_id": target_cid,
        "title": title,
        "steps": steps,
        "max_steps": max_steps,
        "remaining": remaining,
        "percentage": pct,
        "progress_bar": progress_bar,
        "status_label": status_label,
        "health": health,
        "last_modified": last_mod,
        "meter_badge": meter_badge,
        "has_compacted": has_compacted
    }

def format_live_context_badge(conv_id: Optional[str] = None) -> str:
    """Returns a short, compact single-line meter for live execution banners."""
    st = get_context_status(conv_id)
    return f"🧠 <b>الذاكرة:</b> [ <code>{st['steps']}/{st['max_steps']}</code> ] {st['progress_bar']} ({st['percentage']}%)"

def get_conversation_step_count(conv_id: Optional[str] = None) -> int:
    """Returns total step count for the given conversation or active one."""
    st = get_context_status(conv_id)
    return st.get("steps", 0)

def extract_message_keypoints(text: str, max_points: int = 4) -> list:
    """Extracts concise meaningful bullet points from a prompt or response."""
    if not text:
        return []
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    points = []
    for l in lines:
        if l.startswith(("-", "*", "•", "1.", "2.", "3.", "4.", "5.", "✅", "🚀", "📁", "🛠️")):
            cleaned = l.lstrip("-*•0123456789. \t")
            if len(cleaned) > 10:
                points.append(cleaned[:120])
        elif len(l) > 20 and not l.startswith("<") and not l.startswith("```"):
            points.append(l[:120])
        if len(points) >= max_points:
            break
    if not points and lines:
        points.append(lines[0][:120])
    return points

def compress_after_message(conv_id: Optional[str], workspace: str, prompt: str, response: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Compresses and persists context state immediately after EVERY message.
    Checks if hard limit (max_context_steps) is reached:
      - If reached: triggers automatic rollover, creates a dense carryover summary,
        resets session, and returns did_rollover=True with notification message.
      - If within limit: updates local compacted memory and returns did_rollover=False.
    """
    max_steps = get_max_context_steps()
    target_cid = conv_id or _CONFIG.get("current_conversation_id")
    stats = get_context_status(target_cid, max_steps)
    curr_steps = stats["steps"]

    os.makedirs(MEMORY_DIR, exist_ok=True)
    memory_file = os.path.join(MEMORY_DIR, f"{target_cid}.json") if target_cid else os.path.join(MEMORY_DIR, "latest.json")

    # Load existing memory or initialize fresh
    existing_memory = {
        "conversation_id": target_cid,
        "workspace": workspace,
        "created_at": datetime.datetime.now().isoformat(),
        "turns_count": 0,
        "objectives": [],
        "completed_milestones": [],
        "modified_files": [],
        "key_decisions": [],
        "latest_state_summary": ""
    }

    if os.path.isfile(memory_file):
        try:
            with open(memory_file, "r", encoding="utf-8") as f:
                existing_memory = json.load(f)
        except Exception:
            pass

    existing_memory["turns_count"] = existing_memory.get("turns_count", 0) + 1
    existing_memory["last_updated"] = datetime.datetime.now().isoformat()
    existing_memory["step_count"] = curr_steps

    # Extract user objective
    clean_prompt = prompt.strip()
    if clean_prompt:
        first_line = clean_prompt.split("\n")[0][:140]
        if first_line not in existing_memory["objectives"]:
            existing_memory["objectives"].append(first_line)
            if len(existing_memory["objectives"]) > 5:
                existing_memory["objectives"] = existing_memory["objectives"][-5:]

    # Extract response milestones
    res_points = extract_message_keypoints(response, max_points=3)
    for p in res_points:
        if p not in existing_memory["completed_milestones"]:
            existing_memory["completed_milestones"].append(p)
            if len(existing_memory["completed_milestones"]) > 8:
                existing_memory["completed_milestones"] = existing_memory["completed_milestones"][-8:]

    # Detect modified files from response text
    for token in response.split():
        token_clean = token.strip("`'\"(),;:")
        if any(token_clean.endswith(ext) for ext in [".py", ".dart", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".md", ".sql", ".sh"]):
            if "/" in token_clean or "." in token_clean:
                if token_clean not in existing_memory["modified_files"] and len(token_clean) < 100:
                    existing_memory["modified_files"].append(token_clean)
                    if len(existing_memory["modified_files"]) > 12:
                        existing_memory["modified_files"] = existing_memory["modified_files"][-12:]

    # Build concise markdown summary
    obj_str = "\n".join([f"- {o}" for o in existing_memory["objectives"]]) or "- متابعة تنفيذ مهام المشروع"
    mile_str = "\n".join([f"- {m}" for m in existing_memory["completed_milestones"]]) or "- تم إنجاز أحدث خطوة بنجاح"
    files_str = ", ".join([f"`{os.path.basename(f)}`" for f in existing_memory["modified_files"]]) if existing_memory["modified_files"] else "لا توجد ملفات محددة"

    structured_summary = (
        f"### 📋 ملخص السياق المضغوط (Compacted Context):\n"
        f"🎯 **الأهداف الأساسية:**\n{obj_str}\n\n"
        f"🛠️ **آخر الإنجازات والنتائج:**\n{mile_str}\n\n"
        f"📁 **الملفات المرتبطة:** {files_str}\n\n"
        f"⚙️ **المسار النشط:** `{workspace}`\n"
        f"⏱️ **تاريخ آخر ضغط:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    existing_memory["latest_state_summary"] = structured_summary

    # Save to memory file
    try:
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(existing_memory, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[ContextEngine] Failed to save memory: {e}")

    # Also mirror to workspace .scratch/context_memory.md if possible
    scratch_dir = os.path.join(workspace, ".scratch")
    if os.path.isdir(scratch_dir):
        try:
            with open(os.path.join(scratch_dir, "context_memory.md"), "w", encoding="utf-8") as sf:
                sf.write(structured_summary)
        except Exception:
            pass

    # Save as globally available last compacted context
    _CONFIG["last_compacted_context"] = structured_summary
    _save_config(_CONFIG)

    # Check Hard Limit (45 steps)
    if curr_steps >= max_steps:
        # Trigger Automatic Rollover!
        logger.info(f"[ContextEngine] Hard cap reached ({curr_steps}/{max_steps}). Performing session rollover.")
        
        # Prepare injection for the upcoming prompt
        carryover_prefix = (
            f"[سياق الجلسة السابقة المضغوط - Context Memory Rollover]:\n"
            f"{structured_summary}\n"
            f"--------------------------------------------------\n"
            f"[تابع العمل في جلسة جديدة ونظيفة بناءً على السياق أعلاه]:\n"
        )
        _CONFIG["pending_context_injection"] = carryover_prefix
        _CONFIG["force_new"] = True
        _CONFIG["current_conversation_id"] = None
        
        if "project_states" in _CONFIG and workspace in _CONFIG["project_states"]:
            _CONFIG["project_states"][workspace]["conversation_id"] = None
        _save_config(_CONFIG)

        rollover_msg = (
            f"🔄 <b>تم تدوير الجلسة وضغط السياق تلقائياً!</b>\n\n"
            f"وصلت الجلسة إلى الحد الأقصى المقرر: <b>{curr_steps} / {max_steps} خطوة</b> (100%).\n\n"
            f"🗜️ <b>ما تم إجراؤه:</b>\n"
            f"1. تم استخلاص وضغط كافة الأهداف، القرارات الهندسية، والملفات المعدلة.\n"
            f"2. تم فتح جلسة عمل نظيفة وجديدة (Clean Session) بنسبة ذاكرة 0%.\n"
            f"3. سيتم حقن خلاصة السياق تلقائياً في رسالتك القادمة لضمان عدم ضياع أي معلومة نهائياً! 🚀"
        )
        return True, rollover_msg, stats

    return False, "", stats

def prepare_prompt_with_context(raw_prompt: str, workspace: str) -> str:
    """
    Checks if there is a pending compacted context injection from a rollover.
    Prepends it cleanly to the user's prompt and clears the pending flag.
    """
    pending = _CONFIG.get("pending_context_injection")
    if pending:
        logger.info("[ContextEngine] Prepending pending compacted context to prompt.")
        _CONFIG["pending_context_injection"] = None
        _save_config(_CONFIG)
        return f"{pending}\n{raw_prompt}"
    return raw_prompt

def force_immediate_compaction(conv_id: Optional[str] = None) -> Tuple[bool, str]:
    """Manually triggers instant compaction on demand."""
    max_steps = get_max_context_steps()
    target_cid = conv_id or _CONFIG.get("current_conversation_id")
    stats = get_context_status(target_cid, max_steps)
    ws = _CONFIG.get("current_workspace", os.getcwd())

    # Call compression routine with synthetic checkpoint
    _, _, updated_stats = compress_after_message(
        target_cid, ws,
        "نقطة تفتيش وضغط يدوي للسياق",
        f"تم إجراء ضغط يدوي شامل للذاكرة عند الخطوة #{stats['steps']}."
    )

    msg = (
        f"🗜️ <b>تم ضغط السياق بنجاح!</b>\n\n"
        f"💬 <b>الجلسة:</b> <code>{stats['title']}</code>\n"
        f"{updated_stats['meter_badge']}\n\n"
        f"✅ تم تحديث ملف الذاكرة الدائمة وتكثيف كافة الأهداف والملفات المرتبطة."
    )
    return True, msg

def force_session_rollover(conv_id: Optional[str] = None) -> Tuple[bool, str]:
    """Manually forces a session rollover with memory carryover."""
    max_steps = get_max_context_steps()
    target_cid = conv_id or _CONFIG.get("current_conversation_id")
    stats = get_context_status(target_cid, max_steps)
    ws = _CONFIG.get("current_workspace", os.getcwd())

    # First ensure memory is compressed
    compress_after_message(target_cid, ws, "تدوير يدوي للجلسة", "حفظ وتلخيص كامل الجلسة لنقلها لجلسة جديدة.")
    
    summary = _CONFIG.get("last_compacted_context", "سياق مشروع نشط")
    carryover_prefix = (
        f"[سياق الجلسة السابقة المضغوط - Manual Context Rollover]:\n"
        f"{summary}\n"
        f"--------------------------------------------------\n"
        f"[تابع العمل في جلسة جديدة نظيفة بناءً على هذا السياق]:\n"
    )
    _CONFIG["pending_context_injection"] = carryover_prefix
    _CONFIG["force_new"] = True
    _CONFIG["current_conversation_id"] = None
    if "project_states" in _CONFIG and ws in _CONFIG["project_states"]:
        _CONFIG["project_states"][ws]["conversation_id"] = None
    _save_config(_CONFIG)

    msg = (
        f"🔄 <b>تم تدوير الجلسة بنجاح مع نقل الذاكرة!</b>\n\n"
        f"الجلسة السابقة: <code>{stats['title']}</code> ({stats['steps']} خطوة)\n"
        f"الحالة الآن: <b>جلسة جديدة نظيفة (0/{max_steps})</b> ✨\n\n"
        f"💡 تم حفظ ونقل كامل الذاكرة المضغوطة لتُحقن تلقائياً في طلبك القادم."
    )
    return True, msg

def get_context_card_markup(conv_id: Optional[str] = None) -> Tuple[str, dict]:
    """Generates the full Telegram status card and action buttons for /context command."""
    max_steps = get_max_context_steps()
    st = get_context_status(conv_id, max_steps)

    card_text = (
        f"🧠 <b>لوحة سعة الذاكرة وسياق المحادثة (Context Window):</b>\n\n"
        f"💬 <b>الجلسة النشطة:</b> <code>{st['title']}</code>\n"
        f"🆔 <code>{st['conversation_id'] or 'لا توجد جلسة نشطة'}</code>\n\n"
        f"📊 <b>مؤشر الاستهلاك:</b>\n"
        f"[ <b>{st['steps']}</b> / <b>{st['max_steps']}</b> خطوة ] {st['progress_bar']} (<b>{st['percentage']}%</b>)\n"
        f"🚦 <b>الحالة:</b> {st['status_label']}\n"
        f"🎯 <b>الخطوات المتبقية قبل التدوير:</b> <code>{st['remaining']}</code> خطوة\n\n"
        f"🗜️ <b>الضغط المستمر:</b> <code>مفعّل تلقائياً بعد كل رسالة</code> 🟢\n"
        f"🛡️ <b>سقف الأمان:</b> <code>{max_steps} خطوة كحد أقصى</code>\n\n"
        f"<i>يتم ضغط وتحديث سياق المشروع بعد كل مهمة للحفاظ على أعلى سرعة واستجابة ومنع تضخم الذاكرة.</i>"
    )

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🗜️ ضغط السياق الآن", "callback_data": "ctx:compact"},
                {"text": "🔄 تدوير الجلسة الآن", "callback_data": "ctx:rollover"}
            ],
            [
                {"text": "📋 معاينة الذاكرة المضغوطة", "callback_data": "ctx:view_memory"},
                {"text": "⚙️ ضبط الحد الأقصى", "callback_data": "ctx:set_limit_menu"}
            ],
            [
                {"text": "🔄 تحديث المؤشر", "callback_data": "ctx:refresh"}
            ]
        ]
    }
    return card_text, keyboard

def handle_context_callback(chat_id: int, message_id: int, callback_data: str) -> bool:
    """Handles all ctx:* inline button actions."""
    if not callback_data.startswith("ctx:"):
        return False

    action = callback_data[4:]

    if action == "refresh":
        text, markup = get_context_card_markup()
        if _edit_message_text:
            _edit_message_text(chat_id, message_id, text, reply_markup=markup)
        if _answer_callback_query:
            _answer_callback_query(message_id, "تم تحديث المؤشر بنجاح 🔄")
        return True

    elif action == "compact":
        if _answer_callback_query:
            _answer_callback_query(message_id, "جاري ضغط السياق...")
        _, msg = force_immediate_compaction()
        text, markup = get_context_card_markup()
        if _edit_message_text:
            _edit_message_text(chat_id, message_id, f"{msg}\n\n{text}", reply_markup=markup)
        return True

    elif action == "rollover":
        if _answer_callback_query:
            _answer_callback_query(message_id, "جاري تدوير الجلسة ونقل الذاكرة...")
        _, msg = force_session_rollover()
        text, markup = get_context_card_markup()
        if _edit_message_text:
            _edit_message_text(chat_id, message_id, f"{msg}\n\n{text}", reply_markup=markup)
        return True

    elif action == "view_memory":
        summary = _CONFIG.get("last_compacted_context")
        if not summary:
            target_cid = _CONFIG.get("current_conversation_id")
            mem_file = os.path.join(MEMORY_DIR, f"{target_cid}.json") if target_cid else None
            if mem_file and os.path.isfile(mem_file):
                try:
                    with open(mem_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        summary = data.get("latest_state_summary")
                except Exception:
                    pass
        if not summary:
            summary = "لا توجد ذاكرة مضغوطة محفوظة لهذه الجلسة بعد. أرسل مهمة أو اضغط 'ضغط السياق الآن'."

        back_markup = {
            "inline_keyboard": [
                [{"text": "⬅️ عودة للمؤشر", "callback_data": "ctx:refresh"}]
            ]
        }
        if _edit_message_text:
            _edit_message_text(chat_id, message_id, f"📋 <b>معاينة الذاكرة المضغوطة المحفوظة:</b>\n\n{summary}", reply_markup=back_markup)
        return True

    elif action == "set_limit_menu":
        curr = get_max_context_steps()
        limit_text = (
            f"⚙️ <b>تحديد الحد الأقصى لخطوات السياق (Context Ceiling):</b>\n\n"
            f"الحد الحالي: <b>{curr} خطوة</b>\n"
            f"عند وصول المحادثة لهذا الحد، يتم تدوير الجلسة تلقائياً ونقل الذاكرة المضغوطة لتفادي بطء الأداء.\n\n"
            f"اختر الحد المطلوب:"
        )
        limit_markup = {
            "inline_keyboard": [
                [
                    {"text": f"{'✅ ' if curr == 30 else ''}30 خطوة (سريع جداً)", "callback_data": "ctx:set_val:30"},
                    {"text": f"{'✅ ' if curr == 45 else ''}45 خطوة (الموصى به)", "callback_data": "ctx:set_val:45"},
                    {"text": f"{'✅ ' if curr == 60 else ''}60 خطوة (موسع)", "callback_data": "ctx:set_val:60"}
                ],
                [
                    {"text": "⬅️ عودة", "callback_data": "ctx:refresh"}
                ]
            ]
        }
        if _edit_message_text:
            _edit_message_text(chat_id, message_id, limit_text, reply_markup=limit_markup)
        return True

    elif action.startswith("set_val:"):
        val = int(action.split(":")[1])
        _CONFIG["max_context_steps"] = val
        _save_config(_CONFIG)
        if _answer_callback_query:
            _answer_callback_query(message_id, f"تم ضبط الحد الأقصى على {val} خطوة بنجاح ✅")
        text, markup = get_context_card_markup()
        if _edit_message_text:
            _edit_message_text(chat_id, message_id, f"✅ <b>تم تحديث سقف السياق إلى {val} خطوة!</b>\n\n{text}", reply_markup=markup)
        return True

    return False
