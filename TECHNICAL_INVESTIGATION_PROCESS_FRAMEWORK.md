# Technical Investigation Process Framework

**Document Version:** 1.0  
**Created:** September 21, 2025  
**Purpose:** Standardized methodology for conducting thorough technical investigations  
**Audience:** Engineering teams, technical leads, senior developers

---

## Overview

This document establishes a systematic approach for investigating technical issues, ensuring thorough analysis while avoiding common pitfalls like premature optimization, insufficient validation, and over-engineered solutions.

## Investigation Phases

### Phase 1: Problem Definition & Triage (30 minutes)

#### 1.1 Issue Classification
```markdown
**Severity Assessment:**
- [ ] Critical (system down, data loss)
- [ ] High (major feature broken, performance degraded)
- [ ] Medium (minor feature issues, workarounds available)
- [ ] Low (cosmetic, enhancement requests)

**Impact Scope:**
- [ ] Single user
- [ ] Multiple users
- [ ] System-wide
- [ ] Data integrity

**Urgency Timeline:**
- [ ] Immediate (< 1 hour)
- [ ] Same day (< 8 hours)
- [ ] This week (< 5 days)
- [ ] Next sprint (< 2 weeks)
```

#### 1.2 Initial Problem Statement
Document the issue using the 5W framework:
- **What:** Specific error/behavior observed
- **When:** Timeline and frequency of occurrence
- **Where:** System components, environments affected
- **Who:** Users/systems impacted
- **Why:** Business impact and urgency

#### 1.3 Success Criteria
Define clear, measurable outcomes:
```markdown
**Investigation Complete When:**
- [ ] Root cause identified with evidence
- [ ] Solution validated in test environment
- [ ] Risk assessment completed
- [ ] Implementation plan approved

**Solution Successful When:**
- [ ] Error no longer occurs
- [ ] Performance metrics restored
- [ ] No regression in other areas
- [ ] Monitoring confirms stability
```

---

### Phase 2: Evidence Gathering (2-4 hours)

#### 2.1 Immediate Data Collection
**Priority 1: Preserve Evidence**
```bash
# System state capture
kubectl get pods -o wide > system_state.log
docker logs container_name > error_logs.log
journalctl -u service_name --since "1 hour ago" > service_logs.log

# Performance metrics
top -b -n 1 > system_resources.log
free -h > memory_usage.log
df -h > disk_usage.log
```

**Priority 2: Error Context**
- Full stack traces with line numbers
- Request/response payloads (sanitized)
- Database query logs
- Network traffic captures (if applicable)
- Configuration snapshots

#### 2.2 Environmental Analysis
```markdown
**System Information:**
- [ ] OS version and patches
- [ ] Application version and build
- [ ] Database version and configuration
- [ ] Network topology and dependencies
- [ ] Recent deployments or changes

**Dependency Matrix:**
- [ ] External service versions
- [ ] Library and framework versions
- [ ] Infrastructure components
- [ ] Third-party integrations
```

#### 2.3 Historical Context
- When did the issue first appear?
- What changed around that time?
- Has this happened before?
- Are there patterns or triggers?

---

### Phase 3: Minimal Reproduction (1-2 hours)

#### 3.1 Isolation Strategy
**Start Simple, Add Complexity Gradually:**

```python
# Example: Database connection issue
# Step 1: Basic connectivity
def test_basic_connection():
    try:
        conn = database.connect()
        return "SUCCESS: Basic connection works"
    except Exception as e:
        return f"FAIL: {e}"

# Step 2: Simple query
def test_simple_query():
    try:
        result = conn.query("SELECT 1")
        return f"SUCCESS: Simple query returned {result}"
    except Exception as e:
        return f"FAIL: {e}"

# Step 3: Add complexity incrementally
def test_complex_query():
    # Only test if simple cases pass
    pass
```

