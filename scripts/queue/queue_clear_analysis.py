#!/usr/bin/env python3
"""
Pre-clear analysis of the Graphiti queue to understand what we're clearing.
"""

import asyncio
import sys
import os
from collections import defaultdict
from datetime import datetime
import json

sys.path.append('/opt/stacks/graphiti')

async def analyze_queue_before_clear():
    """Analyze the queue contents before clearing."""
    
    # Import the queue client
    from graphiti_core.ingestion.queue_client import QueuedClient
    
    print("🔍 Pre-Clear Queue Analysis")
    print("=" * 50)
    
    try:
        client = QueuedClient('http://192.168.50.90:8093')
        
        # Get basic queue stats
        stats = await client.get_stats()
        print(f"📊 Total messages in queue: {stats.get('message_count', 'unknown')}")
        print(f"📈 Visible messages: {stats.get('visible_count', 'unknown')}")
        print()
        
        # Sample some messages to understand the breakdown
        print("📋 Sampling queue contents...")
        sample_size = 50
        messages = await client.poll('ingestion', count=sample_size)
        
        group_counts = defaultdict(int)
        message_types = defaultdict(int)
        date_counts = defaultdict(int)
        
        print(f"📊 Analyzing {len(messages)} sample messages:")
        
        for msg_id, task, poll_tag in messages:
            try:
                # Count by group_id
                if hasattr(task, 'payload') and isinstance(task.payload, dict):
                    group_id = task.payload.get('group_id', 'unknown')
                    group_counts[group_id] += 1
                    
                    # Extract date if available
                    name = task.payload.get('name', '')
                    if 'claude_session' in name or 'claude_tools' in name:
                        # Try to extract date from name patterns
                        for part in name.split('_'):
                            if len(part) == 8 and part.isdigit():  # YYYYMMDD format
                                try:
                                    date_obj = datetime.strptime(part, '%Y%m%d')
                                    date_str = date_obj.strftime('%Y-%m-%d')
                                    date_counts[date_str] += 1
                                    break
                                except:
                                    pass
                
                # Count by message type
                if hasattr(task, 'type'):
                    message_types[task.type] += 1
                    
                # Return message to queue so we don't consume it
                await client.delete(msg_id, 'ingestion', poll_tag)
                
            except Exception as e:
                print(f"⚠️  Error analyzing message {msg_id}: {e}")
                # Still return it to queue
                try:
                    await client.delete(msg_id, 'ingestion', poll_tag)
                except:
                    pass
        
        print(f"\n🔍 Sample Analysis Results:")
        print(f"📁 Group ID breakdown:")
        for group_id, count in sorted(group_counts.items()):
            print(f"   {group_id}: {count}")
        
        print(f"\n📅 Date breakdown (from sample):")
        for date, count in sorted(date_counts.items()):
            print(f"   {date}: {count}")
        
        print(f"\n📝 Message type breakdown:")
        for msg_type, count in sorted(message_types.items()):
            print(f"   {msg_type}: {count}")
        
        # Extrapolate to full queue
        total_messages = stats.get('message_count', 0)
        if total_messages > 0 and len(messages) > 0:
            print(f"\n📈 Extrapolated Full Queue (based on {len(messages)} sample):")
            scale_factor = total_messages / len(messages)
            for group_id, count in sorted(group_counts.items()):
                estimated = int(count * scale_factor)
                print(f"   {group_id}: ~{estimated:,}")
        
        print(f"\n✅ Analysis complete - ready for queue clear")
        return True
        
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(analyze_queue_before_clear())
    sys.exit(0 if success else 1)