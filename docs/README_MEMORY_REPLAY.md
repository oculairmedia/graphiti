# Memory Replay System Documentation

Complete documentation for the Graphiti Memory Replay System.

## 🚀 Quick Start

**Problem:** Candidate detection returns 0 results instead of 3,456 episodes.

**Solution:** Follow the checklist:

```bash
# 1. Use the checklist
cat docs/CANDIDATE_DETECTION_CHECKLIST.md

# 2. Or run these commands
docker-compose build --no-cache graph
docker-compose up -d --force-recreate graph
curl -X POST "http://localhost:8003/replay/trigger?dry_run=true" | jq
```

## 📚 Documentation Structure

### For Fixing the Current Issue

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **CANDIDATE_DETECTION_CHECKLIST.md** ⭐ | Step-by-step checklist | **Start here** - Fastest path to fix |
| **CANDIDATE_DETECTION_SUMMARY.md** | Quick summary with commands | Need overview before diving in |
| **FIXING_CANDIDATE_DETECTION.md** | Detailed troubleshooting guide | Checklist didn't work, need debugging |
| **LOCAL_BUILD_GUIDE.md** | Docker build reference | Build issues or want to understand build process |

### For Testing After Fix

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **MEMORY_REPLAY_REMAINING_WORK.md** | Complete testing guide | After candidate detection works |

### For Operations & Reference

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **11-memory-replay-operations.md** | Operational guide | Running in production, monitoring |
| **memory_replay_specification.md** | Design specification | Understanding architecture, making changes |

## 🎯 Recommended Reading Order

### If You Just Want to Fix It (10 minutes)

1. **CANDIDATE_DETECTION_CHECKLIST.md** - Follow the checklist
2. If it works → **MEMORY_REPLAY_REMAINING_WORK.md** - Test everything
3. If it doesn't work → **FIXING_CANDIDATE_DETECTION.md** - Debug

### If You Want to Understand First (30 minutes)

1. **CANDIDATE_DETECTION_SUMMARY.md** - Understand the problem
2. **FIXING_CANDIDATE_DETECTION.md** - Learn the solution
3. **CANDIDATE_DETECTION_CHECKLIST.md** - Execute the fix
4. **MEMORY_REPLAY_REMAINING_WORK.md** - Complete testing

### If You're Setting Up Production (2 hours)

1. **memory_replay_specification.md** - Understand the design
2. **FIXING_CANDIDATE_DETECTION.md** - Apply the fix
3. **MEMORY_REPLAY_REMAINING_WORK.md** - Complete all tests
4. **11-memory-replay-operations.md** - Set up monitoring

## 📖 Document Summaries

### CANDIDATE_DETECTION_CHECKLIST.md

**Type:** Checklist
**Length:** ~300 lines
**Time:** 10 minutes

A systematic checklist with 10 steps to fix candidate detection:
- Pre-flight checks
- Code verification
- Docker configuration
- Build and deploy
- Testing and verification
- Troubleshooting for each step

**Use this if:** You want the fastest path to a working system.

### CANDIDATE_DETECTION_SUMMARY.md

**Type:** Summary
**Length:** ~250 lines
**Time:** 5 minutes read

Quick overview with:
- TL;DR commands
- Problem explanation
- What's been done
- What you need to do
- Quick reference

**Use this if:** You want to understand the issue before fixing it.

### FIXING_CANDIDATE_DETECTION.md

**Type:** Detailed Guide
**Length:** ~350 lines
**Time:** 15 minutes read, 10 minutes execute

Complete guide with:
- Root cause analysis
- Code fix explanation
- Step-by-step implementation
- 5-step debugging guide
- Alternative solutions
- Verification checklist

**Use this if:** The checklist didn't work or you want deep understanding.

### LOCAL_BUILD_GUIDE.md

**Type:** Reference
**Length:** ~300 lines
**Time:** Reference as needed

Docker build reference with:
- Build commands and options
- Common workflows
- Troubleshooting build issues
- Switching between local/remote images
- Best practices

**Use this if:** You have Docker build issues or want to understand the build process.

### MEMORY_REPLAY_REMAINING_WORK.md

**Type:** Testing Guide
**Length:** ~400 lines
**Time:** 2 hours to complete all tests

Complete testing guide with:
- 5 prioritized tasks
- Manual end-to-end testing scenarios
- Database verification
- Performance testing
- Success criteria

**Use this if:** Candidate detection is working and you want to verify everything else.

### 11-memory-replay-operations.md

**Type:** Operations Guide
**Length:** ~200 lines
**Time:** Reference as needed

Operational guide with:
- Monitoring endpoints
- Metrics interpretation
- Manual trigger procedures
- Production best practices

**Use this if:** You're running the system in production.

### memory_replay_specification.md

**Type:** Design Specification
**Length:** ~1000 lines
**Time:** 1 hour read

Complete design specification with:
- Architecture overview
- Component design
- API specifications
- Implementation examples
- Safety mechanisms

**Use this if:** You need to understand the architecture or make changes.

## 🔧 Common Scenarios

### Scenario 1: "I just want it to work"

1. Open `CANDIDATE_DETECTION_CHECKLIST.md`
2. Follow steps 1-10
3. Done in 10 minutes

### Scenario 2: "The checklist didn't work"

1. Open `FIXING_CANDIDATE_DETECTION.md`
2. Go to "Debugging If Still Broken" section
3. Follow Debug Steps 1-5
4. Check "Alternative Solutions" if needed

### Scenario 3: "Docker build is failing"

1. Open `LOCAL_BUILD_GUIDE.md`
2. Go to "Troubleshooting" section
3. Find your specific error
4. Follow the solution

### Scenario 4: "It works, now what?"