#### 3.2 Reproduction Checklist
```markdown
**Minimal Reproduction Requirements:**
- [ ] Smallest possible dataset
- [ ] Minimal code to trigger issue
- [ ] Isolated environment (no external dependencies)
- [ ] Consistent reproduction (>80% success rate)
- [ ] Clear pass/fail criteria

**Documentation:**
- [ ] Exact steps to reproduce
- [ ] Expected vs actual behavior
- [ ] Environment specifications
- [ ] Sample data and configurations
```

#### 3.3 Boundary Testing
Test edge cases to understand failure boundaries:
- What works vs. what doesn't?
- At what point does the system fail?
- Are there size, timing, or data-related thresholds?

---

### Phase 4: Hypothesis Formation (30 minutes)

#### 4.1 Hypothesis Framework
Use the **MECE Principle** (Mutually Exclusive, Collectively Exhaustive):

```markdown
**Primary Hypotheses (rank by likelihood):**

1. **Configuration Issue (40% probability)**
   - Evidence: Recent config changes
   - Test: Revert to known good configuration
   - Timeline: 30 minutes

2. **Resource Exhaustion (30% probability)**
   - Evidence: Memory/CPU metrics
   - Test: Scale up resources
   - Timeline: 1 hour

3. **Code Bug (20% probability)**
   - Evidence: Stack trace analysis
   - Test: Code review and unit tests
   - Timeline: 4 hours

4. **External Dependency (10% probability)**
   - Evidence: Network timeouts
   - Test: Dependency health checks
   - Timeline: 2 hours
```

#### 4.2 Hypothesis Validation Plan
For each hypothesis, define:
- **Specific test to validate/invalidate**
- **Expected results if hypothesis is correct**
- **Time required for testing**
- **Risk level of testing**

---

### Phase 5: Systematic Testing (2-6 hours)

#### 5.1 Testing Methodology
**Test hypotheses in order of:**
1. **Likelihood** (most probable first)
2. **Speed** (quick tests before slow ones)
3. **Risk** (safe tests before risky ones)

#### 5.2 Testing Documentation
```markdown
**Test Case Template:**

**Hypothesis:** [Brief description]
**Test Method:** [Specific steps]
**Expected Result:** [If hypothesis is correct]
**Actual Result:** [What actually happened]
**Conclusion:** [Hypothesis confirmed/rejected]
**Evidence:** [Logs, screenshots, metrics]
**Next Steps:** [Based on results]
```

#### 5.3 Validation Criteria
Each test must have:
- Clear pass/fail criteria
- Measurable outcomes
- Rollback plan if test causes issues
- Documentation of results

---

### Phase 6: Root Cause Analysis (1-2 hours)

#### 6.1 Root Cause Identification
Use the **5 Whys Technique:**

```markdown
**Problem:** Database queries failing with timeout

**Why 1:** Why are queries timing out?
**Answer:** Connection pool exhausted

**Why 2:** Why is the connection pool exhausted?
**Answer:** Connections not being released

**Why 3:** Why aren't connections being released?
**Answer:** Exception handling doesn't close connections

**Why 4:** Why doesn't exception handling close connections?
**Answer:** Try-catch blocks missing finally clauses

**Why 5:** Why are finally clauses missing?
**Answer:** Code review process doesn't check resource cleanup

**Root Cause:** Inadequate code review process for resource management
```

#### 6.2 Contributing Factors
Identify all factors that contributed to the issue:
- **Primary cause:** Direct technical failure
- **Secondary causes:** Process, configuration, or environmental factors
- **Systemic issues:** Organizational or architectural problems

#### 6.3 Impact Assessment
```markdown
**Technical Impact:**
- [ ] Data integrity affected
- [ ] Performance degradation
- [ ] Security implications
- [ ] Scalability concerns

**Business Impact:**
- [ ] User experience degraded
- [ ] Revenue impact
- [ ] Compliance issues
- [ ] Reputation damage
```

---

### Phase 7: Solution Design (1-3 hours)

