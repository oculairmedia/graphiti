# How-to: Write and Run Tests

> **Keywords**: `test`, `pytest`, `unit`, `fixture`, `mock`, `integration`

## Quick Start

```bash
# Run all tests
pytest

# Run specific file
pytest tests/test_search.py

# Run with verbose output
pytest -v

# Run specific test
pytest tests/test_search.py::test_hybrid_search
```

---

## Test Structure

```
tests/
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_extractors.py
│   └── test_utils.py
├── integration/             # Integration tests (real DB)
│   ├── test_graphiti.py
│   └── test_search.py
├── fixtures/                # Test fixtures
│   └── sample_data.py
└── conftest.py              # Shared fixtures
```

---

## Writing Unit Tests

### Basic Pattern

```python
import pytest
from graphiti_core.extractors import EntityExtractor

def test_extract_entities():
    """Test entity extraction from text."""
    extractor = EntityExtractor()
    text = "Alice works at Acme Corp"
    
    entities = extractor.extract(text)
    
    assert len(entities) == 2
    assert any(e.name == "Alice" for e in entities)
    assert any(e.name == "Acme Corp" for e in entities)
```

### With Fixtures

```python
# conftest.py
import pytest
from graphiti_core import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver

@pytest.fixture
def graphiti_instance():
    """Create a test Graphiti instance."""
    driver = FalkorDriver(
        host="localhost",
        port=6379,
        database="graphiti_test"  # Use test database!
    )
    graphiti = Graphiti(graph_driver=driver)
    yield graphiti
    
    # Cleanup
    driver.execute_query("MATCH (n) DETACH DELETE n")

# test_search.py
def test_search_returns_results(graphiti_instance):
    """Test search returns expected results."""
    # Setup
    await graphiti_instance.add_episode(
        name="test_ep",
        source_content="Alice likes basketball",
    )
    
    # Test
    results = await graphiti_instance.search("Alice")
    
    # Assert
    assert len(results.edges) > 0
```

### Mocking LLM Calls

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_extraction_with_mock():
    """Test extraction with mocked LLM."""
    with patch("graphiti_core.llm_client.OpenAIClient.generate") as mock_llm:
        mock_llm.return_value = AsyncMock(
            return_value={"entities": [{"name": "Test Entity"}]}
        )
        
        # Test code that calls LLM
        result = await extract_entities("some text")
        
        assert mock_llm.called
```

---

## Writing Integration Tests

### Database Isolation

**CRITICAL**: Use a separate test database to avoid polluting production data.

```python
@pytest.fixture
def test_database():
    """Use isolated test database."""
    driver = FalkorDriver(database="graphiti_test")
    yield driver
    
    # Cleanup after each test
    driver.execute_query("MATCH (n) DETACH DELETE n")
```

### Full Pipeline Test

```python
@pytest.mark.asyncio
async def test_full_ingestion_pipeline(test_database):
    """Test complete ingestion flow."""
    graphiti = Graphiti(graph_driver=test_database)
    
    # Ingest
    episode = await graphiti.add_episode(
        name="integration_test",
        source_content="Bob joined Microsoft as CEO",
    )
    
    # Verify nodes created
    nodes = await test_database.execute_query(
        "MATCH (e:Entity) RETURN count(e)"
    )
    assert nodes[0]["count(e)"] >= 2
    
    # Verify edges created
    edges = await test_database.execute_query(
        "MATCH ()-[r:RELATES_TO]->() RETURN count(r)"
    )
    assert edges[0]["count(r)"] >= 1
```

---

## Test Markers

```python
# Skip slow tests
@pytest.mark.slow
def test_large_batch():
    ...

# Require external service
@pytest.mark.requires_llm
def test_with_real_llm():
    ...

# Skip on CI
@pytest.mark.skip_ci
def test_local_only():
    ...
```

Run by marker:
```bash
pytest -m "not slow"
pytest -m "requires_llm"
```

---

## Fixtures

### Sample Data

```python
# tests/fixtures/sample_data.py

SAMPLE_EPISODES = [
    {
        "name": "ep_1",
        "content": "Alice works at TechCorp as an engineer",
    },
    {
        "name": "ep_2", 
        "content": "Bob is the CEO of StartupInc",
    },
]

# conftest.py
from tests.fixtures.sample_data import SAMPLE_EPISODES

@pytest.fixture
def sample_episodes():
    return SAMPLE_EPISODES
```

### Mock Embeddings

```python
@pytest.fixture
def mock_embedding():
    """Return a deterministic embedding for tests."""
    import numpy as np
    np.random.seed(42)
    return np.random.rand(1536).tolist()
```

---

## CI Integration

### GitHub Actions

```yaml
# .github/workflows/tests.yml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      falkordb:
        image: falkordb/falkordb:latest
        ports:
          - 6379:6379
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: pip install -e .[dev]
      
      - name: Run tests
        run: pytest -v --cov=graphiti_core
        env:
          FALKORDB_HOST: localhost
          FALKORDB_PORT: 6379
```

---

## Best Practices

1. **Isolate tests** - Each test should be independent
2. **Use test databases** - Never pollute production
3. **Mock external services** - Don't call real LLM APIs in unit tests
4. **Clean up** - Remove test data after each test
5. **Name descriptively** - `test_search_returns_empty_for_no_results`

---

## Troubleshooting

### Issue: Tests fail with connection errors

**Check**:
```bash
# FalkorDB running?
docker ps | grep falkordb

# Correct port?
redis-cli -p 6379 ping
```

### Issue: Tests pollute production database

**Fix**: Ensure using `database="graphiti_test"` in test fixtures

### Issue: Async tests not running

**Fix**: Use `@pytest.mark.asyncio` decorator

```python
@pytest.mark.asyncio
async def test_async_operation():
    result = await some_async_function()
    assert result is not None
```

---

## Files to Know

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Shared fixtures |
| `tests/fixtures/` | Test data |
| `pytest.ini` | Pytest configuration |
| `.github/workflows/tests.yml` | CI configuration |

---

## See Also

- [add-episode.md](add-episode.md) - What to test after ingestion
- [search-graph.md](search-graph.md) - What to test for search
- [../gotchas.md](../gotchas.md) - Test isolation gotcha
