#!/usr/bin/env python3

import os
import re
import datetime
import requests

JIRA_BASE = "https://stla-iotpf-jira.atlassian.net"
USERNAME = os.getenv("JIRA_USERNAME")
API_TOKEN = os.getenv("JIRA_API_TOKEN")
if not USERNAME or not API_TOKEN:
    raise SystemExit("Set JIRA_USERNAME and JIRA_API_TOKEN in the environment.")

BOARD_ID = 35
QUICKFILTER_ID = 169

RCZ_RE = re.compile(r"SSDP\s+RCZ", re.IGNORECASE)

session = requests.Session()
session.auth = (USERNAME, API_TOKEN)
session.headers.update({"Accept": "application/json"})


def agile_board_issues():
    issues = []
    start = 0

    while True:
        resp = session.get(
            f"{JIRA_BASE}/rest/agile/1.0/board/{BOARD_ID}/issue",
            params={
                "startAt": start,
                "maxResults": 200,
                "quickFilter": QUICKFILTER_ID,
                "fields": "summary,status,issuetype",
            },
        )
        data = resp.json()
        chunk = data.get("issues", [])
        issues.extend(chunk)
        start += len(chunk)
        if start >= data.get("total", 0):
            break

    return issues


def get_issue_full(key):
    r = session.get(
        f"{JIRA_BASE}/rest/api/3/issue/{key}",
        params={"expand": "changelog"},
    )
    return r.json()


def iso_week(date_str):
    d = datetime.datetime.strptime(date_str.split("T")[0], "%Y-%m-%d").date()
    return d.isocalendar()


print("=" * 80)
print("RCZ STATUS HISTORY WITH ISO WEEK")
print("=" * 80)

issues = agile_board_issues()

for it in issues:
    fields = it["fields"]
    summary = fields["summary"]
    issuetype = fields["issuetype"]["name"]

    if issuetype != "Enabler Version - IOT PF":
        continue

    if not RCZ_RE.search(summary):
        continue

    key = it["key"]
    full = get_issue_full(key)

    print(f"\nISSUE: {key}")
    print(f"SUMMARY: {summary}")
    print("-" * 60)

    histories = full.get("changelog", {}).get("histories", [])
    found = False

    for h in histories:
        created = h.get("created")
        for item in h.get("items", []):
            if item.get("field") == "status":
                found = True
                y, w, _ = iso_week(created)
                print(
                    f"{created} | ISO {y}-W{w:02d} | "
                    f"{item.get('fromString')} → {item.get('toString')}"
                )

    if not found:
        print("NO STATUS HISTORY FOUND")

print("\nDONE")