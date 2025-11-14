# app.py
import json
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
import io

import pandas as pd
import streamlit as st

# -------------------------
# Files / constants
# -------------------------
DATA_FILE = Path("tasks_data.json")
ATTACH_DIR = Path("attachments")
ATTACH_DIR.mkdir(exist_ok=True)
STATUSES = ["ready", "inprogress", "completed"]
TYPE_OPTIONS = ["task", "defect"]
STATE_KEY = "items"  # st.session_state[STATE_KEY]

# -------------------------
# Simple developer credentials (as requested)
# -------------------------
DEV_USERNAME = "jesweer"
DEV_PASSWORD = "jesBMW518"

# -------------------------
# Helpers: time & files
# -------------------------
def _now_iso() -> str:
    return datetime.now().isoformat()

def _save_uploaded_file(uploaded_file, item_id: str) -> str:
    suffix = Path(uploaded_file.name).suffix
    fname = f"{item_id}_{uuid.uuid4().hex}{suffix}"
    dest = ATTACH_DIR / fname
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return str(dest)

def _read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

# -------------------------
# Persistence
# -------------------------
def load_data() -> List[Dict[str, Any]]:
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return _normalize_loaded(raw)
    except Exception:
        return []

def save_and_persist(items: List[Dict[str, Any]]):
    """Canonical save function used everywhere to persist state to JSON and keep session state synced."""
    cleaned = sanitize_items(items)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)
    st.session_state[STATE_KEY] = cleaned

# -------------------------
# Normalize / sanitize
# -------------------------
def _coerce_item(x: Dict[str, Any]) -> Dict[str, Any]:
    # normalize comment history
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
        # approval/payment/review flags
        "needs_client_approval": bool(x.get("needs_client_approval", False) if isinstance(x, dict) else False),
        "client_approved": bool(x.get("client_approved", False) if isinstance(x, dict) else False),
        "review_requested": bool(x.get("review_requested", False) if isinstance(x, dict) else False),
        "payment_requested": bool(x.get("payment_requested", False) if isinstance(x, dict) else False),
        "payment_confirmed_by_dev": bool(x.get("payment_confirmed_by_dev", False) if isinstance(x, dict) else False),
        "payment_requested_at": x.get("payment_requested_at"),
        "payment_confirmed_at": x.get("payment_confirmed_at"),
        "comment_history": norm_ch,
        "attachments": list(x.get("attachments", []) if isinstance(x, dict) else []),
    }
    if base["status"] not in STATUSES:
        base["status"] = "ready"
    return base

def _normalize_loaded(obj) -> List[Dict[str, Any]]:
    if isinstance(obj, list):
        return [_coerce_item(d) for d in obj if isinstance(d, dict)]
    if isinstance(obj, dict):
        if "items" in obj and isinstance(obj["items"], list):
            return [_coerce_item(d) for d in obj["items"] if isinstance(d, dict)]
        vals = list(obj.values())
        if vals and all(isinstance(v, dict) for v in vals):
            return [_coerce_item(v) for v in vals]
    return []

def sanitize_items(items) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []
    clean = []
    for it in items:
        if isinstance(it, dict):
            clean.append(_coerce_item(it))
    return clean

# -------------------------
# Item utilities & flows
# -------------------------
def new_item(title: str, ttype: str, client: str, project: str, billable: bool):
    now = _now_iso()
    item_id = str(uuid.uuid4())
    return {
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
        "needs_client_approval": False,
        "client_approved": False,
        "review_requested": False,
        "payment_requested": False,
        "payment_confirmed_by_dev": False,
        "payment_requested_at": None,
        "payment_confirmed_at": None,
        "attachments": [],
        "comment_history": [{"actor": "system", "comment": "Task created", "attachments": [], "at": now}],
    }

def get_items_by_status(items, status):
    out = []
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, dict) and it.get("status") == status and not it.get("archived", False):
            out.append(it)
    return out

def append_history(items, item_id: str, actor: str, comment: str, attachment_files: Optional[List[Any]] = None):
    """Add entry to conversation and persist using save_and_persist."""
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
            save_and_persist(items)
            return it
    return None

