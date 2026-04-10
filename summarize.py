#!/usr/bin/env python3
"""
summarize.py — APIM/EAH/PATRIC version-accurate release summary

Enhancements:
• Separate tables per version: APIM, EAH, PATRIC
• Release Summary table now shows last NON-NULL version from historical stopper
• Linked issues table includes APIM/EAH/PATRIC
• Classification:
      User Story → FEATURES
      Technical Story → CODE
      Bug/Bug Enabler → BUGS
"""

import os
import sys
import re
import json
import datetime

LINKED_FILE = os.getenv("LINKED_FILE", "Linked_Issues_Report.txt")
SUMMARY_HTML = os.getenv("SUMMARY_HTML", "summary_output.html")
STOPPER_FILE = os.getenv("WEEKLY_STOPPER", "weekly_stopper.json")
WEEK_FILE = os.getenv("WEEK_FILE", "week_number.txt")
META_FILE = os.getenv("META_FILE", "summary_meta.json")

forced_week_raw = None
forced_year = None
forced_week = None
if "--week" in sys.argv:
    forced_week_raw = sys.argv[sys.argv.index("--week") + 1]

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

if forced_week_raw:
    fy, fw = parse_week_arg(forced_week_raw)
    forced_year = fy
    forced_week = fw


def vtuple(v):
    try:
        return tuple(int(x) for x in re.findall(r"\d+", v))
    except Exception:
        return ()


def extract_latest_version(version_string):
    """Extract the latest version from a comma-separated version string"""
    if not version_string or version_string == "None":
        return "None"
    
    # Handle comma-separated versions
    if "," in version_string:
        versions = [v.strip() for v in version_string.split(",")]
        # Sort by version tuple to get the latest
        try:
            latest = max(versions, key=vtuple)
            return latest
        except Exception:
            # If version parsing fails, return the last one
            return versions[-1]
    
    return version_string.strip()


def load_text(path):
    return open(path, "r", encoding="utf-8").read() if os.path.exists(path) else ""


def write(path, txt):
    open(path, "w", encoding="utf-8").write(txt)


def read_week():
    """Return (year, week, display_str)

    display_str will always be like '2026-W04' to maintain consistency.
    """
    today = datetime.date.today()
    current_year = today.isocalendar()[0]
    current_week = today.isocalendar()[1]

    year = forced_year if forced_year is not None else current_year
    week = forced_week if forced_week is not None else current_week

    # validate week
    last_day = datetime.date(year, 12, 28)
    maxw = last_day.isocalendar()[1]
    if week < 1 or week > maxw:
        print(f"Invalid week {week} for year {year}")
        sys.exit(1)

    # Always use year-week format for consistency
    display = f"{year}-W{week:02d}"
    return year, week, display


def parse_blocks(raw):
    pattern = re.compile(
        r"^=+\s*(APIM|EAH|VDR|PATRIC|PATRIC-SSDP|DATACHAIN_MONITOR|VDP_PROC|VDP_PROC_2|VDP_STORE|VDP_STORE_2|VDP_DS|VDP_DS_MON|VDP_DS_SSDP|VDP_DS_2)\s*[- ]\s*([\d\.]+)\s*\((.*?)\)",
        re.MULTILINE
    )
    matches = list(pattern.finditer(raw))

    blocks = []
    for i, m in enumerate(matches):
        system = m.group(1)
        version = m.group(2).rstrip(".")
        key = m.group(3)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = raw[start:end].strip()

        blocks.append({
            "system": system,
            "version": version,
            "key": key,
            "body": body
        })

    return blocks

def extract_issues(body):
    issues = []
    parts = body.split("Issue:")

    for p in parts[1:]:
        summary = ""
        issue_type = ""
        status = ""
        owner = ""
        created = ""
        deploy_date = ""

        m = re.search(r"Summary:\s*(.*)", p)
        if m:
            summary = m.group(1).strip()

        m = re.search(r"Issue Type:\s*(.*)", p)
        if m:
            issue_type = m.group(1).strip()

        m = re.search(r"Status:\s*(.*)", p)
        if m:
            status = m.group(1).strip()

        m = re.search(r"(Owner|Assignee):\s*(.*)", p)
        if m:
            owner = m.group(2).strip()

        m = re.search(r"Created:\s*(.*)", p)
        if m:
            created = m.group(1).strip()

        m = re.search(r"Deploy PPROD Date:\s*(.*)", p)
        if not m:
            m = re.search(r"Deploy Date:\s*(.*)", p)
        if m:
            deploy_date = m.group(1).strip()

        issues.append({
            "summary": summary,
            "issue_type": issue_type,
            "status": status,
            "owner": owner,
            "created": created,
            "deploy_date": deploy_date
        })

    return issues


def classify(issue_type):
    it = issue_type.lower()
    if "user story" in it:
        return "FEATURES"
    if "technical story" in it or "tech" in it:
        return "CODE"
    if "bug" in it:
        return "BUGS"
    return "FEATURES"


def build_changes(blocks):
    out = {
        "APIM": {},
        "EAH": {},
        "VDR": {},
        "DATACHAIN_MONITOR": {},
        "PATRIC-SSDP": {},
        "PATRIC": {},
        "VDP_PROC": {},
        "VDP_PROC_2": {},
        "VDP_STORE": {},
        "VDP_STORE_2": {},
        "VDP_DS": {},
        "VDP_DS_MON": {},
        "VDP_DS_SSDP": {},
        "VDP_DS_2": {},
    }

    for b in blocks:
        sysname = b["system"]
        ver = b["version"]
        issues = extract_issues(b["body"])

        out[sysname].setdefault(
            ver,
            {"FEATURES": [], "CODE": [], "BUGS": [], "DEPLOY": "", "STATUS": ""}
        )

        for iss in issues:
            if not out[sysname][ver]["STATUS"] and iss["status"]:
                out[sysname][ver]["STATUS"] = iss["status"]
            if not out[sysname][ver]["DEPLOY"] and iss["deploy_date"]:
                out[sysname][ver]["DEPLOY"] = iss["deploy_date"]

            bucket = classify(iss["issue_type"])
            if iss["summary"]:
                out[sysname][ver][bucket].append(iss["summary"])

    return out


