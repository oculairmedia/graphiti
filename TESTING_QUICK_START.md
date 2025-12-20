# Testing Quick Start Guide

## 🚀 Getting Started

This guide helps you quickly get up to speed with testing in the Graphiti project.

---

## Installation

### Python Backend
```bash
# Install testing dependencies
pip install pytest pytest-cov pytest-asyncio pytest-mock coverage

# Verify installation
pytest --version
```

### Frontend
```bash
# Navigate to frontend directory
cd frontend

# Install missing coverage tool
npm install --save-dev @vitest/coverage-v8

# Verify installation
npm test -- --version
```

### Rust Services
```bash
# Install coverage tool (optional but recommended)
cargo install cargo-tarpaulin

# Verify installation
cargo test --version
```

---

## Running Tests

### Python

```bash
# Run all tests
pytest

# Run with coverage (recommended)
pytest --cov=graphiti_core --cov-report=html --cov-report=term

# Run only unit tests (fast)
pytest -m "not integration"

# Run only integration tests
pytest -m integration

# Run specific test file
pytest tests/test_graphiti_int.py

# Run specific test function
pytest tests/test_graphiti_int.py::test_add_episode

# Run in parallel (faster)
pytest -n auto

# View HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Frontend

```bash
cd frontend

# Run all tests
npm test -- --run

# Run with coverage (recommended)
npm test -- --run --coverage

# Run in watch mode (for development)
npm test

# Run with UI (interactive)
npm run test:ui

# Run specific test file
npm test -- useGraphSimulation

# View HTML coverage report
open coverage/index.html  # macOS
xdg-open coverage/index.html  # Linux
```

### Rust

```bash
# Run all tests
cargo test

# Run with output
cargo test -- --nocapture

# Run specific test
cargo test test_delta_tracker

# Run with coverage
cargo tarpaulin --out Html --output-dir coverage/

# View coverage report
open coverage/index.html  # macOS
xdg-open coverage/index.html  # Linux
```

---

## Writing Tests

### Python Test Template

```python
"""Test module for [component name]."""
import pytest
from graphiti_core import YourModule


class TestYourModule:
    """Test suite for YourModule."""
    
    def test_basic_functionality(self):
        """Test that basic functionality works."""
        # Arrange
        instance = YourModule()
        
        # Act
        result = instance.do_something()
        
        # Assert
        assert result is not None
    
    @pytest.mark.integration
    async def test_integration_scenario(self):
        """Test integration with external dependencies."""
        # Arrange
        instance = await setup_instance()
        
        # Act
        result = await instance.do_async_operation()
        
        # Assert
        assert result.success is True
        
    @pytest.fixture
    def sample_data(self):
        """Provide sample data for tests."""
        return {"key": "value"}
```

### Frontend Test Template

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { renderHook, act } from '@testing-library/react';
import YourComponent from './YourComponent';
import { useYourHook } from './useYourHook';

describe('YourComponent', () => {
  it('should render correctly', () => {
    render(<YourComponent />);
    expect(screen.getByRole('button')).toBeInTheDocument();
  });
  
  it('should handle user interaction', async () => {
    const mockHandler = vi.fn();
    const { user } = render(
      <YourComponent onClick={mockHandler} />
    );
    
    await user.click(screen.getByRole('button'));
    expect(mockHandler).toHaveBeenCalledTimes(1);
  });
});

describe('useYourHook', () => {
  it('should initialize with default state', () => {
    const { result } = renderHook(() => useYourHook());
    expect(result.current.value).toBe(null);
  });
  
  it('should update state', () => {
    const { result } = renderHook(() => useYourHook());
    
    act(() => {
      result.current.setValue('new value');
    });
    
    expect(result.current.value).toBe('new value');
  });
});
```

### Rust Test Template

```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_basic_functionality() {
        // Arrange
        let instance = YourStruct::new();
        
        // Act
        let result = instance.do_something();
        
        // Assert
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), expected_value);
    }
    
    #[tokio::test]
    async fn test_async_functionality() {
        // Arrange
        let instance = YourStruct::new().await.unwrap();
        
        // Act
        let result = instance.do_async_operation().await;
        
        // Assert
        assert!(result.is_ok());
    }
    
    #[test]
    #[should_panic(expected = "error message")]
    fn test_error_handling() {
        let instance = YourStruct::new();
        instance.operation_that_panics();
    }
}
```

---

## Common Testing Patterns

### Mocking in Python

```python
from unittest.mock import Mock, patch, AsyncMock

# Mock a function
@patch('module.function_name')
def test_with_mock(mock_function):
    mock_function.return_value = "mocked value"
    result = call_function_that_uses_mock()
    assert result == "mocked value"

# Mock an async function
@pytest.mark.asyncio
async def test_async_mock():
    mock = AsyncMock(return_value="result")
    result = await mock()
    assert result == "result"

# Mock a class
mock_instance = Mock()
mock_instance.method.return_value = "value"
```

