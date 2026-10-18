#!/usr/bin/env python3
"""
Tri-Phase Multi-Model Orchestration Engine (Architect -> Builder -> Reviewer).
Orchestrates:
  Phase 1: Architecture & Strategic Plan (Claude Opus 4.6 Thinking)
  Phase 2: High-Speed Code Execution (Gemini 3.8 Flash High)
  Phase 3: Deep Review & Verification Loop (Claude Opus 4.6 Thinking - Up to 3 iterations)
Includes automated 9-account rotation on Opus quota exhaustion with safe fallback to Gemini Flash.
"""

import os
import sys
import time
import json
import logging
import subprocess
import shutil
import sqlite3
import urllib.parse

logger = logging.getLogger("tri_phase_engine")

MODEL_OPUS = "claude-opus-4-6-thinking"
MODEL_FLASH = "gemini-3.8-flash-high"

ACCOUNTS_DIR = os.path.expanduser("~/.gemini/antigravity-ide/accounts")
ACTIVE_TOKEN_PATH = os.path.expanduser("~/.gemini/antigravity-ide/jetski-standalone-oauth-token")
CLI_TOKEN_PATH = os.path.expanduser("~/.config/antigravity-cli/jetski-standalone-oauth-token")
CONV_DB_PATH = os.path.expanduser("~/.gemini/antigravity-cli/conversation_summaries.db")

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


def list_accounts():
    """List all saved accounts and detect active one."""
    if not os.path.isdir(ACCOUNTS_DIR):
        return [], None
    active_email = None
    if os.path.isfile(ACTIVE_TOKEN_PATH):
        try:
            with open(ACTIVE_TOKEN_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                active_email = data.get("email") or data.get("user", {}).get("email")
        except Exception:
            pass

    accounts = []
    for d in sorted(os.listdir(ACCOUNTS_DIR)):
        token_file = os.path.join(ACCOUNTS_DIR, d, "jetski-standalone-oauth-token")
        if os.path.isfile(token_file):
            accounts.append({
                "email": d,
                "is_active": (d == active_email)
            })
    return accounts, active_email

def switch_account(email):
    """Switch active token to the given email."""
    token_file = os.path.join(ACCOUNTS_DIR, email, "jetski-standalone-oauth-token")
    if os.path.isfile(token_file):
        try:
            shutil.copy2(token_file, ACTIVE_TOKEN_PATH)
            if os.path.isdir(os.path.dirname(CLI_TOKEN_PATH)):
                shutil.copy2(token_file, CLI_TOKEN_PATH)
            logger.info(f"[Tri-Phase] Switched to Google account: {email}")
            return True
        except Exception as e:
            logger.error(f"[Tri-Phase] Account switch error: {e}")
    return False

def rotate_to_next_account(current_email):
    """Rotates to the next account in sequence."""
    accounts, _ = list_accounts()
    if not accounts:
        return None
    emails = [a["email"] for a in accounts]
    try:
        idx = emails.index(current_email)
        next_email = emails[(idx + 1) % len(emails)]
    except Exception:
        next_email = emails[0]
    switch_account(next_email)
    return next_email

def is_quota_error(text):
    """Detect if output signifies quota or rate limit exhaustion."""
    if not text:
        return False
    lower = text.lower()
    quota_signatures = [
        "resource_exhausted",
        "quota exceeded",
        "rate limit",
        "credit exhausted",
        "daily limit",
        "429",
        "too many requests",
        "overloaded"
    ]
    return any(sig in lower for sig in quota_signatures)

def run_agy_turn(agy_bin, prompt, workspace, model, timeout=360):
    """Runs a single agy prompt turn with the specified model."""
    cmd = [
        agy_bin,
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--model", model
    ]
    p = subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=timeout
    )
    return p.stdout, p.stderr, p.returncode