def make_box(title, color, items):
    if not items:
        return ""

    list_html = "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"

    return (
        '<ac:structured-macro ac:name="panel">'
        f'<ac:parameter ac:name="title">{title}</ac:parameter>'
        f'<ac:parameter ac:name="bgColor">{color}</ac:parameter>'
        f'<ac:rich-text-body>{list_html}</ac:rich-text-body>'
        '</ac:structured-macro>'
    )


def make_table(ver, boxhtml, status="", deploy_pprod_date="", extra=""):
    return f"""
    <table style="width:100%;border-collapse:collapse;margin:12px 0;border:1px solid #ccc;">
      <tr><th style="background:#F4F5F7;width:200px;padding:10px;border:1px solid #ccc;">Version</th><td style="padding:10px;border:1px solid #ccc;">{ver}</td></tr>
      <tr><th style="background:#F4F5F7;padding:10px;border:1px solid #ccc;">Status</th><td style="padding:10px;border:1px solid #ccc;">{status}</td></tr>
    <tr><th style="background:#F4F5F7;padding:10px;border:1px solid #ccc;">Deploy PPROD Date</th><td style="padding:10px;border:1px solid #ccc;">{deploy_pprod_date}</td></tr>
      <tr><th style="background:#F4F5F7;padding:10px;border:1px solid #ccc;">Dependencies</th><td style="padding:10px;border:1px solid #ccc;"></td></tr>
      <tr><th style="background:#F4F5F7;padding:10px;border:1px solid #ccc;">INDUS configuration</th><td style="padding:10px;border:1px solid #ccc;"></td></tr>
      <tr><th style="background:#F4F5F7;padding:10px;border:1px solid #ccc;">Swagger Release</th><td style="padding:10px;border:1px solid #ccc;">{extra}</td></tr>
      <tr><th style="background:#F4F5F7;padding:10px;border:1px solid #ccc;">Main Changes</th><td style="padding:10px;border:1px solid #ccc;">{boxhtml}</td></tr>
    </table>
    """


def build_linked_table(blocks):
    html = """
    <h1>Combined Linked Issues</h1>
    <table style="width:100%;border-collapse:collapse;border:1px solid #ccc;">
    <tr style="background:#eee;">
    <th style="padding:10px;border:1px solid #ccc;">System</th><th style="padding:10px;border:1px solid #ccc;">Version</th><th style="padding:10px;border:1px solid #ccc;">Key</th><th style="padding:10px;border:1px solid #ccc;">Summary</th><th style="padding:10px;border:1px solid #ccc;">Owner</th><th style="padding:10px;border:1px solid #ccc;">Status</th><th style="padding:10px;border:1px solid #ccc;">Issue Type</th>
    </tr>
    """

    for b in blocks:
        system = b["system"]
        version = b["version"]
        parts = b["body"].split("Issue:")

        for p in parts[1:]:
            m = re.match(r"\s*(\S+)", p)
            if not m:
                continue
            key = m.group(1)

            summary = re.search(r"Summary:\s*(.*)", p)
            status = re.search(r"Status:\s*(.*)", p)
            owner = re.search(r"(Owner|Assignee):\s*(.*)", p)
            itype = re.search(r"Issue Type:\s*(.*)", p)

            html += (
                "<tr>"
                f"<td style='padding:10px;border:1px solid #ccc;'>{system}</td>"
                f"<td style='padding:10px;border:1px solid #ccc;'>{version}</td>"
                f"<td style='padding:10px;border:1px solid #ccc;'><a target='_blank' href='https://stla-iotpf-jira.atlassian.net/browse/{key}'>{key}</a></td>"
                f"<td style='padding:10px;border:1px solid #ccc;'>{summary.group(1).strip() if summary else ''}</td>"
                f"<td style='padding:10px;border:1px solid #ccc;'>{owner.group(2).strip() if owner else ''}</td>"
                f"<td style='padding:10px;border:1px solid #ccc;'>{status.group(1).strip() if status else ''}</td>"
                f"<td style='padding:10px;border:1px solid #ccc;'>{itype.group(1).strip() if itype else ''}</td>"
                "</tr>"
            )

    html += "</table>"
    return html


raw = load_text(LINKED_FILE)
blocks = parse_blocks(raw)
pv = build_changes(blocks)

year, week, week_display = read_week()
week_monday = datetime.date.fromisocalendar(year, week, 1)
week_sunday = datetime.date.fromisocalendar(year, week, 7)
week_range_display = f"{week_monday.strftime('%d/%m/%Y')} - {week_sunday.strftime('%d/%m/%Y')}"

stopper_data = json.load(open(STOPPER_FILE)) if os.path.exists(STOPPER_FILE) else {}

# Try both new format (2026-W04) and legacy format (4) for backward compatibility
week_str = week_display
legacy_week_str = str(week)


def get_stopper_entry_for_week() -> dict:
    """Return stopper entry for current target week in either new or legacy format."""
    if week_str in stopper_data and isinstance(stopper_data[week_str], dict):
        return stopper_data[week_str]
    if legacy_week_str in stopper_data and isinstance(stopper_data[legacy_week_str], dict):
        return stopper_data[legacy_week_str]
    return {}