### Mocking in Frontend

```typescript
import { vi } from 'vitest';

// Mock a function
const mockFn = vi.fn().mockReturnValue('mocked');

// Mock a module
vi.mock('./api', () => ({
  fetchData: vi.fn().mockResolvedValue({ data: [] }),
}));

// Mock fetch
global.fetch = vi.fn().mockResolvedValue({
  json: async () => ({ data: [] }),
});

// Spy on function
const spy = vi.spyOn(object, 'method');
expect(spy).toHaveBeenCalled();
```

### Fixtures in Python

```python
import pytest

@pytest.fixture
def sample_node():
    """Create a sample node for testing."""
    return EntityNode(name="Test", labels=["Entity"])

@pytest.fixture
async def graphiti_client():
    """Provide a test Graphiti client."""
    client = Graphiti(...)
    yield client
    await client.close()  # Cleanup

def test_using_fixture(sample_node):
    """Test uses the fixture."""
    assert sample_node.name == "Test"
```

---

## Coverage Goals

| Component | Target | Current | Status |
|-----------|--------|---------|--------|
| Python Core | 80% | ~45% | 🔴 Needs work |
| Frontend | 75% | ~65% | 🟡 Close |
| Rust Services | 70% | Unknown | 🔴 Needs setup |

---

## Best Practices

### ✅ DO

- Write tests for all new code
- Aim for high coverage on critical paths
- Keep tests fast (< 100ms for unit tests)
- Use descriptive test names
- Test edge cases and error conditions
- Mock external dependencies
- Clean up resources (use fixtures/cleanup)
- Run tests before committing

### ❌ DON'T

- Skip tests for "simple" code
- Test implementation details
- Create test dependencies (test order matters)
- Use real databases in unit tests
- Hardcode credentials or secrets
- Ignore failing tests
- Commit without running tests
- Write flaky tests

---

## Troubleshooting

### Python: Tests not collecting

```bash
# Check pytest can find tests
pytest --collect-only

# Common issues:
# 1. File doesn't start with "test_" or end with "_test.py"
# 2. Function doesn't start with "test_"
# 3. Import errors in test file
# 4. Missing __init__.py in test directories
```

### Frontend: Tests failing with import errors

```bash
# Clear cache
rm -rf node_modules/.vite
npm test -- --clearCache

# Reinstall dependencies
rm -rf node_modules package-lock.json
npm install
```

### Rust: Tests not running

```bash
# Check test discovery
cargo test -- --list

# Run with verbose output
cargo test -- --nocapture --test-threads=1

# Common issues:
# 1. Tests in src/ need #[cfg(test)] module
# 2. Tests in tests/ need to be integration tests
# 3. Missing test features in Cargo.toml
```

### Coverage reports empty

```bash
# Python: Ensure source is specified
pytest --cov=graphiti_core --cov-report=term

# Frontend: Check vite.config.ts includes src/
npm test -- --run --coverage

# Rust: Use correct output format
cargo tarpaulin --out Html
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  python-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pip install pytest pytest-cov
      - run: pytest --cov=graphiti_core --cov-report=xml
      - uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: '20'
      - run: cd frontend && npm ci
      - run: cd frontend && npm test -- --run --coverage
      - uses: codecov/codecov-action@v3
        with:
          files: ./frontend/coverage/lcov.info

  rust-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions-rs/toolchain@v1
        with:
          toolchain: stable
      - run: cargo test --all-features
```

---

## Useful Resources

### Documentation
- **Python**: https://docs.pytest.org/
- **Frontend**: https://vitest.dev/
- **React Testing**: https://testing-library.com/
- **Rust**: https://doc.rust-lang.org/book/ch11-00-testing.html

### Tools
- **Coverage tracking**: https://codecov.io/
- **CI/CD**: https://github.com/features/actions
- **Test generators**: https://github.com/copilot

### Internal Docs
- `TEST_COVERAGE_REQUIREMENTS.md` - Detailed requirements
- `pytest.ini` - Python test configuration
- `vite.config.ts` - Frontend test configuration

---

## Quick Checklist

Before submitting a PR:

- [ ] All tests pass locally
- [ ] New code has tests
- [ ] Coverage didn't decrease
- [ ] No test warnings
- [ ] Tests run in < 5 minutes
- [ ] Integration tests marked correctly
- [ ] Mocks cleaned up properly

---

## Getting Help

### Still stuck?

1. Check test output carefully
2. Run with verbose flag (`-v` or `--verbose`)
3. Check existing tests for examples
4. Ask in team chat
5. Review documentation links above

### Found a bug in tests?

1. Create an issue with:
   - Test command run
   - Full error output
   - Expected vs actual behavior
2. Tag with `testing` label
3. Assign to testing lead

---

**Last Updated**: November 17, 2025  
**Maintainer**: Development Team
