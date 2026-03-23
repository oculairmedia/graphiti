# GraphCanvasV2 Refactoring - Test Validation Plan

## Current Test Coverage

### Existing Test Files
1. **GraphCanvasV2.test.tsx** - Main component tests
   - Rendering tests
   - Node interactions (click, hover)
   - Selection management
   - Statistics updates
   - Imperative handle methods

2. **GraphCanvasV2Simple.test.tsx** - Simplified test suite
3. **GraphCanvasWrapper.test.tsx** - Wrapper component tests
4. **useGraphCanvasEvents.test.tsx** - Event handling hook tests

### Test Categories Covered
- ✅ Component rendering
- ✅ Node click/hover interactions
- ✅ Selection state management
- ✅ Statistics callbacks
- ✅ Imperative handle API
- ⚠️ WebSocket integration (mocked)
- ⚠️ Cosmograph integration (mocked)
- ❌ Performance characteristics
- ❌ Memory leak detection
- ❌ Effect coordination

## Pre-Refactor Baseline

### Step 1: Install Dependencies & Run Current Tests
```bash
cd /opt/stacks/graphiti/frontend
npm install
npm run test:run -- src/__tests__/components/GraphCanvasV2
```

### Step 2: Capture Test Baseline
- Record all passing tests
- Document any failing tests
- Capture test execution time
- Save coverage report

**Baseline Checklist:**
- [ ] All tests passing?
- [ ] Coverage % documented
- [ ] Execution time recorded
- [ ] Any warnings/errors noted

## Refactoring Test Strategy

### Phase 1: Add Missing Tests BEFORE Refactoring

#### 1.1 Imperative Handle Comprehensive Tests
**File**: `src/__tests__/hooks/useGraphCanvasImperativeHandle.test.tsx`

Test all imperative methods:
- [ ] clearSelection()
- [ ] selectNode()
- [ ] selectNodes()
- [ ] focusOnNodes()
- [ ] zoomIn() / zoomOut()
- [ ] fitView()
- [ ] setData()
- [ ] restart()
- [ ] getLiveStats()
- [ ] All selection tools (rect, polygon)
- [ ] addIncrementalData()
- [ ] updateNodes() / updateLinks()
- [ ] removeNodes() / removeLinks()

#### 1.2 Effect Coordination Tests
**File**: `src/__tests__/hooks/useGraphCanvasEffectCoordination.test.tsx`

Test effect synchronization:
- [ ] highlightedNodes → cosmograph selection sync
- [ ] selectedNodes → internal state sync
- [ ] statistics update triggers
- [ ] simulation config re-application
- [ ] context ready notification
- [ ] fitView initialization timing

#### 1.3 Integration Tests
**File**: `src/__tests__/components/GraphCanvasV2.integration.test.tsx`

Test full component lifecycle:
- [ ] Mount → data load → render → ready
- [ ] WebSocket delta updates
- [ ] Selection + camera coordination
- [ ] Config changes → re-render
- [ ] Unmount → cleanup

### Phase 2: Snapshot Tests for Regression Detection

#### 2.1 Component Structure Snapshot
```typescript
it('should match component structure snapshot', () => {
  const { container } = render(<GraphCanvasV2 {...props} />);
  expect(container.firstChild).toMatchSnapshot();
});
```

#### 2.2 Imperative Handle API Snapshot
```typescript
it('should expose expected imperative API', () => {
  const ref = React.createRef<GraphCanvasHandle>();
  render(<GraphCanvasV2 ref={ref} {...props} />);
  expect(Object.keys(ref.current)).toMatchSnapshot();
});
```

### Phase 3: Migration Validation Tests

For EACH refactoring phase, run:

#### 3.1 Functional Equivalence Tests
```bash
# Before refactor
npm run test:run -- GraphCanvasV2 > before.txt

# After refactor
npm run test:run -- GraphCanvasV2 > after.txt

# Compare
diff before.txt after.txt
```

**Acceptance criteria**: Zero test failures, zero new warnings