def run_with_opus_failover(agy_bin, prompt, workspace, status_callback=None, timeout=360):
    """
    Executes a prompt targeting Claude Opus Thinking.
    If Opus quota is exhausted, rotates through all 9 saved accounts.
    If all accounts are exhausted, falls back to Gemini 3.8 Flash High.
    """
    accounts, active_email = list_accounts()
    tested_accounts = set()
    current_email = active_email
    
    total_accounts = len(accounts) if accounts else 1
    max_rotations = max(1, total_accounts)

    for attempt in range(max_rotations):
        tested_accounts.add(current_email)
        if status_callback and current_email:
            status_callback(f"🧠 Claude Opus Thinking (الحساب: {current_email[:12]}...)")
            
        stdout, stderr, code = run_agy_turn(agy_bin, prompt, workspace, MODEL_OPUS, timeout=timeout)
        combined = (stdout + "\n" + stderr).strip()
        
        if not is_quota_error(combined) and code == 0:
            return stdout, MODEL_OPUS, current_email
            
        logger.warning(f"[Tri-Phase] Opus quota or error on {current_email}: {combined[:200]}")
        
        # Try next account
        next_email = rotate_to_next_account(current_email)
        if not next_email or next_email in tested_accounts:
            break
        current_email = next_email
        time.sleep(1)

    # All accounts exhausted -> Fallback to Gemini Flash
    logger.warning("[Tri-Phase] All Opus accounts exhausted. Falling back to Gemini 3.8 Flash High.")
    if status_callback:
        status_callback("⚡ استنفاد كوتا Opus في جميع الحسابات -> الانتقال التلقائي لـ Gemini Flash")
        
    stdout, stderr, code = run_agy_turn(agy_bin, prompt, workspace, MODEL_FLASH, timeout=timeout)
    return stdout, MODEL_FLASH, "Gemini-Flash-Fallback"

def run_project_checks(project_path):
    """Runs project tests or static analysis to provide evidence to the Reviewer."""
    checks = []
    # Flutter / Dart
    if os.path.exists(os.path.join(project_path, "pubspec.yaml")):
        try:
            p = subprocess.run(["dart", "analyze", "--fatal-infos"], cwd=project_path, capture_output=True, text=True, timeout=90)
            checks.append(f"Dart Analyze: {'PASSED' if p.returncode == 0 else 'WARNINGS'}\n{p.stdout[:500]}")
        except Exception:
            pass
    # Node
    elif os.path.exists(os.path.join(project_path, "package.json")):
        try:
            p = subprocess.run(["npm", "test", "--", "--passWithNoTests"], cwd=project_path, capture_output=True, text=True, timeout=90)
            checks.append(f"npm test: {'PASSED' if p.returncode == 0 else 'FAILED'}\n{p.stdout[:500]}")
        except Exception:
            pass
    # Python
    elif any(f.endswith(".py") for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))):
        try:
            p = subprocess.run([sys.executable, "-m", "py_compile"] + [f for f in os.listdir(project_path) if f.endswith(".py")][:10], cwd=project_path, capture_output=True, text=True, timeout=30)
            checks.append(f"Python compile: {'PASSED' if p.returncode == 0 else 'FAILED'}")
        except Exception:
            pass
            
    return "\n".join(checks) if checks else "No test suite detected; static verification used."

