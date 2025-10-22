#!/usr/bin/env python3
"""Test date formatting in migration script."""

from datetime import datetime, timezone
import neo4j.time

def format_datetime_original(value):
    """Original format_value logic for datetime."""
    if isinstance(value, datetime):
        return f"'{value.isoformat()}'"
    elif hasattr(value, 'to_native'):
        # Handle Neo4j DateTime objects
        native_value = value.to_native()
        if isinstance(native_value, datetime):
            return f"'{native_value.isoformat()}'"
    return str(value)

def format_datetime_fixed(value):
    """Fixed format_value logic ensuring timezone."""
    if isinstance(value, datetime):
        # Ensure timezone is present
        if value.tzinfo is None:
            # Assume UTC for naive datetime
            value = value.replace(tzinfo=timezone.utc)
        # isoformat() includes timezone if present
        iso_str = value.isoformat()
        # Ensure it ends with timezone (handle both +00:00 and Z formats)
        if not ('+' in iso_str or iso_str.endswith('Z')):
            iso_str += '+00:00'
        return f"'{iso_str}'"
    elif hasattr(value, 'to_native'):
        # Handle Neo4j DateTime objects
        native_value = value.to_native()
        if isinstance(native_value, datetime):
            return format_datetime_fixed(native_value)
    return str(value)

# Test cases
test_cases = [
    # Python datetime with timezone
    datetime(2025, 9, 4, 5, 46, 33, 520050, tzinfo=timezone.utc),
    # Python datetime without timezone (naive)
    datetime(2025, 9, 1, 13, 38, 54, 664754),
    # Neo4j DateTime mock (would need actual neo4j library for real test)
]

print("=" * 60)
print("DATE FORMAT TESTING")
print("=" * 60)

for dt in test_cases:
    print(f"\nInput: {dt}")
    print(f"  Type: {type(dt).__name__}")
    print(f"  Has tzinfo: {hasattr(dt, 'tzinfo') and dt.tzinfo is not None}")
    
    original = format_datetime_original(dt)
    fixed = format_datetime_fixed(dt)
    
    print(f"  Original format: {original}")
    print(f"  Fixed format:    {fixed}")
    
    # Check if it has proper timezone suffix
    has_tz = '+00:00' in original or 'Z' in original
    print(f"  Original has timezone: {'✅' if has_tz else '❌'}")
    
    has_tz_fixed = '+00:00' in fixed or 'Z' in fixed
    print(f"  Fixed has timezone: {'✅' if has_tz_fixed else '❌'}")

print("\n" + "=" * 60)
print("CONCLUSION")
print("=" * 60)
print("The issue: datetime.isoformat() doesn't add timezone for naive datetime objects.")
print("Solution: Ensure all datetime objects have timezone before calling isoformat().")
print("\nTarget format: YYYY-MM-DDTHH:MM:SS.ffffff+00:00")
