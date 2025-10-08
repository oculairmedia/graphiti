# High Priority Issue #007: Missing Cleanup in Fullscreen Event Listener

## Severity
🟠 **High**

## Component
`GraphViz.tsx` - Lines 128-135 (Fullscreen event listener useEffect)

## Issue Description
The fullscreen event listener in GraphViz is not properly cleaned up when the component unmounts, leading to memory leaks and potential errors when the event fires after component destruction.

## Technical Details

### Current Implementation
```typescript
// GraphViz.tsx - Lines 128-135
useEffect(() => {
  const handleFullscreenChange = () => {
    setIsFullscreen(!!document.fullscreenElement);
  };

  document.addEventListener('fullscreenchange', handleFullscreenChange);
  return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
}, []);
```

### The Problem
While the code appears to have a cleanup function, there are several issues:

#### 1. Function Reference Mismatch (Potential)
```typescript
// If handleFullscreenChange is recreated elsewhere or has closure issues,
// the removeEventListener might not remove the correct listener
document.removeEventListener('fullscreenchange', handleFullscreenChange);
// ↑ This might not be the same function reference that was added
```

#### 2. State Update After Unmount
```typescript
const handleFullscreenChange = () => {
  setIsFullscreen(!!document.fullscreenElement); // ❌ Called after unmount
  // Warning: Cannot update a component that is being unmounted
};
```

#### 3. No Error Handling
```typescript
// If fullscreen API is not supported or restricted:
document.documentElement.requestFullscreen(); // ❌ May throw error
document.exitFullscreen(); // ❌ May throw error
```

## Root Cause Analysis

### 1. Timing Issues
The cleanup function runs during component unmount, but if the fullscreen state changes after cleanup but before the browser finishes cleanup, the event can still fire.

### 2. Browser API Edge Cases
Different browsers have different fullscreen API implementations:
- `fullscreenchange` (standard)
- `webkitfullscreenchange` (WebKit)
- `mozfullscreenchange` (Firefox)
- `MSFullscreenChange` (IE/Edge)

### 3. Component Lifecycle Race Conditions
```typescript
// Timeline of the problem:
// T1: User triggers fullscreen
// T2: Component starts unmounting
// T3: Cleanup function runs, removes listener
// T4: Browser fullscreen change completes
// T5: Event fires on removed listener (no cleanup)
// T6: If listener somehow still exists, setState on unmounted component
```

## Impact Assessment

### Memory Leaks
- **Event Listeners**: Orphaned event listeners remain attached to document
- **Closure References**: Event handlers hold references to unmounted component
- **Browser Resources**: Fullscreen API maintains unnecessary connections

### Runtime Errors
```javascript
Warning: Cannot call setState on an unmounted component
// → setIsFullscreen called after component unmount

Warning: Cannot update a component that is being unmounted
// → State update attempted during unmount process
```

### Browser Compatibility Issues
```javascript
TypeError: document.documentElement.requestFullscreen is not a function
// → Unsupported in older browsers

SecurityError: Fullscreen request denied
// → Browser security restrictions
```

## Reproduction Steps
1. Enter fullscreen mode from GraphViz component
2. Navigate away from the page while in fullscreen
3. Exit fullscreen from browser controls (F11 or ESC)
4. Check console for memory leak warnings or errors

## Proposed Solutions

### Solution 1: Mounted State Check
```typescript
const mountedRef = useRef(true);

useEffect(() => {
  const handleFullscreenChange = () => {
    if (mountedRef.current) {
      setIsFullscreen(!!document.fullscreenElement);
    }
  };

  document.addEventListener('fullscreenchange', handleFullscreenChange);
  
  return () => {
    mountedRef.current = false;
    document.removeEventListener('fullscreenchange', handleFullscreenChange);
  };
}, []);

// Also cleanup on unmount
useEffect(() => {
  return () => {
    mountedRef.current = false;
  };
}, []);
```

### Solution 2: Ref-Based Handler with Explicit Cleanup
```typescript
const handleFullscreenChangeRef = useRef<(() => void) | null>(null);

useEffect(() => {
  const handleFullscreenChange = () => {
    setIsFullscreen(!!document.fullscreenElement);
  };
  
  handleFullscreenChangeRef.current = handleFullscreenChange;
  document.addEventListener('fullscreenchange', handleFullscreenChange);
  
  return () => {
    if (handleFullscreenChangeRef.current) {
      document.removeEventListener('fullscreenchange', handleFullscreenChangeRef.current);
      handleFullscreenChangeRef.current = null;
    }
  };
}, []);
```

