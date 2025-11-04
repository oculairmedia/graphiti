# Testing Guide - Graph Visualizer Rust

## Overview

This document describes the testing infrastructure for the graph visualizer backend.

## Test Structure

```
graph-visualizer-rust/
├── tests/
│   ├── common/
│   │   └── mod.rs              # Shared test utilities and fixtures
│   ├── duckdb_store_tests.rs   # DuckDB store tests
│   ├── delta_tracker_tests.rs  # Delta computation tests
│   ├── cache_tests.rs          # Cache functionality tests
│   └── integration_tests.rs    # End-to-end integration tests
├── benches/
│   ├── full_reload.rs          # Full reload performance benchmarks
│   ├── incremental_update.rs   # Incremental update benchmarks
│   └── query_performance.rs    # Query performance benchmarks
└── src/
    └── [unit tests in source files]
```

## Running Tests

### All Tests
```bash
cargo test
```

### Specific Test Module
```bash
cargo test duckdb_store_tests
cargo test delta_tracker_tests
cargo test cache_tests
cargo test integration_tests
```

### Specific Test Function
```bash
cargo test test_load_initial_data
```

### With Logging Output
```bash
RUST_LOG=debug cargo test -- --nocapture
```

### Integration Tests Only (require database)
```bash
cargo test --test integration_tests -- --ignored
```

### Excluding Integration Tests
```bash
cargo test -- --skip integration_tests
```

## Running Benchmarks

### All Benchmarks
```bash
cargo bench
```

### Specific Benchmark
```bash
cargo bench full_reload
cargo bench incremental_update
cargo bench query_performance
```

### Generate HTML Report
```bash
cargo bench
# Report generated at: target/criterion/report/index.html
```

## Test Categories

### Unit Tests (in source files)
- Test individual functions and methods
- Fast, no external dependencies
- Run with every code change

### Integration Tests (tests/ directory)
- Test interactions between modules
- May require test database
- Run before commits

### Benchmarks (benches/ directory)
- Measure performance
- Compare before/after changes
- Run before and after major refactors

## Test Fixtures and Helpers

### Common Test Utilities (tests/common/mod.rs)

```rust
use tests::common::{
    create_test_node,
    create_test_edge,
    generate_test_graph,
    generate_large_test_graph,
    create_temp_duckdb,
    setup_test_logger,
};

// Create test data
let (nodes, edges) = generate_test_graph();

// Create temporary database
let temp_dir = create_temp_duckdb();

// Enable debug logging in tests
setup_test_logger();
```

## Writing Tests

### Unit Test Example

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_example() {
        let result = my_function(42);
        assert_eq!(result, 84);
    }

    #[tokio::test]
    async fn test_async_example() {
        let result = my_async_function().await;
        assert!(result.is_ok());
    }
}
```

### Integration Test Example

```rust
#[tokio::test]
async fn test_full_flow() {
    setup_test_logger();
    
    // Setup
    let (nodes, edges) = generate_test_graph();
    let temp_dir = create_temp_duckdb();
    let store = DuckDBStore::new(temp_dir.path()).await.unwrap();
    
    // Execute
    store.load_initial_data(nodes.clone(), edges.clone()).await.unwrap();
    
    // Verify
    let node_count = store.get_node_count().await.unwrap();
    assert_eq!(node_count, nodes.len());
}
```

### Benchmark Example

```rust
use criterion::{criterion_group, criterion_main, Criterion};

fn benchmark_my_function(c: &mut Criterion) {
    c.bench_function("my_function", |b| {
        b.iter(|| my_function(42));
    });
}

criterion_group!(benches, benchmark_my_function);
criterion_main!(benches);
```

## Test Coverage

To measure test coverage:

```bash
# Install tarpaulin
cargo install cargo-tarpaulin

# Generate coverage report
cargo tarpaulin --out Html

# View report
open tarpaulin-report.html
```

## Continuous Integration

Tests are run automatically on:
- Every commit (fast tests only)
- Pull requests (all tests)
- Before deployment (all tests + benchmarks)

## Test-Driven Development (TDD)

When implementing new features:

1. **Write test first** (will fail)
2. **Implement minimal code** to pass test
3. **Refactor** while keeping tests passing
4. **Add edge cases** as new tests

Example for incremental update feature:

```bash
# 1. Write failing test
cargo test test_incremental_update_new_nodes
# ❌ Test fails (function not implemented)

# 2. Implement function
# Edit src/duckdb_store.rs

# 3. Run test again
cargo test test_incremental_update_new_nodes
# ✅ Test passes

# 4. Add benchmark
cargo bench incremental_update
# Verify performance target met
```

## Current Status

### ✅ Test Infrastructure Complete
- [x] Test directory structure
- [x] Test utilities and fixtures
- [x] Benchmark framework
- [x] Cargo.toml configuration

### ⚠️ Tests Need Implementation
- [ ] DuckDB store unit tests
- [ ] Delta tracker unit tests
- [ ] Cache unit tests
- [ ] Integration tests
- [ ] Benchmarks with real data

### 🎯 Next Steps

1. **Add unit tests to source files**
   - Open each .rs file in src/
   - Add `#[cfg(test)] mod tests` at bottom
   - Implement tests for key functions

2. **Implement integration tests**
   - Remove `// TODO` comments
   - Add actual test implementations
   - Test with real database connections

3. **Run and validate benchmarks**
   - Establish baseline performance metrics
   - Document current performance
   - Set target metrics for improvements

4. **Enable CI/CD**
   - Add test runs to GitHub Actions
   - Enforce coverage thresholds
   - Block PRs with failing tests

## Best Practices

### ✅ DO
- Write tests before implementing features (TDD)
- Use descriptive test names: `test_incremental_update_with_duplicate_nodes`
- Test edge cases (empty input, null, overflow, etc.)
- Mock external dependencies (FalkorDB, Redis)
- Use `setup_test_logger()` for debugging
- Clean up resources in tests (temp files, connections)

### ❌ DON'T
- Skip tests because "it's too hard"
- Test implementation details (test behavior, not internals)
- Use random data without seeds (makes tests non-deterministic)
- Leave `#[ignore]` on tests permanently
- Commit failing tests
- Make tests depend on each other

## Troubleshooting

### Test Compilation Errors
```bash
cargo test --no-run
# Fix compilation errors first
```

### Test Hangs
```bash
# Run with timeout
cargo test -- --test-threads=1 --timeout 5
```

### Database Connection Issues
```bash
# Ensure FalkorDB is running
docker ps | grep falkordb

# Check connection string
echo $FALKORDB_URL
```

### Flaky Tests
```bash
# Run test multiple times
for i in {1..10}; do cargo test test_name; done
```

## Resources

- [Rust Testing Documentation](https://doc.rust-lang.org/book/ch11-00-testing.html)
- [Tokio Testing Guide](https://tokio.rs/tokio/topics/testing)
- [Criterion Benchmarking](https://github.com/bheisler/criterion.rs)
- [Proptest (Property-based testing)](https://github.com/proptest-rs/proptest)

## Questions?

See also:
- [INCREMENTAL_UPDATE_PLAN.md](./INCREMENTAL_UPDATE_PLAN.md) - Implementation plan
- [API_ENDPOINTS.md](./API_ENDPOINTS.md) - API documentation
- [RUST_SERVER_INSIGHTS.md](./RUST_SERVER_INSIGHTS.md) - Architecture details
