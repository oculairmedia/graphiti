#!/usr/bin/env python3
"""Test the fixed date formatting in migration script."""

import sys
sys.path.insert(0, '/opt/stacks/graphiti/sync_service')

from simple_migration import format_value
from datetime import datetime, timezone

print("=" * 60)
print("TESTING FIXED DATE FORMATTING")
print("=" * 60)

# Test cases
test_cases = [
    ("Datetime with timezone", datetime(2025, 9, 4, 5, 46, 33, 520050, tzinfo=timezone.utc)),
    ("Datetime without timezone (naive)", datetime(2025, 9, 1, 13, 38, 54, 664754)),
    ("Datetime with microseconds", datetime(2025, 8, 29, 14, 34, 21, 461721)),
    ("Datetime without microseconds", datetime(2025, 8, 29, 14, 34, 21)),
]

for description, dt in test_cases:
    formatted = format_value(dt)
    print(f"\n{description}:")
    print(f"  Input:  {dt}")
    print(f"  Output: {formatted}")
    
    # Check format requirements
    has_tz = '+00:00' in formatted or 'Z' in formatted
    has_microseconds = '.' in formatted
    
    print(f"  Has timezone suffix: {'✅' if has_tz else '❌'}")
    print(f"  Has microseconds: {'✅' if has_microseconds else '❌'}")
    
    # Extract just the date string (remove quotes)
    date_str = formatted.strip("'")
    
    # Verify it can be parsed back
    try:
        parsed = datetime.fromisoformat(date_str.replace('+00:00', '+00:00'))
        print(f"  Can be parsed: ✅")
    except Exception as e:
        print(f"  Can be parsed: ❌ ({e})")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print("All datetime values should now have the +00:00 timezone suffix")
print("Target format: YYYY-MM-DDTHH:MM:SS.ffffff+00:00")