### Solution 3: Comprehensive Fullscreen Manager
```typescript
const useFullscreenManager = () => {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const mountedRef = useRef(true);
  
  useEffect(() => {
    const handleFullscreenChange = () => {
      if (!mountedRef.current) return;
      setIsFullscreen(!!document.fullscreenElement);
    };

    // Add listeners for all browser variants
    const events = [
      'fullscreenchange',
      'webkitfullscreenchange', 
      'mozfullscreenchange',
      'MSFullscreenChange'
    ];
    
    events.forEach(event => {
      document.addEventListener(event, handleFullscreenChange);
    });
    
    return () => {
      mountedRef.current = false;
      events.forEach(event => {
        document.removeEventListener(event, handleFullscreenChange);
      });
    };
  }, []);
  
  const toggleFullscreen = useCallback(async () => {
    if (!mountedRef.current) return;
    
    try {
      if (!document.fullscreenElement) {
        await document.documentElement.requestFullscreen();
      } else {
        await document.exitFullscreen();
      }
    } catch (error) {
      console.warn('Fullscreen operation failed:', error);
    }
  }, []);
  
  return { isFullscreen, toggleFullscreen };
};
```

### Solution 4: AbortController Pattern
```typescript
useEffect(() => {
  const abortController = new AbortController();
  
  const handleFullscreenChange = () => {
    if (!abortController.signal.aborted) {
      setIsFullscreen(!!document.fullscreenElement);
    }
  };

  document.addEventListener('fullscreenchange', handleFullscreenChange, {
    signal: abortController.signal
  });
  
  return () => {
    abortController.abort();
  };
}, []);
```

## Recommended Solution
**Solution 3 (Comprehensive Fullscreen Manager)** provides the most robust handling with cross-browser support and proper error handling.

### Benefits
- **Cross-browser Compatibility**: Handles all fullscreen event variants
- **Memory Leak Prevention**: Proper cleanup with mounted state checks
- **Error Handling**: Graceful handling of API failures
- **Reusable**: Can be extracted as a custom hook

## Additional Improvements

### Error Handling for Fullscreen API
```typescript
const toggleFullscreen = async () => {
  try {
    if (!document.fullscreenElement) {
      // Check if fullscreen is supported
      if (!document.documentElement.requestFullscreen) {
        console.warn('Fullscreen API not supported');
        return;
      }
      await document.documentElement.requestFullscreen();
    } else {
      await document.exitFullscreen();
    }
  } catch (error) {
    if (error.name === 'NotAllowedError') {
      console.warn('Fullscreen request denied by user or browser policy');
    } else if (error.name === 'TypeError') {
      console.warn('Fullscreen API not supported in this browser');
    } else {
      console.error('Fullscreen operation failed:', error);
    }
  }
};
```

### Feature Detection
```typescript
const supportsFullscreen = () => {
  return !!(
    document.fullscreenEnabled ||
    document.webkitFullscreenEnabled ||
    document.mozFullScreenEnabled ||
    document.msFullscreenEnabled
  );
};
```

## Testing Strategy
1. **Component Lifecycle Testing**: Mount/unmount component during fullscreen
2. **Browser Compatibility**: Test across different browsers
3. **Memory Leak Detection**: Use browser dev tools to check for orphaned listeners
4. **Error Simulation**: Test with restricted fullscreen permissions

## Priority Justification
This is High Priority because:
- **Memory Leaks**: Can accumulate over app usage, degrading performance
- **User Experience**: Broken fullscreen functionality affects usability
- **Browser Compatibility**: Issues vary across different browsers
- **Error Prevention**: Prevents console warnings and potential crashes

## Related Issues
- [Issue #001: Memory Leak in GraphCanvas](../critical/001-memory-leak-graphcanvas.md)
- [Issue #021: Incomplete Error Handling](../low/021-incomplete-error-handling.md)

## Dependencies
- Browser Fullscreen API
- React cleanup patterns
- Cross-browser compatibility handling
- AbortController API (modern browsers)

## Estimated Fix Time
**1-2 hours** for implementing comprehensive fullscreen manager with proper cleanup and error handling