#### 7.1 Solution Options Analysis
```markdown
**Solution Comparison Matrix:**

| Option | Complexity | Risk | Time | Cost | Maintainability |
|--------|------------|------|------|------|-----------------|
| Quick Fix | Low | Medium | 1h | Low | Poor |
| Proper Fix | Medium | Low | 1d | Medium | Good |
| Redesign | High | Low | 1w | High | Excellent |

**Recommendation:** [Based on current priorities and constraints]
```

#### 7.2 Solution Requirements
```markdown
**Must Have:**
- [ ] Resolves root cause
- [ ] No regression risk
- [ ] Testable and verifiable
- [ ] Rollback capability

**Should Have:**
- [ ] Prevents similar issues
- [ ] Improves monitoring
- [ ] Documentation updated
- [ ] Team knowledge transfer

**Could Have:**
- [ ] Performance improvements
- [ ] Code quality enhancements
- [ ] Process improvements
- [ ] Automation opportunities
```

#### 7.3 Implementation Plan
- **Phase 1:** Immediate fix (stop the bleeding)
- **Phase 2:** Proper solution (address root cause)
- **Phase 3:** Prevention measures (avoid recurrence)

---

### Phase 8: Validation & Testing (2-4 hours)

#### 8.1 Test Strategy
```markdown
**Testing Levels:**

1. **Unit Tests**
   - [ ] New code functionality
   - [ ] Edge cases and error conditions
   - [ ] Performance characteristics

2. **Integration Tests**
   - [ ] Component interactions
   - [ ] Data flow validation
   - [ ] API contract compliance

3. **System Tests**
   - [ ] End-to-end workflows
   - [ ] Load and stress testing
   - [ ] Failure scenario testing

4. **Acceptance Tests**
   - [ ] Business requirement validation
   - [ ] User experience verification
   - [ ] Performance benchmarks
```

#### 8.2 Validation Checklist
```markdown
**Pre-Deployment:**
- [ ] Code review completed
- [ ] All tests passing
- [ ] Performance benchmarks met
- [ ] Security review completed
- [ ] Documentation updated

**Post-Deployment:**
- [ ] Monitoring confirms fix
- [ ] No new errors introduced
- [ ] Performance metrics stable
- [ ] User feedback positive
```

---

### Phase 9: Documentation & Knowledge Transfer (1 hour)

#### 9.1 Investigation Report
```markdown
**Executive Summary:**
- Problem description
- Root cause identified
- Solution implemented
- Business impact resolved

**Technical Details:**
- Detailed timeline
- Evidence collected
- Hypotheses tested
- Solution rationale

**Lessons Learned:**
- What went well
- What could be improved
- Process gaps identified
- Recommendations for future
```

#### 9.2 Knowledge Sharing
- **Team presentation:** Key findings and lessons
- **Documentation updates:** Runbooks, troubleshooting guides
- **Process improvements:** Based on investigation experience
- **Monitoring enhancements:** To catch similar issues earlier

---

## Investigation Quality Gates

### Gate 1: Problem Definition Complete
- [ ] Clear problem statement
- [ ] Impact assessment documented
- [ ] Success criteria defined
- [ ] Timeline established

### Gate 2: Evidence Sufficient
- [ ] Reproduction case created
- [ ] System state captured
- [ ] Historical context analyzed
- [ ] Dependencies mapped

### Gate 3: Root Cause Validated
- [ ] Hypothesis testing completed
- [ ] Root cause identified with evidence
- [ ] Contributing factors documented
- [ ] Impact fully assessed

### Gate 4: Solution Validated
- [ ] Solution addresses root cause
- [ ] Testing completed successfully
- [ ] Risk assessment approved
- [ ] Rollback plan prepared

### Gate 5: Implementation Complete
- [ ] Solution deployed successfully
- [ ] Monitoring confirms resolution
- [ ] Documentation updated
- [ ] Knowledge transferred

---

