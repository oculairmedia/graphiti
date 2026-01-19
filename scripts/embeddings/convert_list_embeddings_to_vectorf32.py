#!/usr/bin/env python3
"""
Convert legacy list-format embeddings to Vectorf32 format in FalkorDB.
This script finds edges that have embeddings stored as lists and converts them to vecf32.
"""

import asyncio
import os
import sys
import logging
from datetime import datetime
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graphiti_core.driver.falkordb_driver import FalkorDriver
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def convert_list_embeddings(dry_run: bool = False, batch_size: int = 100):
    """
    Convert list-format embeddings to Vectorf32 format.

    The strategy is to:
    1. Try to query each edge's embedding with vec.cosineDistance
    2. If it fails with "Type mismatch: expected Null or Vectorf32 but was List",
       that edge has a list-format embedding
    3. Convert those edges by reading the list and writing it back as vecf32
    """

    # Initialize driver
    driver = FalkorDriver(
        host='localhost',
        port=6379,
        database='graphiti_migration'
    )

    print("\n" + "="*80)
    print("CONVERT LIST EMBEDDINGS TO VECTORF32")
    print("="*80 + "\n")
    print(f"Dry Run: {dry_run}")
    print(f"Batch Size: {batch_size}")

    # Step 1: Get all edges with embeddings
    print("\nStep 1: Finding edges with embeddings...")
    print("-" * 50)

    count_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    RETURN count(e) as total
    """

    results, _, _ = await driver.execute_query(count_query)
    total_edges = results[0]['total'] if results else 0

    print(f"Found {total_edges} edges with embeddings\n")

    if total_edges == 0:
        print("No edges with embeddings found!")
        await driver.close()
        return

    # Step 2: Test each edge to find list-format embeddings
    print("\nStep 2: Testing each edge to find list-format embeddings...")
    print("-" * 50)

    # Get all edge UUIDs
    uuid_query = """
    MATCH ()-[e:RELATES_TO]->()
    WHERE e.fact_embedding IS NOT NULL
    RETURN e.uuid as uuid
    """

    results, _, _ = await driver.execute_query(uuid_query)
    all_uuids = [r['uuid'] for r in results]

    print(f"Testing {len(all_uuids)} edges for list-format embeddings...")

    list_format_uuids = []
    vectorf32_uuids = []

    # Test a small sample embedding for the cosine distance query
    # Use 2560 dimensions to match the Qwen embedding model
    test_embedding = [0.0] * 2560  # Dummy embedding for testing

    for i, uuid in enumerate(all_uuids):
        if (i + 1) % 1000 == 0:
            print(f"  Tested {i + 1}/{len(all_uuids)} edges... (Found {len(list_format_uuids)} list-format)")

        # Try to use the embedding in a cosine distance query
        test_query = """
        MATCH ()-[e:RELATES_TO {uuid: $uuid}]->()
        WITH e, (2 - vec.cosineDistance(e.fact_embedding, vecf32($test_embedding)))/2 AS score
        RETURN score
        """

        try:
            await driver.execute_query(test_query, uuid=uuid, test_embedding=test_embedding)
            vectorf32_uuids.append(uuid)
        except Exception as e:
            error_msg = str(e)
            if 'Type mismatch: expected Null or Vectorf32 but was List' in error_msg:
                list_format_uuids.append(uuid)
                if len(list_format_uuids) <= 5:  # Show first 5
                    logger.info(f"Found list-format embedding: {uuid}")
            else:
                logger.warning(f"Unexpected error testing edge {uuid}: {e}")

    print(f"\nResults:")
    print(f"  Total edges tested: {len(all_uuids)}")
    print(f"  Vectorf32 format (OK): {len(vectorf32_uuids)}")
    print(f"  List format (needs conversion): {len(list_format_uuids)}")

    if len(list_format_uuids) == 0:
        print("\n✅ All embeddings are already in Vectorf32 format!")
        await driver.close()
        return

    # Step 3: Convert list-format embeddings
    print(f"\nStep 3: Converting {len(list_format_uuids)} list-format embeddings...")
    print("-" * 50)

    converted = 0
    failed = 0
    start_time = time.time()

    for i, uuid in enumerate(list_format_uuids):
        if dry_run:
            if i < 5:  # Show first 5 in dry run
                print(f"  Would convert edge {uuid}")
            converted += 1
            continue

        try:
            # Read the list embedding
            read_query = """
            MATCH ()-[e:RELATES_TO {uuid: $uuid}]->()
            RETURN e.fact_embedding as embedding
            """

            results, _, _ = await driver.execute_query(read_query, uuid=uuid)
            if not results:
                logger.error(f"Edge {uuid} not found")
                failed += 1
                continue

            embedding_list = results[0]['embedding']

            # Write it back as vecf32
            update_query = """
            MATCH ()-[e:RELATES_TO {uuid: $uuid}]->()
            SET e.fact_embedding = vecf32($embedding)
            RETURN e.uuid as uuid
            """

            await driver.execute_query(update_query, uuid=uuid, embedding=embedding_list)
            converted += 1

            if converted % 100 == 0:
                elapsed = time.time() - start_time
                rate = converted / elapsed if elapsed > 0 else 0
                eta = (len(list_format_uuids) - converted) / rate if rate > 0 else 0
                print(f"  Converted {converted}/{len(list_format_uuids)} edges... "
                      f"(Rate: {rate:.1f} edges/sec, ETA: {eta:.1f}s)")

        except Exception as e:
            logger.error(f"Failed to convert edge {uuid}: {e}")
            failed += 1

    # Step 4: Verification
    print("\nStep 4: Verification...")
    print("-" * 50)

    if not dry_run:
        # Test a few converted edges
        test_count = min(10, len(list_format_uuids))
        verification_passed = 0

        for uuid in list_format_uuids[:test_count]:
            test_query = """
            MATCH ()-[e:RELATES_TO {uuid: $uuid}]->()
            WITH e, (2 - vec.cosineDistance(e.fact_embedding, vecf32($test_embedding)))/2 AS score
            RETURN score
            """

            try:
                await driver.execute_query(test_query, uuid=uuid, test_embedding=test_embedding)
                verification_passed += 1
            except Exception as e:
                logger.error(f"Verification failed for edge {uuid}: {e}")

        print(f"Verified {verification_passed}/{test_count} converted edges can use vec.cosineDistance")

    await driver.close()

    # Final report
    print("\n" + "="*80)
    print("CONVERSION COMPLETE")
    print("="*80 + "\n")

    if not dry_run:
        print(f"Results:")
        print(f"  Successfully converted: {converted} edges")
        print(f"  Failed: {failed} edges")
        print(f"  Time taken: {time.time() - start_time:.2f} seconds")
    else:
        print(f"DRY RUN - Would have converted {len(list_format_uuids)} edges")

    return converted, failed


async def main():
    """Main entry point with command line arguments"""
    import argparse

    parser = argparse.ArgumentParser(description='Convert list-format embeddings to Vectorf32')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without updating')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size for processing')

    args = parser.parse_args()

    try:
        await convert_list_embeddings(
            dry_run=args.dry_run,
            batch_size=args.batch_size
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to convert embeddings: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
