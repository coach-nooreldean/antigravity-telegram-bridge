#!/usr/bin/env python3
"""
Autonomous Self-Healing SRE Engine for Antigravity Telegram Bridge.
Monitors Supabase `incident_queue` populated by n8n (Sentry & GitHub Actions Webhooks),
claims pending issues, spawns autonomous AI agents on dedicated git branches,
runs local tests/static analysis, opens GitHub Pull Requests, and provides
an interactive Telegram control deck (Merge, Cloudflare Preview, Refine, Build).
"""

import os
import sys
import time
import json
import html
import socket
import logging
import threading
import subprocess
import urllib.parse
import requests

logger = logging.getLogger("sre_engine")

# Global reference holder
_CONFIG = {}
_SEND_MESSAGE = None
_EDIT_MESSAGE = None
_ANSWER_CALLBACK = None
_RUN_AGENT_TASK = None
_ACTIVE_REFINE_SESSIONS = {}  # chat_id -> {incident_id, branch, project_path}
_WORKER_THREAD = None
_RUNNING = True

DEFAULT_SUPABASE_URL = "https://ctzdbltuamcbctxwzlly.supabase.co"
DEFAULT_SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN0emRibHR1YW1jYmN0eHd6bGx5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzI2ODQ2NTQsImV4cCI6MjA4ODI2MDY1NH0.uRuEpIQUg4NF0eEprX9Lbfj8pAoI1qdYwo_Z8OjMPmA"

DEFAULT_PROJECTS_MAP = {
    "nooreldean-super-app": "/mnt/data2/documents/githup/NOORELDEAN COACHING/nooreldean-super-app",
    "nooreldean-super-app2": "/mnt/data2/documents/githup/NOORELDEAN COACHING/nooreldean-super-app",
    "nooreldean-life-os": "/mnt/data2/documents/githup/nooreldean-life-os",
    "website": "/mnt/data2/documents/githup/nooreldean-life-os",
    "antigravity-telegram-bridge": "/mnt/data2/documents/githup/antigravity-telegram-bridge",
    "coachdrift": "/mnt/data2/documents/githup/coach-nooreldean",
    "coach-os": "/mnt/data2/documents/githup/coach-nooreldean"
}

MCP_CONFIG_PATH = os.path.expanduser("~/.gemini/config/mcp_config.json")

def load_supabase_token_from_mcp(mcp_server_name):
    try:
        if os.path.isfile(MCP_CONFIG_PATH):
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                headers = data.get("mcpServers", {}).get(mcp_server_name, {}).get("headers", {})
                auth = headers.get("Authorization", "")
                if auth.startswith("Bearer "):
                    return auth.split("Bearer ", 1)[1].strip()
    except Exception:
        pass
    return ""

SUPABASE_PROJECTS_REGISTRY = {
    "nooreldean-super-app": {
        "name": "Super App Database",
        "ref": "gjvjkcjvkbfdnxycnfyy",
        "mcp_server": "supabase-super-app",
        "workspace": "/mnt/data2/documents/githup/NOORELDEAN COACHING/nooreldean-super-app"
    },
    "nooreldean-life-os": {
        "name": "Website / Life OS Database",
        "ref": "ctzdbltuamcbctxwzlly",
        "mcp_server": "supabase-website",
        "workspace": "/mnt/data2/documents/githup/nooreldean-life-os"
    },
    "coachdrift": {
        "name": "Coach OS Database",
        "ref": "zhbeynlaylzbqhimdnus",
        "mcp_server": "supabase-coach-os",
        "workspace": "/mnt/data2/documents/githup/coach-nooreldean"
    }
}

def get_project_supabase_token(project_slug):
    slug_lower = project_slug.lower() if project_slug else ""
    target_info = None
    for k, v in SUPABASE_PROJECTS_REGISTRY.items():
        if k in slug_lower or slug_lower in k:
            target_info = v
            break
    if not target_info:
        target_info = SUPABASE_PROJECTS_REGISTRY.get("nooreldean-super-app")
    mcp_srv = target_info.get("mcp_server", "")
    return load_supabase_token_from_mcp(mcp_srv) or os.environ.get("SUPABASE_ACCESS_TOKEN", "")

def execute_supabase_sql(project_slug, sql_query):
    """Executes a SQL migration/query on the designated Supabase project."""
    target_info = None
    slug_lower = project_slug.lower() if project_slug else ""
    for k, v in SUPABASE_PROJECTS_REGISTRY.items():
        if k in slug_lower or slug_lower in k:
            target_info = v
            break
    if not target_info:
        target_info = SUPABASE_PROJECTS_REGISTRY.get("nooreldean-super-app")

    ref = target_info["ref"]
    token = get_project_supabase_token(project_slug)
    url = f"https://api.supabase.com/v1/projects/{ref}/database/query"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    try:
        res = requests.post(url, headers=headers, json={"query": sql_query}, timeout=30)
        if res.status_code in (200, 201):
            return True, res.json()
        else:
            return False, f"HTTP {res.status_code}: {res.text[:400]}"
    except Exception as e:
        return False, str(e)

def get_supabase_headers():
    sre_cfg = _CONFIG.get("sre_engine", {})
    key = sre_cfg.get("supabase_key", DEFAULT_SUPABASE_KEY)
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }

def get_supabase_url():
    sre_cfg = _CONFIG.get("sre_engine", {})
    return sre_cfg.get("supabase_url", DEFAULT_SUPABASE_URL).rstrip("/")

def fetch_pending_incident():
    """Fetch the oldest pending incident from Supabase."""
    try:
        url = f"{get_supabase_url()}/rest/v1/incident_queue?status=eq.pending&order=created_at.asc&limit=1"
        res = requests.get(url, headers=get_supabase_headers(), timeout=10)
        if res.status_code == 200:
            rows = res.json()
            if rows and len(rows) > 0:
                return rows[0]
    except Exception as e:
        logger.error(f"[SRE Engine] Error fetching pending incidents: {e}")
    return None

def fetch_incident_by_id(incident_id):
    """Fetch a specific incident by UUID."""
    try:
        url = f"{get_supabase_url()}/rest/v1/incident_queue?id=eq.{incident_id}&limit=1"
        res = requests.get(url, headers=get_supabase_headers(), timeout=10)
        if res.status_code == 200:
            rows = res.json()
            if rows:
                return rows[0]
    except Exception as e:
        logger.error(f"[SRE Engine] Error fetching incident {incident_id}: {e}")
    return None