## Common Investigation Anti-Patterns

### ❌ **Premature Solution Jumping**
**Problem:** Implementing solutions before understanding the problem
**Prevention:** Complete evidence gathering before solution design

### ❌ **Confirmation Bias**
**Problem:** Only looking for evidence that supports initial hypothesis
**Prevention:** Actively seek disconfirming evidence

### ❌ **Over-Engineering**
**Problem:** Complex solutions for simple problems
**Prevention:** Always test simplest solution first

### ❌ **Insufficient Testing**
**Problem:** Deploying fixes without proper validation
**Prevention:** Comprehensive testing at multiple levels

### ❌ **Poor Documentation**
**Problem:** Knowledge lost when investigation ends
**Prevention:** Document throughout process, not just at end

---

## Investigation Tools & Templates

### Essential Tools
```bash
# Log analysis
grep -r "ERROR" /var/log/
journalctl -f -u service_name
tail -f application.log | grep -i error

# System monitoring
htop
iotop
netstat -tulpn
ss -tulpn

# Database analysis
EXPLAIN ANALYZE SELECT ...
SHOW PROCESSLIST;
SELECT * FROM pg_stat_activity;

# Network debugging
tcpdump -i any port 80
wireshark
curl -v http://endpoint
```

### Document Templates
- **Investigation Report Template**
- **Root Cause Analysis Template**
- **Solution Design Template**
- **Post-Mortem Template**
- **Runbook Template**

---

## Success Metrics

### Investigation Quality
- **Time to root cause identification**
- **Accuracy of initial hypothesis**
- **Solution effectiveness**
- **Recurrence rate**

### Process Efficiency
- **Investigation duration**
- **Resource utilization**
- **Knowledge transfer effectiveness**
- **Process improvement adoption**

### Business Impact
- **Mean time to resolution (MTTR)**
- **Customer satisfaction**
- **Revenue impact minimization**
- **Reputation protection**

---

## Conclusion

Effective technical investigation requires systematic methodology, thorough documentation, and disciplined execution. This framework provides the structure needed to conduct high-quality investigations that not only solve immediate problems but also improve overall system reliability and team capabilities.

**Remember:** The goal is not just to fix the current issue, but to understand it deeply enough to prevent similar problems in the future.

---

## Appendix: Investigation Checklist

### Quick Reference Checklist
```markdown
**Phase 1: Problem Definition (30 min)**
- [ ] Severity and impact assessed
- [ ] Problem statement documented
- [ ] Success criteria defined

**Phase 2: Evidence Gathering (2-4 hours)**
- [ ] System state captured
- [ ] Error logs collected
- [ ] Environmental analysis complete
- [ ] Historical context reviewed

**Phase 3: Minimal Reproduction (1-2 hours)**
- [ ] Isolation strategy defined
- [ ] Minimal reproduction case created
- [ ] Boundary conditions tested

**Phase 4: Hypothesis Formation (30 min)**
- [ ] Multiple hypotheses generated
- [ ] Hypotheses ranked by likelihood
- [ ] Validation plan created

**Phase 5: Systematic Testing (2-6 hours)**
- [ ] Hypotheses tested systematically
- [ ] Results documented thoroughly
- [ ] Conclusions validated

**Phase 6: Root Cause Analysis (1-2 hours)**
- [ ] Root cause identified
- [ ] Contributing factors documented
- [ ] Impact assessment complete

**Phase 7: Solution Design (1-3 hours)**
- [ ] Solution options analyzed
- [ ] Implementation plan created
- [ ] Risk assessment completed

**Phase 8: Validation & Testing (2-4 hours)**
- [ ] Solution tested thoroughly
- [ ] Regression testing completed
- [ ] Deployment plan validated

**Phase 9: Documentation (1 hour)**
- [ ] Investigation report completed
- [ ] Knowledge transferred
- [ ] Process improvements identified
```

**Total Estimated Time:** 8-24 hours (depending on complexity)
