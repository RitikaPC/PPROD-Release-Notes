#!/usr/bin/env python3
"""Check what week things fall into"""

import datetime

dates_to_check = [
    "2026-02-04",  # Feb 4, 2026
    "2026-02-05",  # Feb 5, 2026
    "2026-02-16",  # Today
]

for date_str in dates_to_check:
    dt = datetime.datetime.fromisoformat(date_str).date()
    iso_year, iso_week, iso_weekday = dt.isocalendar()
    print(f"{date_str}: Week {iso_week}/{iso_year} (weekday: {iso_weekday})")
