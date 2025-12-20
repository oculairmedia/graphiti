# Test Coverage Documentation Index

## Overview

This index provides links to all test coverage documentation for the Graphiti project.

**Last Updated**: November 17, 2025  
**Document Owner**: Development Team

---

## Primary Documents

### 1. [TEST_COVERAGE_REQUIREMENTS.md](./TEST_COVERAGE_REQUIREMENTS.md)
**Purpose**: Comprehensive requirements and standards  
**Audience**: All developers, QA team, project managers  
**Content**:
- Current state assessment
- Coverage requirements and targets
- Test infrastructure setup
- Critical issues and remediation plan
- Coverage metrics and reporting
- Testing best practices

**When to Use**:
- Planning test coverage improvements
- Understanding coverage standards
- Setting up new test infrastructure
- Annual test strategy review

---

### 2. [TESTING_QUICK_START.md](./TESTING_QUICK_START.md)
**Purpose**: Quick reference for day-to-day testing  
**Audience**: Developers  
**Content**:
- Installation instructions
- How to run tests
- Test writing templates
- Common testing patterns
- Troubleshooting guide
- Quick checklists

**When to Use**:
- Daily development work
- Writing new tests
- Running test suites
- Debugging test failures
- Quick reference during coding

---

### 3. [TEST_COVERAGE_SETUP_CHECKLIST.md](./TEST_COVERAGE_SETUP_CHECKLIST.md)
**Purpose**: Step-by-step setup guide  
**Audience**: DevOps, team leads, new team members  
**Content**:
- Pre-requirements
- Installation steps
- Configuration checklist
- Baseline establishment
- CI/CD integration
- Documentation requirements
- Verification procedures

**When to Use**:
- Setting up new development environment
- Onboarding new team members
- Configuring CI/CD pipeline
- Auditing test infrastructure
- Troubleshooting setup issues

---

## Quick Links by Task

### For New Developers
1. Start with [TESTING_QUICK_START.md](./TESTING_QUICK_START.md)
2. Review [TEST_COVERAGE_REQUIREMENTS.md](./TEST_COVERAGE_REQUIREMENTS.md) - Section: "Testing Best Practices"
3. Use templates from Quick Start guide

### For Setting Up Environment
1. Follow [TEST_COVERAGE_SETUP_CHECKLIST.md](./TEST_COVERAGE_SETUP_CHECKLIST.md)
2. Verify installation with Quick Start commands
3. Generate baseline coverage reports

### For Writing Tests
1. Check templates in [TESTING_QUICK_START.md](./TESTING_QUICK_START.md)
2. Review best practices in [TEST_COVERAGE_REQUIREMENTS.md](./TEST_COVERAGE_REQUIREMENTS.md)
3. Follow coverage targets from Requirements doc

### For CI/CD Setup
1. Follow Phase 5 in [TEST_COVERAGE_SETUP_CHECKLIST.md](./TEST_COVERAGE_SETUP_CHECKLIST.md)
2. Review automation section in [TEST_COVERAGE_REQUIREMENTS.md](./TEST_COVERAGE_REQUIREMENTS.md)
3. Configure coverage thresholds

### For Troubleshooting
1. Check Quick Start troubleshooting section
2. Review Setup Checklist common issues
3. Consult Requirements doc remediation plan

---

## Coverage Targets Summary

| Component | Line Coverage | Branch Coverage | Function Coverage |
|-----------|--------------|-----------------|-------------------|
| Python Core | 80% | 75% | 85% |
| Frontend | 75% | 70% | 80% |
| Rust Services | 70% | 65% | 75% |
| Integration Tests | 60% | 55% | 65% |

**Critical Paths**: 100% coverage required  
**High Priority**: 90%+ coverage required  
**Standard**: 75%+ coverage required

---

## Current Status (As of Nov 17, 2025)

### Python Backend
- **Status**: 🔴 Below target
- **Current Coverage**: ~45%
- **Target**: 80%
- **Gap**: 35 percentage points
- **Action Items**: See Requirements doc, Phase 3

### Frontend
- **Status**: 🟡 Near target
- **Current Coverage**: ~65%
- **Target**: 75%
- **Gap**: 10 percentage points
- **Action Items**: Fix failing tests, add component coverage

### Rust Services
- **Status**: 🔴 No data
- **Current Coverage**: Unknown
- **Target**: 70%
- **Gap**: Need baseline measurement
- **Action Items**: Configure and run coverage tools

---

## Running Coverage Reports

### Quick Commands

**Python:**
```bash
pytest --cov=graphiti_core --cov-report=html --cov-report=term
open htmlcov/index.html
```

**Frontend:**
```bash
cd frontend
npm test -- --run --coverage
open coverage/index.html
```

**Rust:**
```bash
cd graph-visualizer-rust
cargo tarpaulin --out Html
open coverage/index.html
```

---

## CI/CD Integration Status

- [ ] GitHub Actions workflow created
- [ ] Codecov integrated
- [ ] Coverage badges added to README
- [ ] Coverage thresholds enforced
- [ ] PR coverage checks enabled
- [ ] Automated reports configured

---

## Related Documentation

### Project Documentation
- `README.md` - Project overview
- `CONTRIBUTING.md` - Contribution guidelines
- `CLAUDE.md` - Claude Code agent instructions
- `AGENTS.md` - Agent configurations

### Configuration Files
- `pytest.ini` - Python test configuration
- `.coveragerc` - Python coverage configuration
- `vite.config.ts` - Frontend test configuration
- `tarpaulin.toml` - Rust coverage configuration

### CI/CD Files
- `.github/workflows/tests.yml` - Test automation
- `codecov.yml` - Coverage service configuration

---

## Maintenance Schedule

### Daily
- Run tests before committing
- Review test failures
- Fix broken tests immediately

### Weekly
- Review coverage trends
- Check for flaky tests
- Update failing tests

### Monthly
- Generate coverage report
- Share with team
- Identify improvement areas
- Update coverage goals

### Quarterly
- Audit test suite
- Update testing tools
- Review coverage targets
- Training refresher

---

## Support and Resources

### Internal Support
- **Testing Lead**: TBD
- **DevOps Team**: For CI/CD issues
- **Development Team**: For general questions

### External Resources
- [pytest documentation](https://docs.pytest.org/)
- [Vitest documentation](https://vitest.dev/)
- [Testing Library](https://testing-library.com/)
- [Codecov documentation](https://docs.codecov.com/)
- [cargo-tarpaulin](https://github.com/xd009642/tarpaulin)

### Getting Help
1. Check documentation index (this file)
2. Review relevant documentation
3. Check troubleshooting sections
4. Ask in team chat
5. Create GitHub issue if needed

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-17 | System | Initial documentation created |

---

## Next Steps

1. **Immediate** (This Week):
   - [ ] Install coverage tools (all platforms)
   - [ ] Fix blocking test errors
   - [ ] Generate baseline coverage reports

2. **Short Term** (This Month):
   - [ ] Fix failing frontend tests
   - [ ] Configure CI/CD integration
   - [ ] Add coverage badges to README

3. **Medium Term** (This Quarter):
   - [ ] Reach 80% Python coverage
   - [ ] Reach 75% Frontend coverage
   - [ ] Establish Rust coverage baseline
   - [ ] Implement automated coverage tracking

4. **Long Term** (This Year):
   - [ ] Achieve all coverage targets
   - [ ] Full CI/CD integration
   - [ ] Comprehensive E2E test suite
   - [ ] Team training completed

---

**For questions or updates to this documentation, please contact the development team.**
