#!/usr/bin/env python3
"""Test VDP_PROC extraction logic"""

import os
import sys
import datetime
from dotenv import load_dotenv

load_dotenv()

# Add the extract module functions
sys.path.insert(0, '/home/t0349e1/Documents/ssdp release notes/SSDP-Release-Notes')
from extract import jira_get_issue_full, parse_iso_date, get_deploying_to_prod_date_from_history

# Check what week we're targeting
today = datetime.date.today()
iso_year, iso_week, _ = today.isocalendar()
print(f"Today: {today}")
print(f"Current week: {iso_week}/{iso_year}")

# Get the VDP_PROC issue
key = "IOTPF-IS201"
print(f"\nFetching {key}...")
full = jira_get_issue_full(key)

if full:
    f = full.get("fields", {}) or {}
    status_name = (f.get("status") or {}).get("name", "")
    print(f"Status: {status_name}")
    
    # Check custom fields
    print(f"customfield_10044 (PROD Deploy Date): {f.get('customfield_10044')}")
    print(f"customfield_10043: {f.get('customfield_10043')}")
    
    # Try the history function
    deploy_date_str = get_deploying_to_prod_date_from_history(full)
    print(f"Date from history: {deploy_date_str}")
    
    # Parse the date
    if deploy_date_str:
        deploy_date = parse_iso_date(deploy_date_str)
        if deploy_date:
            iso_y, iso_w, _ = deploy_date.isocalendar()
            print(f"Parsed date: {deploy_date}")
            print(f"Parsed week: {iso_w}/{iso_y}")
        else:
            print("Could not parse date!")
    else:
        print("No date found!")
else:
    print(f"Failed to fetch {key}")