def get_stopper_value(component):
    """Get stopper value, trying both new and legacy week formats"""
    # Try new format first (e.g., "2026-W04")
    if week_str in stopper_data and stopper_data[week_str].get(component):
        return stopper_data[week_str].get(component)
    # Fall back to legacy format (e.g., "4")
    if legacy_week_str in stopper_data and stopper_data[legacy_week_str].get(component):
        return stopper_data[legacy_week_str].get(component)
    return None


# -------------------------------------------------------
# NEW FUNCTION: find last non-null version historically
# -------------------------------------------------------
def _parse_stopper_key(k: str):
    """Return (year, week, rawkey). Numeric keys without year return (None, int(key))."""
    m = re.match(r"^(?P<y>\d{4})-W?(?P<w>\d{1,2})$", k)
    if m:
        return int(m.group("y")), int(m.group("w")), k
    m2 = re.match(r"^(?P<w>\d{1,2})$", k)
    if m2:
        return None, int(m2.group("w")), k
    return None, None, k

def last_non_null(stopper, target_year, target_week, key):
    """Return the last non-null version for `key` before (target_year, target_week).

    Searches stopper keys parsed as either 'YYYY-Www' or numeric weeks. Best-effort across mixed formats.
    """
    parsed = []
    for k in stopper.keys():
        y, w, raw = _parse_stopper_key(k)
        if w is None:
            continue
        # If year missing, infer year based on week number and target
        # High week numbers (>40) when target is early (<=10) likely mean previous year
        if y is None:
            if target_week <= 10 and w > 40:
                y_effective = target_year - 1
            else:
                y_effective = target_year
        else:
            y_effective = y
        parsed.append((y_effective, w, raw))

    # sort chronologically
    parsed.sort()

    # find entries strictly before target
    candidates = [(y, w, raw) for (y, w, raw) in parsed if (y, w) < (target_year, target_week)]
    for y, w, raw in reversed(candidates):
        val = stopper.get(raw, {}).get(key)
        if val not in (None, "", "None"):
            return val
    return None


def last_non_null_with_key(stopper, target_year, target_week, key):
    """Return tuple (value, raw_week_key) for last non-null version before target."""
    parsed = []
    for k in stopper.keys():
        y, w, raw = _parse_stopper_key(k)
        if w is None:
            continue
        if y is None:
            if target_week <= 10 and w > 40:
                y_effective = target_year - 1
            else:
                y_effective = target_year
        else:
            y_effective = y
        parsed.append((y_effective, w, raw))

    parsed.sort()
    candidates = [(y, w, raw) for (y, w, raw) in parsed if (y, w) < (target_year, target_week)]
    for y, w, raw in reversed(candidates):
        val = stopper.get(raw, {}).get(key)
        if val not in (None, "", "None"):
            return val, raw
    return None, None


def find_deploy_date(entry: dict, component: str, version: str = None) -> str:
    """Find latest deploy date from selected entries for a component (optionally exact version)."""
    if not entry:
        return ""
    selected = entry.get("apim_eah_selected", [])
    if not isinstance(selected, list):
        return ""

    component_norm = (component or "").strip().upper()
    version_norm = (version or "").strip().rstrip(".") if version else None
    dates = []

    for item in selected:
        if not isinstance(item, dict):
            continue
        item_system = (item.get("system") or "").strip().upper()
        if item_system != component_norm:
            continue
        item_version = (item.get("version") or "").strip().rstrip(".")
        if version_norm is not None and item_version != version_norm:
            continue
        deploy_date = (item.get("deploy_date") or "").strip()
        if deploy_date:
            dates.append(deploy_date.split("T")[0])

    return max(dates) if dates else ""


def safe(v):
    """Return the latest version from a version string, or 'None' if empty"""
    if not v:
        return "None"
    return extract_latest_version(v)