def developer_complete(items, item_id: str, hours: float, rate: float, dev_comment: str, dev_files: Optional[List[Any]] = None):
    """Developer completes task: must provide hours + comment (attachments optional).
       Task becomes completed and visible to client as Needs Approval (not archived)."""
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["hours"] = float(hours)
            it["rate_at_completion"] = float(rate)
            it["amount"] = round(float(hours) * float(rate), 2)
            it["status"] = "completed"
            it["completed_at"] = _now_iso()
            it["updated_at"] = _now_iso()
            it["archived"] = False
            it["needs_client_approval"] = True
            it["client_approved"] = False
            # append dev comment and persist
            append_history(items, item_id, "dev", dev_comment or "", dev_files)
            save_and_persist(items)
            return it
    return None

def client_approve(items, item_id: str):
    """Client approves: mark approved (keeps in completed list)"""
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["client_approved"] = True
            it["needs_client_approval"] = False
            append_history(items, item_id, "client", "Approved", None)
            it["updated_at"] = _now_iso()
            save_and_persist(items)
            return it
    return None

def client_request_changes(items, item_id: str, comment: str, files: Optional[List[Any]] = None):
    """Client requests changes: set review_requested and send back to developer (inprogress)"""
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["review_requested"] = True
            it["needs_client_approval"] = False
            it["client_approved"] = False
            it["status"] = "inprogress"
            append_history(items, item_id, "client", comment or "", files)
            it["updated_at"] = _now_iso()
            save_and_persist(items)
            return it
    return None

def developer_respond_changes(items, item_id: str, comment: str, files: Optional[List[Any]] = None, hours: Optional[float] = None, rate: Optional[float] = None):
    """Developer responds to change request: append comment, may update hours/rate, then mark completed again and set needs_client_approval True."""
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            append_history(items, item_id, "dev", comment or "", files)
            if hours is not None:
                try:
                    it["hours"] = float(hours)
                except Exception:
                    pass
            if rate is not None:
                try:
                    it["rate_at_completion"] = float(rate)
                except Exception:
                    pass
            if it.get("hours") is not None and it.get("rate_at_completion") is not None:
                try:
                    it["amount"] = round(float(it["hours"]) * float(it["rate_at_completion"]), 2)
                except Exception:
                    pass
            it["status"] = "completed"
            it["completed_at"] = _now_iso()
            it["review_requested"] = False
            it["needs_client_approval"] = True
            it["client_approved"] = False
            it["updated_at"] = _now_iso()
            save_and_persist(items)
            return it
    return None

def client_mark_paid(items, ids: List[str]):
    """Client marks tasks as paid — sets payment_requested flag and timestamp."""
    for it in items:
        if isinstance(it, dict) and it.get("id") in ids:
            it["payment_requested"] = True
            it["payment_requested_at"] = _now_iso()
            append_history(items, it["id"], "client", "Marked as Paid (client)", None)
    save_and_persist(items)

def developer_confirm_payment(items, ids: List[str]):
    """Developer confirms payment: mark payment_confirmed_by_dev True and archive tasks (history)."""
    for it in items:
        if isinstance(it, dict) and it.get("id") in ids:
            it["payment_confirmed_by_dev"] = True
            it["payment_confirmed_at"] = _now_iso()
            it["archived"] = True  # move to history
            append_history(items, it["id"], "dev", "Confirmed receipt of payment", None)
    save_and_persist(items)

# -------------------------
# Session init & defaults
# -------------------------
if STATE_KEY not in st.session_state:
    st.session_state[STATE_KEY] = load_data()
st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])

if "billing_hourly_rate" not in st.session_state:
    st.session_state.billing_hourly_rate = 75.0

# developer login flag
if "dev_logged_in" not in st.session_state:
    st.session_state.dev_logged_in = False

# -------------------------
# Routing: developer or client
# Use st.query_params; ?page=client to show client dashboard exclusively
# -------------------------
params = st.query_params
page = params.get("page", ["developer"])
if isinstance(page, list):
    page = page[0] if page else "developer"

# -------------------------
# Developer login UI & handling
# -------------------------
def developer_login_box():
    st.title("🔐 Developer Login")
    st.info("Please login to access the Developer Dashboard.")
    with st.form("login_form", clear_on_submit=False):
        uname = st.text_input("Username", key="login_username")
        pwd = st.text_input("Password", type="password", key="login_password")
        submit = st.form_submit_button("Login")
        if submit:
            if (uname == DEV_USERNAME) and (pwd == DEV_PASSWORD):
                st.session_state.dev_logged_in = True
                st.success("Logged in — opening Developer Dashboard.")
                # force show developer page in URL
                st.query_params["page"] = ["developer"]
                st.rerun()
            else:
                st.error("Invalid credentials. Please try again.")