1. Open `MEMORY_REPLAY_REMAINING_WORK.md`
2. Follow "Remaining Tasks" section
3. Complete all 5 tasks
4. Check off items in "Testing Checklist"

### Scenario 5: "How do I monitor it in production?"

1. Open `11-memory-replay-operations.md`
2. Set up monitoring endpoints
3. Configure alerts
4. Follow operational best practices

## 🐛 Troubleshooting Quick Reference

### Issue: Returns 0 candidates

**Documents:**
1. `CANDIDATE_DETECTION_CHECKLIST.md` - Step 9
2. `FIXING_CANDIDATE_DETECTION.md` - "Debugging If Still Broken"

**Quick fix:**
```bash
docker-compose build --no-cache graph
docker-compose up -d --force-recreate graph
```

### Issue: Build fails

**Documents:**
1. `LOCAL_BUILD_GUIDE.md` - "Troubleshooting" section
2. `FIXING_CANDIDATE_DETECTION.md` - Step 2

**Quick fix:**
```bash
# Check you're in repo root
pwd  # Should be u:\graphiti

# Verify Dockerfile exists
ls -la Dockerfile

# Try verbose build
docker build --no-cache --progress=plain -t graphiti-api-local:latest -f Dockerfile .
```

### Issue: Service won't start

**Documents:**
1. `CANDIDATE_DETECTION_CHECKLIST.md` - Step 7
2. `LOCAL_BUILD_GUIDE.md` - "Troubleshooting"

**Quick fix:**
```bash
# Check logs
docker-compose logs graph

# Force recreate
docker-compose up -d --force-recreate graph
```

### Issue: Changes not reflected

**Documents:**
1. `LOCAL_BUILD_GUIDE.md` - "Issue: Changes not reflected after rebuild"

**Quick fix:**
```bash
# Force clean build
docker-compose build --no-cache graph
docker-compose up -d --force-recreate graph
```

## 📊 Documentation Metrics

| Document | Lines | Read Time | Execute Time | Difficulty |
|----------|-------|-----------|--------------|------------|
| CANDIDATE_DETECTION_CHECKLIST.md | 300 | 5 min | 10 min | Easy |
| CANDIDATE_DETECTION_SUMMARY.md | 250 | 5 min | 10 min | Easy |
| FIXING_CANDIDATE_DETECTION.md | 350 | 15 min | 10 min | Medium |
| LOCAL_BUILD_GUIDE.md | 300 | 10 min | N/A | Medium |
| MEMORY_REPLAY_REMAINING_WORK.md | 400 | 20 min | 2 hours | Medium |
| 11-memory-replay-operations.md | 200 | 15 min | N/A | Easy |
| memory_replay_specification.md | 1000 | 60 min | N/A | Hard |

## 🎓 Learning Path

### Beginner (Just Fix It)

1. CANDIDATE_DETECTION_CHECKLIST.md
2. CANDIDATE_DETECTION_SUMMARY.md

**Time:** 15 minutes
**Outcome:** Working system

### Intermediate (Understand & Fix)

1. CANDIDATE_DETECTION_SUMMARY.md
2. FIXING_CANDIDATE_DETECTION.md
3. LOCAL_BUILD_GUIDE.md
4. MEMORY_REPLAY_REMAINING_WORK.md

**Time:** 3 hours
**Outcome:** Working system + full understanding + complete testing

### Advanced (Production Ready)

1. memory_replay_specification.md
2. FIXING_CANDIDATE_DETECTION.md
3. MEMORY_REPLAY_REMAINING_WORK.md
4. 11-memory-replay-operations.md
5. LOCAL_BUILD_GUIDE.md

**Time:** 5 hours
**Outcome:** Production-ready deployment with monitoring

## 🔗 External References

- **FalkorDB Docs:** https://docs.falkordb.com/
- **Docker Compose Docs:** https://docs.docker.com/compose/
- **Graphiti Main README:** `../README.md`

## 📝 Document Maintenance

### When to Update

- **CANDIDATE_DETECTION_*.md** - When fix changes or new issues discovered
- **LOCAL_BUILD_GUIDE.md** - When Docker setup changes
- **MEMORY_REPLAY_REMAINING_WORK.md** - When new tests added
- **11-memory-replay-operations.md** - When monitoring changes
- **memory_replay_specification.md** - When architecture changes

### Version History

- **2025-01-30** - Initial documentation created for candidate detection fix
- **2025-01-30** - Added comprehensive troubleshooting guides
- **2025-01-30** - Created quick reference checklist

## 🆘 Getting Help

If you're stuck after reading the documentation:

1. **Check logs first:**
   ```bash
   docker-compose logs graph | grep -i error
   docker-compose logs graph | grep "ReplayCandidateDetector"
   ```

2. **Verify environment:**
   ```bash
   docker exec $(docker-compose ps -q graph) env | grep REPLAY
   ```

3. **Test database directly:**
   ```bash
   docker exec -it $(docker ps | grep falkor | awk '{print $1}') redis-cli -p 6379
   GRAPH.QUERY default_db "MATCH (ep:Episodic) RETURN count(ep)"
   ```

4. **Review relevant documentation:**
   - Build issues → `LOCAL_BUILD_GUIDE.md`
   - Candidate detection → `FIXING_CANDIDATE_DETECTION.md`
   - Testing → `MEMORY_REPLAY_REMAINING_WORK.md`

## ✅ Success Checklist

You're done when:

- [ ] Candidate detection returns `requested > 0`
- [ ] Manual trigger schedules tasks
- [ ] Workers process tasks successfully
- [ ] Database metadata is updated
- [ ] All tests pass
- [ ] Monitoring is set up
- [ ] Documentation is understood

See `MEMORY_REPLAY_REMAINING_WORK.md` for complete success criteria.

