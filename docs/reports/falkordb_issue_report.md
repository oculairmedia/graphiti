# FalkorDB compatibility issue with Neo4j runtime hints

## Description

When using Graphiti with FalkorDB as the graph driver, queries fail with the following error:

```
errMsg: Invalid input at end of input: expected '=' line: 1, column: 14, offset: 13 errCtx: CYPHER params errCtxOffset: 13
```

## Root Cause

The issue is caused by Neo4j-specific runtime hints being prepended to queries in `graphiti_core/helpers.py`:

```python
RUNTIME_QUERY: LiteralString = (
    'CYPHER runtime = parallel parallelRuntimeSupport=all\n' if USE_PARALLEL_RUNTIME else ''
)
```

This `RUNTIME_QUERY` string is used in multiple places throughout `search_utils.py` and prepended to queries. FalkorDB doesn't understand this Neo4j-specific syntax.

## Steps to Reproduce

1. Set up Graphiti with FalkorDB driver
2. Try to add an episode and perform entity extraction
3. The operation fails during the search phase with the above error

## Temporary Workaround

Set `RUNTIME_QUERY` to an empty string in `helpers.py`:

```python
RUNTIME_QUERY: LiteralString = ''
```

## Suggested Fix

The `RUNTIME_QUERY` should be conditionally applied based on the graph driver being used. Perhaps:

1. Add a property to the GraphDriver base class to indicate runtime hint support
2. Only apply `RUNTIME_QUERY` when using Neo4j driver
3. Or move the runtime hint logic into the Neo4j driver itself

## Environment

- Graphiti version: Latest from main branch
- FalkorDB version: 1.1.2+
- Python version: 3.11

## Additional Context

FalkorDB support was recently added to Graphiti, and this appears to be an oversight where Neo4j-specific optimizations are being applied to all graph drivers.

## Test Case

Here's a minimal test case that reproduces the issue:

```python
from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver
from graphiti_core.nodes import EpisodeType
from datetime import datetime

# Create FalkorDB driver
driver = FalkorDriver(host="localhost", port=6379)

# Create Graphiti instance
graphiti = Graphiti(graph_driver=driver)

# This will fail during the search phase
await graphiti.add_episode(
    name="Test Episode",
    episode_body="Test content with entities",
    source_description="Test",
    reference_time=datetime.now(),
    source=EpisodeType.text
)
```