def developer_logout():
    if st.sidebar.button("Logout (Developer)"):
        st.session_state.dev_logged_in = False
        st.success("Logged out.")
        # refresh to show login screen
        st.rerun()

# top navigation (only when NOT in strict client page)
if page != "client":
    # If trying to open developer page and not logged in, show login
    if page == "developer" and not st.session_state.dev_logged_in:
        # Minimal left-panel: keep only Add Task for developer? We adhere to prior user request to keep left panel minimal.
        # But login needs to be visible; show login and return early.
        developer_login_box()
        st.stop()
    # If logged in, show logout control in sidebar
    if page == "developer" and st.session_state.dev_logged_in:
        st.sidebar.markdown("---")
        st.sidebar.write("Logged in as developer.")
        developer_logout()

    nav = st.selectbox("Open", ["Developer Dashboard", "Client Dashboard"], index=0 if page == "developer" else 1)
    if nav == "Developer Dashboard" and page != "developer":
        st.query_params["page"] = ["developer"]
        st.rerun()
    if nav == "Client Dashboard" and page != "client":
        st.query_params["page"] = ["client"]
        st.rerun()
else:
    # client-only view; no login required
    st.markdown("### 🔒 Client Dashboard (single-page view)")

# -------------------------
# Sidebar for both: Add Task
# The user requested "remove everything from left panel except add task" earlier.
# We'll show a minimal sidebar: only Add Task and (for developer) hourly rate + logout.
# -------------------------
if page == "developer":
    # Minimal left panel: hourly rate + Add Task + Logout (handled above)
    st.sidebar.header("Developer Settings")
    st.session_state.billing_hourly_rate = st.sidebar.number_input("Default hourly rate (per hour)", min_value=0.0, step=1.0, value=float(st.session_state.billing_hourly_rate), key="rate_setting")
    st.sidebar.markdown("---")
    st.sidebar.header("➕ Add Task / Defect")
    with st.sidebar.form("add_form_dev", clear_on_submit=True):
        ttype = st.selectbox("Type", TYPE_OPTIONS, index=0, key="add_type_dev")
        title = st.text_input("Title", placeholder="Task title", key="add_title_dev")
        client_name = st.text_input("Client (optional)", placeholder="Client name", key="add_client_dev")
        project = st.text_input("Project (optional)", placeholder="Project", key="add_project_dev")
        billable = st.checkbox("Billable", value=True, key="add_billable_dev")
        files = st.file_uploader("Attach images (optional)", accept_multiple_files=True, key="add_files_dev")
        submitted = st.form_submit_button("Create Task")
        if submitted:
            if not title.strip():
                st.sidebar.error("Please enter a title.")
            else:
                item = new_item(title, ttype, client_name, project, billable)
                if files:
                    saved_paths = []
                    for f in files:
                        saved = _save_uploaded_file(f, item["id"])
                        saved_paths.append(saved)
                        item.setdefault("attachments", []).append(saved)
                    item.setdefault("comment_history", []).append({"actor": "dev", "comment": "Initial attachments", "attachments": saved_paths, "at": _now_iso()})
                st.session_state[STATE_KEY].append(item)
                save_and_persist(st.session_state[STATE_KEY])
                st.sidebar.success("Task created.")
elif page == "client":
    # Client sidebar: only Add Task (as requested)
    st.sidebar.header("➕ Client: Add Task / Defect")
    with st.sidebar.form("add_form_client", clear_on_submit=True):
        ttype = st.selectbox("Type", TYPE_OPTIONS, index=0, key="add_type_client")
        title = st.text_input("Title", placeholder="Task title", key="add_title_client")
        project = st.text_input("Project (optional)", placeholder="Project", key="add_project_client")
        billable = st.checkbox("Billable", value=True, key="add_billable_client")
        files = st.file_uploader("Attach images (optional)", accept_multiple_files=True, key="add_files_client")
        submitted = st.form_submit_button("Create Task")
        if submitted:
            if not title.strip():
                st.sidebar.error("Please enter a title.")
            else:
                item = new_item(title, ttype, "Client", project, billable)
                if files:
                    saved_paths = []
                    for f in files:
                        saved = _save_uploaded_file(f, item["id"])
                        saved_paths.append(saved)
                        item.setdefault("attachments", []).append(saved)
                    item.setdefault("comment_history", []).append({"actor": "client", "comment": "Initial attachments", "attachments": saved_paths, "at": _now_iso()})
                st.session_state[STATE_KEY].append(item)
                save_and_persist(st.session_state[STATE_KEY])
                st.sidebar.success("Task created.")

