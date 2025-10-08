#!/usr/bin/env python3
"""
Configure RedisInsight to automatically connect to FalkorDB.
"""

import json
import time

import requests

REDISINSIGHT_URL = 'http://localhost:5540'


def wait_for_redisinsight():
    """Wait for RedisInsight to be ready."""
    print('Waiting for RedisInsight to be ready...')
    for i in range(30):
        try:
            response = requests.get(f'{REDISINSIGHT_URL}/api/')
            if response.status_code in [200, 404]:  # API is responding
                print('✓ RedisInsight is ready')
                return True
        except:
            pass
        time.sleep(1)
    return False


def check_existing_databases():
    """Check if any databases are already configured."""
    try:
        response = requests.get(f'{REDISINSIGHT_URL}/api/databases')
        if response.status_code == 200:
            databases = response.json()
            print(f'Found {len(databases)} existing databases')
            for db in databases:
                print(f'  - {db.get("name", "Unknown")} at {db.get("host")}:{db.get("port")}')
            return databases
        return []
    except Exception as e:
        print(f'Error checking databases: {e}')
        return []


def add_falkordb_connection():
    """Add FalkorDB connection to RedisInsight."""
    print('\nAdding FalkorDB connection...')

    # Connection configuration
    config = {
        'host': 'falkordb',
        'port': 6379,
        'name': 'FalkorDB Graph Database',
        'username': '',
        'password': '',
        'tls': False,
        'verifyServerCert': False,
        'timeout': 30000,
        'modules': [],
    }

    try:
        # Try the v2 API endpoint first
        response = requests.post(
            f'{REDISINSIGHT_URL}/api/databases',
            json=config,
            headers={'Content-Type': 'application/json'},
        )

        if response.status_code in [200, 201]:
            print('✓ Successfully added FalkorDB connection!')
            db_info = response.json()
            print(f'  Database ID: {db_info.get("id", "Unknown")}')
            return True
        else:
            print(f'✗ Failed to add connection: {response.status_code}')
            print(f'  Response: {response.text}')

            # Try alternative API endpoint
            print('\nTrying alternative API endpoint...')
            response = requests.post(
                f'{REDISINSIGHT_URL}/api/instance',
                json=config,
                headers={'Content-Type': 'application/json'},
            )

            if response.status_code in [200, 201]:
                print('✓ Successfully added FalkorDB connection via alternative API!')
                return True
            else:
                print(f'✗ Alternative API also failed: {response.status_code}')
                print(f'  Response: {response.text}')

    except Exception as e:
        print(f'✗ Error adding connection: {e}')

    return False


def test_connection(db_id=None):
    """Test the FalkorDB connection."""
    print('\nTesting FalkorDB connection...')

    try:
        # If we have a database ID, try to connect directly
        if db_id:
            response = requests.get(f'{REDISINSIGHT_URL}/api/databases/{db_id}/connect')
            if response.status_code == 200:
                print('✓ Connection test successful!')
                return True

        # Otherwise, list databases and test the first one
        databases = check_existing_databases()
        if databases:
            db = databases[0]
            print(f'Testing connection to {db.get("name")}...')
            # Try to execute a simple command
            command_data = {'command': 'PING'}
            response = requests.post(
                f'{REDISINSIGHT_URL}/api/databases/{db.get("id")}/cli',
                json=command_data,
                headers={'Content-Type': 'application/json'},
            )
            if response.status_code == 200:
                print('✓ Connection test successful!')
                return True

    except Exception as e:
        print(f'✗ Connection test failed: {e}')

    return False


def main():
    """Main configuration function."""
    print('=== RedisInsight Configuration for FalkorDB ===\n')

    # Wait for RedisInsight to be ready
    if not wait_for_redisinsight():
        print("✗ RedisInsight is not responding. Please check if it's running.")
        return

    # Check existing databases
    existing_dbs = check_existing_databases()

    # Check if FalkorDB is already configured
    falkordb_exists = any(
        db.get('host') == 'falkordb' or 'falkor' in db.get('name', '').lower()
        for db in existing_dbs
    )

    if falkordb_exists:
        print('\n✓ FalkorDB connection already exists!')
    else:
        # Add FalkorDB connection
        if add_falkordb_connection():
            print('\n✓ FalkorDB has been configured in RedisInsight!')
        else:
            print('\n✗ Failed to configure FalkorDB automatically.')
            print('\nManual Configuration Instructions:')
            print('1. Open RedisInsight at http://localhost:5540')
            print("2. Click 'Add Redis Database'")
            print('3. Enter:')
            print('   - Host: falkordb')
            print('   - Port: 6379')
            print('   - Database Alias: FalkorDB Graph Database')
            print("4. Click 'Add Redis Database'")

    print('\n=== Configuration Complete ===')
    print(f'\nYou can now access RedisInsight at: {REDISINSIGHT_URL}')
    print('\nTo query your graph data:')
    print('1. Click on the FalkorDB connection')
    print("2. Go to the 'Browser' or 'Workbench' section")
    print('3. Use commands like:')
    print('   GRAPH.QUERY graphiti_migration "MATCH (n) RETURN count(n)"')
    print('   GRAPH.QUERY graphiti_migration "MATCH (n) RETURN n LIMIT 10"')


if __name__ == '__main__':
    main()
