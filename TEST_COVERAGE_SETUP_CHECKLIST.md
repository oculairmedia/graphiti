# Test Coverage Setup Checklist

## Overview
This checklist ensures proper test coverage infrastructure is in place for the Graphiti project.

**Date Created**: November 17, 2025  
**Status**: In Progress  
**Owner**: Development Team

---

## Pre-Requirements

### System Requirements
- [ ] Python 3.11+ installed
- [ ] Node.js 20+ installed
- [ ] Rust 1.70+ installed
- [ ] Git installed and configured
- [ ] Docker installed (for integration tests)

### Access Requirements
- [ ] GitHub repository access
- [ ] CI/CD pipeline access
- [ ] Code coverage service account (Codecov/Coveralls)
- [ ] Test database credentials (for integration tests)

---

## Phase 1: Install Coverage Tools

### Python Backend
- [ ] Install pytest-cov
  ```bash
  pip install pytest-cov
  ```
- [ ] Install coverage
  ```bash
  pip install coverage
  ```
- [ ] Install pytest-asyncio
  ```bash
  pip install pytest-asyncio
  ```
- [ ] Install pytest-mock
  ```bash
  pip install pytest-mock
  ```
- [ ] Install pytest-xdist (optional, for parallel execution)
  ```bash
  pip install pytest-xdist
  ```
- [ ] Verify installation
  ```bash
  pytest --version
  pytest --cov --version
  ```

### Frontend
- [ ] Navigate to frontend directory
  ```bash
  cd frontend
  ```
- [ ] Install @vitest/coverage-v8
  ```bash
  npm install --save-dev @vitest/coverage-v8
  ```
- [ ] Verify installation
  ```bash
  npm test -- --version
  npm list @vitest/coverage-v8
  ```

### Rust Services
- [ ] Install cargo-tarpaulin
  ```bash
  cargo install cargo-tarpaulin
  ```
- [ ] OR install cargo-llvm-cov
  ```bash
  rustup component add llvm-tools-preview
  cargo install cargo-llvm-cov
  ```
- [ ] Verify installation
  ```bash
  cargo tarpaulin --version
  # OR
  cargo llvm-cov --version
  ```

---

## Phase 2: Configure Coverage Settings

### Python Configuration

#### Create .coveragerc
- [ ] Create `.coveragerc` in project root
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
  fail_under = 80
  
  [html]
  directory = htmlcov
  
  [xml]
  output = coverage.xml
  ```

#### Update pytest.ini
- [ ] Update `pytest.ini` with coverage settings
  ```ini
  [pytest]
  markers =
      integration: marks tests as integration tests
      unit: marks tests as unit tests
      slow: marks tests as slow running
  asyncio_default_fixture_loop_scope = function
  
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

#### Update requirements.txt
- [ ] Add test dependencies to `requirements.txt`
  ```text
  pytest>=8.0.0
  pytest-cov>=4.1.0
  pytest-asyncio>=0.21.0
  pytest-mock>=3.12.0
  pytest-xdist>=3.5.0
  coverage>=7.3.0
  ```

### Frontend Configuration