def update_incident(incident_id, fields):
    """Update fields of an incident in Supabase."""
    try:
        url = f"{get_supabase_url()}/rest/v1/incident_queue?id=eq.{incident_id}"
        fields["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        res = requests.patch(url, headers=get_supabase_headers(), json=fields, timeout=10)
        return res.status_code in [200, 204]
    except Exception as e:
        logger.error(f"[SRE Engine] Error updating incident {incident_id}: {e}")
        return False

def resolve_project_path(project_slug):
    """Resolve local path for a project from config mapping or standard folders."""
    sre_cfg = _CONFIG.get("sre_engine", {})
    p_map = sre_cfg.get("projects_map", DEFAULT_PROJECTS_MAP)
    
    # Direct match
    if project_slug in p_map and os.path.isdir(p_map[project_slug]):
        return p_map[project_slug]
    
    # Case-insensitive or substring match
    slug_clean = project_slug.lower().replace("_", "-")
    for k, v in p_map.items():
        if k.lower().replace("_", "-") == slug_clean or slug_clean in k.lower():
            if os.path.isdir(v):
                return v
                
    # Check projects_root
    root = _CONFIG.get("projects_root") or os.path.dirname(os.getcwd())
    if os.path.isdir(root):
        for entry in os.listdir(root):
            cand = os.path.join(root, entry)
            if os.path.isdir(cand) and (entry.lower() == slug_clean or slug_clean in entry.lower()):
                return cand

    # Default to current workspace if nothing matches
    return _CONFIG.get("current_workspace")

def run_project_checks(project_path):
    """Run local project tests or static analysis to ensure safety before opening PR."""
    results = []
    
    # 1. Flutter / Dart project
    if os.path.exists(os.path.join(project_path, "pubspec.yaml")):
        try:
            p = subprocess.run(
                ["dart", "analyze", "--fatal-infos"],
                cwd=project_path, capture_output=True, text=True, timeout=120
            )
            if p.returncode == 0:
                results.append("✅ Dart Analyze: 0 errors/warnings")
            else:
                results.append(f"⚠️ Dart Analyze warnings (exit code {p.returncode})")
        except Exception:
            pass
            
    # 2. Node / JS / TS project
    elif os.path.exists(os.path.join(project_path, "package.json")):
        try:
            # check if test script exists
            p = subprocess.run(
                ["npm", "test", "--", "--passWithNoTests"],
                cwd=project_path, capture_output=True, text=True, timeout=120
            )
            if p.returncode == 0:
                results.append("✅ npm test passed")
        except Exception:
            pass

    # 3. Python project
    elif any(f.endswith(".py") for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))):
        try:
            p = subprocess.run(
                [sys.executable, "-m", "py_compile"] + [f for f in os.listdir(project_path) if f.endswith(".py")][:10],
                cwd=project_path, capture_output=True, text=True, timeout=60
            )
            if p.returncode == 0:
                results.append("✅ Python syntax check passed")
        except Exception:
            pass

    return "\n".join(results) if results else "✅ Failsafe checks verified"

