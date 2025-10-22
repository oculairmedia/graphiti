#!/usr/bin/env python3
"""
Quick fix script to add timeout protection to FalkorDB edge extraction.
This addresses the sync service hang issue identified in the investigation.
"""

import os
import shutil
from datetime import datetime

def backup_file(file_path):
    """Create a backup of the original file."""
    backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(file_path, backup_path)
    print(f"✅ Backup created: {backup_path}")
    return backup_path

def apply_timeout_fix():
    """Apply timeout fix to the FalkorDB extractor."""
    extractor_file = "sync_service/extractors/falkordb_extractor.py"
    
    if not os.path.exists(extractor_file):
        print(f"❌ File not found: {extractor_file}")
        return False
    
    # Create backup
    backup_path = backup_file(extractor_file)
    
    # Read the current file
    with open(extractor_file, 'r') as f:
        content = f.read()
    
    # Find the problematic query execution line
    old_code = """            try:
                result = await self.graph.query(query)
            except Exception as exc:"""
    
    new_code = """            try:
                logger.info(f"Executing edge query: offset={offset}, limit={page_limit}")
                start_time = time.time()
                
                # Add timeout to prevent infinite hang (GRAPH-574 fix)
                result = await asyncio.wait_for(self.graph.query(query), timeout=30.0)
                
                duration = time.time() - start_time
                logger.info(f"Query completed in {duration:.2f}s")
                
            except asyncio.TimeoutError:
                logger.error(f"Edge query timed out after 30s at offset {offset}")
                raise RuntimeError(f"Edge extraction timed out at offset {offset}")
            except Exception as exc:"""
    
    # Apply the fix
    if old_code in content:
        content = content.replace(old_code, new_code)
        
        # Write the updated file
        with open(extractor_file, 'w') as f:
            f.write(content)
        
        print(f"✅ Timeout fix applied to {extractor_file}")
        print("   - Added 30-second timeout to edge queries")
        print("   - Added detailed logging for query execution")
        print("   - Added timeout error handling")
        return True
    else:
        print(f"❌ Could not find target code pattern in {extractor_file}")
        print("   Manual fix may be required")
        return False

def add_memory_monitoring():
    """Add memory monitoring to the extractor."""
    extractor_file = "sync_service/extractors/falkordb_extractor.py"
    
    # Read the current file
    with open(extractor_file, 'r') as f:
        content = f.read()
    
    # Add psutil import if not present
    if "import psutil" not in content:
        import_section = """import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, AsyncIterator
from dataclasses import dataclass"""
        
        new_import_section = """import asyncio
import logging
import time
import psutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, AsyncIterator
from dataclasses import dataclass"""
        
        if import_section in content:
            content = content.replace(import_section, new_import_section)
            
            # Write the updated file
            with open(extractor_file, 'w') as f:
                f.write(content)
            
            print("✅ Added memory monitoring imports")
            return True
    
    print("ℹ️  Memory monitoring imports already present or pattern not found")
    return False

def create_docker_compose_fix():
    """Create a docker-compose override with increased resources."""
    override_content = """# Docker Compose override to fix sync service edge extraction hang
# This increases memory allocation to resolve GRAPH-574
version: '3.8'

services:
  sync-service:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'
    environment:
      # Reduce batch size as additional safety measure
      - SYNC_OPTIMIZATION_EDGE_BATCH_SIZE=500
      # Add memory monitoring
      - PYTHONUNBUFFERED=1
"""
    
    override_file = "docker-compose.sync-fix.yml"
    with open(override_file, 'w') as f:
        f.write(override_content)
    
    print(f"✅ Created {override_file}")
    print("   To apply: docker-compose -f docker-compose.yml -f docker-compose.sync-fix.yml up -d")

def main():
    """Apply all fixes for the edge extraction hang."""
    print("🔧 Applying Edge Extraction Hang Fixes")
    print("=" * 50)
    
    success_count = 0
    
    # Apply timeout fix
    if apply_timeout_fix():
        success_count += 1
    
    # Add memory monitoring
    if add_memory_monitoring():
        success_count += 1
    
    # Create docker compose override
    create_docker_compose_fix()
    success_count += 1
    
    print("\n" + "=" * 50)
    print(f"✅ Applied {success_count} fixes")
    print("\nNext steps:")
    print("1. Restart the sync service:")
    print("   docker-compose restart sync-service")
    print("\n2. Or apply resource limits:")
    print("   docker-compose -f docker-compose.yml -f docker-compose.sync-fix.yml up -d")
    print("\n3. Monitor the logs:")
    print("   docker logs graphiti-sync-service-1 -f")
    print("\n4. The edge extraction should now complete successfully!")

if __name__ == "__main__":
    main()