#### 3.2 Performance Regression Tests
```typescript
describe('Performance', () => {
  it('should render 1000 nodes within 2 seconds', async () => {
    const start = performance.now();
    render(<GraphCanvasV2 nodes={generate1000Nodes()} />);
    await waitFor(() => expect(screen.getByTestId('cosmograph')).toBeInTheDocument());
    const duration = performance.now() - start;
    expect(duration).toBeLessThan(2000);
  });
  
  it('should handle 100 incremental updates within 1 second', async () => {
    const ref = React.createRef<GraphCanvasHandle>();
    render(<GraphCanvasV2 ref={ref} />);
    
    const start = performance.now();
    for (let i = 0; i < 100; i++) {
      ref.current.addIncrementalData([generateNode()], []);
    }
    const duration = performance.now() - start;
    expect(duration).toBeLessThan(1000);
  });
});
```

#### 3.3 Memory Leak Detection Tests
```typescript
describe('Memory', () => {
  it('should cleanup on unmount', () => {
    const { unmount } = render(<GraphCanvasV2 {...props} />);
    
    // Get initial memory
    const before = (performance as any).memory?.usedJSHeapSize;
    
    // Mount/unmount 10 times
    for (let i = 0; i < 10; i++) {
      const { unmount } = render(<GraphCanvasV2 {...props} />);
      unmount();
    }
    
    // Force GC if available
    if (global.gc) global.gc();
    
    const after = (performance as any).memory?.usedJSHeapSize;
    
    // Memory should not grow significantly (allow 10% variance)
    expect(after).toBeLessThan(before * 1.1);
  });
});
```

## Migration Checklist

### Before Each Phase

- [ ] All existing tests passing
- [ ] Coverage baseline documented
- [ ] Performance baseline recorded
- [ ] Git commit with clean state

### During Each Phase

- [ ] Write new tests for extracted module FIRST
- [ ] Extract module
- [ ] Update imports in GraphCanvasV2
- [ ] Run full test suite
- [ ] Verify zero regressions

### After Each Phase

- [ ] All tests still passing
- [ ] Coverage maintained or improved
- [ ] Performance maintained or improved
- [ ] Git commit with descriptive message
- [ ] Update REFACTOR_PLAN.md progress

## Final Validation

### Acceptance Criteria

1. **Functional**
   - [ ] All original tests passing
   - [ ] All new tests passing
   - [ ] Zero console warnings
   - [ ] Zero console errors

2. **Performance**
   - [ ] Render time ≤ baseline
   - [ ] Update time ≤ baseline
   - [ ] Memory usage ≤ baseline

3. **Code Quality**
   - [ ] GraphCanvasV2.tsx < 150 lines
   - [ ] All extracted modules < 300 lines each
   - [ ] Test coverage ≥ 80%
   - [ ] No ESLint errors
   - [ ] No TypeScript errors

4. **Documentation**
   - [ ] REFACTOR_PLAN.md updated
   - [ ] All new modules have JSDoc comments
   - [ ] Migration guide written
   - [ ] Changelog updated

## Rollback Plan

If any phase fails validation:

1. **Immediate**: Revert to last passing commit
2. **Analyze**: Review test failures and performance issues
3. **Fix**: Address issues in isolated branch
4. **Re-test**: Run full validation suite
5. **Retry**: Attempt migration again

## Test Execution Commands

```bash
# Run all GraphCanvas tests
npm run test:run -- GraphCanvas

# Run specific test file
npm run test:run -- GraphCanvasV2.test.tsx

# Run with coverage
npm run test:coverage -- GraphCanvas

# Run in watch mode (during development)
npm run test -- GraphCanvas

# Run integration tests only
npm run test:run -- integration.test.tsx

# Run performance tests
npm run test:run -- performance.test.tsx
```

## Success Metrics

- ✅ 100% of original tests passing
- ✅ ≥20 new tests added
- ✅ Test coverage ≥ 80%
- ✅ Zero performance regressions
- ✅ Zero memory leaks detected
- ✅ GraphCanvasV2.tsx reduced to <150 lines