# Build df_all for tables
items_list = sanitize_items(st.session_state[STATE_KEY])
df_all = pd.DataFrame(items_list) if items_list else pd.DataFrame(columns=[
    "id","type","title","client","project","billable","status","hours","rate_at_completion","amount","created_at","updated_at","completed_at","archived",
    "needs_client_approval","client_approved","review_requested","payment_requested","payment_confirmed_by_dev","comment_history","attachments"
])

# -------------------------
# Download helpers (CSV + JSON)
# -------------------------
def render_download_buttons(df: pd.DataFrame, key_prefix: str = "all"):
    """Render CSV download button and JSON download button side-by-side."""
    if df is None or df.empty:
        return
    # Prepare CSV bytes
    try:
        csv_bytes = df.to_csv(index=False).encode("utf-8")
    except Exception:
        csv_bytes = "".encode("utf-8")
    # Prepare JSON bytes (use orient records for readable list-of-objects)
    try:
        json_records = df.to_dict(orient="records")
        json_bytes = json.dumps(json_records, indent=2, ensure_ascii=False).encode("utf-8")
    except Exception:
        try:
            json_bytes = json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False).encode("utf-8")
        except Exception:
            json_bytes = "[]".encode("utf-8")

    c1, c2 = st.columns([1,1])
    # CSV download first
    with c1:
        st.download_button(
            label="⬇ Download CSV",
            data=csv_bytes,
            file_name=f"tasks_{key_prefix}.csv",
            mime="text/csv",
            key=f"dl_csv_{key_prefix}"
        )
    # JSON download immediately after CSV (icon right after)
    with c2:
        st.download_button(
            label="🗒️ Download JSON",
            data=json_bytes,
            file_name=f"tasks_{key_prefix}.json",
            mime="application/json",
            key=f"dl_json_{key_prefix}"
        )

# -------------------------
# UI Helpers: attachments & conversation history
# -------------------------
def render_attachments_list(attachments: List[str], key_prefix: str):
    if not attachments:
        return
    for idx, p in enumerate(attachments):
        try:
            pth = Path(p)
            if not pth.exists():
                st.caption(f"Missing attachment: {p}")
                continue
            try:
                st.image(str(pth), caption=pth.name, use_column_width=False)
            except Exception:
                st.write(f"Attachment: {pth.name}")
            data = _read_file_bytes(str(pth))
            st.download_button(label=f"Download {pth.name}", data=data, file_name=pth.name, key=f"dl_{key_prefix}_{idx}")
        except Exception as e:
            st.write("Attachment error:", e)