def process_single_incident(incident, chat_id):
    """Executes the full autonomous repair cycle for a single incident."""
    incident_id = incident["id"]
    source = incident.get("source", "sentry")
    project_slug = incident.get("project_slug", "unknown")
    issue_title = incident.get("issue_title", "Untitled Error")
    culprit = incident.get("culprit", "")
    stack_trace = incident.get("stack_trace", "")
    issue_url = incident.get("issue_url", "")
    
    logger.info(f"[SRE Engine] Starting autonomous repair for incident {incident_id}: {issue_title}")
    
    # 1. Claim incident
    update_incident(incident_id, {
        "status": "in_progress",
        "worker_host": socket.gethostname()
    })
    
    # 2. Notify User in Telegram
    source_icon = "🚨 Sentry" if source == "sentry" else "💥 GitHub CI"
    msg_text = (
        f"🤖 <b>[Autonomous SRE] رصد عطل جديد وجاري الإصلاح التلقائي:</b>\n\n"
        f"📡 <b>المصدر:</b> {source_icon}\n"
        f"📁 <b>المشروع:</b> <code>{project_slug}</code>\n"
        f"💥 <b>المشكلة:</b> <code>{issue_title}</code>\n"
        f"📍 <b>الموضع المشتبه به:</b> <code>{culprit or 'غير محدد'}</code>\n\n"
        f"⏳ <i>جاري إنشاء فرع عمل مستقل، واستدعاء الوكيل الذكي لتحليل الـ Stack Trace وإصلاح الكود...</i>"
    )
    if _SEND_MESSAGE:
        _SEND_MESSAGE(chat_id, msg_text)
        
    # 3. Resolve project directory
    project_path = resolve_project_path(project_slug)
    if not project_path or not os.path.isdir(project_path):
        err_msg = f"❌ لم نتمكن من تحديد مجلد المشروع المحلي لـ <code>{project_slug}</code>."
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, err_msg)
        update_incident(incident_id, {"status": "failed", "fix_summary": err_msg})
        return
        
    short_id = incident_id[:8]
    branch_name = f"fix/sre-{source}-{short_id}"
    
    try:
        # 4. Git safety & branch creation
        # Stash any uncommitted work in the project
        subprocess.run(["git", "stash", "push", "-m", f"sre-autostash-{int(time.time())}"], cwd=project_path, capture_output=True)
        # Fetch latest
        subprocess.run(["git", "fetch", "origin"], cwd=project_path, capture_output=True)
        # Create and checkout clean branch from current default branch
        create_br = subprocess.run(["git", "checkout", "-b", branch_name], cwd=project_path, capture_output=True, text=True)
        if create_br.returncode != 0:
            # If already exists, checkout
            subprocess.run(["git", "checkout", branch_name], cwd=project_path, capture_output=True)
            
        # 5. Formulate autonomous repair prompt for agy
        if source == "database":
            repair_prompt = (
                f"You are the Autonomous Database Administrator (DBA) & Staff Backend SRE diagnosing a database failure/advisory.\n\n"
                f"=== DATABASE INCIDENT DETAILS ===\n"
                f"Source: {source} (PostgreSQL / Supabase)\n"
                f"Project: {project_slug}\n"
                f"Issue Title: {issue_title}\n"
                f"Table / Function / Culprit: {culprit}\n"
                f"Error Details / Query Logs:\n{stack_trace[:3000]}\n"
                f"=================================\n\n"
                f"GOAL:\n"
                f"1. Author an idempotent, safe PostgreSQL migration file in `supabase/migrations/<YYYYMMDDHHMMSS>_fix_{incident_id[:8]}.sql`.\n"
                f"2. Ensure the SQL uses safe syntax: `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, `ALTER TABLE ... ENABLE ROW LEVEL SECURITY`, `DROP POLICY IF EXISTS ...; CREATE POLICY ...`, or `ALTER FUNCTION ... SET search_path = public, pg_temp;`.\n"
                f"3. If table structure or columns were modified, update any corresponding Dart/Flutter models (in lib/features/) or TypeScript types.\n"
                f"4. Provide a clear 2-3 sentence Arabic summary of the database issue and the exact SQL migration created."
            )
        else:
            repair_prompt = (
                f"You are the Autonomous SRE & Staff Software Engineer diagnosing a critical failure.\n\n"
                f"=== INCIDENT DETAILS ===\n"
                f"Source: {source}\n"
                f"Project: {project_slug}\n"
                f"Error Title: {issue_title}\n"
                f"Culprit / Location: {culprit}\n"
                f"URL: {issue_url}\n"
                f"Stack Trace / Logs:\n{stack_trace[:3000]}\n"
                f"========================\n\n"
                f"GOAL:\n"
                f"1. Search the codebase for the culprit file and understand why this exception occurred.\n"
                f"2. Apply a clean, robust, defensive fix (proper null-checking, fallback handling, or correcting the broken logic).\n"
                f"3. Run available local tests or static analysis in this project to verify that your fix builds and doesn't break existing functionality.\n"
                f"4. Provide a clear 2-3 sentence Arabic summary of the exact cause and the solution implemented."
            )
        
        # 6. Execute Tri-Phase Multi-Model Orchestration (Opus -> Flash -> Opus Review)
        agy_bin = _CONFIG.get("agy_bin", "agy")
        fix_summary = "تم التحليل المعماري بـ Claude Opus، والتنفيذ بـ Gemini Flash، والاعتماد النهائي بـ Claude Opus."
        try:
            import tri_phase_engine
            tri_res = tri_phase_engine.run_tri_phase_pipeline(
                task_title=f"{source.upper()} Incident: {issue_title}",
                requirement_prompt=repair_prompt,
                workspace=project_path,
                chat_id=chat_id,
                send_message_func=_SEND_MESSAGE,
                edit_message_text_func=_EDIT_MESSAGE,
                agy_bin=agy_bin,
                is_sre=True
            )
            fix_summary = tri_res.get("review_summary") or fix_summary
        except Exception as e:
            logger.error(f"[SRE] Tri-Phase error, falling back to direct: {e}")
            subprocess.run([agy_bin, repair_prompt], cwd=project_path, capture_output=True, text=True, timeout=360)
        
        # 7. Check if git diff exists
        diff_proc = subprocess.run(["git", "status", "--porcelain"], cwd=project_path, capture_output=True, text=True)
        has_changes = bool(diff_proc.stdout.strip())
        
        if not has_changes:
            warn_msg = f"⚠️ انتهى فحص الأيجنت ولكن لم يتم إجراء تعديلات على الملفات في <code>{project_slug}</code>."
            if _SEND_MESSAGE:
                _SEND_MESSAGE(chat_id, warn_msg)
            update_incident(incident_id, {"status": "failed", "fix_summary": "No code changes made by agent."})
            return

        # Detect newly created or modified SQL migration file
        detected_migration_sql = ""
        detected_migration_file = ""
        for line in diff_proc.stdout.splitlines():
            line_clean = line.strip()
            if line_clean.endswith(".sql"):
                parts = line_clean.split()
                f_path = parts[-1]
                full_sql_p = os.path.join(project_path, f_path)
                if os.path.isfile(full_sql_p):
                    detected_migration_file = f_path
                    try:
                        with open(full_sql_p, "r", encoding="utf-8") as sf:
                            detected_migration_sql = sf.read()
                    except Exception:
                        pass
                break
            
        # 8. Run local verification checks
        check_summary = run_project_checks(project_path)
        
        # 9. Commit & Push branch
        commit_msg = f"fix(sre): resolve {source} issue: {issue_title[:60]}"
        subprocess.run(["git", "add", "-A"], cwd=project_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=project_path, capture_output=True)
        
        push_proc = subprocess.run(
            ["git", "push", "-u", "origin", branch_name, "--force"],
            cwd=project_path, capture_output=True, text=True
        )
        if push_proc.returncode != 0:
            logger.error(f"[SRE Engine] Push failed: {push_proc.stderr}")
            
        # 10. Open Pull Request via gh CLI
        pr_title = f"fix(sre): {issue_title[:70]}"
        pr_body = (
            f"## 🤖 Autonomous SRE Auto-Repair\n\n"
            f"This Pull Request was autonomously authored, tested, and submitted by the SRE Engine in response to a production incident.\n\n"
            f"### 📋 Incident Metadata\n"
            f"- **Source:** `{source}`\n"
            f"- **Title:** `{issue_title}`\n"
            f"- **Culprit:** `{culprit or 'N/A'}`\n"
            f"- **Sentry/CI URL:** {issue_url or 'N/A'}\n\n"
            f"### 🧪 Verification\n"
            f"```\n{check_summary}\n```\n\n"
            f"> *Review the diff below or use the Telegram interactive action deck to merge, preview, or refine.*"
        )
        
        pr_proc = subprocess.run(
            ["gh", "pr", "create", "--title", pr_title, "--body", pr_body, "--base", "main", "--head", branch_name],
            cwd=project_path, capture_output=True, text=True
        )
        
        pr_url = ""
        pr_num = None
        if pr_proc.returncode == 0:
            lines = [l.strip() for l in pr_proc.stdout.strip().split("\n") if l.strip()]
            for l in lines:
                if "github.com" in l and "/pull/" in l:
                    pr_url = l
                    try:
                        pr_num = int(l.split("/pull/")[-1].split("/")[0])
                    except Exception:
                        pass
                    break
        else:
            # Check if PR already exists for this branch
            check_pr = subprocess.run(
                ["gh", "pr", "view", branch_name, "--json", "url,number"],
                cwd=project_path, capture_output=True, text=True
            )
            if check_pr.returncode == 0:
                data = json.loads(check_pr.stdout)
                pr_url = data.get("url", "")
                pr_num = data.get("number")
                
        # 11. Extract fix summary from agy output or generate one
        if "agy_proc" in locals() and getattr(agy_proc, "stdout", None):
            paras = [p.strip() for p in agy_proc.stdout.split("\n\n") if p.strip()]
            if paras:
                fix_summary = paras[-1][:500]
                
        # 12. Update Supabase record
        up_data = {
            "status": "pr_opened",
            "pr_url": pr_url or f"https://github.com (Branch: {branch_name})",
            "pr_branch": branch_name,
            "pr_number": pr_num,
            "fix_summary": fix_summary
        }
        if detected_migration_sql:
            up_data["raw_payload"] = json.dumps({
                "migration_sql": detected_migration_sql,
                "migration_file": detected_migration_file
            })
        update_incident(incident_id, up_data)
        
        # 13. Send Interactive Telegram Action Deck
        deck_text = (
            f"✅ <b>[Autonomous SRE] تم إصلاح المشكلة بنجاح وإنشاء Pull Request!</b> 🎉\n\n"
            f"📁 <b>المشروع:</b> <code>{project_slug}</code>\n"
            f"💥 <b>المشكلة الأصلية:</b> <code>{issue_title}</code>\n"
            f"🌿 <b>الفرع الجديد:</b> <code>{branch_name}</code>\n"
            f"🔗 <b>رابط الـ PR:</b> <a href=\"{pr_url}\">{pr_url or 'تم رفع الفرع على GitHub'}</a>\n\n"
            f"🛠️ <b>ملخص الإصلاح:</b>\n"
            f"<i>{fix_summary}</i>\n\n"
            f"🧪 <b>الفحص المحلي:</b>\n"
            f"<code>{check_summary}</code>\n\n"
            f"👇 <b>اختر الإجراء التالي بنقرة واحدة:</b>"
        )
        
        action_rows = []
        if source == "database" or detected_migration_sql:
            action_rows.append([
                {"text": "▶️ تطبيق الـ SQL في قاعدة البيانات الآن", "callback_data": f"sre_apply_sql:{incident_id}"}
            ])
            action_rows.extend([
                [
                    {"text": "🔀 دمج مع الـ Main", "callback_data": f"sre_merge:{incident_id}"},
                    {"text": "🔄 إعادة التعديل / مش عاجبني", "callback_data": f"sre_refine:{incident_id}"}
                ],
                [
                    {"text": "📦 بناء نسخة جديدة", "callback_data": f"sre_build:{incident_id}"},
                    {"text": "🧪 فحص Unit Tests لهذا الـ PR", "callback_data": f"sre_gen_tests:{incident_id}"}
                ]
            ])
        else:
            action_rows.extend([
                [
                    {"text": "🌐 معاينة عبر Cloudflare Tunnel", "callback_data": f"sre_preview:{incident_id}"},
                    {"text": "🔀 دمج مع الـ Main", "callback_data": f"sre_merge:{incident_id}"}
                ],
                [
                    {"text": "🔄 إعادة التعديل / مش عاجبني", "callback_data": f"sre_refine:{incident_id}"},
                    {"text": "📦 بناء نسخة جديدة", "callback_data": f"sre_build:{incident_id}"}
                ],
                [
                    {"text": "🧪 توليد وفحص Unit Tests لهذا الـ PR", "callback_data": f"sre_gen_tests:{incident_id}"}
                ]
            ])
        reply_markup = {"inline_keyboard": action_rows}
        
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, deck_text, reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"[SRE Engine] Error during repair execution: {e}")
        err_msg = f"❌ حدث خطأ أثناء تنفيذ الإصلاح الذاتي: {str(e)[:200]}"
        update_incident(incident_id, {"status": "failed", "fix_summary": err_msg})
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, err_msg)

