#!/usr/bin/env python3
"""
extract.py — APIM/EAH/PATRIC extractor

Behavior
- Pull APIM/EAH/PATRIC candidates from Agile board summaries
- Select candidates for target ISO week/year using transition date logic
- Preserve already-selected enablers for the same week (no delete, only add)
- Write Linked_Issues_Report.txt
- Update weekly_stopper.json
"""

from dotenv import load_dotenv
load_dotenv()

import os
import sys
import re
import json
import datetime
from typing import List, Dict

import requests

JIRA_BASE = "https://stla-iotpf-jira.atlassian.net"
BOARD_ID = 35
QUICKFILTER_ID = 169
VALIDATION_TRIGGER_STATUS = "Ready for validation"

USERNAME = os.getenv("JIRA_USERNAME")
API_TOKEN = os.getenv("JIRA_API_TOKEN")

if not USERNAME or not API_TOKEN:
    raise RuntimeError(
        "Missing JIRA credentials. Ensure JIRA_USERNAME and JIRA_API_TOKEN are set."
    )

LINKED_FILE = os.getenv("LINKED_FILE", "Linked_Issues_Report.txt")
WEEKLY_STOPPER = os.getenv("WEEKLY_STOPPER", "weekly_stopper.json")

APIM_RE = re.compile(r"APIM[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
EAH_RE = re.compile(r"EAH[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
PATRIC_RE = re.compile(r"PATRIC[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDR_RE = re.compile(r"VDR[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
PATRIC_SSDP_RE = re.compile(r"PATRIC[-_\s]*SSDP[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
DATACHAIN_MONITOR_RE = re.compile(r"DATACHAIN_MONITOR[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDP_PROC_2_RE = re.compile(r"VDP_PROC[_\s-]*2[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDP_PROC_RE = re.compile(r"VDP_PROC[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDP_STORE_2_RE = re.compile(r"VDP_STORE[_\s-]*2[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDP_STORE_RE = re.compile(r"VDP_STORE[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDP_DS_MON_RE = re.compile(r"VDP_DS[_\s-]*MON[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDP_DS_SSDP_RE = re.compile(r"VDP_DS[_\s-]*SSDP[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDP_DS_2_RE = re.compile(r"VDP_DS[_\s-]*2[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)
VDP_DS_RE = re.compile(r"VDP_DS[-\s]*([0-9]+\.[0-9]+\.[0-9]+)", re.IGNORECASE)

SESSION = requests.Session()
SESSION.auth = (USERNAME, API_TOKEN)
SESSION.headers.update({"Accept": "application/json"})


def parse_week_arg(raw: str):
    if not raw:
        return None, None
    raw = raw.strip()
    m = re.match(r"^(?P<year>\d{4})[-_ ]*W?(?P<week>\d{1,2})$", raw)
    if m:
        return int(m.group("year")), int(m.group("week"))
    m2 = re.match(r"^W?(?P<week>\d{1,2})$", raw)
    if m2:
        return None, int(m2.group("week"))
    return None, None


def weeks_in_year(year: int) -> int:
    return datetime.date(year, 12, 28).isocalendar()[1]


def parse_iso_date(date_str: str):
    if not date_str:
        return None
    try:
        if "T" in date_str:
            return datetime.datetime.strptime(date_str.split("T")[0], "%Y-%m-%d").date()
        return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", date_str or "")
        if not m:
            return None
        try:
            return datetime.datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except Exception:
            return None


def vtuple(v: str):
    try:
        return tuple(int(x) for x in re.findall(r"\d+", v or ""))
    except Exception:
        return ()


def load_stopper() -> dict:
    if not os.path.exists(WEEKLY_STOPPER):
        return {}
    try:
        with open(WEEKLY_STOPPER, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_stopper(data: dict):
    with open(WEEKLY_STOPPER, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def agile_board_issues(board_id: int, quickfilter=None, max_per_page=200) -> List[dict]:
    results = []
    start_at = 0
    while True:
        url = f"{JIRA_BASE}/rest/agile/1.0/board/{board_id}/issue"
        params = {
            "startAt": start_at,
            "maxResults": max_per_page,
            "fields": "summary,status,assignee,issuetype,customfield_10041,customfield_10042,customfield_10043,customfield_10044",
        }
        if quickfilter is not None:
            params["quickFilter"] = quickfilter

        resp = SESSION.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"Agile API failed {resp.status_code}: {resp.text}", file=sys.stderr)
            sys.exit(1)

        data = resp.json()
        issues = data.get("issues", [])
        total = data.get("total", len(issues))
        results.extend(issues)
        start_at += len(issues)
        if start_at >= total or not issues:
            break
    return results


def jira_get_issue_full(key: str) -> dict:
    url = f"{JIRA_BASE}/rest/api/3/issue/{key}"
    params = {
        "expand": "changelog",
        "fields": (
            "summary,status,assignee,issuetype,created,issuelinks,"
            "customfield_10041,customfield_10042,customfield_10043,customfield_10044"
        ),
    }
    try:
        resp = SESSION.get(url, params=params, timeout=30)
    except Exception:
        return {}
    if resp.status_code != 200:
        return {}
    return resp.json()


def get_transition_date(issue_json: dict, statuses: tuple) -> str:
    histories = issue_json.get("changelog", {}).get("histories", [])
    for h in histories:
        for item in h.get("items", []):
            if item.get("field") == "status" and item.get("toString") in statuses:
                created = h.get("created")
                if created:
                    return created.split("T")[0]
    return ""


def get_latest_transition_date(issue_json: dict, target_status: str) -> str:
    histories = issue_json.get("changelog", {}).get("histories", [])
    latest_created = ""
    latest_date = ""
    target_norm = (target_status or "").strip().lower()
    for h in histories:
        created = h.get("created") or ""
        if not created:
            continue
        for item in h.get("items", []):
            if item.get("field") != "status":
                continue
            to_status = (item.get("toString") or "").strip().lower()
            if to_status == target_norm and created > latest_created:
                latest_created = created
                latest_date = created.split("T")[0]
    return latest_date


def get_last_status_from_history(issue_json: dict) -> str:
    histories = issue_json.get("changelog", {}).get("histories", [])
    latest_created = ""
    latest_status = ""
    for h in histories:
        created = h.get("created") or ""
        if not created:
            continue
        for item in h.get("items", []):
            if item.get("field") != "status":
                continue
            to_status = (item.get("toString") or "").strip()
            if to_status and created > latest_created:
                latest_created = created
                latest_status = to_status
    return latest_status


def extract_linked_issues_from_issue_json(issue_json: dict) -> List[Dict]:
    result = []
    fields = issue_json.get("fields", {})
    links = fields.get("issuelinks", []) or []
    for link in links:
        linked = link.get("outwardIssue") or link.get("inwardIssue")
        if not linked:
            continue
        key = linked.get("key", "")
        lf = linked.get("fields", {}) or {}
        issuetype = (lf.get("issuetype") or {}).get("name", "").lower()
        if key.startswith(("CVCP", "CVMP")):
            continue
        if link.get("type", {}).get("name", "").lower().startswith("cloner"):
            continue
        if not (
            key.startswith(("APIM", "EAH", "DOCG", "VDR", "VDP", "PATRIC"))
            or "story" in issuetype
            or "bug" in issuetype
        ):
            continue

        result.append(
            {
                "key": key,
                "summary": (lf.get("summary") or "").strip(),
                "status": (lf.get("status") or {}).get("name", ""),
                "assignee": (lf.get("assignee") or {}).get("displayName", ""),
                "issuetype": (lf.get("issuetype") or {}).get("name", ""),
                "created": lf.get("created") or "",
            }
        )
    return result


def split_report_blocks(content: str):
    blocks = []
    current = []
    for line in content.splitlines(keepends=True):
        if line.startswith("======= ") and current:
            blocks.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("".join(current))

    keyed = []
    for block in blocks:
        first = block.splitlines()[0] if block.splitlines() else ""
        m = re.match(r"^=+\s+.*\(([^)]+)\)\s*=+\s*$", first)
        if m:
            keyed.append((m.group(1), block.rstrip("\n") + "\n"))
    return keyed


def render_enabler_block(item: dict) -> str:
    lines = []
    sysname = item.get("system", "")
    ver = item.get("version", "")
    lines.append(f"======= {sysname}-{ver} ({item['key']}) =======")
    lines.append("")
    lines.append(f"Issue: {item['key']}")
    lines.append(f"Summary: {item.get('summary', '')}")
    lines.append(f"Status: {item.get('status', '')}")
    if item.get("assignee"):
        lines.append(f"Owner: {item['assignee']}")
    if item.get("issuetype"):
        lines.append(f"Issue Type: {item['issuetype']}")
    if item.get("deploy_date"):
        lines.append(f"Deploy PPROD Date: {item['deploy_date']}")
    lines.append("")

    linked = extract_linked_issues_from_issue_json(item.get("full", {}))
    if linked:
        lines.append("Linked issues:")
        lines.append("")
        for linked_item in linked:
            lines.append(f"Issue: {linked_item.get('key','')}")
            lines.append(f"Summary: {(linked_item.get('summary','') or '').replace(chr(10), ' ').strip()}")
            lines.append(f"Status: {linked_item.get('status','')}")
            if linked_item.get("assignee"):
                lines.append(f"Owner: {linked_item['assignee']}")
            if linked_item.get("issuetype"):
                lines.append(f"Issue Type: {linked_item['issuetype']}")
            if linked_item.get("created"):
                lines.append(f"Created: {linked_item['created']}")
            lines.append("")
    else:
        lines.append("No linked issues found.")
        lines.append("")
    lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def normalize_enabler_name(raw_name: str) -> str:
    name = (raw_name or "").strip().upper()
    if not name:
        return ""
    if name in (
        "APIM",
        "EAH",
        "VDR",
        "PATRIC",
        "PATRIC-SSDP",
        "DATACHAIN_MONITOR",
        "VDP_PROC",
        "VDP_PROC_2",
        "VDP_STORE",
        "VDP_STORE_2",
        "VDP_DS",
        "VDP_DS_MON",
        "VDP_DS_SSDP",
        "VDP_DS_2",
    ):
        return name
    return ""


def resolve_patric_component(system: str, summary: str) -> str:
    if system != "PATRIC":
        return system
    s = (summary or "").strip().upper()
    if "DATACHAIN_MONITOR" in s:
        return "DATACHAIN_MONITOR"
    if "PATRIC-SSDP" in s or "PATRIC_SSDP" in s:
        return "PATRIC-SSDP"
    return "PATRIC"


def resolve_vdp_proc_component(system: str, summary: str) -> str:
    if system not in ("VDP_PROC", "VDP_PROC_2"):
        return system
    s = (summary or "").strip().upper()
    if "VDP_PROC_2" in s or "VDP_PROC 2" in s or "VDP_PROC-2" in s:
        return "VDP_PROC_2"
    return "VDP_PROC"


def resolve_vdp_store_component(system: str, summary: str) -> str:
    if system not in ("VDP_STORE", "VDP_STORE_2"):
        return system
    s = (summary or "").strip().upper()
    if "VDP_STORE_2" in s or "VDP_STORE 2" in s or "VDP_STORE-2" in s:
        return "VDP_STORE_2"
    return "VDP_STORE"


def resolve_vdp_ds_component(system: str, summary: str) -> str:
    if system not in ("VDP_DS", "VDP_DS_MON", "VDP_DS_SSDP", "VDP_DS_2"):
        return system
    s = (summary or "").strip().upper()
    if "VDP_DS_MON" in s or "VDP_DS MON" in s or "VDP_DS-MON" in s:
        return "VDP_DS_MON"
    if "VDP_DS_SSDP" in s or "VDP_DS SSDP" in s or "VDP_DS-SSDP" in s:
        return "VDP_DS_SSDP"
    if "VDP_DS_2" in s or re.search(r"\bVDP_DS\s+2\b", s) or re.search(r"\bVDP_DS-2(?:\s|_|-|$)", s):
        return "VDP_DS_2"
    return "VDP_DS"


def get_system_version_from_issue_fields(fields: dict, summary: str):
    """Resolve (system, version) using Enabler Name first, then summary title fallback."""
    enabler_name_field = fields.get("customfield_10041")
    enabler_name = ""
    if isinstance(enabler_name_field, dict):
        enabler_name = enabler_name_field.get("value", "")
    elif isinstance(enabler_name_field, str):
        enabler_name = enabler_name_field

    system = normalize_enabler_name(enabler_name)
    version = (fields.get("customfield_10042") or "").strip().rstrip(".")

    if system == "PATRIC":
        system = resolve_patric_component(system, summary)
    if system in ("VDP_PROC", "VDP_PROC_2"):
        system = resolve_vdp_proc_component(system, summary)
    if system in ("VDP_STORE", "VDP_STORE_2"):
        system = resolve_vdp_store_component(system, summary)
    if system in ("VDP_DS", "VDP_DS_MON", "VDP_DS_SSDP", "VDP_DS_2"):
        system = resolve_vdp_ds_component(system, summary)

    if system and version:
        return system, version

    # Fallback: detect from title/summary
    mdc = DATACHAIN_MONITOR_RE.search(summary or "")
    if mdc:
        return "DATACHAIN_MONITOR", mdc.group(1).strip().rstrip(".")

    mps = PATRIC_SSDP_RE.search(summary or "")
    if mps:
        return "PATRIC-SSDP", mps.group(1).strip().rstrip(".")

    mvp2 = VDP_PROC_2_RE.search(summary or "")
    if mvp2:
        return "VDP_PROC_2", mvp2.group(1).strip().rstrip(".")

    mvp = VDP_PROC_RE.search(summary or "")
    if mvp:
        return "VDP_PROC", mvp.group(1).strip().rstrip(".")

    mvs2 = VDP_STORE_2_RE.search(summary or "")
    if mvs2:
        return "VDP_STORE_2", mvs2.group(1).strip().rstrip(".")

    mvs = VDP_STORE_RE.search(summary or "")
    if mvs:
        return "VDP_STORE", mvs.group(1).strip().rstrip(".")

    mvdsm = VDP_DS_MON_RE.search(summary or "")
    if mvdsm:
        return "VDP_DS_MON", mvdsm.group(1).strip().rstrip(".")

    mvdsssdp = VDP_DS_SSDP_RE.search(summary or "")
    if mvdsssdp:
        return "VDP_DS_SSDP", mvdsssdp.group(1).strip().rstrip(".")

    mvds2 = VDP_DS_2_RE.search(summary or "")
    if mvds2:
        return "VDP_DS_2", mvds2.group(1).strip().rstrip(".")

    mvds = VDP_DS_RE.search(summary or "")
    if mvds:
        return "VDP_DS", mvds.group(1).strip().rstrip(".")

    m = APIM_RE.search(summary or "")
    if m:
        return "APIM", m.group(1).strip().rstrip(".")

    mvdr = VDR_RE.search(summary or "")
    if mvdr:
        return "VDR", mvdr.group(1).strip().rstrip(".")

    m2 = EAH_RE.search(summary or "")
    if m2:
        return "EAH", m2.group(1).strip().rstrip(".")

    m3 = PATRIC_RE.search(summary or "")
    if m3:
        return "PATRIC", m3.group(1).strip().rstrip(".")

    return "", ""


# week selection
override_year = None
override_week = None
if "--week" in sys.argv:
    raw = sys.argv[sys.argv.index("--week") + 1]
    override_year, override_week = parse_week_arg(raw)

today = datetime.date.today()
target_year = override_year if override_year else today.isocalendar()[0]
target_week = override_week if override_week else today.isocalendar()[1]

if target_week < 1 or target_week > weeks_in_year(target_year):
    print(f"ERROR: week {target_week} is not valid for year {target_year}", file=sys.stderr)
    sys.exit(1)

week_str = f"{target_year}-W{target_week:02d}"

stopper = load_stopper()
issues = agile_board_issues(BOARD_ID, quickfilter=QUICKFILTER_ID, max_per_page=200)

records = []
for it in issues:
    key = it.get("key")
    fields = it.get("fields", {}) or {}
    summary = (fields.get("summary") or "").strip()
    status = (fields.get("status") or {}).get("name", "") or ""
    assignee = (fields.get("assignee") or {}).get("displayName", "") or ""
    issuetype = (fields.get("issuetype") or {}).get("name", "") or ""

    system, version = get_system_version_from_issue_fields(fields, summary)
    if system and version:
        records.append(
            {
                "system": system,
                "version": version,
                "key": key,
                "summary": summary,
                "status": status,
                "assignee": assignee,
                "issuetype": issuetype,
            }
        )

print(f"Discovered {len(records)} APIM/EAH/PATRIC candidates", file=sys.stderr)
print("Processing APIM/EAH/PATRIC issues...", file=sys.stderr)

# Preserve previously selected enablers for same week (NO DELETE behavior)
previous_selected = {}
existing_week = stopper.get(week_str, {})
for item in existing_week.get("apim_eah_selected", []):
    item_key = item.get("key")
    if item_key:
        previous_selected[item_key] = item

apim_eah_enablers = []
newly_found_keys = set()

for r in records:
    full = jira_get_issue_full(r["key"])
    if not full:
        continue
    fields = full.get("fields", {}) or {}
    status_name = (fields.get("status") or {}).get("name", "")

    # Include cards only for issues that have already reached the validation trigger.
    ready_for_validation_date = get_latest_transition_date(full, VALIDATION_TRIGGER_STATUS)
    if not ready_for_validation_date:
        continue

    # Week filtering still uses Deploy PPROD Date field.
    last_status = status_name

    # Use Deploy PPROD Date (custom fields)
    deploy_date_str = fields.get("customfield_10043") or fields.get("customfield_10044") or ""
    if not deploy_date_str:
        continue

    deploy_date = parse_iso_date(deploy_date_str)
    if not deploy_date:
        continue

    iso_year, iso_week, _ = deploy_date.isocalendar()
    if iso_year == target_year and iso_week == target_week:
        newly_found_keys.add(r["key"])
        apim_eah_enablers.append(
            {
                "key": r["key"],
                "system": r["system"],
                "version": r["version"],
                "summary": r["summary"],
                "status": last_status or status_name or r.get("status", ""),
                "assignee": r.get("assignee") or "",
                "issuetype": r.get("issuetype") or "",
                "deploy_date": deploy_date_str,
                "full": full,
            }
        )

# Merge old + new (no delete)
for key, old_item in previous_selected.items():
    if key not in newly_found_keys:
        # keep historical entry; fetch live details if possible for linked-issue rendering
        full = jira_get_issue_full(key)
        live_fields = full.get("fields", {}) if full else {}
        live_status = (live_fields.get("status") or {}).get("name", "") if live_fields else ""
        live_deploy_date = ""
        if live_fields:
            live_deploy_date = (
                live_fields.get("customfield_10043")
                or live_fields.get("customfield_10044")
                or ""
            )
        if full:
            ready_for_validation_date = get_latest_transition_date(full, VALIDATION_TRIGGER_STATUS)
            if not ready_for_validation_date:
                continue
        else:
            old_status = (old_item.get("status") or "").strip().lower()
            if old_status != VALIDATION_TRIGGER_STATUS.lower():
                continue

        effective_deploy_date = live_deploy_date or old_item.get("deploy_date", "")
        effective_deploy = parse_iso_date(effective_deploy_date)
        if not effective_deploy:
            continue
        eff_year, eff_week, _ = effective_deploy.isocalendar()
        if eff_year != target_year or eff_week != target_week:
            continue

        merged = {
            "key": key,
            "system": old_item.get("system", ""),
            "version": old_item.get("version", ""),
            "summary": old_item.get("summary", ""),
            "status": live_status or old_item.get("status", ""),
            "assignee": old_item.get("assignee", ""),
            "issuetype": old_item.get("issuetype", ""),
            "deploy_date": live_deploy_date or old_item.get("deploy_date", ""),
            "full": full if full else {"fields": {"issuelinks": []}},
        }
        apim_eah_enablers.append(merged)

# dedupe by key (prefer newest)
by_key = {}
for item in apim_eah_enablers:
    by_key[item["key"]] = item
apim_eah_enablers = list(by_key.values())

# Write Linked_Issues_Report.txt for selected week only.
# Historical preservation is handled in weekly_stopper.json via previous_selected,
# so old weeks should not remain in this week's linked report output.
new_pairs = []
for item in sorted(apim_eah_enablers, key=lambda d: (d.get("system", ""), vtuple(d.get("version", "")))):
    new_pairs.append((item["key"], render_enabler_block(item)))

with open(LINKED_FILE, "w", encoding="utf-8") as f:
    f.write("".join(block for _, block in new_pairs))

# Update stopper (component versions)
store_entry = stopper.get(week_str, {}) if isinstance(stopper.get(week_str), dict) else {}

systems_to_store = [
    "APIM",
    "EAH",
    "VDR",
    "DATACHAIN_MONITOR",
    "PATRIC-SSDP",
    "PATRIC",
    "VDP_PROC",
    "VDP_PROC_2",
    "VDP_STORE",
    "VDP_STORE_2",
    "VDP_DS",
    "VDP_DS_MON",
    "VDP_DS_SSDP",
    "VDP_DS_2",
]
for system_name in systems_to_store:
    versions = sorted(
        {e["version"] for e in apim_eah_enablers if e.get("system") == system_name and e.get("version")},
        key=vtuple,
    )
    store_entry[system_name] = ",".join(versions) if versions else None

store_entry["apim_eah_selected"] = [
    {
        "key": d.get("key"),
        "system": d.get("system"),
        "version": d.get("version"),
        "summary": d.get("summary"),
        "status": d.get("status"),
        "assignee": d.get("assignee"),
        "issuetype": d.get("issuetype"),
        "deploy_date": d.get("deploy_date"),
    }
    for d in sorted(apim_eah_enablers, key=lambda x: x.get("key", ""))
]

stopper[week_str] = store_entry
save_stopper(stopper)

print("Done extract.py")
print(
    json.dumps(
        {
            "week": week_str,
            "curr_stoppler_entry": stopper.get(week_str),
            "apim_eah_selected": [
                {
                    "key": d.get("key"),
                    "system": d.get("system"),
                    "version": d.get("version"),
                    "deploy_date": d.get("deploy_date"),
                }
                for d in apim_eah_enablers
            ],
            "counts": {"APIM/EAH/PATRIC": len(apim_eah_enablers)},
            "linked_file": os.path.abspath(LINKED_FILE),
            "stopper_file": os.path.abspath(WEEKLY_STOPPER),
        },
        indent=2,
    )
)