#### Update vite.config.ts
- [ ] Add coverage configuration to `vite.config.ts`
  ```typescript
  import { defineConfig } from 'vite';
  
  export default defineConfig({
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/test/setup.ts',
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
          '**/*.d.ts',
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

#### Update package.json
- [ ] Ensure test scripts are configured
  ```json
  {
    "scripts": {
      "test": "vitest",
      "test:ui": "vitest --ui",
      "test:run": "vitest run",
      "test:coverage": "vitest run --coverage"
    }
  }
  ```

### Rust Configuration

#### Create tarpaulin.toml
- [ ] Create `tarpaulin.toml` in Rust project root
  ```toml
  [report]
  out = ["Html", "Xml", "Lcov"]
  output-dir = "coverage/"
  
  [run]
  exclude-files = [
      "*/tests/*",
      "*/target/*",
  ]
  
  [html]
  output-dir = "coverage/html/"
  
  [xml]
  output-dir = "coverage/"
  ```

---

## Phase 3: Fix Blocking Issues

### Python Test Collection Errors
- [ ] Fix `tests/cross_encoder/test_bge_reranker_client.py`
  - [ ] Check import statements
  - [ ] Verify dependencies installed
  - [ ] Add conditional imports if needed
  
- [ ] Fix `tests/cross_encoder/test_gemini_reranker_client.py`
  - [ ] Check API key configuration
  - [ ] Add skip markers for optional dependencies
  
- [ ] Fix `tests/embedder/test_gemini.py`
  - [ ] Verify Gemini SDK installed
  - [ ] Add environment variable checks
  
- [ ] Fix `tests/embedder/test_voyage.py`
  - [ ] Check Voyage API configuration
  - [ ] Add skip markers if API key missing
  
- [ ] Fix `tests/llm_client/test_gemini_client.py`
  - [ ] Verify client initialization
  - [ ] Check authentication setup

### Frontend GraphCanvasV2 Tests
- [ ] Fix loadingCoordinator mock in test setup
  ```typescript
  const mockLoadingCoordinator = {
    getStageStatus: vi.fn().mockReturnValue('ready'),
    setStageComplete: vi.fn(),
    // ... other methods
  };
  ```
- [ ] Update all 19 failing tests
- [ ] Verify tests pass

### Rust Test Configuration
- [ ] Check `Cargo.toml` test configuration
- [ ] Verify test features are enabled
- [ ] Add `[[test]]` sections if needed
- [ ] Run `cargo test --list` to verify discovery

---

## Phase 4: Baseline Coverage

### Generate Initial Reports

#### Python
- [ ] Run full test suite with coverage
  ```bash
  pytest --cov=graphiti_core --cov-report=html --cov-report=term --cov-report=xml
  ```
- [ ] Document baseline coverage percentage: ______%
- [ ] Review HTML report (`htmlcov/index.html`)
- [ ] Identify top 10 uncovered modules
- [ ] Save coverage.xml for tracking

#### Frontend
- [ ] Run full test suite with coverage
  ```bash
  cd frontend
  npm test -- --run --coverage
  ```
- [ ] Document baseline coverage percentage: ______%
- [ ] Review HTML report (`coverage/index.html`)
- [ ] Identify top 10 uncovered components
- [ ] Save lcov.info for tracking

#### Rust
- [ ] Run full test suite with coverage
  ```bash
  cd graph-visualizer-rust
  cargo tarpaulin --out Html --out Xml
  ```
- [ ] Document baseline coverage percentage: ______%
- [ ] Review HTML report (`coverage/index.html`)
- [ ] Identify uncovered modules
- [ ] Save cobertura.xml for tracking

---

## Phase 5: CI/CD Integration

### GitHub Actions

#### Create workflow file
- [ ] Create `.github/workflows/tests.yml`
  ```yaml
  name: Tests and Coverage
  
  on:
    push:
      branches: [ main, develop ]
    pull_request:
      branches: [ main, develop ]
  
  jobs:
    python-tests:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v3
        - uses: actions/setup-python@v4
          with:
            python-version: '3.11'
        - name: Install dependencies
          run: |
            pip install -r requirements.txt
            pip install pytest pytest-cov
        - name: Run tests
          run: pytest --cov=graphiti_core --cov-report=xml --cov-report=term
        - name: Upload coverage
          uses: codecov/codecov-action@v3
          with:
            files: ./coverage.xml
            flags: python
            name: python-coverage
    
    frontend-tests:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v3
        - uses: actions/setup-node@v3
          with:
            node-version: '20'
        - name: Install dependencies
          run: cd frontend && npm ci
        - name: Run tests
          run: cd frontend && npm test -- --run --coverage
        - name: Upload coverage
          uses: codecov/codecov-action@v3
          with:
            files: ./frontend/coverage/lcov.info
            flags: frontend
            name: frontend-coverage
    
    rust-tests:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v3
        - uses: actions-rs/toolchain@v1
          with:
            toolchain: stable
        - name: Install tarpaulin
          run: cargo install cargo-tarpaulin
        - name: Run tests
          run: |
            cd graph-visualizer-rust
            cargo tarpaulin --out Xml
        - name: Upload coverage
          uses: codecov/codecov-action@v3
          with:
            files: ./graph-visualizer-rust/coverage/cobertura.xml
            flags: rust
            name: rust-coverage
  ```

### Codecov Setup
- [ ] Create Codecov account
- [ ] Link GitHub repository
- [ ] Get upload token
- [ ] Add token to GitHub secrets (`CODECOV_TOKEN`)
- [ ] Create `codecov.yml` configuration
  ```yaml
  coverage:
    status:
      project:
        default:
          target: 80%
          threshold: 1%
      patch:
        default:
          target: 80%
  
  comment:
    layout: "reach,diff,flags,tree"
    behavior: default
  
  ignore:
    - "tests/"
    - "**/*_test.py"
    - "**/*.test.ts"
    - "**/*.test.tsx"
  ```

---

## Phase 6: Documentation

### Update README.md
- [ ] Add testing section
- [ ] Add coverage badges
  ```markdown
  ## Testing
  
  ![Python Coverage](https://codecov.io/gh/org/repo/branch/main/graph/badge.svg?flag=python)
  ![Frontend Coverage](https://codecov.io/gh/org/repo/branch/main/graph/badge.svg?flag=frontend)
  ![Rust Coverage](https://codecov.io/gh/org/repo/branch/main/graph/badge.svg?flag=rust)
  
  ### Running Tests
  
  See [TESTING_QUICK_START.md](./TESTING_QUICK_START.md) for details.
  ```

### Create Developer Guide
- [ ] Document test writing standards
- [ ] Provide test templates
- [ ] Document CI/CD process
- [ ] Add troubleshooting section

### Update Contributing Guide
- [ ] Add testing requirements for PRs
- [ ] Document coverage expectations
- [ ] Add pre-commit checklist

---

## Phase 7: Team Onboarding

### Training Materials
- [ ] Create testing workshop slides
- [ ] Record demo video
- [ ] Write example test walkthrough
- [ ] Document common patterns

### Team Meeting
- [ ] Schedule testing standards meeting
- [ ] Review coverage requirements
- [ ] Demo coverage tools
- [ ] Q&A session

### Code Review Guidelines
- [ ] Update PR template with test checklist
- [ ] Add coverage check to review process
- [ ] Document test review criteria

---

## Phase 8: Monitoring & Maintenance

### Weekly Tasks
- [ ] Review coverage trends
- [ ] Check for flaky tests
- [ ] Update failing tests
- [ ] Review new uncovered code

### Monthly Tasks
- [ ] Generate coverage report
- [ ] Share with team
- [ ] Identify improvement areas
- [ ] Update coverage goals

### Quarterly Tasks
- [ ] Audit test suite
- [ ] Update testing tools
- [ ] Review coverage targets
- [ ] Training refresher

---

## Verification

### Final Checks
- [ ] All tests run successfully on CI/CD
- [ ] Coverage reports generated automatically
- [ ] Coverage badges visible on README
- [ ] Team trained on testing standards
- [ ] Documentation complete and accessible
- [ ] Pre-commit hooks configured
- [ ] Coverage thresholds enforced
- [ ] Monitoring in place

### Sign-off
- [ ] Development Lead: ________________ Date: ________
- [ ] QA Lead: ________________ Date: ________
- [ ] DevOps Lead: ________________ Date: ________

---

## Troubleshooting Common Issues

### Issue: Coverage tool not found
**Solution**: Verify installation, check PATH, reinstall if needed

### Issue: Tests not discovered
**Solution**: Check naming conventions, verify pytest.ini configuration

### Issue: Coverage report empty
**Solution**: Ensure source paths correct, check .coveragerc configuration

### Issue: CI/CD failing
**Solution**: Check GitHub Actions logs, verify secrets configured

### Issue: Flaky tests
**Solution**: Identify timing issues, improve mocking, add retries

---

## Resources

- [TEST_COVERAGE_REQUIREMENTS.md](./TEST_COVERAGE_REQUIREMENTS.md) - Detailed requirements
- [TESTING_QUICK_START.md](./TESTING_QUICK_START.md) - Quick reference guide
- [pytest documentation](https://docs.pytest.org/)
- [Vitest documentation](https://vitest.dev/)
- [Codecov documentation](https://docs.codecov.com/)

---

**Status Key:**
- ✅ Complete
- 🟡 In Progress
- ❌ Not Started
- ⚠️ Blocked

**Last Updated**: November 17, 2025