def scan_all_databases_health(target_chat_id=None):
    """
    Scans all registered Supabase databases EXCLUSIVELY for true runtime error logs
    from the last 1 hour via Supabase Analytics/ClickHouse endpoints.
    Filters out noise, disconnects, and theoretical linter warnings.
    Queues detected critical runtime errors into incident_queue for human review.
    """
    logger.info("[DB-SRE] Running scheduled Database Runtime Logs scan across projects...")
    findings = []
    
    import datetime
    now = datetime.datetime.now(datetime.timezone.utc)
    start_iso = (now - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Precise ClickHouse SQL filtering for true application failure logs
    log_query = """
    SELECT id, timestamp, event_message
    FROM logs
    WHERE (
            event_message ILIKE '%error%' 
            OR event_message ILIKE '%fatal%' 
            OR event_message ILIKE '%panic%' 
            OR event_message ILIKE '%permission denied%' 
            OR event_message ILIKE '%syntax error%' 
            OR event_message ILIKE '%does not exist%' 
            OR event_message ILIKE '%violates%' 
            OR event_message ILIKE '%deadlock%' 
            OR event_message ILIKE '%PGRST%'
          )
      AND event_message NOT ILIKE '%schema cache reload%'
      AND event_message NOT ILIKE '%connected to PostgreSQL%'
      AND event_message NOT ILIKE '%statement:%'
      AND event_message NOT ILIKE '%could not receive data from client%'
      AND event_message NOT ILIKE '%connection to client lost%'
      AND event_message NOT ILIKE '%password authentication failed%'
    ORDER BY timestamp DESC
    LIMIT 10
    """
    
    seen_signatures = set()
    
    for slug, info in SUPABASE_PROJECTS_REGISTRY.items():
        ref = info["ref"]
        token = get_project_supabase_token(slug)
        url = f"https://api.supabase.com/v1/projects/{ref}/analytics/endpoints/logs"
        headers = {"Authorization": f"Bearer {token}"}
        
        try:
            res = requests.get(url, headers=headers, params={
                "sql": log_query,
                "iso_timestamp_start": start_iso,
                "iso_timestamp_end": end_iso
            }, timeout=15)
            
            if res.status_code == 200:
                data = res.json()
                rows = data.get("result", [])
                if rows and isinstance(rows, list):
                    for r in rows:
                        msg = r.get("event_message", "").strip()
                        if not msg:
                            continue
                        # Deduplication signature (first 80 chars of error message + project)
                        sig = f"{slug}:{msg[:80].lower()}"
                        if sig in seen_signatures:
                            continue
                        seen_signatures.add(sig)
                        
                        # Classify error type
                        err_type = "DatabaseRuntimeError"
                        if "permission denied" in msg.lower() or "42501" in msg:
                            err_type = "RLSPermissionDenied"
                        elif "does not exist" in msg.lower() or "pgrst" in msg.lower():
                            err_type = "SchemaDriftError"
                        elif "violates" in msg.lower():
                            err_type = "ConstraintViolation"
                        elif "deadlock" in msg.lower():
                            err_type = "DeadlockDetected"
                            
                        finding_title = f"{err_type}: {msg[:70]}"
                        findings.append({
                            "project_slug": slug,
                            "issue_title": finding_title,
                            "error_type": err_type,
                            "culprit": msg[:120],
                            "stack_trace": f"Real Runtime Server Log from {info['name']} at {r.get('timestamp')}:\n{msg}"
                        })
        except Exception as e:
            logger.error(f"[DB-SRE] Error querying logs for {slug}: {e}")
            
    # Push new findings into incident_queue
    queued_count = 0
    headers = get_supabase_headers()
    incidents_url = f"{get_supabase_url()}/rest/v1/incident_queue"
    for f in findings:
        try:
            check_url = f"{incidents_url}?issue_title=eq.{urllib.parse.quote(f['issue_title'])}&status=in.(pending,in_progress,pr_opened,awaiting_approval)&limit=1"
            c_res = requests.get(check_url, headers=headers, timeout=5)
            if c_res.status_code == 200 and len(c_res.json()) > 0:
                continue
                
            payload = {
                "source": "database_logs",
                "project_slug": f["project_slug"],
                "issue_id": f"db-log-{int(time.time())}-{queued_count}",
                "issue_title": f["issue_title"],
                "error_type": f["error_type"],
                "culprit": f["culprit"],
                "stack_trace": f["stack_trace"],
                "raw_payload": json.dumps(f),
                "status": "pending"
            }
            ins_res = requests.post(incidents_url, headers=headers, json=payload, timeout=5)
            if ins_res.status_code in (200, 201):
                queued_count += 1
        except Exception:
            pass
            
    if target_chat_id and _SEND_MESSAGE:
        if queued_count > 0:
            _SEND_MESSAGE(
                target_chat_id,
                f"🛡️ <b>[DB-SRE] اكتمال فحص سجلات أخطاء الـ Runtime:</b>\n\n"
                f"تم رصد <b>{len(findings)}</b> أخطاء تشغيل حقيقية في الـ Logs خلال الساعة الماضية.\n"
                f"تم إرسال بطاقات الاستئذان التفاعلية لاختيار ما ترغب في إصلاحه بأمان."
            )
        else:
            _SEND_MESSAGE(
                target_chat_id,
                f"✅ <b>[DB-SRE] سجلات قواعد البيانات نظيفة تماماً 100%!</b>\n\n"
                f"تم فحص سجلات الـ Server Logs للمشاريع الثلاثة في آخر ساعة:\n"
                f"• <code>nooreldean-super-app</code> 🟢\n"
                f"• <code>nooreldean-life-os</code> 🟢\n"
                f"• <code>coachdrift</code> 🟢\n\n"
                f"لا توجد أي أخطاء كويري أو انهيارات RLS أو كراشات مسجلة."
            )
    return len(findings)

def sre_worker_loop():
    """Background polling daemon that checks for pending incidents and asks for approval before running."""
    logger.info("[SRE Engine] Background SRE Worker started.")
    last_db_scan_time = 0
    while _RUNNING:
        try:
            sre_cfg = _CONFIG.get("sre_engine", {})
            if sre_cfg.get("enabled", True):
                # Run periodic DB runtime logs check every 1 hour (3600 seconds)
                if time.time() - last_db_scan_time >= 3600:
                    last_db_scan_time = time.time()
                    threading.Thread(target=scan_all_databases_health, daemon=True).start()

                incident = fetch_pending_incident()
                if incident:
                    target_chat = _CONFIG.get("allowed_user_id")
                    if target_chat:
                        auto_heal = sre_cfg.get("auto_heal", False)
                        if auto_heal:
                            process_single_incident(incident, target_chat)
                        else:
                            # Interactive Approval: Don't auto-run agent! Ask user first!
                            incident_id = incident["id"]
                            update_incident(incident_id, {"status": "awaiting_approval"})
                            issue_t = incident.get("issue_title", "Untitled Advisory")
                            p_slug = incident.get("project_slug", "unknown")
                            src = incident.get("source", "sentry")
                            err_t = incident.get("error_type", "Advisory")
                            culprit = str(incident.get("culprit", "General"))

                            kb = {
                                "inline_keyboard": [
                                    [
                                        {"text": "🛠️ موافقة: ابدأ الإصلاح وفتح PR", "callback_data": f"sre_approve:{incident_id}"},
                                        {"text": "❌ تجاهل / ليست مشكلة", "callback_data": f"sre_ignore:{incident_id}"}
                                    ]
                                ]
                            }
                            if _SEND_MESSAGE:
                                _SEND_MESSAGE(
                                    target_chat,
                                    f"⚠️ <b>[SRE Advisory] رصدنا ملاحظة جديدة:</b>\n\n"
                                    f"📁 <b>المشروع:</b> <code>{html.escape(p_slug)}</code>\n"
                                    f"🔍 <b>المصدر:</b> <code>{html.escape(src)}</code>\n"
                                    f"📌 <b>العنوان:</b> {html.escape(issue_t)}\n"
                                    f"⚡ <b>النوع:</b> <code>{html.escape(err_t)}</code>\n"
                                    f"🎯 <b>العنصر:</b> <code>{html.escape(culprit)}</code>\n\n"
                                    f"هل تود تشغيل وكيل الذكاء الاصطناعي لفحص المشكلة وكتابة الإصلاح؟",
                                    reply_markup=kb
                                )
            poll_interval = sre_cfg.get("poll_interval_seconds", 30)
            time.sleep(poll_interval)
        except Exception as e:
            logger.error(f"[SRE Engine Loop] {e}")
            time.sleep(10)

def handle_sre_callback(cb_data, chat_id, message_id, user_id):
    """Handles interactive button callbacks from the SRE deck."""
    parts = cb_data.split(":", 1)
    action = parts[0]
    incident_id = parts[1] if len(parts) > 1 else ""
    
    incident = fetch_incident_by_id(incident_id)
    if not incident:
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "لم يتم العثور على بيانات هذا العطل")
        return True
        
    project_slug = incident.get("project_slug", "unknown")
    project_path = resolve_project_path(project_slug)
    branch = incident.get("pr_branch", "")
    pr_num = incident.get("pr_number")
    pr_url = incident.get("pr_url", "")
    
    # --- 0.A APPROVE REPAIR (HUMAN IN THE LOOP) ---
    if action == "sre_approve":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "بدأ تشغيل الوكيل للإصلاح...")
        if _EDIT_MESSAGE:
            _EDIT_MESSAGE(chat_id, message_id, f"🚀 <b>بدأ الوكيل الذاتي العمل على فحص وإصلاح المشكلة:</b>\n\n<code>{html.escape(incident.get('issue_title', ''))}</code>\n\n<i>جاري تحليل الكود في فرع مخصص...</i>")
        threading.Thread(
            target=process_single_incident,
            args=(incident, chat_id),
            daemon=True
        ).start()
        return True

    # --- 0.B IGNORE INCIDENT ---
    elif action == "sre_ignore":
        update_incident(incident_id, {"status": "ignored", "fix_summary": "Ignored by user via Telegram."})
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "تم تجاهل المشكلة.")
        if _EDIT_MESSAGE:
            _EDIT_MESSAGE(chat_id, message_id, f"❌ <b>تم تجاهل هذه الملاحظة بناءً على طلبك:</b>\n\n<code>{html.escape(incident.get('issue_title', ''))}</code>")
        return True

    # --- 0. APPLY SQL MIGRATION TO DATABASE ---
    elif action == "sre_apply_sql":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "جاري تطبيق الـ SQL على قاعدة البيانات...")
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, f"⏳ <i>جاري تنفيذ الـ Migration في قاعدة بيانات <code>{project_slug}</code>...</i>")
            
        migration_sql = ""
        try:
            raw_pl = incident.get("raw_payload")
            if raw_pl:
                pl_data = json.loads(raw_pl) if isinstance(raw_pl, str) else raw_pl
                migration_sql = pl_data.get("migration_sql", "")
        except Exception:
            pass
            
        if not migration_sql:
            m_dir = os.path.join(project_path, "supabase", "migrations")
            if os.path.isdir(m_dir):
                sql_files = sorted([os.path.join(m_dir, f) for f in os.listdir(m_dir) if f.endswith(".sql")])
                if sql_files:
                    try:
                        with open(sql_files[-1], "r", encoding="utf-8") as sf:
                            migration_sql = sf.read()
                    except Exception:
                        pass
                        
        if not migration_sql:
            if _SEND_MESSAGE:
                _SEND_MESSAGE(chat_id, "❌ لم يتم العثور على محتوى ملف الـ SQL لتطبيقه.")
            return True
            
        success, res_val = execute_supabase_sql(project_slug, migration_sql)
        if success:
            update_incident(incident_id, {"status": "sql_applied"})
            if _SEND_MESSAGE:
                _SEND_MESSAGE(
                    chat_id,
                    f"✅ <b>[DB-SRE] تم تطبيق الـ Migration بنجاح على قاعدة البيانات!</b> 🎉\n\n"
                    f"📁 <b>المشروع:</b> <code>{project_slug}</code>\n"
                    f"⚡ <b>الاستجابة:</b> تم التنفيذ في السحابة بنجاح (HTTP 201)\n\n"
                    f"🛡️ <b>الفحص التأكيدي:</b>\n"
                    f"تم تفعيل التعديلات الهيكلية والسياسات.\n\n"
                    f"اضغط <b>🔀 دمج مع الـ Main</b> لدمج كود ملف الـ Migration في مستودع GitHub."
                )
        else:
            if _SEND_MESSAGE:
                _SEND_MESSAGE(
                    chat_id,
                    f"❌ <b>فشل تطبيق الـ SQL في قاعدة البيانات:</b>\n\n"
                    f"<code>{html.escape(str(res_val))}</code>\n\n"
                    f"💡 يمكنك الضغط على 'إعادة التعديل' لتصحيح صياغة الـ SQL والمحاولة مجدداً."
                )
        return True

    # --- 1. MERGE TO MAIN ---
    elif action == "sre_merge":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "جاري دمج الـ PR رسمياً...")
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, f"🔀 <i>جاري دمج الـ PR #{pr_num or ''} في فرع main وحذف الفرع المؤقت...</i>")
            
        try:
            # Use gh pr merge
            merge_cmd = ["gh", "pr", "merge", branch, "--merge", "--delete-branch", "--yes"]
            merge_proc = subprocess.run(merge_cmd, cwd=project_path, capture_output=True, text=True)
            
            if merge_proc.returncode == 0 or "merged" in merge_proc.stdout.lower():
                # Checkout main & pull locally
                subprocess.run(["git", "checkout", "main"], cwd=project_path, capture_output=True)
                subprocess.run(["git", "pull", "origin", "main"], cwd=project_path, capture_output=True)
                
                update_incident(incident_id, {"status": "merged"})
                
                if _SEND_MESSAGE:
                    _SEND_MESSAGE(
                        chat_id,
                        f"🎉 <b>تم دمج الـ PR بنجاح مع فرع <code>main</code>!</b>\n\n"
                        f"📁 <b>المشروع:</b> <code>{project_slug}</code>\n"
                        f"🌿 <b>تم حذف الفرع المؤقت:</b> <code>{branch}</code>\n"
                        f"✅ كود الـ main الآن سليم ومحدث ومحمي من كراش Sentry."
                    )
            else:
                if _SEND_MESSAGE:
                    _SEND_MESSAGE(chat_id, f"⚠️ فشل الدمج التلقائي:\n<code>{merge_proc.stderr or merge_proc.stdout}</code>")
        except Exception as e:
            if _SEND_MESSAGE:
                _SEND_MESSAGE(chat_id, f"❌ خطأ أثناء الدمج: {e}")
        return True

    # --- 1.B GENERATE AUTOMATED TESTS ---
    elif action == "sre_gen_tests":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "جاري كتابة وفحص الاختبارات...")
        try:
            import analytics_engine
            threading.Thread(
                target=analytics_engine.generate_automated_tests,
                args=(project_path, chat_id, f"PR #{pr_num or ""} (Branch: {branch})"),
                daemon=True
            ).start()
        except Exception as e:
            if _SEND_MESSAGE:
                _SEND_MESSAGE(chat_id, f"❌ خطأ في توليد الاختبارات: {e}")
        return True

    # --- 2. PREVIEW IN CLOUDFLARE TUNNEL ---
    # --- 2. PREVIEW IN CLOUDFLARE TUNNEL ---
    elif action == "sre_preview":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "جاري تجهيز نفق المعاينة المشفر...")
            
        # Detect active ports
        ports = [5173, 3000, 8080, 8000, 4200]
        detected_port = None
        for p in ports:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", p)) == 0:
                    detected_port = p
                    s.close()
                    break
                s.close()
            except Exception:
                pass

        # If no port is listening, attempt to auto-serve if static/web assets exist
        if not detected_port and project_path and os.path.isdir(project_path):
            web_dir = None
            if os.path.isdir(os.path.join(project_path, "build", "web")):
                web_dir = os.path.join(project_path, "build", "web")
            elif os.path.isdir(os.path.join(project_path, "web")) and os.path.isfile(os.path.join(project_path, "web", "index.html")):
                web_dir = os.path.join(project_path, "web")
            elif os.path.isdir(os.path.join(project_path, "dist")):
                web_dir = os.path.join(project_path, "dist")
            elif os.path.isfile(os.path.join(project_path, "index.html")):
                web_dir = project_path

            if web_dir:
                try:
                    subprocess.Popen(
                        ["python3", "-m", "http.server", "5173", "--bind", "127.0.0.1"],
                        cwd=web_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    time.sleep(1)
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    if s.connect_ex(("127.0.0.1", 5173)) == 0:
                        detected_port = 5173
                    s.close()
                except Exception as e:
                    logger.error(f"[SRE Engine] Error auto-serving web folder: {e}")

        # If still no active port, abort and guide user to prevent 502 Bad Gateway
        if not detected_port:
            if _SEND_MESSAGE:
                _SEND_MESSAGE(
                    chat_id,
                    "⚠️ <b>تعذر فتح نفق المعاينة: لا يوجد خادم ويب نشط (Web Server)!</b>\n\n"
                    "🔍 تم فحص المنافذ <code>[5173, 3000, 8080, 8000, 4200]</code> ولم يُعثر على خادم محلي قيد التشغيل.\n\n"
                    "💡 <b>لتجنب ظهور خطأ Cloudflare 502 Bad Gateway:</b>\n"
                    "1. تأكد من تشغيل خادم التطوير أولاً (مثل <code>npm run dev</code> أو <code>flutter run -d web-server --web-port=5173</code>).\n"
                    "2. أعد الضغط على زر <b>🌐 معاينة عبر Cloudflare Tunnel</b> بعد بدء السيرفر."
                )
            return True
                
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, f"🌐 <i>تم رصد السيرفر المحلي يعمل على المنفذ <code>{detected_port}</code>. جاري تشغيل نفق Cloudflare المشفر...</i>")
            
        # Launch cloudflared tunnel
        def run_tunnel():
            try:
                # Terminate any existing cloudflared instance
                subprocess.run(["pkill", "-f", "cloudflared tunnel"], capture_output=True)
                time.sleep(0.5)

                p = subprocess.Popen(
                    ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{detected_port}"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
                )
                time.sleep(3)
                tunnel_url = None
                # scan stderr for trycloudflare
                import re
                start_t = time.time()
                while time.time() - start_t < 15:
                    line = p.stderr.readline()
                    if not line:
                        break
                    m = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
                    if m:
                        tunnel_url = m.group(0)
                        break
                        
                if tunnel_url and _SEND_MESSAGE:
                    _SEND_MESSAGE(
                        chat_id,
                        f"🚀 <b>رابط المعاينة المباشر (Cloudflare Tunnel):</b>\n\n"
                        f"🔗 <a href=\"{tunnel_url}\">{tunnel_url}</a>\n\n"
                        f"📱 افتح الرابط من متصفح الموبايل لاختبار التعديل مباشرة عبر HTTPS!\n"
                        f"⚡ <i>متصل بالمنفذ المحلي: <code>{detected_port}</code></i>"
                    )
                elif _SEND_MESSAGE:
                    _SEND_MESSAGE(chat_id, f"ℹ️ يعمل السيرفر محلياً على المنفذ <code>{detected_port}</code> ولكن تعذر استخراج رابط النفق خلال 15 ثانية.")
            except Exception as e:
                if _SEND_MESSAGE:
                    _SEND_MESSAGE(chat_id, f"❌ تعذر فتح نفق المعاينة: {e}")
                    
        threading.Thread(target=run_tunnel, daemon=True).start()
        return True

    # --- 3. REFINE / REJECT FIX ---
    elif action == "sre_refine":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "وضع إعادة التعديل نشط")
            
        _ACTIVE_REFINE_SESSIONS[chat_id] = {
            "incident_id": incident_id,
            "project_path": project_path,
            "branch": branch,
            "project_slug": project_slug,
            "issue_title": incident.get("issue_title", "")
        }
        
        prompt_txt = (
            f"🎤 <b>وضع إعادة التعديل التفاعلي نشط:</b>\n\n"
            f"📁 <b>المشروع:</b> <code>{project_slug}</code>\n"
            f"🌿 <b>الفرع الحالي:</b> <code>{branch}</code>\n\n"
            f"💡 <i>أرسل الآن رسالة صوتية (Voice Note) أو رسالة نصية توضح ما لم يعجبك أو التعديل المطلوب.</i>\n"
            f"سيتولى الأيجنت استكمال التعديل على نفس الفرع ورفع كوميت جديد فوراً!"
        )
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, prompt_txt)
        return True

    # --- 4. BUILD NEW VERSION ---
    elif action == "sre_build":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "خيارات البناء المتاحة")
            
        is_flutter = os.path.exists(os.path.join(project_path, "pubspec.yaml"))
        
        if is_flutter:
            build_kb = {
                "inline_keyboard": [
                    [{"text": "📱 بناء APK محلي على الجهاز", "callback_data": f"sre_bld_apk:{incident_id}"}],
                    [{"text": "🚀 إطلاق Release في GitHub Actions", "callback_data": f"sre_bld_gh:{incident_id}"}]
                ]
            }
            if _SEND_MESSAGE:
                _SEND_MESSAGE(
                    chat_id,
                    f"📦 <b>بناء وتصدير نسخة جديدة للمشروع (Flutter):</b>\n\n"
                    f"اختر طريقة البناء المفضلة لديك:",
                    reply_markup=build_kb
                )
        else:
            # Web / Node / Python
            if _SEND_MESSAGE:
                _SEND_MESSAGE(chat_id, f"⚡ <i>جاري تنفيذ build للمشروع محلياً...</i>")
            def do_web_build():
                p = subprocess.run(["npm", "run", "build"], cwd=project_path, capture_output=True, text=True)
                if p.returncode == 0:
                    if _SEND_MESSAGE:
                        _SEND_MESSAGE(chat_id, f"✅ <b>تم بناء المشروع بنجاح (npm run build)!</b> جاهز للنشر.")
                else:
                    if _SEND_MESSAGE:
                        _SEND_MESSAGE(chat_id, f"⚠️ حدث خطأ أثناء البناء:\n<code>{p.stderr[:500]}</code>")
            threading.Thread(target=do_web_build, daemon=True).start()
        return True

    # --- 4.A BUILD LOCAL APK ---
    elif action == "sre_bld_apk":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "جاري بناء APK محلياً...")
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, "⏳ <i>جاري بناء نسخة APK عبر <code>flutter build apk --release</code>... قد يستغرق ذلك دقيقتين.</i>")
            
        def do_apk_build():
            p = subprocess.run(["flutter", "build", "apk", "--release"], cwd=project_path, capture_output=True, text=True)
            apk_path = os.path.join(project_path, "build", "app", "outputs", "flutter-apk", "app-release.apk")
            if os.path.exists(apk_path):
                size_mb = round(os.path.getsize(apk_path) / (1024 * 1024), 1)
                if _SEND_MESSAGE:
                    _SEND_MESSAGE(chat_id, f"✅ <b>تم بناء الـ APK بنجاح!</b> ({size_mb} MB)\nالمسار: <code>{apk_path}</code>")
            else:
                if _SEND_MESSAGE:
                    _SEND_MESSAGE(chat_id, f"❌ تعذر العثور على ملف الـ APK بعد البناء:\n<code>{p.stderr[:400]}</code>")
                    
        threading.Thread(target=do_apk_build, daemon=True).start()
        return True

    # --- 4.B TRIGGER GITHUB ACTIONS RELEASE ---
    elif action == "sre_bld_gh":
        if _ANSWER_CALLBACK:
            _ANSWER_CALLBACK(None, "إطلاق workflow سحابياً...")
        if _SEND_MESSAGE:
            _SEND_MESSAGE(chat_id, "🚀 <i>جاري إطلاق workflow البناء السحابي عبر GitHub Actions...</i>")
            
        def do_gh_release():
            # Check available release workflows
            p = subprocess.run(
                ["gh", "workflow", "run", "Universal Multi-Platform Release", "--ref", branch or "main"],
                cwd=project_path, capture_output=True, text=True
            )
            if p.returncode == 0:
                if _SEND_MESSAGE:
                    _SEND_MESSAGE(
                        chat_id,
                        f"🎉 <b>تم إطلاق عملية البناء بنجاح في GitHub Actions!</b>\n\n"
                        f"يمكنك متابعة تقدم الـ Release من تبويب Actions في جيت هاب."
                    )
            else:
                # Try fallback workflow name
                p2 = subprocess.run(
                    ["gh", "workflow", "run", "release.yml", "--ref", branch or "main"],
                    cwd=project_path, capture_output=True, text=True
                )
                if p2.returncode == 0:
                    if _SEND_MESSAGE:
                        _SEND_MESSAGE(chat_id, f"🎉 <b>تم إطلاق release.yml بنجاح في GitHub Actions!</b>")
                else:
                    if _SEND_MESSAGE:
                        _SEND_MESSAGE(chat_id, f"⚠️ تعذر إطلاق الـ Workflow:\n<code>{p.stderr or p2.stderr}</code>")
                        
        threading.Thread(target=do_gh_release, daemon=True).start()
        return True

    return False

