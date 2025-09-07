# Embedding Dimension 1024 References - Fix Required

## Issue Summary
The error "expected 1024 but got 2560" occurs because several parts of the codebase still reference 1024 as the default embedding dimension, while the actual model (Qwen3-Embedding-4B) produces 2560-dimensional embeddings.

## Critical Fix Required

### 1. Primary Issue: Python Embedder Default
**File:** `graphiti_core/embedder/client.py`
**Line 33:** 
```python
return int(os.getenv('EMBEDDING_DIMENSION', '1024'))  # ❌ Should be '2560'
```

**Line ~40 (EmbedderConfig):**
```python
class EmbedderConfig(BaseModel):
    embedding_dim: int = Field(default=EMBEDDING_DIM, frozen=True)  # Uses the 1024 default
```

**Fix:** Change the default from '1024' to '2560' to match the Qwen3-Embedding-4B model.

## Test Files Using 1024 (Need Updates)

### 2. Rust Test File
**File:** `graphiti-search-rs/tests/test_falkordb_sdk.rs`
**Lines 29, 147:**
```rust
let test_vector: Vec<f32> = (0..1024).map(|i| ((i as f32) * 0.001).sin()).collect();
```
**Fix:** Change `1024` to `2560`

### 3. Python Integration Tests
**File:** `testing/integration/test_direct_v2.py`
**Line 20:**
```python
test_embedding = np.random.randn(1024).astype(np.float32)
```
**Fix:** Change `1024` to `2560`

### 4. Vector Wrapping Test
**File:** `test_vector_wrapping.py`
**Line 61:**
```python
test_vector = [0.1] * 1024
```
**Fix:** Change `1024` to `2560`

### 5. Vector Error Investigation Test
**File:** `test_vector_error_investigation.py`
**Line 72:**
```python
test_vector = [0.1] * 1024
```
**Fix:** Change `1024` to `2560`

### 6. Direct Query Test
**File:** `testing/integration/test_direct_query.py`
**Line 28:**
```python
test_embedding = [0.1] * 384  # This one uses 384, might be intentional
```
**Note:** This uses 384 dimensions - verify if this is correct for the test scenario.

## Documentation References

### 7. Model Documentation
**File:** `docs/investigations/falkordb_similarity_type_mismatch.md`
**Line 132:**
```markdown
Ensure dimensions match the underlying model (Ollama mxbai-embed-large = 1024)
```
**Fix:** Update to reflect current model: `(Qwen3-Embedding-4B = 2560)`

## Configuration Files (Already Fixed)

✅ **docker-compose.yml** - Already set to 2560
✅ **Rust search service** - Already defaults to 2560

## Root Cause Analysis

The issue stems from:
1. **Legacy default**: The Python embedder client still defaults to 1024 from when mxbai-embed-large was used
2. **Model change**: System now uses Qwen3-Embedding-4B which produces 2560-dimensional embeddings
3. **Environment variable**: When EMBEDDING_DIMENSION is not set, the system falls back to the hardcoded 1024 default

## Fix Priority

**High Priority (Critical):**
1. `graphiti_core/embedder/client.py` - Change default from 1024 to 2560

**Medium Priority (Test Consistency):**
2. Update all test files to use 2560 dimensions
3. Update documentation references

## Verification Steps

After fixes:
1. Restart services to pick up new defaults
2. Run embedding operations to verify no dimension mismatches
3. Check FalkorDB vector operations work correctly
4. Run test suite to ensure all tests pass with new dimensions

## Environment Variable Override

Users can still override the dimension via:
```bash
EMBEDDING_DIMENSION=2560
```

But the default should match the actual model being used (Qwen3-Embedding-4B = 2560).