# -------------------------------------------------------
# REPLACE ALL prev_* LOGIC WITH NON-NULL LOOKUP
# -------------------------------------------------------
components = [
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

prev_versions_raw = {}
prev_week_keys = {}
curr_versions = {}
for comp in components:
    raw_val, raw_week_key = last_non_null_with_key(stopper_data, year, week, comp)
    prev_versions_raw[comp] = raw_val
    prev_week_keys[comp] = raw_week_key
    curr_versions[comp] = safe(get_stopper_value(comp))

prev_versions = {comp: safe(prev_versions_raw.get(comp)) for comp in components}

current_week_entry = get_stopper_entry_for_week()

curr_dates = {
    comp: find_deploy_date(
        current_week_entry,
        comp,
        curr_versions[comp] if curr_versions[comp] != "None" else None,
    )
    for comp in components
}

prev_dates = {}
for comp in components:
    prev_entry = stopper_data.get(prev_week_keys.get(comp), {}) if prev_week_keys.get(comp) else {}
    prev_ver = prev_versions.get(comp)
    prev_dates[comp] = find_deploy_date(
        prev_entry,
        comp,
        prev_ver if prev_ver not in ("None", "null") else None,
    )

# Baseline rule for week 9: show last version as null
if week == 9:
    for comp in components:
        prev_versions[comp] = "null"
        prev_dates[comp] = ""


def get_enabler_key_for_system(system_name, version_value):
    if not version_value or version_value in ("None", "null"):
        return None
    for block in blocks:
        if block.get("system") == system_name and block.get("version") == version_value:
            return block.get("key")
    # Fallback to latest block for that system
    candidates = [b for b in blocks if b.get("system") == system_name]
    if not candidates:
        return None
    latest = sorted(candidates, key=lambda b: vtuple(b.get("version", "")))[-1]
    return latest.get("key")


def get_enabler_key_from_week_entry(system_name, version_value, week_key):
    if not week_key:
        return None
    entry = stopper_data.get(week_key, {})
    selected = entry.get("apim_eah_selected", [])
    if not isinstance(selected, list):
        return None
    system_norm = (system_name or "").strip().upper()
    version_norm = (version_value or "").strip().rstrip(".")
    for item in selected:
        if not isinstance(item, dict):
            continue
        item_system = (item.get("system") or "").strip().upper()
        item_version = (item.get("version") or "").strip().rstrip(".")
        if item_system == system_norm and item_version == version_norm:
            return item.get("key")
    return None


def render_version_with_link(system_name, version_value, week_key=None):
    if not version_value or version_value in ("None", "null"):
        return version_value or "None"

    enabler_key = get_enabler_key_from_week_entry(system_name, version_value, week_key)
    if not enabler_key:
        enabler_key = get_enabler_key_for_system(system_name, version_value)
    if not enabler_key:
        return version_value
    jira_url = f"https://stla-iotpf-jira.atlassian.net/browse/{enabler_key}"
    return f"<a target='_blank' href='{jira_url}'>{version_value}</a> ({enabler_key})"


curr_cells = {comp: render_version_with_link(comp, curr_versions[comp]) for comp in components}
prev_cells = {
    comp: render_version_with_link(comp, prev_versions[comp], prev_week_keys.get(comp))
    for comp in components
}


# -------------------------------------------------------
# EXPANDED RELEASE SUMMARY FOR ALL COMPONENTS
# -------------------------------------------------------

# Determine which components have releases this week
def get_highlight_style(component):
    """Returns inline background style if component has releases"""
    # Check the current version for this component
    current_version = curr_versions.get(component, "None")
    if current_version and current_version != "None" and current_version.strip():
        return "background-color:#DFFCF0 !important;"
    else:
        return ''


def get_highlight_bg_attr(component):
    current_version = curr_versions.get(component, "None")
    if current_version and current_version != "None" and current_version.strip():
        return 'bgcolor="#DFFCF0"'
    return ''

release_summary_html = f"""
<h1>Release Summary</h1>
<table style="width:100%;border-collapse:collapse;border:1px solid #ccc;">
<tr style="background:#0747A6;color:white;">
    <th style="padding:10px;text-align:left;border:1px solid #0747A6;">Enabler/Application</th>
    <th style="padding:10px;text-align:left;border:1px solid #0747A6;">Current Version</th>
    <th style="padding:10px;text-align:left;border:1px solid #0747A6;">Deploy PPROD Date</th>
    <th style="padding:10px;text-align:left;border:1px solid #0747A6;">Previous Version</th>
    <th style="padding:10px;text-align:left;border:1px solid #0747A6;">Date of Previous Version</th>
</tr>

<tr {get_highlight_bg_attr("APIM")}><td style="{get_highlight_style("APIM")}padding:10px;border:1px solid #ccc;">APIM</td><td style="{get_highlight_style("APIM")}padding:10px;border:1px solid #ccc;">{curr_cells["APIM"]}</td><td style="{get_highlight_style("APIM")}padding:10px;border:1px solid #ccc;">{curr_dates["APIM"]}</td><td style="{get_highlight_style("APIM")}padding:10px;border:1px solid #ccc;">{prev_cells["APIM"]}</td><td style="{get_highlight_style("APIM")}padding:10px;border:1px solid #ccc;">{prev_dates["APIM"]}</td></tr>
<tr {get_highlight_bg_attr("EAH")}><td style="{get_highlight_style("EAH")}padding:10px;border:1px solid #ccc;">EAH</td><td style="{get_highlight_style("EAH")}padding:10px;border:1px solid #ccc;">{curr_cells["EAH"]}</td><td style="{get_highlight_style("EAH")}padding:10px;border:1px solid #ccc;">{curr_dates["EAH"]}</td><td style="{get_highlight_style("EAH")}padding:10px;border:1px solid #ccc;">{prev_cells["EAH"]}</td><td style="{get_highlight_style("EAH")}padding:10px;border:1px solid #ccc;">{prev_dates["EAH"]}</td></tr>
<tr {get_highlight_bg_attr("VDR")}><td style="{get_highlight_style("VDR")}padding:10px;border:1px solid #ccc;">VDR</td><td style="{get_highlight_style("VDR")}padding:10px;border:1px solid #ccc;">{curr_cells["VDR"]}</td><td style="{get_highlight_style("VDR")}padding:10px;border:1px solid #ccc;">{curr_dates["VDR"]}</td><td style="{get_highlight_style("VDR")}padding:10px;border:1px solid #ccc;">{prev_cells["VDR"]}</td><td style="{get_highlight_style("VDR")}padding:10px;border:1px solid #ccc;">{prev_dates["VDR"]}</td></tr>
<tr {get_highlight_bg_attr("DATACHAIN_MONITOR")}><td style="{get_highlight_style("DATACHAIN_MONITOR")}padding:10px;border:1px solid #ccc;">DATACHAIN_MONITOR</td><td style="{get_highlight_style("DATACHAIN_MONITOR")}padding:10px;border:1px solid #ccc;">{curr_cells["DATACHAIN_MONITOR"]}</td><td style="{get_highlight_style("DATACHAIN_MONITOR")}padding:10px;border:1px solid #ccc;">{curr_dates["DATACHAIN_MONITOR"]}</td><td style="{get_highlight_style("DATACHAIN_MONITOR")}padding:10px;border:1px solid #ccc;">{prev_cells["DATACHAIN_MONITOR"]}</td><td style="{get_highlight_style("DATACHAIN_MONITOR")}padding:10px;border:1px solid #ccc;">{prev_dates["DATACHAIN_MONITOR"]}</td></tr>
<tr {get_highlight_bg_attr("PATRIC-SSDP")}><td style="{get_highlight_style("PATRIC-SSDP")}padding:10px;border:1px solid #ccc;">PATRIC-SSDP</td><td style="{get_highlight_style("PATRIC-SSDP")}padding:10px;border:1px solid #ccc;">{curr_cells["PATRIC-SSDP"]}</td><td style="{get_highlight_style("PATRIC-SSDP")}padding:10px;border:1px solid #ccc;">{curr_dates["PATRIC-SSDP"]}</td><td style="{get_highlight_style("PATRIC-SSDP")}padding:10px;border:1px solid #ccc;">{prev_cells["PATRIC-SSDP"]}</td><td style="{get_highlight_style("PATRIC-SSDP")}padding:10px;border:1px solid #ccc;">{prev_dates["PATRIC-SSDP"]}</td></tr>
<tr {get_highlight_bg_attr("PATRIC")}><td style="{get_highlight_style("PATRIC")}padding:10px;border:1px solid #ccc;">PATRIC</td><td style="{get_highlight_style("PATRIC")}padding:10px;border:1px solid #ccc;">{curr_cells["PATRIC"]}</td><td style="{get_highlight_style("PATRIC")}padding:10px;border:1px solid #ccc;">{curr_dates["PATRIC"]}</td><td style="{get_highlight_style("PATRIC")}padding:10px;border:1px solid #ccc;">{prev_cells["PATRIC"]}</td><td style="{get_highlight_style("PATRIC")}padding:10px;border:1px solid #ccc;">{prev_dates["PATRIC"]}</td></tr>
<tr {get_highlight_bg_attr("VDP_PROC")}><td style="{get_highlight_style("VDP_PROC")}padding:10px;border:1px solid #ccc;">VDP_PROC</td><td style="{get_highlight_style("VDP_PROC")}padding:10px;border:1px solid #ccc;">{curr_cells["VDP_PROC"]}</td><td style="{get_highlight_style("VDP_PROC")}padding:10px;border:1px solid #ccc;">{curr_dates["VDP_PROC"]}</td><td style="{get_highlight_style("VDP_PROC")}padding:10px;border:1px solid #ccc;">{prev_cells["VDP_PROC"]}</td><td style="{get_highlight_style("VDP_PROC")}padding:10px;border:1px solid #ccc;">{prev_dates["VDP_PROC"]}</td></tr>
<tr {get_highlight_bg_attr("VDP_PROC_2")}><td style="{get_highlight_style("VDP_PROC_2")}padding:10px;border:1px solid #ccc;">VDP_PROC_2</td><td style="{get_highlight_style("VDP_PROC_2")}padding:10px;border:1px solid #ccc;">{curr_cells["VDP_PROC_2"]}</td><td style="{get_highlight_style("VDP_PROC_2")}padding:10px;border:1px solid #ccc;">{curr_dates["VDP_PROC_2"]}</td><td style="{get_highlight_style("VDP_PROC_2")}padding:10px;border:1px solid #ccc;">{prev_cells["VDP_PROC_2"]}</td><td style="{get_highlight_style("VDP_PROC_2")}padding:10px;border:1px solid #ccc;">{prev_dates["VDP_PROC_2"]}</td></tr>
<tr {get_highlight_bg_attr("VDP_STORE")}><td style="{get_highlight_style("VDP_STORE")}padding:10px;border:1px solid #ccc;">VDP_STORE</td><td style="{get_highlight_style("VDP_STORE")}padding:10px;border:1px solid #ccc;">{curr_cells["VDP_STORE"]}</td><td style="{get_highlight_style("VDP_STORE")}padding:10px;border:1px solid #ccc;">{curr_dates["VDP_STORE"]}</td><td style="{get_highlight_style("VDP_STORE")}padding:10px;border:1px solid #ccc;">{prev_cells["VDP_STORE"]}</td><td style="{get_highlight_style("VDP_STORE")}padding:10px;border:1px solid #ccc;">{prev_dates["VDP_STORE"]}</td></tr>
<tr {get_highlight_bg_attr("VDP_STORE_2")}><td style="{get_highlight_style("VDP_STORE_2")}padding:10px;border:1px solid #ccc;">VDP_STORE_2</td><td style="{get_highlight_style("VDP_STORE_2")}padding:10px;border:1px solid #ccc;">{curr_cells["VDP_STORE_2"]}</td><td style="{get_highlight_style("VDP_STORE_2")}padding:10px;border:1px solid #ccc;">{curr_dates["VDP_STORE_2"]}</td><td style="{get_highlight_style("VDP_STORE_2")}padding:10px;border:1px solid #ccc;">{prev_cells["VDP_STORE_2"]}</td><td style="{get_highlight_style("VDP_STORE_2")}padding:10px;border:1px solid #ccc;">{prev_dates["VDP_STORE_2"]}</td></tr>
<tr {get_highlight_bg_attr("VDP_DS")}><td style="{get_highlight_style("VDP_DS")}padding:10px;border:1px solid #ccc;">VDP_DS</td><td style="{get_highlight_style("VDP_DS")}padding:10px;border:1px solid #ccc;">{curr_cells["VDP_DS"]}</td><td style="{get_highlight_style("VDP_DS")}padding:10px;border:1px solid #ccc;">{curr_dates["VDP_DS"]}</td><td style="{get_highlight_style("VDP_DS")}padding:10px;border:1px solid #ccc;">{prev_cells["VDP_DS"]}</td><td style="{get_highlight_style("VDP_DS")}padding:10px;border:1px solid #ccc;">{prev_dates["VDP_DS"]}</td></tr>
<tr {get_highlight_bg_attr("VDP_DS_MON")}><td style="{get_highlight_style("VDP_DS_MON")}padding:10px;border:1px solid #ccc;">VDP_DS_MON</td><td style="{get_highlight_style("VDP_DS_MON")}padding:10px;border:1px solid #ccc;">{curr_cells["VDP_DS_MON"]}</td><td style="{get_highlight_style("VDP_DS_MON")}padding:10px;border:1px solid #ccc;">{curr_dates["VDP_DS_MON"]}</td><td style="{get_highlight_style("VDP_DS_MON")}padding:10px;border:1px solid #ccc;">{prev_cells["VDP_DS_MON"]}</td><td style="{get_highlight_style("VDP_DS_MON")}padding:10px;border:1px solid #ccc;">{prev_dates["VDP_DS_MON"]}</td></tr>
<tr {get_highlight_bg_attr("VDP_DS_SSDP")}><td style="{get_highlight_style("VDP_DS_SSDP")}padding:10px;border:1px solid #ccc;">VDP_DS_SSDP</td><td style="{get_highlight_style("VDP_DS_SSDP")}padding:10px;border:1px solid #ccc;">{curr_cells["VDP_DS_SSDP"]}</td><td style="{get_highlight_style("VDP_DS_SSDP")}padding:10px;border:1px solid #ccc;">{curr_dates["VDP_DS_SSDP"]}</td><td style="{get_highlight_style("VDP_DS_SSDP")}padding:10px;border:1px solid #ccc;">{prev_cells["VDP_DS_SSDP"]}</td><td style="{get_highlight_style("VDP_DS_SSDP")}padding:10px;border:1px solid #ccc;">{prev_dates["VDP_DS_SSDP"]}</td></tr>
<tr {get_highlight_bg_attr("VDP_DS_2")}><td style="{get_highlight_style("VDP_DS_2")}padding:10px;border:1px solid #ccc;">VDP_DS_2</td><td style="{get_highlight_style("VDP_DS_2")}padding:10px;border:1px solid #ccc;">{curr_cells["VDP_DS_2"]}</td><td style="{get_highlight_style("VDP_DS_2")}padding:10px;border:1px solid #ccc;">{curr_dates["VDP_DS_2"]}</td><td style="{get_highlight_style("VDP_DS_2")}padding:10px;border:1px solid #ccc;">{prev_cells["VDP_DS_2"]}</td><td style="{get_highlight_style("VDP_DS_2")}padding:10px;border:1px solid #ccc;">{prev_dates["VDP_DS_2"]}</td></tr>
</table>
"""

# -------------------------------------------------------
# RELEASE NOTE SUMMARY SECTION
# -------------------------------------------------------
def count_components_with_releases():
    """Count how many components have new releases this week"""
    components_with_releases = 0
    for component, version in curr_versions.items():
        if version and version != "None" and version.strip():
            components_with_releases += 1
    
    return components_with_releases

def generate_component_toc():
    """Generate table of contents for components that have releases"""
    component_links = []
    
    # Define component mapping for consistent anchor IDs
    component_anchors = {
        "APIM": "apim",
        "EAH": "eah",
        "VDR": "vdr",
        "DATACHAIN_MONITOR": "datachain_monitor",
        "PATRIC-SSDP": "patric_ssdp",
        "PATRIC": "patric",
        "VDP_PROC": "vdp_proc",
        "VDP_PROC_2": "vdp_proc_2",
        "VDP_STORE": "vdp_store",
        "VDP_STORE_2": "vdp_store_2",
        "VDP_DS": "vdp_ds",
        "VDP_DS_MON": "vdp_ds_mon",
        "VDP_DS_SSDP": "vdp_ds_ssdp",
        "VDP_DS_2": "vdp_ds_2",
    }

    # Check each component for releases and add to TOC if it has releases
    for component in [
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
    ]:
        if component in pv and pv[component]:
            # Use component name as anchor - Confluence will auto-generate for native headings
            anchor_id = component_anchors[component]
            component_links.append(f'<li><a href="#{anchor_id}" style="color:#0066CC;text-decoration:none;">{component}</a></li>')
    
    return '\n'.join(component_links)

# Check how many components have releases to determine layout
num_releases = count_components_with_releases()

if num_releases == 0:
    # No releases - show condensed version
    release_note_summary_html = f"""
<div style="background:#F8F9FA;border:1px solid #e0e0e0;border-radius:8px;padding:25px;margin-bottom:30px;">
    <h2 style="margin-top:0;color:#0747A6;border-bottom:2px solid #0747A6;padding-bottom:10px;">Release Note Summary</h2>
    <p style="color:#666;margin-bottom:20px;">No component releases this week.</p>
    
    <div style="background:#E3F2FD;border:1px solid #2196F3;border-radius:4px;padding:15px;">
        <div style="display:flex;align-items:center;margin-bottom:10px;">
            <span style="background:#2196F3;color:white;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;margin-right:10px;font-size:12px;">ℹ</span>
            <strong>Product Team Notes:</strong>
        </div>
        <div style="margin-left:30px;">
            <p style="margin:0;color:#666;font-style:italic;">High-level business impact and change descriptions will be added by the Product Team after release deployment.</p>
        </div>
    </div>
</div>
"""
else:
    # One or more releases - show full detailed version
    release_note_summary_html = f"""
<div style="display:flex;gap:30px;margin-bottom:30px;align-items:flex-start;flex-wrap:nowrap;width:100%;">
    <div style="flex:2;min-width:400px;max-width:65%;">
        <h2 style="margin-top:0;">Release Note Summary</h2>
        <p style="color:#666;margin-bottom:20px;"><em>High-level description of the primary changes from a business perspective, updated by the Product Team.</em></p>
        
        <div style="background:#E8F5E8;border:1px solid #4CAF50;border-radius:4px;padding:15px;margin-bottom:15px;">
            <div style="display:flex;align-items:center;margin-bottom:10px;">
                <span style="background:#4CAF50;color:white;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;margin-right:10px;font-size:12px;">✓</span>
                <strong>What we added:</strong>
            </div>
            <div style="margin-left:30px;min-height:40px;padding:10px;background:#f9f9f9;border-radius:3px;border:1px dashed #ccc;">
                <em style="color:#999;">Content to be filled manually by Product Team</em>
            </div>
        </div>
        
        <div style="background:#E8F5E8;border:1px solid #4CAF50;border-radius:4px;padding:15px;margin-bottom:15px;">
            <div style="display:flex;align-items:center;margin-bottom:10px;">
                <span style="background:#4CAF50;color:white;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;margin-right:10px;font-size:12px;">✓</span>
                <strong>What we changed:</strong>
            </div>
            <div style="margin-left:30px;min-height:40px;padding:10px;background:#f9f9f9;border-radius:3px;border:1px dashed #ccc;">
                <em style="color:#999;">Content to be filled manually by Product Team</em>
            </div>
        </div>
        
        <div style="background:#F3E5F5;border:1px solid #9C27B0;border-radius:4px;padding:15px;margin-bottom:15px;">
            <div style="display:flex;align-items:center;margin-bottom:10px;">
                <span style="background:#9C27B0;color:white;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;margin-right:10px;font-size:12px;">🗑</span>
                <strong>What we Deprecated/ Removed:</strong>
            </div>
            <div style="margin-left:30px;">
                <p style="margin:0;color:#666;">No explicit deprecations or removals were executed in this release.</p>
            </div>
        </div>
        
        <div style="background:#E8F5E8;border:1px solid #4CAF50;border-radius:4px;padding:15px;margin-bottom:15px;">
            <div style="display:flex;align-items:center;margin-bottom:10px;">
                <span style="background:#4CAF50;color:white;border-radius:50%;width:20px;height:20px;display:flex;align-items:center;justify-content:center;margin-right:10px;font-size:12px;">✓</span>
                <strong>What we fixed:</strong>
            </div>
            <div style="margin-left:30px;min-height:40px;padding:10px;background:#f9f9f9;border-radius:3px;border:1px dashed #ccc;">
                <em style="color:#999;">Content to be filled manually by Product Team</em>
            </div>
        </div>
    </div>
    
    <div style="flex:1;min-width:300px;max-width:35%;background:#F8F9FA;padding:20px;border-radius:4px;height:fit-content;border:1px solid #e0e0e0;">
        <h3 style="margin-top:0;color:#0747A6;border-bottom:2px solid #0747A6;padding-bottom:5px;">TABLE of Contents</h3>
        <ol style="line-height:1.8;margin-left:0;padding-left:20px;">
            <li><a href="#release-summary" style="color:#0066CC;text-decoration:none;">Release Summary</a></li>
            <li><a href="#release-note-summary" style="color:#0066CC;text-decoration:none;">Release Note Summary</a></li>
            <li><a href="#release-notes" style="color:#0066CC;text-decoration:none;">RELEASE NOTES</a>
                <ol style="margin-left:10px;">
                    <li><a href="#high-level-summary" style="color:#0066CC;text-decoration:none;">High level summary by application</a>
                        <ol style="margin-left:10px;">
                            {generate_component_toc()}
                        </ol>
                    </li>
                    <li><a href="#detailed-list" style="color:#0066CC;text-decoration:none;">Detailed List</a></li>
                </ol>
            </li>
        </ol>
    </div>
</div>
"""

# -------------------------------------------------------
# RELEASE NOTES INTRODUCTION SECTION
# -------------------------------------------------------
release_notes_intro_html = """
<h1>RELEASE NOTES</h1>
<p>To clarify the releases across the various enablers and components, we have divided the release notes into a high-level summary and a detailed list of user stories extracted from Jira.</p>

<h3>High level summary by application</h3>
"""

# -------------------------------------------------------
# SECTIONS: unchanged from your script
# -------------------------------------------------------
section_html = ""

# APIM
apim_html = ""
for ver in sorted(pv["APIM"].keys(), key=vtuple, reverse=True):
    d = pv["APIM"][ver]
    apim_html += make_table(
        f"APIM-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra="<a href='https://pages.github.psa-cloud.com/mph00/cloud-api-capabilities/#/changelog' target='_blank'>Swagger Changelog</a>"
    )
if apim_html.strip():
    section_html += "<h3 id='APIM'>APIM</h3>\n" + apim_html

# EAH
eah_html = ""
for ver in sorted(pv["EAH"].keys(), key=vtuple, reverse=True):
    d = pv["EAH"][ver]
    eah_html += make_table(
        f"EAH-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra="<a href='https://pages.github.psa-cloud.com/mph00/cloud-api-capabilities/#/changelog' target='_blank'>Swagger Changelog</a>"
    )
if eah_html.strip():
    section_html += "<h3 id='EAH'>EAH</h3>\n" + eah_html

# VDR
vdr_html = ""
for ver in sorted(pv["VDR"].keys(), key=vtuple, reverse=True):
    d = pv["VDR"][ver]
    vdr_html += make_table(
        f"VDR-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdr_html.strip():
    section_html += "<h3 id='VDR'>VDR</h3>\n" + vdr_html

# PATRIC
patric_html = ""
for ver in sorted(pv["PATRIC"].keys(), key=vtuple, reverse=True):
    d = pv["PATRIC"][ver]
    patric_html += make_table(
        f"PATRIC-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if patric_html.strip():
    section_html += "<h3 id='PATRIC'>PATRIC</h3>\n" + patric_html

# DATACHAIN_MONITOR
datachain_monitor_html = ""
for ver in sorted(pv["DATACHAIN_MONITOR"].keys(), key=vtuple, reverse=True):
    d = pv["DATACHAIN_MONITOR"][ver]
    datachain_monitor_html += make_table(
        f"DATACHAIN_MONITOR-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if datachain_monitor_html.strip():
    section_html += "<h3 id='DATACHAIN_MONITOR'>DATACHAIN_MONITOR</h3>\n" + datachain_monitor_html

# PATRIC-SSDP
patric_ssdp_html = ""
for ver in sorted(pv["PATRIC-SSDP"].keys(), key=vtuple, reverse=True):
    d = pv["PATRIC-SSDP"][ver]
    patric_ssdp_html += make_table(
        f"PATRIC-SSDP-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if patric_ssdp_html.strip():
    section_html += "<h3 id='PATRIC-SSDP'>PATRIC-SSDP</h3>\n" + patric_ssdp_html

# VDP_PROC
vdp_proc_html = ""
for ver in sorted(pv["VDP_PROC"].keys(), key=vtuple, reverse=True):
    d = pv["VDP_PROC"][ver]
    vdp_proc_html += make_table(
        f"VDP_PROC-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdp_proc_html.strip():
    section_html += "<h3 id='VDP_PROC'>VDP_PROC</h3>\n" + vdp_proc_html

# VDP_PROC_2
vdp_proc_2_html = ""
for ver in sorted(pv["VDP_PROC_2"].keys(), key=vtuple, reverse=True):
    d = pv["VDP_PROC_2"][ver]
    vdp_proc_2_html += make_table(
        f"VDP_PROC_2-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdp_proc_2_html.strip():
    section_html += "<h3 id='VDP_PROC_2'>VDP_PROC_2</h3>\n" + vdp_proc_2_html

# VDP_STORE
vdp_store_html = ""
for ver in sorted(pv["VDP_STORE"].keys(), key=vtuple, reverse=True):
    d = pv["VDP_STORE"][ver]
    vdp_store_html += make_table(
        f"VDP_STORE-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdp_store_html.strip():
    section_html += "<h3 id='VDP_STORE'>VDP_STORE</h3>\n" + vdp_store_html

# VDP_STORE_2
vdp_store_2_html = ""
for ver in sorted(pv["VDP_STORE_2"].keys(), key=vtuple, reverse=True):
    d = pv["VDP_STORE_2"][ver]
    vdp_store_2_html += make_table(
        f"VDP_STORE_2-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdp_store_2_html.strip():
    section_html += "<h3 id='VDP_STORE_2'>VDP_STORE_2</h3>\n" + vdp_store_2_html

# VDP_DS
vdp_ds_html = ""
for ver in sorted(pv["VDP_DS"].keys(), key=vtuple, reverse=True):
    d = pv["VDP_DS"][ver]
    vdp_ds_html += make_table(
        f"VDP_DS-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdp_ds_html.strip():
    section_html += "<h3 id='VDP_DS'>VDP_DS</h3>\n" + vdp_ds_html

# VDP_DS_MON
vdp_ds_mon_html = ""
for ver in sorted(pv["VDP_DS_MON"].keys(), key=vtuple, reverse=True):
    d = pv["VDP_DS_MON"][ver]
    vdp_ds_mon_html += make_table(
        f"VDP_DS_MON-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdp_ds_mon_html.strip():
    section_html += "<h3 id='VDP_DS_MON'>VDP_DS_MON</h3>\n" + vdp_ds_mon_html

# VDP_DS_SSDP
vdp_ds_ssdp_html = ""
for ver in sorted(pv["VDP_DS_SSDP"].keys(), key=vtuple, reverse=True):
    d = pv["VDP_DS_SSDP"][ver]
    vdp_ds_ssdp_html += make_table(
        f"VDP_DS_SSDP-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdp_ds_ssdp_html.strip():
    section_html += "<h3 id='VDP_DS_SSDP'>VDP_DS_SSDP</h3>\n" + vdp_ds_ssdp_html

# VDP_DS_2
vdp_ds_2_html = ""
for ver in sorted(pv["VDP_DS_2"].keys(), key=vtuple, reverse=True):
    d = pv["VDP_DS_2"][ver]
    vdp_ds_2_html += make_table(
        f"VDP_DS_2-{ver}",
        make_box("Features", "#E3FCEF", d["FEATURES"])
        + make_box("Code Refactoring", "#DEEBFF", d["CODE"])
        + make_box("Bug Fixes", "#FFEBE6", d["BUGS"]),
        status=d["STATUS"],
        deploy_pprod_date=d["DEPLOY"],
        extra=""
    )
if vdp_ds_2_html.strip():
    section_html += "<h3 id='VDP_DS_2'>VDP_DS_2</h3>\n" + vdp_ds_2_html

# Non-APIM/EAH component sections are intentionally disabled.
# Keeping the previous section logic commented out by removal for APIM/EAH-only mode.


linked_html = build_linked_table(blocks)

html = f"""
{release_summary_html}

{release_notes_intro_html}

{section_html}

{linked_html}
"""

write(SUMMARY_HTML, html)

# Check if there are actual releases in the parsed data (not just stopper file)
has_actual_releases = any(pv.get(comp, {}) for comp in pv.keys())

meta = {
    "week": week_display,
    "has_releases": has_actual_releases,
    "prev_versions": prev_versions,
    "curr_versions": curr_versions,
}

write(META_FILE, json.dumps(meta, indent=2))

with open(WEEK_FILE, "w", encoding="utf-8") as f:
    f.write(str(week_display))

print("summarize.py completed successfully with historical lookback for Release Summary.")