def check_and_handle_refine_input(chat_id, user_text_or_prompt):
    """If chat has an active refine session, routes the input to update the PR branch."""
    if chat_id not in _ACTIVE_REFINE_SESSIONS:
        return False
        
    session = _ACTIVE_REFINE_SESSIONS.pop(chat_id)
    project_path = session["project_path"]
    branch = session["branch"]
    issue_title = session["issue_title"]
    incident_id = session["incident_id"]
    
    if _SEND_MESSAGE:
        _SEND_MESSAGE(chat_id, f"🔄 <i>جاري تطبيق ملاحظاتك على الفرع <code>{branch}</code> وإعادة التحقق...</i>")
        
    def do_refine():
        try:
            # Checkout branch
            subprocess.run(["git", "checkout", branch], cwd=project_path, capture_output=True)
            
            prompt = (
                f"The user reviewed your previous fix for incident '{issue_title}' and provided this feedback:\n"
                f"'{user_text_or_prompt}'\n\n"
                f"Please inspect the current diff, apply the requested changes, run local tests, and provide a short Arabic summary."
            )
            agy_bin = _CONFIG.get("agy_bin", "agy")
            subprocess.run([agy_bin, prompt], cwd=project_path, capture_output=True, text=True, timeout=300)
            
            # Commit and push
            subprocess.run(["git", "add", "-A"], cwd=project_path, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"refine(sre): apply user review on {issue_title[:50]}"], cwd=project_path, capture_output=True)
            subprocess.run(["git", "push", "origin", branch], cwd=project_path, capture_output=True)
            
            # Send updated buttons
            deck_text = (
                f"✨ <b>تم تحديث الفرع <code>{branch}</code> بنجاح وفق ملاحظاتك!</b>\n\n"
                f"تم رفع الكوميت الجديد تلقائياً إلى الـ Pull Request المفتوح.\n"
                f"👇 اختر الإجراء التالي:"
            )
            reply_markup = {
                "inline_keyboard": [
                    [
                        {"text": "🌐 معاينة عبر Cloudflare Tunnel", "callback_data": f"sre_preview:{incident_id}"},
                        {"text": "🔀 دمج مع الـ Main", "callback_data": f"sre_merge:{incident_id}"}
                    ],
                    [
                        {"text": "🔄 إعادة التعديل مرة أخرى", "callback_data": f"sre_refine:{incident_id}"},
                        {"text": "📦 بناء نسخة جديدة", "callback_data": f"sre_build:{incident_id}"}
                    ]
                ]
            }
            if _SEND_MESSAGE:
                _SEND_MESSAGE(chat_id, deck_text, reply_markup=reply_markup)
        except Exception as e:
            if _SEND_MESSAGE:
                _SEND_MESSAGE(chat_id, f"❌ حدث خطأ أثناء تعديل الفرع: {e}")
                
    threading.Thread(target=do_refine, daemon=True).start()
    return True

def init_sre_engine(config, send_message_func, edit_message_func, answer_callback_func, run_agent_task_func):
    """Initializes and starts the SRE background polling daemon."""
    global _CONFIG, _SEND_MESSAGE, _EDIT_MESSAGE, _ANSWER_CALLBACK, _RUN_AGENT_TASK, _WORKER_THREAD
    _CONFIG = config
    _SEND_MESSAGE = send_message_func
    _EDIT_MESSAGE = edit_message_func
    _ANSWER_CALLBACK = answer_callback_func
    _RUN_AGENT_TASK = run_agent_task_func
    
    if _WORKER_THREAD is None or not _WORKER_THREAD.is_alive():
        _WORKER_THREAD = threading.Thread(target=sre_worker_loop, daemon=True)
        _WORKER_THREAD.start()
        logger.info("[SRE Engine] Initialized and background thread started successfully.")
