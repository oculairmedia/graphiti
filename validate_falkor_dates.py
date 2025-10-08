#!/usr/bin/env python3
"""Validate FalkorDB date fields against known good format."""

import redis
from datetime import datetime
import json

def validate_date_format(date_str):
    """Validate date string matches expected format."""
    if not date_str:
        return False, "Missing date"
    
    try:
        # Expected format: 2025-09-04T05:46:33.520050+00:00
        dt = datetime.fromisoformat(date_str.replace('+00:00', '+00:00'))
        
        # Check it has microseconds
        if '.' not in date_str:
            return False, "Missing microseconds"
        
        # Check timezone
        if not date_str.endswith('+00:00'):
            return False, f"Wrong timezone: {date_str[-6:]}"
            
        return True, "Valid"
    except Exception as e:
        return False, f"Parse error: {e}"

def validate_falkor_dates():
    """Validate all date fields in FalkorDB."""
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    graph = r.graph('graphiti_migration')
    
    print("=" * 60)
    print("FALKORDB DATE VALIDATION REPORT")
    print("=" * 60)
    
    # Count totals
    result = graph.query("MATCH (n) RETURN count(n) as total")
    total_nodes = result.result_set[0][0]
    
    result = graph.query("MATCH ()-[r]->() RETURN count(r) as total")
    total_edges = result.result_set[0][0]
    
    print(f"\nTotal nodes: {total_nodes}")
    print(f"Total edges: {total_edges}")
    
    # Validate Entity nodes
    print("\n" + "=" * 40)
    print("ENTITY NODES")
    print("=" * 40)
    
    result = graph.query("""
        MATCH (n:Entity)
        RETURN n.uuid, n.name, n.created_at
        ORDER BY n.created_at DESC
    """)
    
    entity_issues = []
    for record in result.result_set:
        uuid, name, created_at = record
        valid, msg = validate_date_format(created_at)
        if not valid:
            entity_issues.append(f"  - {name} ({uuid}): {msg}")
    
    result = graph.query("MATCH (n:Entity) RETURN count(n)")
    entity_count = result.result_set[0][0]
    
    if entity_issues:
        print(f"❌ Found {len(entity_issues)} issues out of {entity_count} Entity nodes:")
        for issue in entity_issues[:10]:  # Show first 10
            print(issue)
        if len(entity_issues) > 10:
            print(f"  ... and {len(entity_issues) - 10} more")
    else:
        print(f"✅ All {entity_count} Entity nodes have valid created_at dates")
    
    # Check for missing created_at
    result = graph.query("MATCH (n:Entity) WHERE n.created_at IS NULL RETURN count(n)")
    missing_count = result.result_set[0][0]
    if missing_count > 0:
        print(f"⚠️  {missing_count} Entity nodes are missing created_at")
    
    # Validate Episodic nodes
    print("\n" + "=" * 40)
    print("EPISODIC NODES")
    print("=" * 40)
    
    result = graph.query("""
        MATCH (n:Episodic)
        RETURN n.uuid, n.name, n.created_at, n.valid_at
        ORDER BY n.created_at DESC
    """)
    
    episodic_issues = []
    for record in result.result_set:
        uuid, name, created_at, valid_at = record
        
        # Check created_at
        valid_c, msg_c = validate_date_format(created_at)
        if not valid_c:
            episodic_issues.append(f"  - {name} ({uuid}): created_at {msg_c}")
        
        # Check valid_at
        valid_v, msg_v = validate_date_format(valid_at)
        if not valid_v:
            episodic_issues.append(f"  - {name} ({uuid}): valid_at {msg_v}")
    
    result = graph.query("MATCH (n:Episodic) RETURN count(n)")
    episodic_count = result.result_set[0][0]
    
    if episodic_issues:
        print(f"❌ Found {len(episodic_issues)} issues out of {episodic_count} Episodic nodes:")
        for issue in episodic_issues[:10]:
            print(issue)
        if len(episodic_issues) > 10:
            print(f"  ... and {len(episodic_issues) - 10} more")
    else:
        print(f"✅ All {episodic_count} Episodic nodes have valid date fields")
    
    # Validate RELATES_TO edges
    print("\n" + "=" * 40)
    print("RELATES_TO EDGES")
    print("=" * 40)
    
    result = graph.query("""
        MATCH ()-[r:RELATES_TO]->()
        RETURN r.uuid, r.name, r.created_at, r.valid_at, r.invalid_at, r.expired_at
        ORDER BY r.created_at DESC
    """)
    
    edge_issues = []
    date_field_stats = {
        'created_at': {'present': 0, 'valid': 0},
        'valid_at': {'present': 0, 'valid': 0},
        'invalid_at': {'present': 0, 'valid': 0},
        'expired_at': {'present': 0, 'valid': 0}
    }
    
    for record in result.result_set:
        uuid, name, created_at, valid_at, invalid_at, expired_at = record
        
        # Check each date field
        for field_name, field_value in [
            ('created_at', created_at),
            ('valid_at', valid_at),
            ('invalid_at', invalid_at),
            ('expired_at', expired_at)
        ]:
            if field_value:
                date_field_stats[field_name]['present'] += 1
                valid, msg = validate_date_format(field_value)
                if valid:
                    date_field_stats[field_name]['valid'] += 1
                elif field_name == 'created_at':  # created_at should always be valid
                    edge_issues.append(f"  - {name} ({uuid}): {field_name} {msg}")
    
    result = graph.query("MATCH ()-[r:RELATES_TO]->() RETURN count(r)")
    relates_count = result.result_set[0][0]
    
    print(f"Total RELATES_TO edges: {relates_count}")
    print("\nDate field statistics:")
    for field_name, stats in date_field_stats.items():
        print(f"  {field_name:12}: {stats['present']:4}/{relates_count} present, {stats['valid']:4} valid")
    
    if edge_issues:
        print(f"\n❌ Found {len(edge_issues)} validation issues:")
        for issue in edge_issues[:10]:
            print(issue)
        if len(edge_issues) > 10:
            print(f"  ... and {len(edge_issues) - 10} more")
    else:
        print(f"\n✅ All RELATES_TO edges have valid date formats")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_issues = len(entity_issues) + len(episodic_issues) + len(edge_issues)
    if total_issues == 0:
        print("✅ ALL DATE FIELDS ARE VALID!")
        print("\nExpected format: YYYY-MM-DDTHH:MM:SS.ffffff+00:00")
        print("Example: 2025-09-04T05:46:33.520050+00:00")
    else:
        print(f"❌ Found {total_issues} total issues across the database")
        print("\nMost common issues:")
        all_issues = entity_issues + episodic_issues + edge_issues
        issue_types = {}
        for issue in all_issues:
            issue_type = issue.split(':')[-1].strip()
            issue_types[issue_type] = issue_types.get(issue_type, 0) + 1
        
        for issue_type, count in sorted(issue_types.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {issue_type}: {count} occurrences")

if __name__ == "__main__":
    validate_falkor_dates()