def render_comment_history(item: Dict[str, Any]):
    history = item.get("comment_history", []) or []
    if not history:
        st.info("No conversation yet.")
        return
    history = sorted(history, key=lambda e: e.get("at", ""))
    st.markdown("#### Conversation / Chat History")
    for entry in history:
        actor = entry.get("actor", "system")
        at = entry.get("at", "")
        comment = entry.get("comment", "")
        attachments = entry.get("attachments", []) or []
        if actor == "client":
            bg = "#e6f2ff"
            label = "Client"
        elif actor == "dev":
            bg = "#e8ffe6"
            label = "Developer"
        else:
            bg = "#f5f5f5"
            label = "System"
        safe_comment = (comment.replace("\n", "<br/>") if comment else "")
        html = f"""
        <div style="background:{bg};padding:10px;border-radius:8px;margin-bottom:8px;border:1px solid #ddd;color:#000;">
          <strong>{label}</strong> <span style="color:#666;font-size:12px"> — {at.replace('T',' ')[:19]}</span>
          <div style="margin-top:6px;font-size:14px;color:#000;">{safe_comment}</div>
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)
        if attachments:
            render_attachments_list(attachments, key_prefix=f"{item['id']}_{actor}_{at}")

# -------------------------
# Developer Dashboard
# -------------------------
def developer_dashboard():
    st.title("👨‍💻 Developer Dashboard")
    st.caption("Use this board to manage tasks. When you complete a task you must enter hours + comment and can attach images. Completed tasks become visible to Client for approval.")

    # KPIs
    ready = get_items_by_status(st.session_state[STATE_KEY], "ready")
    inprog = get_items_by_status(st.session_state[STATE_KEY], "inprogress")
    # special section: tasks returned by client (review_requested True)
    needs_dev_response = [it for it in st.session_state[STATE_KEY] if it.get("review_requested") and not it.get("archived")]
    payments_pending = [it for it in st.session_state[STATE_KEY] if it.get("payment_requested") and not it.get("payment_confirmed_by_dev") and not it.get("archived")]

    st.subheader("Overview")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Ready", len(ready))
    col2.metric("In Progress", len(inprog))
    col3.metric("Needs Dev Response", len(needs_dev_response))
    col4.metric("Payment Requests", len(payments_pending))

    st.markdown("---")
    st.subheader("Needs Developer Response (sent back by client)")
    if not needs_dev_response:
        st.info("No tasks sent back by client.")
    else:
        for it in needs_dev_response:
            with st.expander(f"{it['title']} — #{it['id'][:8]}"):
                st.write(f"Client: {it.get('client','')}  •  Project: {it.get('project','')}")
                render_attachments_list(it.get("attachments", []), key_prefix=it["id"])
                render_comment_history(it)
                # Developer must provide comment and optionally attachments/hours/rate
                with st.form(f"dev_resp_form_{it['id']}", clear_on_submit=False):
                    dev_comment = st.text_area("Response to client (REQUIRED)", key=f"dev_resp_{it['id']}")
                    add_files = st.file_uploader("Attach images/files (optional)", accept_multiple_files=True, key=f"dev_resp_files_{it['id']}")
                    new_hours = st.number_input("Hours (optional - leave 0 to keep)", min_value=0.0, step=0.25, value=float(it.get("hours") or 0.0), key=f"dev_resp_hours_{it['id']}")
                    new_rate = st.number_input("Rate (optional)", min_value=0.0, step=1.0, value=float(it.get("rate_at_completion") or st.session_state.billing_hourly_rate), key=f"dev_resp_rate_{it['id']}")
                    submit = st.form_submit_button("Submit changes back to client (will mark completed & needs approval)")
                    if submit:
                        if not dev_comment.strip():
                            st.warning("Response comment is required.")
                        else:
                            files_list = add_files if add_files else []
                            developer_respond_changes(st.session_state[STATE_KEY], it["id"], dev_comment.strip(), files_list, hours=(new_hours if new_hours>0 else None), rate=(new_rate if new_rate>0 else None))
                            st.success("Submitted back to client for approval.")
                            st.rerun()

    st.markdown("---")
    st.subheader("Kanban")
    cols = st.columns(2)
    # Ready column
    with cols[0]:
        st.markdown("### Ready")
        if not ready:
            st.info("No ready tasks.")
        else:
            for it in ready:
                with st.container():
                    st.markdown(f"**{it['title']}**  \n*{it['type']}* • `#{it['id'][:8]}`")
                    st.caption(f"Client: {it.get('client','')}  • Project: {it.get('project','')}")
                    render_attachments_list(it.get("attachments", []), key_prefix=it["id"])
                    render_comment_history(it)
                    c1, c2, c3 = st.columns([1,1,1])
                    if c1.button("→ In Progress", key=f"to_inprog_{it['id']}"):
                        set_status_local(it["id"], "inprogress")
                        st.rerun()
                    if c2.button("Edit", key=f"edit_{it['id']}"):
                        with st.form(f"edit_form_{it['id']}", clear_on_submit=False):
                            new_title = st.text_input("Title", value=it["title"], key=f"title_edit_{it['id']}")
                            new_client = st.text_input("Client", value=it.get("client",""), key=f"client_edit_{it['id']}")
                            new_project = st.text_input("Project", value=it.get("project",""), key=f"project_edit_{it['id']}")
                            add_files = st.file_uploader("Add attachments", accept_multiple_files=True, key=f"edit_files_{it['id']}")
                            save = st.form_submit_button("Save")
                            if save:
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
                                save_and_persist(st.session_state[STATE_KEY])
                                st.success("Saved.")
                                st.rerun()
                    if c3.button("Delete", key=f"del_{it['id']}"):
                        st.session_state[STATE_KEY] = [x for x in st.session_state[STATE_KEY] if x.get("id") != it["id"]]
                        save_and_persist(st.session_state[STATE_KEY])
                        st.rerun()

    # In Progress column
    with cols[1]:
        st.markdown("### In Progress")
        if not inprog:
            st.info("No in-progress tasks.")
        else:
            for it in inprog:
                with st.container():
                    st.markdown(f"**{it['title']}**  \n*{it['type']}* • `#{it['id'][:8]}`")
                    st.caption(f"Client: {it.get('client','')}  • Project: {it.get('project','')}")
                    render_attachments_list(it.get("attachments", []), key_prefix=it["id"])
                    render_comment_history(it)

                    # INLINE completion form for reliability:
                    with st.form(f"complete_form_inline_{it['id']}", clear_on_submit=False):
                        st.markdown("**Complete task & send to client**")
                        hours = st.number_input("Hours worked (required)", min_value=0.0, step=0.25, value=float(it.get("hours") or 0.0), key=f"hours_complete_{it['id']}")
                        rate = st.number_input("Rate (per hour)", min_value=0.0, step=1.0, value=float(it.get("rate_at_completion") or st.session_state.billing_hourly_rate), key=f"rate_complete_{it['id']}")
                        dev_comment = st.text_area("Comments for client (required)", key=f"dev_comment_complete_{it['id']}")
                        add_files = st.file_uploader("Attach images (optional)", accept_multiple_files=True, key=f"complete_files_{it['id']}")
                        submit_complete = st.form_submit_button("Complete & Send to Client (Requires comment)")
                        if submit_complete:
                            files_list = list(add_files) if add_files else []
                            if not dev_comment or not dev_comment.strip():
                                st.warning("Please provide a comment for the client before completing.")
                            elif (hours is None) or (hours == 0):
                                st.warning("Please enter hours worked (can be fractional).")
                            else:
                                developer_complete(st.session_state[STATE_KEY], it["id"], hours, rate, dev_comment.strip(), dev_files=files_list)
                                st.success("Task completed and sent to client for approval.")
                                st.rerun()

                    c1, c2 = st.columns([1,1])
                    if c1.button("↩ Ready", key=f"back_ready_{it['id']}"):
                        set_status_local(it["id"], "ready")
                        st.rerun()
                    if c2.button("Delete", key=f"del2_{it['id']}"):
                        st.session_state[STATE_KEY] = [x for x in st.session_state[STATE_KEY] if x.get("id") != it["id"]]
                        save_and_persist(st.session_state[STATE_KEY])
                        st.rerun()

    st.markdown("---")
    st.subheader("Payments Requests (Pending confirmation)")
    payments_pending = [it for it in st.session_state[STATE_KEY] if it.get("payment_requested") and not it.get("payment_confirmed_by_dev") and not it.get("archived")]
    if not payments_pending:
        st.info("No payment requests.")
    else:
        for it in payments_pending:
            with st.expander(f"{it['title']} — #{it['id'][:8]}"):
                st.write(f"Client: {it.get('client','')}, Amount: {it.get('amount')}")
                render_comment_history(it)
                if st.button("Confirm payment received", key=f"confirm_pay_{it['id']}"):
                    developer_confirm_payment(st.session_state[STATE_KEY], [it["id"]])
                    st.success("Payment confirmed and task archived.")
                    st.rerun()

    st.markdown("---")
    st.subheader("Completed / Archived Tasks Table")
    # Show completed or archived tasks
    show_table = [it for it in st.session_state[STATE_KEY] if (it.get("status") == "completed" or it.get("archived"))]
    df_table = pd.DataFrame(show_table) if show_table else pd.DataFrame(columns=["id","title","client","project","hours","rate_at_completion","amount","status","archived"])
    if df_table.empty:
        st.info("No completed or archived tasks yet.")
    else:
        view = df_table[["id","title","type","client","project","hours","rate_at_completion","amount","status","archived"]].copy()
        view["id"] = view["id"].apply(lambda x: x[:8])
        st.dataframe(view, width="stretch")
        total_hours = float(df_table["hours"].fillna(0).sum())
        total_bill = float(df_table["amount"].fillna(0).sum())
        st.markdown(f"**Totals (shown rows):** Hours = {total_hours:.2f} h  •  Bill = {total_bill:.2f}")

    st.markdown("---")
    st.subheader("All tasks (raw JSON)")
    # render download buttons (CSV + JSON) side-by-side, JSON right after CSV
    render_download_buttons(df_all, key_prefix="developer_all")
    st.dataframe(df_all, width="stretch")

# helper to set status quickly (and persist)
def set_status_local(item_id: str, new_status: str):
    for it in st.session_state[STATE_KEY]:
        if it.get("id") == item_id:
            it["status"] = new_status
            it["updated_at"] = _now_iso()
            if new_status != "completed":
                it["completed_at"] = None
            save_and_persist(st.session_state[STATE_KEY])
            return

# -------------------------
# Client Dashboard (single page)
# -------------------------
def client_dashboard():
    st.title("👤 Client Dashboard")
    st.caption("Client view is single-page: approve, request changes, or mark paid. Client cannot navigate to other pages.")

    st.markdown("### Tasks needing your attention")
    needs_approval = [it for it in st.session_state[STATE_KEY] if it.get("status") == "completed" and it.get("needs_client_approval") and not it.get("archived")]
    approved = [it for it in st.session_state[STATE_KEY] if it.get("status") == "completed" and it.get("client_approved") and not it.get("archived")]

    # ---------- Fixed: always-render Request Changes form inside each expander ----------
    st.markdown("#### Needs Approval")
    if not needs_approval:
        st.info("No tasks waiting for approval.")
    else:
        for it in needs_approval:
            with st.expander(f"{it['title']} — #{it['id'][:8]}"):
                st.write(f"Developer hours: {it.get('hours')}  •  Amount: {it.get('amount')}")
                render_attachments_list(it.get("attachments", []), key_prefix=it["id"])
                render_comment_history(it)

                cols = st.columns([1,1])
                # Approve button (quick action)
                if cols[0].button("✅ Approve", key=f"c_approve_{it['id']}"):
                    client_approve(st.session_state[STATE_KEY], it["id"])
                    st.success("Approved.")
                    st.rerun()

                # Always-visible Request Changes form (no outer button)
                with cols[1]:
                    st.markdown("**↩ Request changes (send back to developer)**")
                    with st.form(f"client_req_form_{it['id']}", clear_on_submit=True):
                        comment = st.text_area("Describe changes required (required)", key=f"req_comment_{it['id']}")
                        owner_files = st.file_uploader("Attach images (optional)", accept_multiple_files=True, key=f"req_files_{it['id']}")
                        send = st.form_submit_button("Send to Developer")
                        if send:
                            if not comment or not comment.strip():
                                st.warning("Please provide comments explaining required changes.")
                            else:
                                files_list = list(owner_files) if owner_files else []
                                client_request_changes(st.session_state[STATE_KEY], it['id'], comment.strip(), files_list if files_list else None)
                                st.success("Sent back to developer for fixes.")
                                st.rerun()
    # -------------------------------------------------------------------------

    st.markdown("---")
    st.markdown("#### Approved Tasks")
    if not approved:
        st.info("No approved tasks.")
    else:
        for it in approved:
            with st.expander(f"{it['title']} — #{it['id'][:8]}"):
                st.write(f"Hours: {it.get('hours')} • Amount: {it.get('amount')}")
                render_attachments_list(it.get("attachments", []), key_prefix=it["id"])
                render_comment_history(it)

    st.markdown("---")
    st.subheader("Mark Approved Tasks as Paid (select date range)")
    col1, col2 = st.columns(2)
    start_d = col1.date_input("From", value=date.today())
    end_d = col2.date_input("To", value=date.today())
    def in_range(iso):
        try:
            d = datetime.fromisoformat(iso).date()
        except Exception:
            return False
        return (d >= start_d) and (d <= end_d)
    approved_in_range = [it for it in approved if it.get("completed_at") and in_range(it.get("completed_at")) and not it.get("payment_requested")]
    if not approved_in_range:
        st.info("No approved tasks in selected date range available for payment.")
    else:
        ids = []
        for it in approved_in_range:
            checked = st.checkbox(f"{it['title']} — {it.get('amount')} — #{it['id'][:8]}", key=f"pay_chk_{it['id']}")
            if checked:
                ids.append(it["id"])
        if ids:
            if st.button("Mark selected as Paid"):
                client_mark_paid(st.session_state[STATE_KEY], ids)
                st.success("Marked as Paid — developer will confirm receipt.")
                st.rerun()

    st.markdown("---")
    st.subheader("All tasks (client view)")
    # render download buttons (CSV + JSON) with JSON right after CSV
    render_download_buttons(df_all, key_prefix="client_all")
    st.dataframe(df_all, width="stretch")

# -------------------------
# Page routing & launch
# -------------------------
if page == "client":
    client_dashboard()
else:
    developer_dashboard()
