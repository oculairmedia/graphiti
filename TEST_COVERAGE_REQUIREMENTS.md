# Test Coverage Requirements

## Document Version
- **Version**: 1.0
- **Date**: November 17, 2025
- **Last Updated**: November 17, 2025

## Executive Summary

This document outlines the test coverage requirements, current status, and remediation plan for the Graphiti project. The project is a multi-language stack consisting of Python (backend core), TypeScript/React (frontend), and Rust (visualization services).

---

## Table of Contents

1. [Current State Assessment](#current-state-assessment)
2. [Coverage Requirements](#coverage-requirements)
3. [Test Infrastructure Setup](#test-infrastructure-setup)
4. [Critical Issues](#critical-issues)
5. [Remediation Plan](#remediation-plan)
6. [Coverage Metrics & Reporting](#coverage-metrics--reporting)
7. [Testing Best Practices](#testing-best-practices)

---

## Current State Assessment

### Python Backend (graphiti_core)

**Source Code:**
- Total files: 108 Python files
- Main components:
  - Core engine (`graphiti.py`, `helpers.py`)
  - Models (nodes, edges)
  - Utils (maintenance, validation, compression)
  - LLM clients and embedders
  - Cross-encoders and rerankers

**Test Status:**
- Test files: 40 files
- Total tests: 170 tests collected
- Collection errors: 5 files failing to import
- Coverage tool: **NOT INSTALLED**
- Estimated coverage: **40-50%**

**Issues:**
- Missing `pytest-cov` and `coverage` packages
- 5 test files with import errors (Gemini/Voyage APIs)
- Pydantic V1 deprecation warnings throughout
- No coverage reporting configured

### Frontend (TypeScript/React)

**Source Code:**
- Modern React app with TypeScript
- Custom hooks for graph management
- WebSocket real-time updates
- Component library with Shadcn UI

**Test Status:**
- Test files: 26 files
- Total tests: ~280 tests
- Passing: ~210 tests (75%)
- Failing: ~70 tests (25%)
- Coverage tool: Configured but **NOT INSTALLED**
- Estimated coverage: **60-70%**

**Issues:**
- Missing `@vitest/coverage-v8` package
- GraphCanvasV2 test suite completely broken (19 failures)
- Multiple integration test failures
- React `act()` warnings in component tests
- Incomplete mocking strategies

### Rust Services (graph-visualizer-rust, graphiti-search-rs, graphiti-centrality-rs)

**Source Code:**
- Graph visualizer backend (main service)
- Search optimization service
- Centrality calculation service

**Test Status:**
- Test files: 5+ files across services
- Tests running: **0 tests collected**
- Coverage tool: Built into `cargo` (tarpaulin recommended)
- Estimated coverage: **Unknown**

**Issues:**
- Tests not executing (configuration issue)
- No coverage metrics available
- Integration tests may require specific features/flags

---

## Coverage Requirements

### Minimum Coverage Targets

| Component | Line Coverage | Branch Coverage | Function Coverage | Priority |
|-----------|--------------|-----------------|-------------------|----------|
| **Python Core** | 80% | 75% | 85% | Critical |
| **Frontend** | 75% | 70% | 80% | High |
| **Rust Services** | 70% | 65% | 75% | High |
| **Integration** | 60% | 55% | 65% | Medium |

### Critical Path Coverage

**Must have 100% coverage:**
- Data persistence logic (Neo4j, FalkorDB)
- Authentication and authorization
- Data validation and sanitization
- Error handling in critical paths
- WebSocket message handling
- Graph data synchronization

**Must have 90%+ coverage:**
- Core graph operations (node/edge CRUD)
- LLM prompt construction and parsing
- Embedding generation and storage
- Centrality calculations
- Search and query operations

**Should have 75%+ coverage:**
- UI components and hooks
- Utility functions
- Helper modules
- Configuration management

**Can have 50%+ coverage:**
- CLI tools and scripts
- Development utilities
- Diagnostic tools
- One-off migration scripts

---

## Test Infrastructure Setup

### Python Backend Setup

#### Required Packages

```bash
# Install testing and coverage tools
pip install pytest pytest-cov pytest-asyncio pytest-mock coverage

# Install optional but recommended
pip install pytest-xdist  # Parallel test execution
pip install pytest-timeout  # Timeout handling
pip install pytest-html  # HTML reports
```

#### Configuration Files

**pytest.ini** (Current - needs enhancement):
```ini
[pytest]
markers =
    integration: marks tests as integration tests
    unit: marks tests as unit tests
    slow: marks tests as slow running
asyncio_default_fixture_loop_scope = function

# Add these:
testpaths = tests
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*
addopts = 
    --strict-markers
    --tb=short
    --disable-warnings
    -v
```

**.coveragerc** (NEW - needs creation):
```ini
[run]
source = graphiti_core
omit = 
    */tests/*
    */test_*.py
    */__pycache__/*
    */migrations/*
    */venv/*
    */virtualenv/*

[report]
precision = 2
show_missing = True
skip_covered = False

[html]
directory = htmlcov

[xml]
output = coverage.xml
```

#### Running Tests with Coverage

```bash
# Run all tests with coverage
pytest --cov=graphiti_core --cov-report=html --cov-report=term --cov-report=xml

# Run only unit tests
pytest -m "not integration" --cov=graphiti_core

# Run only integration tests
pytest -m integration --cov=graphiti_core

# Run in parallel (faster)
pytest -n auto --cov=graphiti_core
```

### Frontend Setup

#### Required Packages

```bash
# Install coverage tool
npm install --save-dev @vitest/coverage-v8

# Optional but recommended
npm install --save-dev @vitest/ui  # Already installed
npm install --save-dev @testing-library/jest-dom  # Already installed
```

#### Configuration

**vite.config.ts** - Add coverage configuration:
```typescript
export default defineConfig({
  test: {
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html', 'lcov'],
      exclude: [
        'node_modules/',
        'src/**/*.test.{ts,tsx}',
        'src/**/__tests__/',
        '**/*.config.{ts,js}',
        '**/dist/',
        '**/build/',
      ],
      include: ['src/**/*.{ts,tsx}'],
      all: true,
      lines: 75,
      functions: 80,
      branches: 70,
      statements: 75,
    },
  },
});
```

#### Running Tests with Coverage

```bash
# Run tests with coverage
npm test -- --run --coverage

# Run with UI
npm run test:ui

# Watch mode
npm test

# Run specific test file
npm test -- src/__tests__/hooks/useGraphSimulation.test.tsx
```

### Rust Services Setup

#### Required Tools

```bash
# Install cargo-tarpaulin for coverage
cargo install cargo-tarpaulin

# Or use llvm-cov (built into newer Rust)
rustup component add llvm-tools-preview
cargo install cargo-llvm-cov
```

#### Running Tests with Coverage

```bash
# Using tarpaulin
cargo tarpaulin --out Html --out Xml --output-dir coverage/

# Using llvm-cov
cargo llvm-cov --html --output-dir coverage/
cargo llvm-cov --lcov --output-path coverage/lcov.info

# Run tests normally
cargo test
cargo test --all-features
cargo test --release
```

---

## Critical Issues

### Priority 1: Blocking Issues

#### 1. Missing Coverage Tools
**Impact**: Cannot measure or report coverage  
**Affected**: All components  
**Resolution**:
```bash
# Python
pip install pytest-cov coverage

# Frontend
cd frontend && npm install --save-dev @vitest/coverage-v8

# Rust
cargo install cargo-tarpaulin
```

#### 2. Python Test Collection Errors (5 files)
**Impact**: Tests cannot run  
**Files**:
- `tests/cross_encoder/test_bge_reranker_client.py`
- `tests/cross_encoder/test_gemini_reranker_client.py`
- `tests/embedder/test_gemini.py`
- `tests/embedder/test_voyage.py`
- `tests/llm_client/test_gemini_client.py`

**Root Cause**: Missing API keys or import errors  
**Resolution**: Fix imports or mark as optional dependencies

#### 3. Frontend GraphCanvasV2 Tests (19/19 failing)
**Impact**: Cannot test critical visualization component  
**Error**: `loadingCoordinator.getStageStatus is not a function`  
**Root Cause**: Incomplete mock of loadingCoordinator  
**Resolution**: Fix mock implementation in test setup

### Priority 2: High Impact Issues

#### 4. Frontend Integration Tests (35 failures)
**Files**:
- `incrementalUpdates.test.ts` - 13/15 failing
- `websocket-flow.test.ts` - 5/15 failing
- `memory-optimization.test.ts` - 2/15 failing
- `GraphCanvasWrapper.test.tsx` - 8/23 failing

**Root Cause**: Mock timing issues, incomplete API mocks  
**Resolution**: Improve async handling and mock completeness

#### 5. Rust Tests Not Running
**Impact**: No test execution for Rust services  
**Issue**: `cargo test` reports 0 tests  
**Resolution**: Investigate test configuration and feature flags

### Priority 3: Medium Impact Issues

#### 6. Pydantic V1 Deprecation Warnings
**Impact**: Future compatibility issues  
**Files**: `graphiti_core/nodes.py` and others  
**Resolution**: Migrate validators from V1 to V2 style

#### 7. React act() Warnings
**Impact**: Test reliability and maintenance  
**Resolution**: Wrap state updates in `act()`

---

## Remediation Plan

### Phase 1: Foundation (Week 1-2)

**Objectives**: Install tools, fix blocking issues

**Tasks**:
1. ✅ Install coverage tools for all platforms
   - Python: `pytest-cov`, `coverage`
   - Frontend: `@vitest/coverage-v8`
   - Rust: `cargo-tarpaulin`

2. ✅ Fix Python test collection errors
   - Review API key requirements
   - Add optional dependency markers
   - Fix import paths

3. ✅ Configure coverage reporting
   - Create `.coveragerc` for Python
   - Update `vite.config.ts` for frontend
   - Configure `tarpaulin.toml` for Rust

4. ✅ Establish baseline coverage metrics
   - Run full coverage reports
   - Document current state
   - Identify coverage gaps

**Deliverables**:
- All coverage tools installed and working
- Baseline coverage reports for all components
- Documentation of current coverage state

### Phase 2: Critical Fixes (Week 3-4)

**Objectives**: Fix high-impact test failures

**Tasks**:
1. ✅ Fix GraphCanvasV2 test suite
   - Implement proper loadingCoordinator mock
   - Fix all 19 failing tests
   - Add missing test cases

2. ✅ Fix frontend integration tests
   - Resolve `incrementalUpdates.test.ts` failures
   - Fix WebSocket flow test timing issues
   - Resolve memory optimization test issues

3. ✅ Fix Rust test execution
   - Debug `cargo test` configuration
   - Ensure tests are discovered
   - Add missing test cases

4. ✅ Address React act() warnings
   - Wrap state updates properly
   - Update testing utilities

**Deliverables**:
- All critical test suites passing
- No blocking test failures
- Clean test output (no warnings)

### Phase 3: Coverage Improvement (Week 5-8)

**Objectives**: Reach minimum coverage targets

**Tasks**:
1. ✅ Identify untested modules
   - Run coverage reports
   - Generate coverage gap analysis
   - Prioritize by criticality

2. ✅ Add tests for critical paths
   - Data persistence (100% target)
   - Authentication/authorization (100% target)
   - Core graph operations (90% target)

3. ✅ Add tests for utility modules
   - `utils/prompt_compression.py`
   - `utils/fuzzy_matching.py`
   - `utils/resilient_ingestion.py`
   - Other utils reaching 75% target

4. ✅ Improve frontend component coverage
   - Add missing component tests
   - Increase hook coverage
   - Add integration test scenarios

**Deliverables**:
- Python core: 80% line coverage
- Frontend: 75% line coverage
- Rust: 70% line coverage
- All critical paths at 100%

### Phase 4: Automation & CI/CD (Week 9-10)

**Objectives**: Automate coverage tracking and enforcement

**Tasks**:
1. ✅ Configure CI/CD pipeline
   - Add coverage reporting to builds
   - Set up coverage thresholds
   - Configure failure on coverage drops

2. ✅ Set up coverage tracking
   - Integrate with Codecov/Coveralls
   - Add coverage badges to README
   - Track coverage trends over time

3. ✅ Add pre-commit hooks
   - Run tests on changed files
   - Verify coverage for new code
   - Enforce coverage standards

4. ✅ Documentation
   - Update developer guides
   - Document testing standards
   - Create testing templates

**Deliverables**:
- Automated coverage reporting
- Coverage enforcement in CI/CD
- Developer documentation
- Coverage badges and tracking

---

## Coverage Metrics & Reporting

### Required Reports

#### 1. Per-Commit Reports
- Generated on every commit
- Show coverage delta (increase/decrease)
- Block merge if coverage drops below threshold

#### 2. Per-PR Reports
- Full coverage report in PR comments
- Highlight uncovered lines in changed files
- Show coverage comparison with base branch

#### 3. Daily Reports
- Automated daily coverage snapshots
- Track trends over time
- Email digest to team

#### 4. Release Reports
- Comprehensive coverage before each release
- Include all test types (unit, integration, E2E)
- Document coverage improvements since last release

### Report Formats

**Terminal Output** (for local development):
```bash
# Python
pytest --cov=graphiti_core --cov-report=term-missing

# Frontend
npm test -- --run --coverage --reporter=verbose

# Rust
cargo tarpaulin --out Stdout
```

**HTML Reports** (for detailed analysis):
- Python: `htmlcov/index.html`
- Frontend: `coverage/index.html`
- Rust: `coverage/index.html`

**XML/LCOV Reports** (for CI/CD integration):
- Python: `coverage.xml`
- Frontend: `coverage/lcov.info`
- Rust: `coverage/cobertura.xml`

### Coverage Badges

Add to `README.md`:
```markdown
![Python Coverage](https://img.shields.io/badge/coverage-80%25-green)
![Frontend Coverage](https://img.shields.io/badge/coverage-75%25-yellow)
![Rust Coverage](https://img.shields.io/badge/coverage-70%25-yellow)
```

---

## Testing Best Practices

### General Principles

1. **Test Pyramid**: 70% unit, 20% integration, 10% E2E
2. **Fast Tests**: Unit tests < 100ms, Integration < 5s
3. **Isolated Tests**: No shared state, no test dependencies
4. **Readable Tests**: Clear naming, minimal setup, obvious assertions
5. **Maintainable Tests**: Follow DRY, use fixtures/factories

### Python Testing Standards

```python
# Good: Clear, focused unit test
def test_node_creation_with_valid_data():
    """Test that a node can be created with valid data."""
    node = EntityNode(
        name="TestNode",
        labels=["Entity"],
        uuid="test-uuid-123"
    )
    assert node.name == "TestNode"
    assert "Entity" in node.labels


# Good: Integration test with proper markers
@pytest.mark.integration
async def test_graphiti_add_episode_integration():
    """Test full episode addition flow with real database."""
    graphiti = await setup_test_graphiti()
    result = await graphiti.add_episode(
        name="test_episode",
        episode_body="Test content",
        source_description="test"
    )
    assert result is not None


# Good: Using fixtures for setup
@pytest.fixture
async def graphiti_client():
    """Provide a test graphiti client."""
    client = Graphiti(...)
    yield client
    await client.close()
```

### Frontend Testing Standards

```typescript
// Good: Component test with proper mocking
describe('GraphCanvas', () => {
  it('should render with initial data', () => {
    const { getByRole } = render(
      <GraphCanvas 
        nodes={mockNodes}
        edges={mockEdges}
      />
    );
    expect(getByRole('canvas')).toBeInTheDocument();
  });
});

// Good: Hook test with proper setup
describe('useGraphSimulation', () => {
  it('should start simulation', () => {
    const { result } = renderHook(() => useGraphSimulation());
    act(() => {
      result.current.start();
    });
    expect(result.current.isRunning).toBe(true);
  });
});

// Good: Integration test with proper async handling
describe('WebSocket Integration', () => {
  it('should handle graph updates', async () => {
    const { result, waitFor } = renderHook(() => useGraphWebSocket());
    
    await waitFor(() => {
      expect(result.current.connected).toBe(true);
    });
    
    // Trigger update
    mockWebSocket.send({ type: 'graph_updated' });
    
    await waitFor(() => {
      expect(result.current.version).toBeGreaterThan(0);
    });
  });
});
```

### Rust Testing Standards

```rust
// Good: Unit test
#[test]
fn test_delta_tracker_add_node() {
    let mut tracker = DeltaTracker::new();
    tracker.add_node("node1".to_string(), NodeData::default());
    assert_eq!(tracker.added_nodes.len(), 1);
}

// Good: Integration test
#[test]
fn test_duckdb_store_integration() {
    let store = DuckDBStore::new(":memory:").unwrap();
    store.insert_node(&node_data).unwrap();
    let retrieved = store.get_node("node1").unwrap();
    assert_eq!(retrieved.id, "node1");
}

// Good: Async test
#[tokio::test]
async fn test_falkordb_connection() {
    let client = FalkorDBClient::new("localhost", 6379).await.unwrap();
    let result = client.query("MATCH (n) RETURN count(n)").await;
    assert!(result.is_ok());
}
```

---

## Continuous Improvement

### Monthly Review

- Review coverage trends
- Identify new gaps
- Update coverage targets
- Celebrate improvements

### Quarterly Goals

- Increase coverage by 5% per quarter
- Reduce test execution time by 10%
- Improve test reliability (reduce flakiness)
- Update testing documentation

### Annual Audit

- Comprehensive test suite review
- Update testing infrastructure
- Evaluate new testing tools
- Training and knowledge sharing

---

## Appendix

### Useful Commands Reference

#### Python
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=graphiti_core --cov-report=html

# Run specific test
pytest tests/test_graphiti_int.py

# Run integration tests only
pytest -m integration

# Run in parallel
pytest -n auto
```

#### Frontend
```bash
# Run all tests
npm test

# Run with coverage
npm test -- --run --coverage

# Run specific test
npm test -- useGraphSimulation

# Run in UI mode
npm run test:ui

# Run in watch mode
npm test -- --watch
```

#### Rust
```bash
# Run all tests
cargo test

# Run with coverage
cargo tarpaulin --out Html

# Run specific test
cargo test test_delta_tracker

# Run with features
cargo test --all-features

# Run in release mode
cargo test --release
```

### Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [Vitest documentation](https://vitest.dev/)
- [Testing Library](https://testing-library.com/)
- [cargo-tarpaulin](https://github.com/xd009642/tarpaulin)
- [Codecov](https://about.codecov.io/)

---

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-17 | System | Initial requirements document |