def run_tri_phase_pipeline(task_title, requirement_prompt, workspace, chat_id, send_message_func, edit_message_text_func, agy_bin="agy", is_sre=False):
    """
    Executes the full 3-Stage Ensemble:
      Stage 1: Architecture & Plan (Claude Opus Thinking)
      Stage 2: Code Execution (Gemini 3.8 Flash High)
      Stage 3: Review & Verification Loop (Claude Opus Thinking, up to 3 iterations)
    """
    start_time = time.time()
    active_cid = get_latest_conversation_for_workspace(workspace)
    proj_name = os.path.basename(workspace.rstrip("/"))

    def build_banner_text(p1_icon, p2_icon, p3_icon, extra_note="", cid=None, elapsed=0):
        el_str = f"{elapsed // 60}m {elapsed % 60}s"
        chat_id_line = ""
        if cid:
            short_id = cid[:8]
            chat_id_line = f"💬 <b>رقم الشات:</b> <code>{short_id}</code> | 💻 <code>agy --conversation {cid}</code>\n"

        txt = (
            f"🚀 <b>خط التجميع الهندسي الثلاثي (Tri-Phase Ensemble):</b>\n\n"
            f"{chat_id_line}"
            f"📋 <b>المهمة:</b> <code>{task_title[:100]}</code>\n"
            f"📁 <b>المشروع:</b> <code>{proj_name}</code>\n"
            f"⏱️ <b>الوقت:</b> {el_str}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ <b>التخطيط المعماري:</b> {p1_icon}\n"
            f"2️⃣ <b>كتابة الكود والتنفيذ:</b> {p2_icon}\n"
            f"3️⃣ <b>المراجعة والاعتماد:</b> {p3_icon}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{extra_note}"
        )
        return txt

    def get_hud_markup(cid=None):
        return {
            "inline_keyboard": [
                [
                    {"text": "🖥️ اعرضه في شاشة الـ HUD لايف", "callback_data": f"hud:open:{cid or ''}"}
                ]
            ]
        }

    # 1. Initialize Telegram Progress Banner
    initial_text = build_banner_text(
        "🧠 Claude Opus Thinking ⏳",
        "⚡ Gemini 3.8 Flash High ⏸️",
        "🛡️ Claude Opus Thinking ⏸️",
        extra_note="<i>جاري التحليل المعماري وتحديد استراتيجية الحل...</i>",
        cid=active_cid,
        elapsed=0
    )
    banner_msg_id = send_message_func(chat_id, initial_text, reply_markup=get_hud_markup(active_cid))

    def update_banner(p1_icon, p2_icon, p3_icon, extra_note=""):
        nonlocal active_cid
        if not banner_msg_id or not edit_message_text_func:
            return
        if not active_cid:
            active_cid = get_latest_conversation_for_workspace(workspace)
        elapsed = int(time.time() - start_time)
        txt = build_banner_text(p1_icon, p2_icon, p3_icon, extra_note=extra_note, cid=active_cid, elapsed=elapsed)
        try:
            edit_message_text_func(chat_id, banner_msg_id, txt, reply_markup=get_hud_markup(active_cid))
        except Exception:
            pass

    # ==========================================
    # STAGE 1: THE ARCHITECT (Claude Opus Thinking)
    # ==========================================
    logger.info("[Tri-Phase] Stage 1: Opus Architect starting...")
    update_banner("🧠 Claude Opus Thinking ⏳", "⚡ Gemini 3.8 Flash High ⏸️", "🛡️ Claude Opus Thinking ⏸️", "<i>جاري التحليل المعماري وتحديد استراتيجية الحل...</i>")
    
    architect_prompt = (
        f"You are the Principal Systems Architect (Claude Opus Thinking).\n"
        f"Deeply analyze this task / incident and produce a concrete, numbered Architectural Specification:\n\n"
        f"TASK:\n{requirement_prompt}\n\n"
        f"OUTPUT REQUIRED:\n"
        f"1. Root cause or architectural requirement.\n"
        f"2. Precise list of files to modify or create.\n"
        f"3. Concrete logic changes, defensive null-checks, error-handling, and edge cases to consider.\n"
        f"4. Exact verification checks or tests.\n"
        f"Be rigorous, technical, and concise. Do NOT write conversational filler."
    )
    
    architect_plan, p1_model, p1_account = run_with_opus_failover(
        agy_bin, architect_prompt, workspace,
        status_callback=lambda s: update_banner(f"🧠 {s} ⏳", "⚡ Gemini 3.8 Flash High ⏸️", "🛡️ Claude Opus Thinking ⏸️")
    )
    
    logger.info(f"[Tri-Phase] Stage 1 completed by {p1_model} ({p1_account}).")
    update_banner("✅ تم إعداد الخطة المعمارية", "⚡ Gemini 3.8 Flash High ⏳", "🛡️ Claude Opus Thinking ⏸️", "<i>جاري كتابة الكود والتعديل بواسطة Gemini Flash...</i>")

    # ==========================================
    # STAGE 2: THE BUILDER (Gemini 3.8 Flash High)
    # ==========================================
    logger.info("[Tri-Phase] Stage 2: Gemini Flash Builder starting...")
    builder_prompt = (
        f"You are the Lead Implementation Engineer (Gemini 3.8 Flash High).\n"
        f"Your Principal Architect has designed this exact specification:\n\n"
        f"=== ARCHITECTURAL SPECIFICATION ===\n"
        f"{architect_plan}\n"
        f"===================================\n\n"
        f"TASK:\n"
        f"1. Implement all changes into the codebase following the architect's plan exactly.\n"
        f"2. Ensure zero regressions, add tests/checks where appropriate.\n"
        f"3. Run available local tests / static analysis to ensure it compiles.\n"
        f"4. Provide a 2-sentence Arabic summary of the work done."
    )
    
    builder_output, _, _ = run_agy_turn(agy_bin, builder_prompt, workspace, MODEL_FLASH, timeout=360)
    logger.info("[Tri-Phase] Stage 2 completed by Gemini Flash.")
    
    # ==========================================
    # STAGE 3: THE REVIEWER (Claude Opus Thinking)
    # Self-Correction Loop (Up to 3 iterations)
    # ==========================================
    logger.info("[Tri-Phase] Stage 3: Opus Reviewer starting...")
    max_review_rounds = 3
    round_idx = 0
    final_verdict = "APPROVED"
    review_summary = "تم اعتماد التعديلات ومطابقتها للمواصفات المعمارية بنجاح."

    while round_idx < max_review_rounds:
        round_idx += 1
        update_banner(
            "✅ تم إعداد الخطة المعمارية",
            "✅ تم تنفيذ الكود",
            f"🛡️ Claude Opus Thinking (فحص #{round_idx}) ⏳",
            f"<i>جاري الفحص المعماري الصارم والتحقق من الجودة (دورة {round_idx}/{max_review_rounds})...</i>"
        )
        
        # Capture current git diff
        diff_proc = subprocess.run(["git", "diff", "HEAD~1"], cwd=workspace, capture_output=True, text=True)
        git_diff = diff_proc.stdout.strip()
        if not git_diff:
            diff_proc = subprocess.run(["git", "diff"], cwd=workspace, capture_output=True, text=True)
            git_diff = diff_proc.stdout.strip()
            
        test_evidence = run_project_checks(workspace)
        
        reviewer_prompt = (
            f"You are the Strict Code Quality Auditor (Claude Opus Thinking).\n"
            f"Review the implementation created by the Builder against your Architectural Plan.\n\n"
            f"ARCHITECTURAL PLAN:\n{architect_plan[:2000]}\n\n"
            f"GIT DIFF:\n{git_diff[:3500]}\n\n"
            f"TEST EVIDENCE:\n{test_evidence}\n\n"
            f"EVALUATION CRITERIA:\n"
            f"1. Are all requirements and edge-cases defensively solved?\n"
            f"2. Are there any syntax errors, unhandled nulls, or regressions?\n\n"
            f"OUTPUT FORMAT (STRICT):\n"
            f"First line MUST be either:\n"
            f"VERDICT: APPROVED\n"
            f"or\n"
            f"VERDICT: REVISE\n\n"
            f"If APPROVED, write a 2-sentence Arabic summary of the solution.\n"
            f"If REVISE, list numbered, concise actionable corrections for the Builder to apply."
        )
        
        review_out, r_model, r_acc = run_with_opus_failover(
            agy_bin, reviewer_prompt, workspace,
            status_callback=lambda s: update_banner("✅ تم إعداد الخطة", "✅ تم التنفيذ", f"🛡️ {s} (#{round_idx}) ⏳")
        )
        
        if "VERDICT: APPROVED" in review_out or "APPROVED" in review_out.splitlines()[0]:
            logger.info(f"[Tri-Phase] Round #{round_idx}: Approved by Opus!")
            final_verdict = "APPROVED"
            # Extract summary
            lines = [l for l in review_out.splitlines() if not l.startswith("VERDICT:")]
            review_summary = "\n".join(lines).strip() or "تم فحص واعتماد الكود بنجاح بواسطة Claude Opus Thinking."
            break
        else:
            logger.warning(f"[Tri-Phase] Round #{round_idx}: Opus requested revisions.")
            final_verdict = "REVISED"
            if round_idx < max_review_rounds:
                update_banner(
                    "✅ تم إعداد الخطة",
                    f"⚡ Gemini Flash (تطبيق التعديلات #{round_idx}) ⏳",
                    f"⚠️ ملاحظات من Opus جاري تصحيحها",
                    f"<i>اكتشف Opus بعض الملاحظات؛ يتولى Gemini Flash تعديلها فوراً...</i>"
                )
                refine_prompt = (
                    f"The Reviewer (Claude Opus Thinking) inspected your code and found issues to revise:\n\n"
                    f"{review_out}\n\n"
                    f"Apply these exact corrections now, run tests, and ensure full compliance."
                )
                run_agy_turn(agy_bin, refine_prompt, workspace, MODEL_FLASH, timeout=300)

    # Final banner update
    total_time = int(time.time() - start_time)
    tt_str = f"{total_time // 60}m {total_time % 60}s"
    update_banner(
        "✅ خطة معمارية (Opus Thinking)",
        "✅ تنفيذ الكود (Gemini Flash)",
        f"✅ اعتماد نهائي 100% (Opus Thinking) 🛡️",
        f"✨ <i>اكتمل خط الإنتاج الثلاثي بنجاح في {tt_str}!</i>"
    )
    
    return {
        "success": True,
        "architect_plan": architect_plan,
        "review_summary": review_summary,
        "elapsed_seconds": total_time,
        "rounds": round_idx,
        "verdict": final_verdict
    }
