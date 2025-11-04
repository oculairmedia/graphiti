# Test Infrastructure Quick Start

## ✅ What's Been Created

### Directory Structure
```
graph-visualizer-rust/
├── tests/
│   ├── common/mod.rs              ✅ Test utilities & fixtures
│   ├── duckdb_store_tests.rs      ✅ 10 test cases (skeleton)
│   ├── delta_tracker_tests.rs     ✅ 9 test cases (skeleton)
│   ├── cache_tests.rs             ✅ 8 test cases (skeleton)
│   └── integration_tests.rs       ✅ 8 test cases (skeleton)
├── benches/
│   ├── full_reload.rs             ✅ Performance benchmarks
│   ├── incremental_update.rs      ✅ Incremental benchmarks
│   └── query_performance.rs       ✅ Query benchmarks
├── Cargo.toml                      ✅ Dev dependencies added
├── TESTING.md                      ✅ Full testing guide
└── TEST_QUICKSTART.md             ✅ This file
```

### Test Statistics
- **Total test files**: 7
- **Test cases ready**: 35+
- **Benchmark suites**: 3
- **Helper utilities**: 6 functions

## 🚀 Quick Commands

### Run All Tests
```bash
cargo test
```

### Run Specific Module
```bash
cargo test duckdb_store_tests
cargo test delta_tracker_tests
cargo test cache_tests
```

### Run with Debug Output
```bash
RUST_LOG=debug cargo test -- --nocapture
```

### Run Benchmarks
```bash
cargo bench
```

### Generate Coverage Report
```bash
cargo install cargo-tarpaulin
cargo tarpaulin --out Html
```

## 📝 Next Steps

### Phase 1: Implement Unit Tests (Priority 1)

#### 1. Add Tests to `duckdb_store.rs`
Open `src/duckdb_store.rs` and add at the end:

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use tokio;
    
    #[tokio::test]
    async fn test_store_creation() {
        let temp_dir = tempfile::tempdir().unwrap();
        let store = DuckDBStore::new(temp_dir.path()).await;
        assert!(store.is_ok());
    }
    
    #[tokio::test]
    async fn test_load_initial_data() {
        // TODO: Implement based on tests/duckdb_store_tests.rs
    }
}
```

#### 2. Implement Integration Tests
Edit `tests/duckdb_store_tests.rs` and replace `// TODO` comments with actual implementations:

```rust
#[tokio::test]
async fn test_load_initial_data() {
    setup_test_logger();
    
    let (nodes, edges) = generate_test_graph();
    let temp_dir = create_temp_duckdb();
    
    // Import actual DuckDBStore (remove this comment when ready)
    // use graph_visualizer_backend::DuckDBStore;
    // let store = DuckDBStore::new(temp_dir.path()).await.unwrap();
    // store.load_initial_data(nodes.clone(), edges.clone()).await.unwrap();
    
    // For now, this test will be skipped
}
```

#### 3. Make Types Public for Testing
In `src/duckdb_store.rs`, ensure structs are public:

```rust
pub struct DuckDBStore { ... }
pub struct Node { ... }
pub struct Edge { ... }
```

### Phase 2: Run Baseline Tests

```bash
# Should compile (tests will be ignored/skipped until implemented)
cargo test

# Expected output:
# running 35 tests
# test result: ok. 4 passed; 0 failed; 31 ignored
```

### Phase 3: Implement Benchmarks

```bash
# Run benchmarks (mock data for now)
cargo bench

# View HTML reports
open target/criterion/report/index.html
```

### Phase 4: Add More Tests

Priority order:
1. ✅ **DuckDB Store** - Critical for data integrity
2. ✅ **Delta Tracker** - Critical for incremental updates
3. ⚠️ **Cache** - Important for performance
4. ⚠️ **Integration** - End-to-end validation

## 🔧 Troubleshooting

