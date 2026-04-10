#!/usr/bin/env python3
import os
import sys
import json
from jira import JIRA

# Load Jira credentials from environment
JIRA_BASE = os.environ.get("JIRA_BASE", "stla-iotpf-jira.atlassian.net")
JIRA_USER = os.environ.get("JIRA_USER", "")
JIRA_TOKEN = os.environ.get("JIRA_TOKEN", "")

# Connect to Jira
jira_client = JIRA(server=f"https://{JIRA_BASE}", basic_auth=(JIRA_USER, JIRA_TOKEN), options={"verify": False})

# Test ticket IOTPF-14118 (VDP_STORE-2.19.2)
try:
    issue = jira_client.issue("IOTPF-14118")
    print(f"Issue: {issue.key}")
    print(f"Summary: {issue.fields.summary}")
    print(f"Status: {issue.fields.status.name if issue.fields.status else 'N/A'}")
    
    # Check custom fields
    customfield_10041 = issue.fields.customfield_10041  # Enabler name
    customfield_10042 = issue.fields.customfield_10042  # Enabler version
    customfield_10043 = issue.fields.customfield_10043  # PPROD date
    customfield_10044 = issue.fields.customfield_10044  # Prod date
    
    print(f"Enabler name (10041): {customfield_10041}")
    print(f"Enabler version (10042): {customfield_10042}")
    print(f"PPROD date (10043): {customfield_10043}")
    print(f"Prod date (10044): {customfield_10044}")
    
    # Check status transitions
    print("\nStatus transitions:")
    changelog = issue.changelog
    for history in changelog.histories:
        for item in history.items:
            if item.field == "status":
                print(f"  {history.created}: {item.fromString} -> {item.toString}")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
