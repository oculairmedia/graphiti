#!/usr/bin/env python3
"""
Backfill valid_at for episodes missing it

This script finds all Episodic nodes without valid_at and sets it to created_at.
"""

import asyncio
import sys
import os

# Add graphiti to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_info(text: str):
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")

async def check_missing_valid_at(driver: FalkorDriver) -> int:
    """Count episodes without valid_at"""
    print_header("1. Checking for Episodes Without valid_at")
    
    query = """
    MATCH (ep:Episodic)
    WHERE ep.valid_at IS NULL
    RETURN count(ep) as missing_count
    """
    
    try:
        result = await driver.execute_query(query)
        
        if result and len(result[0]) > 0:
            # FalkorDB returns list of records
            missing_count = result[0][0].get('missing_count', 0)
            
            if missing_count > 0:
                print_warning(f"Found {missing_count} episodes without valid_at")
            else:
                print_success("All episodes have valid_at set")
            
            return missing_count
        else:
            print_info("No results returned")
            return 0
            
    except Exception as e:
        print_error(f"Error checking episodes: {e}")
        raise

async def backfill_valid_at(driver: FalkorDriver, dry_run: bool = False) -> int:
    """Backfill valid_at for episodes missing it"""
    print_header("2. Backfilling valid_at")
    
    if dry_run:
        print_warning("DRY RUN MODE - No changes will be made")
        query = """
        MATCH (ep:Episodic)
        WHERE ep.valid_at IS NULL
        RETURN ep.uuid as uuid, ep.created_at as created_at
        LIMIT 10
        """
        
        try:
            result = await driver.execute_query(query)
            
            if result and len(result[0]) > 0:
                print_info("Sample episodes that would be updated:")
                for i, record in enumerate(result[0][:10], 1):
                    uuid = record.get('uuid', 'unknown')
                    created_at = record.get('created_at', 'unknown')
                    print(f"  {i}. {uuid} (created_at: {created_at})")
            else:
                print_info("No episodes need updating")
            
            return 0
            
        except Exception as e:
            print_error(f"Error in dry run: {e}")
            raise
    
    else:
        query = """
        MATCH (ep:Episodic)
        WHERE ep.valid_at IS NULL
        SET ep.valid_at = ep.created_at
        RETURN count(ep) as updated_count
        """
        
        try:
            result = await driver.execute_query(query)
            
            if result and len(result[0]) > 0:
                updated_count = result[0][0].get('updated_count', 0)
                
                if updated_count > 0:
                    print_success(f"Updated {updated_count} episodes")
                else:
                    print_info("No episodes needed updating")
                
                return updated_count
            else:
                print_info("No results returned")
                return 0
                
        except Exception as e:
            print_error(f"Error updating episodes: {e}")
            raise

async def verify_fix(driver: FalkorDriver) -> bool:
    """Verify all episodes now have valid_at"""
    print_header("3. Verifying Fix")
    
    query = """
    MATCH (ep:Episodic)
    WHERE ep.valid_at IS NULL
    RETURN count(ep) as missing_count
    """
    
    try:
        result = await driver.execute_query(query)
        
        if result and len(result[0]) > 0:
            missing_count = result[0][0].get('missing_count', 0)
            
            if missing_count == 0:
                print_success("All episodes now have valid_at set!")
                return True
            else:
                print_error(f"Still {missing_count} episodes without valid_at")
                return False
        else:
            print_success("Verification complete")
            return True
            
    except Exception as e:
        print_error(f"Error verifying: {e}")
        raise

async def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill valid_at for episodes')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    parser.add_argument('--host', default='falkordb', help='FalkorDB host (default: falkordb)')
    parser.add_argument('--port', type=int, default=6379, help='FalkorDB port (default: 6379)')
    parser.add_argument('--database', default='default_db', help='Database name (default: default_db)')
    
    args = parser.parse_args()
    
    print(f"\n{Colors.BOLD}Backfill valid_at for Episodes{Colors.END}")
    print(f"Host: {args.host}:{args.port}")
    print(f"Database: {args.database}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}\n")
    
    # Connect to FalkorDB
    try:
        driver = FalkorDriver(
            host=args.host,
            port=args.port,
            database=args.database
        )
        print_success(f"Connected to FalkorDB at {args.host}:{args.port}")
    except Exception as e:
        print_error(f"Failed to connect to FalkorDB: {e}")
        return 1
    
    try:
        # Step 1: Check how many episodes are missing valid_at
        missing_count = await check_missing_valid_at(driver)
        
        if missing_count == 0:
            print_success("\nNo action needed - all episodes have valid_at")
            return 0
        
        # Step 2: Backfill
        updated_count = await backfill_valid_at(driver, dry_run=args.dry_run)
        
        if args.dry_run:
            print_info(f"\nDry run complete. Would update {missing_count} episodes.")
            print_info("Run without --dry-run to apply changes.")
            return 0
        
        # Step 3: Verify
        success = await verify_fix(driver)
        
        if success:
            print_header("Summary")
            print_success(f"Successfully backfilled valid_at for {updated_count} episodes")
            print_info("\nNext steps:")
            print_info("  1. Restart worker: docker-compose restart graphiti-worker")
            print_info("  2. Monitor logs: docker-compose logs -f graphiti-worker")
            print_info("  3. Check replay tasks are processing")
            return 0
        else:
            print_error("\nVerification failed - some episodes still missing valid_at")
            return 1
            
    except Exception as e:
        print_error(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

