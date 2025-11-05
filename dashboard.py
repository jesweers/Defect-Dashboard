import json
import uuid
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any
import io

import pandas as pd
import streamlit as st

# =========================
# Files & constants
# =========================
DATA_FILE = Path("tasks_data.json")
STATUSES = ["ready", "inprogress", "completed"]
TYPE_OPTIONS = ["task", "defect"]
STATE_KEY = "items"  # stored in st.session_state[STATE_KEY]

# =========================
# Persistence helpers (robust)
# =========================
def _coerce_item(x: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure an item has all expected keys."""
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
        "created_at": (x.get("created_at") if isinstance(x, dict) else datetime.now().isoformat()) or datetime.now().isoformat(),
        "updated_at": (x.get("updated_at") if isinstance(x, dict) else datetime.now().isoformat()) or datetime.now().isoformat(),
        "completed_at": (x.get("completed_at") if isinstance(x, dict) else None),
        "archived": bool(x.get("archived", False) if isinstance(x, dict) else False),
        # owner / review fields
        "pr_url": str(x.get("pr_url", "") if isinstance(x, dict) else "").strip(),
        "owner_approved": bool(x.get("owner_approved", False) if isinstance(x, dict) else False),
        "owner_approved_at": (x.get("owner_approved_at") if isinstance(x, dict) else None),
        "owner_approved_by": (x.get("owner_approved_by") if isinstance(x, dict) else None),
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
    now = datetime.now().isoformat()
    return {
        "id": str(uuid.uuid4()),
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
    }

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
            it["updated_at"] = datetime.now().isoformat()
            if new_status != "completed":
                it["completed_at"] = None
            return it
    return None

def set_hours_and_complete(items, item_id, hours: float, rate_now: float):
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["hours"] = float(hours)
            it["status"] = "completed"
            it["completed_at"] = datetime.now().isoformat()
            it["updated_at"] = datetime.now().isoformat()
            it["rate_at_completion"] = float(rate_now)
            it["amount"] = round(float(hours) * float(rate_now), 2)
            return it
    return None

def set_archived(items, item_id, archived=True):
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["archived"] = bool(archived)
            it["updated_at"] = datetime.now().isoformat()
            return it
    return None

# =========================
# Owner approval (modified behavior)
#  - Do NOT archive on approve.
#  - Move between Needs Approval and Approved lists via owner_approved flag.
# =========================
def approve_item(items, item_id):
    """Mark an item as owner approved (no name required) and keep it visible."""
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["owner_approved"] = True
            it["owner_approved_at"] = datetime.now().isoformat()
            it["owner_approved_by"] = None
            it["updated_at"] = datetime.now().isoformat()
            # DO NOT set archived here so Owner can see Approved tasks
            return it
    return None

def revoke_approval(items, item_id):
    for it in items:
        if isinstance(it, dict) and it.get("id") == item_id:
            it["owner_approved"] = False
            it["owner_approved_at"] = None
            it["owner_approved_by"] = None
            it["updated_at"] = datetime.now().isoformat()
            return it
    return None

def validate_for_approval(it: Dict[str, Any], max_age_days: int, require_pr: bool) -> (bool, str):
    """Return (ok, reason). Checks completed_at within max_age_days and presence of pr_url if required."""
    if not it.get("completed_at"):
        return False, "Not completed"
    try:
        completed_dt = datetime.fromisoformat(it["completed_at"]) if isinstance(it["completed_at"], str) else None
    except Exception:
        completed_dt = None
    if not completed_dt:
        return False, "Invalid completed_at"
    age = datetime.now() - completed_dt
    if age > timedelta(days=max_age_days):
        return False, f"Completed {age.days} days ago — exceeds {max_age_days}d limit"
    if require_pr and not it.get("pr_url"):
        return False, "Missing PR URL"
    return True, "OK"

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

# billing defaults (kept but NOT exposed in sidebar)
if "billing_currency" not in st.session_state:
    st.session_state.billing_currency = "$"
if "billing_hourly_rate" not in st.session_state:
    st.session_state.billing_hourly_rate = 75.0
if "billing_tax_percent" not in st.session_state:
    st.session_state.billing_tax_percent = 0.0

# auto_archive default (kept internal; not in sidebar)
AUTO_ARCHIVE_DEFAULT = False

# =========================
# Routing / Navigation
#  - Sidebar will only contain Add Task form (user requested).
#  - Provide a small top-level selector for switching pages when not on owner page.
# =========================
params = st.query_params
page = params.get("page", ["developer"])
if isinstance(page, list):
    page = page[0] if page else "developer"

# Top-level navigation control (visible only on developer/visitor pages).
# Owner page will not show this control (so Owner can't navigate to Developer).
if page != "owner":
    nav_sel = st.selectbox("View", ["Developer Board", "Owner Board"], index=0 if page == "developer" else 1)
    target = "developer" if nav_sel == "Developer Board" else "owner"
    if target != page:
        st.query_params["page"] = [target]
        st.rerun()
else:
    # on owner page, show a plain header (no switching controls)
    st.markdown("### 🔒 Owner Board (read-only)")

# -------------------------
# Sidebar: ONLY Add Task / Defect (per request)
# -------------------------
st.sidebar.header("➕ Add Task / Defect")
with st.sidebar.form("add_form", clear_on_submit=True):
    ttype = st.selectbox("Type", TYPE_OPTIONS, index=0)
    title = st.text_input("Title", placeholder="e.g., Fix checkout crash")
    client = st.text_input("Client", placeholder="e.g., Acme Corp")
    project = st.text_input("Project", placeholder="e.g., Website Revamp")
    billable = st.checkbox("Billable", value=True)
    submitted = st.form_submit_button("Add to Board")
    if submitted:
        if not title.strip():
            st.sidebar.error("Please enter a title.")
        else:
            st.session_state[STATE_KEY].append(new_item(title, ttype, client, project, billable))
            st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
            save_data(st.session_state[STATE_KEY])
            st.sidebar.success("Added!")

# Build DataFrame safely
items_list = sanitize_items(st.session_state[STATE_KEY])
df_all = pd.DataFrame(items_list) if items_list else pd.DataFrame(
    columns=["id","type","title","client","project","billable","status","hours",
             "rate_at_completion","amount","created_at","updated_at","completed_at","archived","pr_url","owner_approved","owner_approved_at","owner_approved_by"]
)

total_hours_all = float(df_all["hours"].fillna(0).sum()) if not df_all.empty else 0.0
total_hours_billable = float(df_all.loc[(df_all["billable"] == True), "hours"].fillna(0).sum()) if not df_all.empty else 0.0

# =========================
# Invoice helpers (kept as-is)
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

date_sel = st.empty()  # placeholder; invoice filter UI not in sidebar anymore

def build_invoice_df(start_d=date.today(), end_d=date.today(), client_filter="All"):
    if df_all.empty:
        return pd.DataFrame(columns=["Date","Title","Type","Client","Project","Hours","Rate","Amount"])

    df = df_all.copy()
    # Only completed, billable, with hours (archived or not — invoice should include them)
    df = df[(df["status"] == "completed") & (df["billable"] == True) & df["hours"].notna()]

    # Client filter
    if client_filter != "All":
        df = df[df["client"] == client_filter]

    # Date range filter
    def in_range(iso):
        d = parse_iso_d(iso)
        if not d:
            return False
        return (d >= start_d) and (d <= end_d)
    df = df[df["completed_at"].apply(in_range)]

    if df.empty:
        return pd.DataFrame(columns=["Date","Title","Type","Client","Project","Hours","Rate","Amount"])

    # Rate fallback: use rate_at_completion if present; else current setting
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
# Developer Board (Kanban) UI
# =========================
def developer_board():
    st.title("📋 Developer Board: Tasks & Defects")
    st.caption("Completed items are hidden from Kanban by default. Use the Developer controls to edit.")

    # KPIs (active = not archived)
    active_ready = len(get_items_by_status(st.session_state[STATE_KEY], "ready"))
    active_inprog = len(get_items_by_status(st.session_state[STATE_KEY], "inprogress"))
    active_completed = len([it for it in st.session_state[STATE_KEY] if it["status"] == "completed" and not it.get("archived", False)])

    colA, colB, colC, colD, colE = st.columns(5)
    colA.metric("Ready (active)", active_ready)
    colB.metric("In Progress (active)", active_inprog)
    colC.metric("Completed (active)", active_completed)
    colD.metric("Total Hours (all)", f"{total_hours_all:.2f} h")
    colE.metric("Billable Hours", f"{total_hours_billable:.2f} h")

    st.markdown("---")
    st.subheader("🧱 Kanban Board")

    board_statuses = ["ready", "inprogress", "completed"]
    status_titles_map = {"ready": "Ready", "inprogress": "In Progress", "completed": "Completed"}
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
                        (f" • Completed: {str(it['completed_at'])[:19].replace('T',' ')}" if it['completed_at'] else "")
                    )

                    # show PR link if present
                    if it.get("pr_url"):
                        st.markdown(f"PR: {it.get('pr_url')}")

                    # Hours edit/complete mode
                    if st.session_state.awaiting_hours_id == it["id"]:
                        with st.form(f"hours_form_{it['id']}"):
                            default_hours = float(it["hours"] or 0.0)
                            default_rate = float(it["rate_at_completion"]) if it.get("rate_at_completion") else float(st.session_state.billing_hourly_rate)
                            hrs = st.number_input("Hours worked", min_value=0.0, step=0.25, value=default_hours, key=f"hrs_input_{it['id']}")
                            rate_now = st.number_input("Lock rate (per hour)", min_value=0.0, step=50.0,
                                                       value=default_rate, key=f"rate_input_{it['id']}")
                            c1, c2 = st.columns(2)
                            save_btn = c1.form_submit_button("Save Hours & Complete")
                            cancel_btn = c2.form_submit_button("Cancel")
                            if save_btn:
                                updated = set_hours_and_complete(st.session_state[STATE_KEY], it["id"], hrs, rate_now)
                                # developer chooses whether to archive completed items via Developer actions
                                st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                save_data(st.session_state[STATE_KEY])
                                st.session_state.awaiting_hours_id = None
                                st.session_state.awaiting_action = None
                                st.success("Saved & completed.")
                                st.rerun()
                            if cancel_btn:
                                st.session_state.awaiting_hours_id = None
                                st.session_state.awaiting_action = None
                                st.info("Cancelled.")
                                st.rerun()
                    else:
                        # Normal action buttons based on current status
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
                            if c3.button("Edit", key=f"edit_meta_{it['id']}"):
                                with st.form(f"edit_form_{it['id']}"):
                                    new_title = st.text_input("Title", value=it["title"])
                                    new_client = st.text_input("Client", value=it["client"])
                                    new_project = st.text_input("Project", value=it["project"])
                                    new_billable = st.checkbox("Billable", value=bool(it["billable"]))
                                    ok = st.form_submit_button("Save")
                                    if ok:
                                        it["title"] = new_title.strip()
                                        it["client"] = new_client.strip()
                                        it["project"] = new_project.strip()
                                        it["billable"] = bool(new_billable)
                                        it["updated_at"] = datetime.now().isoformat()
                                        st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                        save_data(st.session_state[STATE_KEY])
                                        st.rerun()

                        elif status == "inprogress":
                            c1, c2, c3 = st.columns(3)
                            if c1.button("↩ Ready", key=f"back_ready_{it['id']}"):
                                set_status(st.session_state[STATE_KEY], it["id"], "ready")
                                st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                save_data(st.session_state[STATE_KEY])
                                st.rerun()
                            if c2.button("✓ Complete", key=f"complete_{it['id']}"):
                                st.session_state.awaiting_hours_id = it["id"]
                                st.session_state.awaiting_action = "complete"
                                st.rerun()
                            if c3.button("Delete", key=f"del_{it['id']}"):
                                st.session_state[STATE_KEY] = [
                                    x for x in st.session_state[STATE_KEY]
                                    if isinstance(x, dict) and x.get("id") != it["id"]
                                ]
                                st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                save_data(st.session_state[STATE_KEY])
                                st.rerun()

                        elif status == "completed":
                            # Developers still get archive/edit/delete controls
                            c1, c2, c3, c4 = st.columns(4)
                            if c1.button("✏ Edit Hours", key=f"edit_{it['id']}"):
                                st.session_state.awaiting_hours_id = it["id"]
                                st.session_state.awaiting_action = "edit"
                                st.rerun()
                            if c2.button("↩ In Progress", key=f"back_inprog_{it['id']}"):
                                set_status(st.session_state[STATE_KEY], it["id"], "inprogress")
                                set_archived(st.session_state[STATE_KEY], it["id"], False)
                                st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                save_data(st.session_state[STATE_KEY])
                                st.rerun()
                            if c3.button("🗂 Archive (hide)", key=f"archive_{it['id']}"):
                                set_archived(st.session_state[STATE_KEY], it["id"], True)
                                st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                save_data(st.session_state[STATE_KEY])
                                st.rerun()
                            if c4.button("🗑 Delete", key=f"del_{it['id']}"):
                                st.session_state[STATE_KEY] = [
                                    x for x in st.session_state[STATE_KEY]
                                    if isinstance(x, dict) and x.get("id") != it["id"]
                                ]
                                st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                                save_data(st.session_state[STATE_KEY])
                                st.rerun()

    st.markdown("---")
    st.subheader("📑 All Saved Data")
    st.caption("Everything currently in your JSON file (including archived).")
    st.dataframe(
        df_all if not df_all.empty else pd.DataFrame(
            columns=["id","type","title","client","project","billable","status","hours",
                     "rate_at_completion","amount","created_at","updated_at","completed_at","archived","pr_url","owner_approved","owner_approved_at","owner_approved_by"]
        ),
        use_container_width=True
    )

    st.markdown(f"**JSON file:** `{DATA_FILE.resolve()}`")

# =========================
# Owner Board UI (two sections)
# =========================
def owner_board():
    st.title("🔒 Owner Board: Needs Approval / Approved")
    st.caption("Owner view is read-only except for Approve / Revoke. Approving moves tasks from Needs Approval → Approved.")

    # Owner controls: filtering options (read-only)
    col1, col2 = st.columns(2)
    max_age_days = col1.number_input("Max age (days) for approval", min_value=0, max_value=365, value=30)
    require_pr = col2.checkbox("Require Bitbucket PR URL to approve", value=True)

    # Separate lists
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

                ok, reason = validate_for_approval(it, max_age_days, require_pr)
                if ok:
                    if st.button("✅ Approve (move to Approved)", key=f"approve_{it['id']}"):
                        approve_item(st.session_state[STATE_KEY], it['id'])
                        st.session_state[STATE_KEY] = sanitize_items(st.session_state[STATE_KEY])
                        save_data(st.session_state[STATE_KEY])
                        st.success("Approved (moved to Approved tasks).")
                        st.rerun()
                else:
                    st.error(f"Cannot approve: {reason}")

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
            columns=["id","type","title","client","project","billable","status","hours",
                     "rate_at_completion","amount","created_at","updated_at","completed_at","archived","pr_url","owner_approved","owner_approved_at","owner_approved_by"]
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
# Invoice preview (shared at bottom of pages if needed)
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
