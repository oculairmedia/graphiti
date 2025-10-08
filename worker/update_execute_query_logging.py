#!/usr/bin/env python3
from pathlib import Path

path = Path('/opt/stacks/graphiti/graphiti_core/driver/falkordb_driver.py')
text = path.read_text()
old = "        try:\n            result = await graph.query(cypher_query_, params)  # type: ignore[reportUnknownArgumentType]\n        except Exception as e:\n            if 'already indexed' in str(e):\n                # check if index already exists\n                logger.info(f'Index already exists: {e}')\n                return None\n            logger.error(f'Error executing FalkorDB query: {e}')\n            raise\n\n        # Convert the result header to a list of strings\n        header = [h[1] for h in result.header]\n"

new = "        if logger.isEnabledFor(logging.DEBUG):\n            logger.debug(\"Falkor EXECUTE query on graph '%s':\\n%s\\nparams=%s\", graph_name, cypher_query_, params)\n        try:\n            result = await graph.query(cypher_query_, params)  # type: ignore[reportUnknownArgumentType]\n        except Exception as e:\n            logger.error(\n                \"Falkor EXECUTE query failed on graph '%s':\\n%s\\nparams=%s\",\n                graph_name,\n                cypher_query_,\n                params,\n                exc_info=True,\n            )\n            if 'already indexed' in str(e):\n                logger.info(f'Index already exists: {e}')\n                return None\n            raise\n\n        # Convert the result header to a list of strings\n        header = [h[1] for h in result.header]\n"

if old not in text:
    raise SystemExit('pattern not found for execute_query')
path.write_text(text.replace(old, new))
print('Updated execute_query with debug logging')
