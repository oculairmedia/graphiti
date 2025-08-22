# Testing Directory Structure

This directory contains all test, debug, and utility Python files organized by category.

## Directory Structure

### `/debug/`
Debug scripts for troubleshooting specific components:
- `debug_neo4j.py` - Neo4j connection debugging
- `debug_falkor_params.py` - FalkorDB parameter testing
- `debug_queue.py` - Queue system debugging
- `debug_entity_extraction.py` - Entity extraction debugging

### `/integration/`
Integration tests that test multiple components working together:
- Queue integration tests (`test_queue_*.py`)
- FalkorDB integration tests (`test_falkor*.py`)
- Cross-system tests (`test_integration.py`, `test_direct_*.py`)
- Database write tests (`test_database_writes.py`)
- Data ingestion tests (`test_simple_ingestion.py`, `test_add_data.py`)
- Real-time functionality tests (`test-websocket-update.py`)

### `/unit/`
Unit tests for individual components and algorithms:
- Validator tests (`test_*validator*.py`)
- Entity and edge tests (`test_entity*.py`, `test_*edge*.py`)
- Algorithm tests (`test_deterministic_uuid.py`, `test_fuzzy_matching.py`)
- Validation tests (`test_*validation*.py`)
- Transaction tests (`test_transaction_*.py`)
- Integrity tests (`test_integrity_*.py`)

### `/demos/`
Demo scripts and model-specific tests:
- Ollama integration demos (`test_*ollama*.py`)
- Model comparison tests (`test_cerebras*.py`, `test_qwen*.py`, `test_devstral*.py`)
- Simple demo scripts (`test_*demo*.py`)

### `/performance/`
Performance testing and benchmarking:
- Performance test scripts (`simple_performance_test.py`)
- Load testing scripts (`8b_test.py`)
- Benchmark utilities

### `/utilities/`
Utility scripts for test setup and maintenance:
- Queue management (`clear_queue.py`, `submit_to_queue.py`)
- Test data management
- Setup and teardown scripts

## Usage

### Running Tests by Category

```bash
# Run all integration tests
python -m pytest testing/integration/

# Run all unit tests  
python -m pytest testing/unit/

# Run performance tests
python -m pytest testing/performance/

# Run specific test
python testing/integration/test_falkordb_client.py
```

### Debug Scripts

```bash
# Debug FalkorDB connection
python testing/debug/debug_falkor_params.py

# Debug entity extraction
python testing/debug/debug_entity_extraction.py
```

### Utility Scripts

```bash
# Clear test queue
python testing/utilities/clear_queue.py

# Submit test data to queue
python testing/utilities/submit_to_queue.py
```

## Test Configuration

The main test configuration is in the root `conftest.py` file, which sets up:
- Database connections
- Test fixtures
- Common test utilities
- Environment configuration

## Contributing

When adding new test files:

1. **Debug scripts** → `/debug/`
2. **Component integration tests** → `/integration/`
3. **Individual function/class tests** → `/unit/`
4. **Example/demo scripts** → `/demos/`
5. **Performance benchmarks** → `/performance/`
6. **Test utilities** → `/utilities/`

Follow the existing naming conventions:
- `test_*.py` for actual tests
- `debug_*.py` for debug scripts
- Descriptive names indicating what is being tested