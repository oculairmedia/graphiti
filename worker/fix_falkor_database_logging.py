#!/usr/bin/env python3
"""
Add logging to FalkorDriver to confirm database name being used
"""

DRIVER_FILE = '/opt/stacks/graphiti/graphiti_core/driver/falkordb_driver.py'


def add_database_logging():
    with open(DRIVER_FILE, 'r') as f:
        content = f.read()

    # Add logging after self._database is set
    old_code = """        else:
            self.client = FalkorDB(host=host, port=port, username=username, password=password)
            self._database = database

        self.fulltext_syntax = '@'  # FalkorDB uses a redisearch-like syntax for fulltext queries see https://redis.io/docs/latest/develop/ai/search-and-query/query/full-text/"""

    new_code = """        else:
            self.client = FalkorDB(host=host, port=port, username=username, password=password)
            self._database = database
            logger.info(f"FalkorDriver initialized with database: {self._database}")

        self.fulltext_syntax = '@'  # FalkorDB uses a redisearch-like syntax for fulltext queries see https://redis.io/docs/latest/develop/ai/search-and-query/query/full-text/"""

    # Also need to fix the bug where falkor_db branch doesn't set _database
    bug_code = """        if falkor_db is not None:
            # If a FalkorDB instance is provided, use it directly
            self.client = falkor_db
        else:"""

    bug_fix = """        if falkor_db is not None:
            # If a FalkorDB instance is provided, use it directly
            self.client = falkor_db
            self._database = database  # BUG FIX: Set database even when falkor_db is provided
            logger.info(f"FalkorDriver initialized with provided client, database: {self._database}")
        else:"""

    if old_code in content:
        content = content.replace(old_code, new_code)
        print('✅ Added database logging to else branch')

    if bug_code in content:
        content = content.replace(bug_code, bug_fix)
        print('✅ Fixed bug: database not set when falkor_db is provided')

    with open(DRIVER_FILE, 'w') as f:
        f.write(content)

    print(f'✅ Updated {DRIVER_FILE}')


if __name__ == '__main__':
    add_database_logging()
