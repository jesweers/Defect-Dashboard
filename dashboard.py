import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
import io

import pandas as pd
import streamlit as st

# =========================
# Files & constants
# =========================
DATA_FILE = Path("tasks_data.json")
ATTACH_DIR = Path("attachments")
ATTACH_DIR.mkdir(exist_ok=True)
STATUSES = ["ready", "inprogress", "completed"]
TYPE_OPTIONS = ["task", "defect"]
STATE_KEY = "items"  # stored in st.session_state[STATE_KEY]

# =========================
# Attachment helpers
# =========================
def _save_uploaded_file(uploaded_file, item_id: str) -> str:
    """Save an uploaded file to attachments directory and return relative path string."""
    suffix = Path(uploaded_file.name).suffix
    fname = f"{item_id}_{uuid.uuid4().hex}{suffix}"
    dest = ATTACH_DIR / fname
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(dest)

def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

# =========================
# Persistence / helpers
# =========================
def _now_iso() -> str:
    return datetime.now().isoformat()

def _coerce_item(x: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure an item has all expected keys, including a comment_history list."""
    ch = x.get("comment_history") if isinstance(x, dict) else None
    if not isinstance(ch, list):
        ch = []
    norm_ch = []
    for e in ch:
        if not isinstance(e, dict):
            continue
        norm_ch.append({
            "actor": str(e.get("actor", "system")),
            "comment": str(e.get("comment", "") or ""),
            "attachments": list(e.get("attachments", []) or []),
            "at": e.get("at") or _now_iso(),
        })
    base = {
        "id": x.get("id", str(uuid.uuid4())) if isinstance(x, dict) else str(uuid.uuid4()),
        "type": (x.get("type") if isinstance(x, dict) else "task") or "task",
        "title": str(x.get("title", "") if isinstance(x, dict) else "").strip(),
        "client": str(x.get("client", "") if isinstance(x, dict) else "").strip(),
        "project": str(x.get("project", "") if isinstance(x, dict) else "").strip(),
        "billable": bool(x.get("billable", True) if isinstance(x, dict) else True),
        "status": (x.get("status") if isinstance(x, dict) else "ready") or "ready",
        "hours": (x.get("hours") if isinstance(x, dict) else None),
        "rate_at_completion": (x.get("rate_at_completion") if isinstance(x, dict) else None),
        "amount": (x.get("amount") if isinstance(x, dict) else None),
        "created_at": (x.get("created_at") if isinstance(x, dict) else _now_iso()) or _now_iso(),
        "updated_at": (x.get("updated_at") if isinstance(x, dict) else _now_iso()) or _now_iso(),
        "completed_at": (x.get("completed_at") if isinstance(x, dict) else None),
        "archived": bool(x.get("archived", False) if isinstance(x, dict) else False),
        # approval / review flags
        "pr_url": str(x.get("pr_url", "") if isinstance(x, dict) else "").strip(),
        "owner_approved": bool(x.get("owner_approved", False) if isinstance(x, dict) else False),
        "owner_approved_at": (x.get("owner_approved_at") if isinstance(x, dict) else None),
        "owner_approved_by": (x.get("owner_approved_by") if isinstance(x, dict) else None),
        # review flag
        "review_requested": bool(x.get("review_requested", False) if isinstance(x, dict) else False),
        "review_comments": str(x.get("review_comments", "") if isinstance(x, dict) else "").strip(),
        "review_requested_at": (x.get("review_requested_at") if isinstance(x, dict) else None),
        # developer response
        "dev_response_comments": str(x.get("dev_response_comments", "") if isinstance(x, dict) else "").strip(),
        "dev_response_at": (x.get("dev_response_at") if isinstance(x, dict) else None),
        # attachments (global list for convenience)
        "attachments": list(x.get("attachments", []) if isinstance(x, dict) else []),
        # chronological comment history
        "comment_history": norm_ch,
    }
    if base["status"] not in STATUSES:
        base["status"] = "ready"
    return base

def _normalize_loaded(obj) -> List[Dict[str, Any]]:
    """Accept many shapes and return a list of coerced dicts."""
    if isinstance(obj, list):
        return [_coerce_item(d) for d in obj if isinstance(d, dict)]
    if isinstance(obj, dict):
        if "items" in obj and isinstance(obj["items"], list):
            return [_coerce_item(d) for d in obj["items"] if isinstance(d, dict)]
        vals = list(obj.values())
        if vals and all(isinstance(v, dict) for v in vals):
            return [_coerce_item(v) for v in vals]
    return []

def load_data() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return _normalize_loaded(raw)
    except Exception:
        return []

def save_data(items: List[Dict[str, Any]]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

def sanitize_items(items) -> List[Dict[str, Any]]:
    """Always return a list of valid item dicts."""
    if not isinstance(items, list):
        return []
    clean = []
    for it in items:
        if isinstance(it, dict):
            clean.append(_coerce_item(it))
    return clean

# =========================
# Item utilities
# =========================
def new_item(title: str, ttype: str, client: str, project: str, billable: bool):
    now = _now_iso()
    item_id = str(uuid.uuid4())
    base = {
        "id": item_id,
        "type": ttype,
        "title": title.strip(),
        "client": client.strip(),
        "project": project.strip(),
        "billable": bool(billable),
        "status": "ready",
        "hours": None,
        "rate_at_completion": None,
        "amount": None,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "archived": False,
        "pr_url": "",
        "owner_approved": False,
        "owner_approved_at": None,
        "owner_approved_by": None,
        "review_requested": False,
        "review_comments": "",
        "review_requested_at": None,
        "dev_response_comments": "",
        "dev_response_at": None,
        "attachments": [],
        "comment_history": [
            {"actor": "system", "comment": "Task created", "attachments": [], "at": now}
        ],
    }
    return base

def get_items_by_status(items, status):
    out = []
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, dict) and it.get("status") == status and not it.get("archived", False):
            out.append(it)
    return out

def set_status(items, item_id, new_status):
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["status"] = new_status
            it["updated_at"] = _now_iso()
            if new_status != "completed":
                it["completed_at"] = None
            return it
    return None

def set_hours_and_complete(items, item_id, hours: float, rate_now: float):
    """
    Developer completes item: set hours, amount, mark completed and auto-archive.
    Also clears owner approval and review flags so it's a fresh completed item for owner.
    """
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["hours"] = float(hours)
            it["status"] = "completed"
            it["completed_at"] = _now_iso()
            it["updated_at"] = _now_iso()
            it["rate_at_completion"] = float(rate_now)
            it["amount"] = round(float(hours) * float(rate_now), 2)
            # auto-archive on developer complete (per earlier request)
            it["archived"] = True
            # reset approval/review state
            it["owner_approved"] = False
            it["owner_approved_at"] = None
            it["owner_approved_by"] = None
            it["review_requested"] = False
            it["review_comments"] = ""
            it["review_requested_at"] = None
            # add history entry
            it.setdefault("comment_history", []).append({
                "actor": "dev",
                "comment": f"Completed by developer: {hours}h @ {rate_now}",
                "attachments": [],
                "at": _now_iso(),
            })
            save_data(items)  # persist immediately
            return it
    return None

def set_archived(items, item_id, archived=True):
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["archived"] = bool(archived)
            it["updated_at"] = _now_iso()
            save_data(items)
            return it
    return None

# =========================
# Comment history flows
# =========================
def append_history(items, item_id: str, actor: str, comment: str, attachment_files: Optional[List[Any]] = None):
    """Add a chronological comment entry and save any attachments; returns the updated item.
       Saves to disk immediately to ensure persistence."""
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            saved_paths = []
            if attachment_files:
                for f in attachment_files:
                    if f is not None:
                        saved = _save_uploaded_file(f, item_id)
                        saved_paths.append(saved)
                        if saved not in it.get("attachments", []):
                            it.setdefault("attachments", []).append(saved)
            entry = {
                "actor": actor,
                "comment": str(comment or ""),
                "attachments": saved_paths,
                "at": _now_iso(),
            }
            it.setdefault("comment_history", []).append(entry)
            it["updated_at"] = _now_iso()
            # persist immediately
            save_data(items)
            return it
    return None

def request_review(items, item_id: str, owner_comment: str, owner_files: Optional[List[Any]] = None):
    """
    Owner requests review: move item back to developer (inprogress),
    append owner comment entry with owner_files.
    """
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["review_requested"] = True
            it["review_comments"] = owner_comment or ""
            it["review_requested_at"] = _now_iso()
            it["owner_approved"] = False
            it["owner_approved_at"] = None
            it["owner_approved_by"] = None
            it["status"] = "inprogress"
            it["archived"] = False
            append_history(items, item_id, "owner", owner_comment or "", owner_files)
            save_data(items)
            return it
    return None

def submit_back_to_owner(items, item_id: str, dev_comment: str, dev_files: Optional[List[Any]] = None, hours: Optional[float] = None, rate_now: Optional[float] = None):
    """
    Developer responds to review and submits back to owner:
    - appends developer comment entry and attachments
    - optionally saves hours & rate
    - marks task completed immediately and archives it (so it's removed from Kanban)
    """
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            # append dev comment and save attachments first (append_history will persist)
            append_history(items, item_id, "dev", dev_comment or "", dev_files)
            it["dev_response_comments"] = dev_comment or ""
            it["dev_response_at"] = _now_iso()
            # optionally update hours/rate
            if hours is not None:
                try:
                    it["hours"] = float(hours)
                except Exception:
                    pass
            if rate_now is not None:
                try:
                    it["rate_at_completion"] = float(rate_now)
                except Exception:
                    pass
            # recompute amount if both present
            if it.get("hours") is not None and it.get("rate_at_completion") is not None:
                try:
                    it["amount"] = round(float(it["hours"]) * float(it["rate_at_completion"]), 2)
                except Exception:
                    pass
            # mark as completed immediately and archive it
            it["status"] = "completed"
            it["completed_at"] = _now_iso()
            it["updated_at"] = _now_iso()
            it["archived"] = True  # archived on submit-to-owner per your latest request
            # clear review flags
            it["review_requested"] = False
            it["review_comments"] = ""
            it["review_requested_at"] = None
            it["owner_approved"] = False
            it["owner_approved_at"] = None
            it["owner_approved_by"] = None
            save_data(items)
            return it
    return None

def approve_item(items, item_id: str):
    """Owner approves: mark owner_approved True and append history entry (owner)."""
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["owner_approved"] = True
            it["owner_approved_at"] = _now_iso()
            it["owner_approved_by"] = None
            append_history(items, item_id, "owner", "Approved", None)
            it["updated_at"] = _now_iso()
            save_data(items)
            return it
    return None

def revoke_approval(items, item_id: str):
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["owner_approved"] = False
            it["owner_approved_at"] = None
            it["owner_approved_by"] = None
            append_history(items, item_id, "owner", "Revoked approval", None)
            it["updated_at"] = _now_iso()
            save_data(items)
            return it
    return None

# =========================
# Session state init + sanitize
# =========================
if STATE_KEY not in st.session_state:
    st.session_state[STATE_KEY] = load_data()
st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])

if "awaiting_hours_id" not in st.session_state:
    st.session_state.awaiting_hours_id = None
if "awaiting_action" not in st.session_state:
    st.session_state.awaiting_action = None

# billing defaults (kept but not displayed)
if "billing_currency" not in st.session_state:
    st.session_state.billing_currency = "$"
if "billing_hourly_rate" not in st.session_state:
    st.session_state.billing_hourly_rate = 75.0
if "billing_tax_percent" not in st.session_state:
    st.session_state.billing_tax_percent = 0.0

# =========================
# Routing / Navigation (st.query_params)
# =========================
params = st.query_params
page = params.get("page", ["developer"])
if isinstance(page, list):
    page = page[0] if page else "developer"

# top selector visible only when not owner page
if page != "owner":
    nav_sel = st.selectbox("View", ["Developer Board", "Owner Board"], index=0 if page == "developer" else 1)
    target = "developer" if nav_sel == "Developer Board" else "owner"
    if target != page:
        st.query_params["page"] = [target]
        st.rerun()
else:
    st.markdown("### 🔒 Owner Board (read-only)")

# -------------------------
# Sidebar: ONLY Add Task / Defect (with attachments)
# -------------------------
st.sidebar.header("➕ Add Task / Defect")
with st.sidebar.form("add_form", clear_on_submit=True):
    ttype = st.selectbox("Type", TYPE_OPTIONS, index=0)
    title = st.text_input("Title", placeholder="e.g., Fix checkout crash")
    client = st.text_input("Client", placeholder="e.g., Acme Corp")
    project = st.text_input("Project", placeholder="e.g., Website Revamp")
    billable = st.checkbox("Billable", value=True)
    add_files = st.file_uploader("Attach images/files (optional)", accept_multiple_files=True)
    submitted = st.form_submit_button("Add to Board")
    if submitted:
        if not title.strip():
            st.sidebar.error("Please enter a title.")
        else:
            item = new_item(title, ttype, client, project, billable)
            saved_paths = []
            if add_files:
                for f in add_files:
                    saved = _save_uploaded_file(f, item["id"])
                    saved_paths.append(saved)
                    item.setdefault("attachments", []).append(saved)
            if saved_paths:
                item.setdefault("comment_history", []).append({
                    "actor": "dev",
                    "comment": "Initial attachments",
                    "attachments": saved_paths,
                    "at": _now_iso(),
                })
            st.session_state[STATE_KEY].append(item)
            st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
            save_data(st.session_state[STATE_KEY])
            st.sidebar.success("Added!")

# Build DataFrame safely
items_list = sanitize_items(st.session_state[STATE_KEY])
df_all = pd.DataFrame(items_list) if items_list else pd.DataFrame(
    columns=[
        "id","type","title","client","project","billable","status","hours",
        "rate_at_completion","amount","created_at","updated_at","completed_at",
        "archived","pr_url","owner_approved","owner_approved_at","owner_approved_by",
        "review_requested","review_comments","review_requested_at",
        "dev_response_comments","dev_response_at","attachments","comment_history"
    ]
)

total_hours_all = float(df_all["hours"].fillna(0).sum()) if not df_all.empty else 0.0
total_hours_billable = float(df_all.loc[(df_all["billable"] == True), "hours"].fillna(0).sum()) if not df_all.empty else 0.0

# =========================
# Invoice helpers (kept)
# =========================
def parse_iso_d(d):
    try:
        return datetime.fromisoformat(d).date()
    except Exception:
        return None

if not df_all.empty and "completed_at" in df_all.columns and df_all["completed_at"].notna().any():
    dates = [parse_iso_d(x) for x in df_all["completed_at"].dropna()]
    valid_dates = [d for d in dates if d]
    min_d = min(valid_dates) if valid_dates else date.today()
    max_d = max(valid_dates) if valid_dates else date.today()
else:
    min_d = max_d = date.today()

def build_invoice_df(start_d=date.today(), end_d=date.today(), client_filter="All"):
    if df_all.empty:
        return pd.DataFrame(columns=["Date","Title","Type","Client","Project","Hours","Rate","Amount"])
    df = df_all.copy()
    df = df[(df["status"] == "completed") & (df["billable"] == True) & df["hours"].notna()]
    if client_filter != "All":
        df = df[df["client"] == client_filter]
    def in_range(iso):
        d = parse_iso_d(iso)
        if not d:
            return False
        return (d >= start_d) and (d <= end_d)
    df = df[df["completed_at"].apply(in_range)]
    if df.empty:
        return pd.DataFrame(columns=["Date","Title","Type","Client","Project","Hours","Rate","Amount"])
    rate_col, amt_col = [], []
    for _, r in df.iterrows():
        rate = float(r["rate_at_completion"]) if pd.notna(r["rate_at_completion"]) else float(st.session_state.billing_hourly_rate)
        hours = float(r["hours"]) if pd.notna(r["hours"]) else 0.0
        amount = round(rate * hours, 2)
        rate_col.append(rate)
        amt_col.append(amount)
    out = pd.DataFrame({
        "Date": [str(x)[:10] for x in df["completed_at"]],
        "Title": df["title"],
        "Type": df["type"],
        "Client": df["client"].fillna(""),
        "Project": df["project"].fillna(""),
        "Hours": df["hours"].fillna(0.0).astype(float),
        "Rate": rate_col,
        "Amount": amt_col,
    })
    return out

# =========================
# UI helpers: render attachments & comment history (with colors & black text)
# =========================
def render_attachments_list(attachments: List[str], key_prefix: str):
    """Show thumbnails for images and download buttons for all attachments."""
    if not attachments:
        return
    for idx, p in enumerate(attachments):
        try:
            pth = Path(p)
            if not pth.exists():
                st.caption(f"Missing attachment: {p}")
                continue
            # Try to show as image if possible
            try:
                st.image(str(pth), caption=pth.name, use_column_width=False)
            except Exception:
                st.write(f"Attachment: {pth.name}")
            # download button
            data = _read_file_bytes(str(pth))
            st.download_button(label=f"Download {pth.name}", data=data, file_name=pth.name, key=f"dl_{key_prefix}_{idx}")
        except Exception as e:
            st.write("Attachment error:", e)

def render_comment_history(item: Dict[str, Any]):
    """Render chronological comment history as a boxed timeline with color-coded entries and black text."""
    history = item.get("comment_history", []) or []
    if not history:
        st.info("No comments yet.")
        return
    history = sorted(history, key=lambda e: e.get("at", ""))
    st.markdown("#### Conversation / History")
    for entry in history:
        actor = entry.get("actor", "system")
        at = entry.get("at", "")
        comment = entry.get("comment", "")
        attachments = entry.get("attachments", []) or []
        # choose background color for actor
        if actor == "owner":
            bg = "#e6f2ff"  # light blue
            label = "Owner"
        elif actor == "dev":
            bg = "#e8ffe6"  # light green
            label = "Developer"
        else:
            bg = "#f5f5f5"  # light gray for system
            label = "System"
        safe_comment = (comment.replace("\n", "<br/>") if comment else "")
        # Use black text color explicitly for readability
        html = f"""
        <div style="background:{bg};padding:10px;border-radius:8px;margin-bottom:8px;border:1px solid #ddd;color:#000;">
          <strong>{label}</strong> <span style="color:#666;font-size:12px">— {at.replace('T',' ')[:19]}</span>
          <div style="margin-top:6px;font-size:14px;color:#000;">{safe_comment}</div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)
        if attachments:
            render_attachments_list(attachments, key_prefix=f"{item['id']}_{actor}_{at}")

# =========================
# Developer Board (no Completed column)
# =========================
def developer_board():
    st.title("📋 Developer Board: Tasks & Defects")
    st.caption("Developer controls available. Completed items are archived on completion and not shown in Kanban.")

    # KPIs
    active_ready = len(get_items_by_status(st.session_state[STATE_KEY], "ready"))
    active_inprog = len(get_items_by_status(st.session_state[STATE_KEY], "inprogress"))
    active_completed = len([it for it in st.session_state[STATE_KEY] if it.get("status") == "completed" and not it.get("archived", False)])

    colA, colB, colC, colD, colE = st.columns(5)
    colA.metric("Ready (active)", active_ready)
    colB.metric("In Progress (active)", active_inprog)
    colC.metric("Completed (active)", active_completed)
    colD.metric("Total Hours (all)", f"{total_hours_all:.2f} h")
    colE.metric("Billable Hours", f"{total_hours_billable:.2f} h")

    st.markdown("---")
    st.subheader("🧱 Kanban Board (Developer)")
    # only show ready and inprogress columns
    board_statuses = ["ready", "inprogress"]
    status_titles_map = {"ready": "Ready", "inprogress": "In Progress"}
    cols = st.columns(len(board_statuses))

    for idx, status in enumerate(board_statuses):
        with cols[idx]:
            st.markdown(f"### {status_titles_map[status]}")
            for it in get_items_by_status(st.session_state[STATE_KEY], status):
                with st.container():
                    st.markdown(f"**{it['title']}**  \n*{it['type']}* • `#{it['id'][:8]}`")
                    meta = []
                    if it.get("client"): meta.append(f"Client: {it['client']}")
                    if it.get("project"): meta.append(f"Project: {it['project']}")
                    meta.append("Billable" if it.get("billable") else "Non-billable")
                    st.caption(" • ".join(meta))

                    if it.get("hours") is not None:
                        cur = st.session_state.billing_currency or ""
                        hours_txt = f"{it['hours']} h"
                        if it.get("rate_at_completion") is not None and it.get("amount") is not None:
                            hours_txt += f" • {cur}{it['rate_at_completion']} ⇒ {cur}{it['amount']}"
                        st.caption(f"⏱ {hours_txt}")

                    st.caption(
                        f"Created: {it['created_at'][:19].replace('T',' ')}" +
                        (f" • Completed: {str(it.get('completed_at'))[:19].replace('T',' ')}" if it.get('completed_at') else "")
                    )

                    # render attachments (global)
                    render_attachments_list(it.get("attachments", []), key_prefix=it["id"])

                    # render conversation / timeline (color-coded, black text)
                    render_comment_history(it)

                    # Actions
                    if status == "ready":
                        c1, c2, c3 = st.columns(3)
                        if c1.button("→ In Progress", key=f"to_inprog_{it['id']}"):
                            set_status(st.session_state[STATE_KEY], it["id"], "inprogress")
                            st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                            save_data(st.session_state[STATE_KEY])
                            st.rerun()
                        if c2.button("Delete", key=f"del_{it['id']}"):
                            st.session_state[STATE_KEY] = [
                                x for x in st.session_state[STATE_KEY]
                                if isinstance(x, dict) and x.get("id") != it["id"]
                            ]
                            st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                            save_data(st.session_state[STATE_KEY])
                            st.rerun()
                        if c3.button("Edit & Submit to Owner", key=f"edit_submit_{it['id']}"):
                            with st.form(f"dev_edit_form_{it['id']}"):
                                new_title = st.text_input("Title", value=it["title"])
                                new_client = st.text_input("Client", value=it["client"])
                                new_project = st.text_input("Project", value=it["project"])
                                add_files = st.file_uploader("Add attachments (optional)", accept_multiple_files=True)
                                dev_resp = st.text_area("Response to owner (REQUIRED)", value="")
                                # allow dev to set hours & rate while submitting
                                dev_hours = st.number_input("Hours (optional, will set on submit)", min_value=0.0, step=0.25, value=float(it.get("hours") or 0.0))
                                dev_rate = st.number_input("Rate (optional, will set on submit)", min_value=0.0, step=1.0, value=float(it.get("rate_at_completion") or st.session_state.billing_hourly_rate))
                                submit_to_owner = st.form_submit_button("Submit to Owner (will complete & archive)")
                                save_only = st.form_submit_button("Save")
                                if save_only:
                                    it["title"] = new_title.strip()
                                    it["client"] = new_client.strip()
                                    it["project"] = new_project.strip()
                                    if add_files:
                                        for f in add_files:
                                            saved = _save_uploaded_file(f, it["id"])
                                            if saved not in it.get("attachments", []):
                                                it.setdefault("attachments", []).append(saved)
                                                append_history(st.session_state[STATE_KEY], it["id"], "dev", "Added attachment", [f])
                                    it["updated_at"] = _now_iso()
                                    st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                    save_data(st.session_state[STATE_KEY])
                                    st.rerun()
                                if submit_to_owner:
                                    if not dev_resp.strip():
                                        st.warning("Developer response/comment is required before submitting to owner.")
                                    else:
                                        # store new title/client/project
                                        it["title"] = new_title.strip()
                                        it["client"] = new_client.strip()
                                        it["project"] = new_project.strip()
                                        # submit and immediately mark completed and archived
                                        submit_back_to_owner(
                                            st.session_state[STATE_KEY],
                                            it["id"],
                                            dev_resp,
                                            dev_files=add_files,
                                            hours=(dev_hours if dev_hours and dev_hours > 0 else None),
                                            rate_now=(dev_rate if dev_rate and dev_rate > 0 else None),
                                        )
                                        st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                        save_data(st.session_state[STATE_KEY])
                                        st.success("Submitted to Owner for review, task marked completed and archived.")
                                        st.rerun()

                    elif status == "inprogress":
                        c1, c2, c3 = st.columns(3)
                        if c1.button("↩ Ready", key=f"back_ready_{it['id']}"):
                            set_status(st.session_state[STATE_KEY], it["id"], "ready")
                            st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                            save_data(st.session_state[STATE_KEY])
                            st.rerun()
                        if c2.button("✓ Complete (Save Hours)", key=f"complete_{it['id']}"):
                            st.session_state.awaiting_hours_id = it["id"]
                            st.session_state.awaiting_action = "complete"
                            st.rerun()
                        if c3.button("Edit & Submit to Owner", key=f"edit_submit2_{it['id']}"):
                            with st.form(f"dev_edit_form2_{it['id']}"):
                                new_title = st.text_input("Title", value=it["title"])
                                new_client = st.text_input("Client", value=it["client"])
                                new_project = st.text_input("Project", value=it["project"])
                                add_files = st.file_uploader("Add attachments (optional)", accept_multiple_files=True)
                                dev_resp = st.text_area("Response to owner (REQUIRED)", value="")
                                dev_hours = st.number_input("Hours (optional, will set on submit)", min_value=0.0, step=0.25, value=float(it.get("hours") or 0.0))
                                dev_rate = st.number_input("Rate (optional, will set on submit)", min_value=0.0, step=1.0, value=float(it.get("rate_at_completion") or st.session_state.billing_hourly_rate))
                                submit_to_owner = st.form_submit_button("Submit to Owner (will complete & archive)")
                                cancel = st.form_submit_button("Cancel")
                                if cancel:
                                    st.rerun()
                                if submit_to_owner:
                                    if not dev_resp.strip():
                                        st.warning("Developer response/comment is required before submitting to owner.")
                                    else:
                                        submit_back_to_owner(
                                            st.session_state[STATE_KEY],
                                            it["id"],
                                            dev_resp,
                                            dev_files=add_files,
                                            hours=(dev_hours if dev_hours and dev_hours > 0 else None),
                                            rate_now=(dev_rate if dev_rate and dev_rate > 0 else None),
                                        )
                                        st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                        save_data(st.session_state[STATE_KEY])
                                        st.success("Submitted to Owner for review, task marked completed and archived.")
                                        st.rerun()

                    # Hours form (pop-up-like)
                    if st.session_state.awaiting_hours_id == it["id"]:
                        with st.form(f"hours_form_{it['id']}"):
                            default_hours = float(it.get("hours") or 0.0)
                            default_rate = float(it.get("rate_at_completion") if it.get("rate_at_completion") is not None else st.session_state.billing_hourly_rate)
                            hrs = st.number_input("Hours worked", min_value=0.0, step=0.25, value=default_hours, key=f"hrs_input_{it['id']}")
                            rate_now = st.number_input("Lock rate (per hour)", min_value=0.0, step=1.0,
                                                       value=default_rate, key=f"rate_input_{it['id']}")
                            add_files = st.file_uploader("Add attachments (optional)", accept_multiple_files=True)
                            c1, c2 = st.columns(2)
                            save_btn = c1.form_submit_button("Save Hours & Complete")
                            cancel_btn = c2.form_submit_button("Cancel")
                            if save_btn:
                                updated = set_hours_and_complete(st.session_state[STATE_KEY], it["id"], hrs, rate_now)
                                if add_files and updated:
                                    for f in add_files:
                                        saved = _save_uploaded_file(f, it["id"])
                                        if saved not in updated.get("attachments", []):
                                            updated.setdefault("attachments", []).append(saved)
                                            append_history(st.session_state[STATE_KEY], it["id"], "dev", "Added attachments on completion", [f])
                                st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                save_data(st.session_state[STATE_KEY])
                                st.session_state.awaiting_hours_id = None
                                st.session_state.awaiting_action = None
                                st.success("Saved & completed (auto-archived).")
                                st.rerun()
                            if cancel_btn:
                                st.session_state.awaiting_hours_id = None
                                st.session_state.awaiting_action = None
                                st.info("Cancelled.")
                                st.rerun()

    st.markdown("---")
    st.subheader("📑 All Saved Data (Developer view)")
    st.caption("Everything currently in your JSON file (including archived).")
    st.dataframe(
        df_all if not df_all.empty else pd.DataFrame(
            columns=[
                "id","type","title","client","project","billable","status","hours",
                "rate_at_completion","amount","created_at","updated_at","completed_at",
                "archived","pr_url","owner_approved","owner_approved_at","owner_approved_by",
                "review_requested","review_comments","review_requested_at",
                "dev_response_comments","dev_response_at","attachments","comment_history"
            ]
        ),
        use_container_width=True
    )

    st.markdown(f"**JSON file:** `{DATA_FILE.resolve()}`")

# =========================
# Owner Board UI (Needs Approval / Approved)
# =========================
def owner_board():
    st.title("🔒 Owner Board: Needs Approval / Approved")
    st.caption("Owner view is read-only except for Approve / Request changes. Owners can attach images when requesting review.")

    needs_approval = [
        it for it in st.session_state[STATE_KEY]
        if it.get("status") == "completed" and not it.get("owner_approved", False)
    ]
    approved = [
        it for it in st.session_state[STATE_KEY]
        if it.get("status") == "completed" and it.get("owner_approved", False)
    ]

    st.markdown("## Needs Approval")
    if not needs_approval:
        st.info("No completed items awaiting approval.")
    else:
        for it in needs_approval:
            with st.expander(f"{it['title']}  —  #{it['id'][:8]}"):
                st.write(f"**Client:** {it.get('client','')}  •  **Project:** {it.get('project','')}")
                st.write(f"**Completed at:** {it.get('completed_at')}")
                st.write(f"**Hours:** {it.get('hours')}  •  **Amount:** {it.get('amount')}")
                st.write(f"**PR URL:** {it.get('pr_url') or '*None*'}")
                st.write(f"**Owner approved:** {'Yes' if it.get('owner_approved') else 'No'}")

                # show attachments and comment history
                render_attachments_list(it.get("attachments", []), key_prefix=it["id"])
                render_comment_history(it)

                # Approve button
                if st.button("✅ Approve (move to Approved)", key=f"approve_{it['id']}"):
                    approve_item(st.session_state[STATE_KEY], it['id'])
                    st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                    save_data(st.session_state[STATE_KEY])
                    st.success("Approved (moved to Approved tasks).")
                    st.rerun()

                # Owner review form with attachments (request changes)
                with st.form(f"review_form_{it['id']}", clear_on_submit=True):
                    review_txt = st.text_area("Leave review comments (developer will see this and fix)", value="")
                    owner_files = st.file_uploader("Attach images/files with review (optional)", accept_multiple_files=True)
                    submit_review = st.form_submit_button("Request changes / Send to Developer")
                    if submit_review:
                        if not review_txt.strip():
                            st.warning("Please enter review comments before submitting.")
                        else:
                            request_review(st.session_state[STATE_KEY], it['id'], review_txt.strip(), owner_files)
                            st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                            save_data(st.session_state[STATE_KEY])
                            st.success("Review requested — moved back to developer board for fixes.")
                            st.rerun()

    st.markdown("---")
    st.markdown("## Approved Tasks")
    if not approved:
        st.info("No approved tasks.")
    else:
        for it in approved:
            with st.expander(f"{it['title']}  —  #{it['id'][:8]}"):
                st.write(f"**Client:** {it.get('client','')}  •  **Project:** {it.get('project','')}")
                st.write(f"**Completed at:** {it.get('completed_at')}")
                st.write(f"**Hours:** {it.get('hours')}  •  **Amount:** {it.get('amount')}")
                st.write(f"**PR URL:** {it.get('pr_url') or '*None*'}")
                st.write(f"**Approved at:** {it.get('owner_approved_at') or '*Unknown*'}")
                render_attachments_list(it.get("attachments", []), key_prefix=it["id"])
                render_comment_history(it)
                if st.button("Revoke approval (move back to Needs Approval)", key=f"revoke_{it['id']}"):
                    revoke_approval(st.session_state[STATE_KEY], it['id'])
                    st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                    save_data(st.session_state[STATE_KEY])
                    st.success("Approval revoked.")
                    st.rerun()

    st.markdown("---")
    st.subheader("📑 All Saved Data (Owner view - read only)")
    st.caption("Includes archived and approved items.")
    st.dataframe(
        df_all if not df_all.empty else pd.DataFrame(
            columns=[
                "id","type","title","client","project","billable","status","hours",
                "rate_at_completion","amount","created_at","updated_at","completed_at",
                "archived","pr_url","owner_approved","owner_approved_at","owner_approved_by",
                "review_requested","review_comments","review_requested_at",
                "dev_response_comments","dev_response_at","attachments","comment_history"
            ]
        ),
        use_container_width=True
    )

# =========================
# Page router
# =========================
if page == "owner":
    owner_board()
else:
    developer_board()

# =========================
# Invoice preview (shared)
# =========================
st.markdown("---")
st.subheader("🧾 Invoice Preview (filtered)")
invoice_preview = build_invoice_df(start_d=min_d, end_d=max_d, client_filter="All")
if invoice_preview.empty:
    st.info("No completed, billable items match the invoice filters.")
else:
    currency = st.session_state.billing_currency or ""
    st.dataframe(invoice_preview, use_container_width=True)
    subtotal = float(invoice_preview["Amount"].sum()) if not invoice_preview.empty else 0.0
    tax_amt = round(subtotal * (st.session_state.billing_tax_percent / 100.0), 2) if subtotal > 0 else 0.0
    grand_total = round(subtotal + tax_amt, 2) if subtotal > 0 else 0.0
    st.write(f"**Subtotal:** {currency}{subtotal:.2f}")
    if st.session_state.billing_tax_percent > 0:
        st.write(f"**Tax ({st.session_state.billing_tax_percent:.1f}%):** {currency}{tax_amt:.2f}")
    st.write(f"**Grand Total:** {currency}{grand_total:.2f}")