### Issue: Tests Don't Compile
```bash
# Check for syntax errors
cargo check --tests

# Fix any import issues
# Make sure src/lib.rs exists or modules are properly exposed
```

### Issue: Can't Import Test Modules
Create `src/lib.rs`:
```rust
pub mod duckdb_store;
pub mod delta_tracker;
pub mod cache;
pub mod websocket;
pub mod arrow_converter;
```

### Issue: DuckDB Connection Fails
```bash
# Tests use temp directories, but ensure permissions
ls -la /tmp/
```

## 📊 Test Coverage Goals

| Module | Current | Target | Priority |
|--------|---------|--------|----------|
| duckdb_store.rs | 0% | 80%+ | HIGH |
| delta_tracker.rs | 0% | 80%+ | HIGH |
| cache.rs | 0% | 70%+ | MEDIUM |
| main.rs | 0% | 50%+ | MEDIUM |
| websocket.rs | 0% | 60%+ | LOW |

## 🎯 Test-First Development Workflow

When implementing incremental updates:

```bash
# 1. Write test first
cd tests/
# Edit duckdb_store_tests.rs
# Add test_incremental_update_new_nodes()

# 2. Run test (should fail)
cargo test test_incremental_update_new_nodes

# 3. Implement feature
cd ../src/
# Edit duckdb_store.rs
# Add update_incremental() method

# 4. Run test again (should pass)
cargo test test_incremental_update_new_nodes

# 5. Run all tests
cargo test

# 6. Run benchmarks
cargo bench incremental_update

# 7. Commit
git add .
git commit -m "feat: implement incremental updates with tests"
```

## 📚 Learning Resources

- **Test Fixtures**: See `tests/common/mod.rs`
- **Example Tests**: See `tests/duckdb_store_tests.rs`
- **Benchmark Examples**: See `benches/full_reload.rs`
- **Full Guide**: See `TESTING.md`

## ✨ Test Infrastructure Features

✅ **Common Test Utilities**
- `create_test_node()` - Generate test nodes
- `create_test_edge()` - Generate test edges  
- `generate_test_graph()` - Small test dataset (3 nodes, 3 edges)
- `generate_large_test_graph(n, m)` - Large test dataset
- `create_temp_duckdb()` - Temporary test database
- `setup_test_logger()` - Enable debug logging in tests

✅ **Dev Dependencies Added**
- `tokio-test` - Async testing
- `mockall` - Mocking framework
- `proptest` - Property-based testing
- `fake` - Fake data generation
- `rstest` - Fixture-based testing
- `tempfile` - Temporary file handling
- `wiremock` - HTTP mocking
- `serial_test` - Sequential test execution
- `criterion` - Benchmarking with HTML reports

✅ **Test Categories**
- Unit tests (in source files)
- Integration tests (tests/ directory)
- Benchmarks (benches/ directory)
- Property-based tests (proptest)

## 🎉 Success Criteria

You'll know the test infrastructure is working when:

1. ✅ `cargo test` compiles without errors
2. ✅ `cargo bench` runs benchmarks
3. ✅ Test utilities work: `generate_test_graph()`
4. ⚠️ At least 1 real test passes (not just skeleton)
5. ⚠️ Coverage report can be generated
6. ⚠️ CI/CD runs tests automatically

**Current Status: 3/6 ✅ (Infrastructure Complete, Implementation Pending)**

## 🚨 Important Notes

- **Tests are skeletons** - They need actual implementations
- **Use TDD** - Write tests before implementing incremental updates
- **Don't skip tests** - They're critical for production safety
- **Benchmark first** - Establish baseline before optimizing

## 🔗 Related Documents

- [INCREMENTAL_UPDATE_PLAN.md](./INCREMENTAL_UPDATE_PLAN.md) - What to implement
- [TESTING.md](./TESTING.md) - Complete testing guide
- [API_ENDPOINTS.md](./API_ENDPOINTS.md) - API documentation

---

**Questions?** Check TESTING.md or review test examples in `tests/common/mod.rs`
