# Low Priority Issue #025: Inconsistent Focus Management

## Severity
🟢 **Low**

## Component
Application-wide - Inconsistent focus handling across modals, panels, and interactive elements

## Issue Description
The application lacks consistent focus management patterns, making keyboard navigation unpredictable and creating accessibility issues. Focus may get lost when opening/closing modals, trapped incorrectly in components, or not properly indicated visually, leading to poor user experience for keyboard and assistive technology users.

## Technical Details

### Current Focus Management Issues

#### 1. No Focus Trap in Modals
```typescript
// NodeDetailsPanel.tsx - Modal without focus trap
export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose 
}) => {
  // ❌ No focus trap implementation
  // ❌ Focus can escape modal to background elements
  // ❌ Tab navigation continues to hidden elements
  // ❌ No focus restoration when modal closes
  
  return (
    <Card className="glass-panel w-96 max-h-[80vh] overflow-hidden flex flex-col">
      <CardHeader>
        <CardTitle>{data.name}</CardTitle>
        <Button variant="ghost" size="sm" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>
      {/* Modal content without focus management */}
    </Card>
  );
};
```

#### 2. Missing Focus Restoration
```typescript
// When modals open/close, focus not managed
const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);

// Opening modal
const handleNodeClick = (node: GraphNode) => {
  setSelectedNode(node);  // ❌ No focus management when opening
};

// Closing modal  
const handleCloseModal = () => {
  setSelectedNode(null);  // ❌ No focus restoration to triggering element
};
```

#### 3. Invisible Focus Indicators
```css
/* Missing or inadequate focus indicators */
.button:focus {
  /* ❌ Default browser outline may be removed */
  outline: none;
}

/* No custom focus indicators for complex components */
.graph-canvas:focus {
  /* ❌ No visible focus indication for graph canvas */
}

.panel:focus-within {
  /* ❌ No focus indication for active panels */
}
```

#### 4. Inconsistent Tab Order
```typescript
// GraphViz.tsx - No explicit tab order management
<div className="h-screen w-full bg-background">
  {/* ❌ Tab order depends on DOM order, may not be logical */}
  <GraphSearch />
  <ControlPanel />
  <GraphCanvas />
  {selectedNode && <NodeDetailsPanel />}
  
  {/* ❌ No skip links for keyboard users */}
  {/* ❌ No tabindex management for complex interactions */}
</div>
```

#### 5. Focus Lost During Dynamic Updates
```typescript
// GraphSearch.tsx - Focus may be lost during search
const [searchResults, setSearchResults] = useState<GraphNode[]>([]);

const handleSearch = (results: GraphNode[]) => {
  setSearchResults(results);  // ❌ DOM updates may steal focus
  // ❌ Search input focus may be lost
  // ❌ No announcement of results to screen readers
};
```

### Missing Focus Management Patterns

#### 1. No Focus Trapping Utility
```typescript
// Missing utility for focus trap implementation
// No reusable focus management hooks
// No standardized modal focus patterns
```

#### 2. No Skip Navigation
```typescript
// Missing skip links for keyboard users
// No way to quickly navigate to main content
// No shortcuts to jump between major sections
```

#### 3. No Focus History
```typescript
// No tracking of focus history for restoration
// No memory of where focus should return
// No handling of deleted/unmounted focus targets
```

#### 4. No Programmatic Focus Control
```typescript
// No APIs for:
// - Setting initial focus on page load
// - Moving focus to important announcements
// - Focusing first interactive element in sections
// - Managing focus during route changes
```

## Root Cause Analysis

### 1. Accessibility Afterthought
Focus management not considered during initial component development.

### 2. Complex UI Patterns
Graph visualization and dynamic panels make focus management more challenging.

### 3. No Focus Management Strategy
No systematic approach to handling focus across the application.

### 4. Limited Testing
Focus behavior not tested with keyboard-only navigation or assistive technology.

## Impact Assessment

### Accessibility Issues
- **Keyboard Users**: Cannot navigate efficiently or predictably
- **Screen Reader Users**: Focus announcements inconsistent or missing
- **Motor Impairment Users**: Tab navigation inefficient without proper focus management
- **WCAG Compliance**: Fails focus management requirements

### User Experience Problems
- **Confusion**: Focus disappears or jumps unexpectedly
- **Inefficiency**: Cannot quickly navigate to desired elements
- **Frustration**: Must use mouse even when preferring keyboard
- **Lost Context**: Focus location unclear in complex interfaces

### Development Complexity
- **Bug Reports**: Focus-related issues are hard to reproduce and fix
- **Testing Overhead**: Manual testing required for each focus interaction
- **Maintenance**: Focus bugs accumulate as components change

## Scenarios Where Focus Issues Occur

### Scenario 1: Modal Dialog Interaction
```typescript
// User opens node details modal
// 1. Clicks on graph node (focus on graph canvas)
// 2. Modal opens (focus should move to modal)
// 3. User tabs through modal (focus may escape to background)
// 4. User presses Escape or clicks close (focus should return to graph canvas)
// 5. Currently: focus is lost or goes to wrong element
```

### Scenario 2: Search Workflow
```typescript
// User searches for nodes
// 1. Presses Ctrl+F to focus search box (if shortcut exists)
// 2. Types search query (search results update dynamically)
// 3. Presses Enter to select results (focus should move to graph or results)
// 4. Wants to clear search (focus should return to search box)
// 5. Currently: focus behavior unpredictable
```

### Scenario 3: Panel Management
```typescript
// User opens filter panel
// 1. Clicks filter button (focus on button)
// 2. Panel opens (focus should move to first input in panel)
// 3. User configures filters (tab navigation within panel)
// 4. User clicks outside panel to close (focus should return to filter button)
// 5. Currently: focus management inconsistent
```

## Proposed Solutions

### Solution 1: Focus Management Hook
```typescript
// src/hooks/useFocusManagement.ts
import { useRef, useEffect, useCallback } from 'react';

interface FocusOptions {
  restoreOnUnmount?: boolean;
  trapFocus?: boolean;
  initialFocus?: 'first' | 'last' | string;
  skipLinks?: boolean;
}

export const useFocusManagement = (
  containerRef: React.RefObject<HTMLElement>,
  isActive: boolean,
  options: FocusOptions = {}
) => {
  const previousFocusRef = useRef<HTMLElement | null>(null);
  const {
    restoreOnUnmount = true,
    trapFocus = false,
    initialFocus = 'first',
    skipLinks = false
  } = options;
  
  // Store previous focus when component becomes active
  useEffect(() => {
    if (isActive) {
      previousFocusRef.current = document.activeElement as HTMLElement;
      
      // Set initial focus
      const container = containerRef.current;
      if (container) {
        setTimeout(() => {
          setInitialFocus(container, initialFocus);
        }, 0);
      }
    }
  }, [isActive, initialFocus]);
  
  // Restore focus when component becomes inactive
  useEffect(() => {
    return () => {
      if (restoreOnUnmount && previousFocusRef.current) {
        // Ensure element still exists and is focusable
        if (document.contains(previousFocusRef.current)) {
          previousFocusRef.current.focus();
        }
      }
    };
  }, [restoreOnUnmount]);
  
  // Focus trap implementation
  useEffect(() => {
    if (!trapFocus || !isActive) return;
    
    const container = containerRef.current;
    if (!container) return;
    
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      
      const focusableElements = getFocusableElements(container);
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      
      if (event.shiftKey) {
        // Shift + Tab
        if (document.activeElement === firstElement) {
          event.preventDefault();
          lastElement?.focus();
        }
      } else {
        // Tab
        if (document.activeElement === lastElement) {
          event.preventDefault();
          firstElement?.focus();
        }
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [trapFocus, isActive]);
  
  const moveFocusTo = useCallback((selector: string) => {
    const container = containerRef.current;
    if (!container) return false;
    
    const element = container.querySelector(selector) as HTMLElement;
    if (element && isFocusable(element)) {
      element.focus();
      return true;
    }
    return false;
  }, []);
  
  const moveFocusToFirst = useCallback(() => {
    const container = containerRef.current;
    if (!container) return false;
    
    const focusableElements = getFocusableElements(container);
    if (focusableElements[0]) {
      focusableElements[0].focus();
      return true;
    }
    return false;
  }, []);
  
  return {
    moveFocusTo,
    moveFocusToFirst,
    previousFocus: previousFocusRef.current
  };
};

// Helper functions
const getFocusableElements = (container: HTMLElement): HTMLElement[] => {
  const selector = [
    'button',
    'input',
    'select',
    'textarea', 
    'a[href]',
    '[tabindex]:not([tabindex="-1"])',
    '[contenteditable]'
  ].join(',');
  
  return Array.from(container.querySelectorAll(selector))
    .filter(el => isFocusable(el as HTMLElement)) as HTMLElement[];
};

const isFocusable = (element: HTMLElement): boolean => {
  if (element.tabIndex < 0) return false;
  if (element.hasAttribute('disabled')) return false;
  if (element.getAttribute('aria-hidden') === 'true') return false;
  
  // Check if element is visible
  const style = window.getComputedStyle(element);
  if (style.display === 'none' || style.visibility === 'hidden') return false;
  
  return true;
};

const setInitialFocus = (container: HTMLElement, initialFocus: string) => {
  switch (initialFocus) {
    case 'first':
      const firstFocusable = getFocusableElements(container)[0];
      firstFocusable?.focus();
      break;
    case 'last':
      const focusableElements = getFocusableElements(container);
      focusableElements[focusableElements.length - 1]?.focus();
      break;
    default:
      const element = container.querySelector(initialFocus) as HTMLElement;
      if (element && isFocusable(element)) {
        element.focus();
      }
  }
};
```

### Solution 2: Enhanced Modal with Focus Management
```typescript
// NodeDetailsPanel.tsx - Add proper focus management
export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose 
}) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const { moveFocusToFirst } = useFocusManagement(modalRef, true, {
    trapFocus: true,
    restoreOnUnmount: true,
    initialFocus: 'first'
  });
  
  // Handle Escape key
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);
  
  // Announce modal opening to screen readers
  useEffect(() => {
    const announcement = `Node details panel opened for ${data.name}`;
    announceToScreenReader(announcement);
  }, [data.name]);
  
  return (
    <Card 
      ref={modalRef}
      className="glass-panel w-96 max-h-[80vh] overflow-hidden flex flex-col focus-within:ring-2 focus-within:ring-primary"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      aria-describedby="modal-description"
    >
      <CardHeader className="flex-shrink-0">
        <div className="flex items-start justify-between">
          <CardTitle 
            id="modal-title"
            className="text-lg leading-tight mb-2"
            tabIndex={-1}  // Programmatically focusable but not in tab order
          >
            {data.name}
          </CardTitle>
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={onClose}
            aria-label={`Close details for ${data.name}`}
            className="focus:ring-2 focus:ring-primary"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      </CardHeader>

      <CardContent 
        id="modal-description"
        className="flex-1 overflow-y-auto space-y-4 min-h-0"
      >
        {/* Content with proper focus indicators */}
        <div className="space-y-2">
          {Object.entries(data.properties).map(([key, value]) => (
            <div key={key} className="flex justify-between items-start">
              <span className="text-xs text-muted-foreground capitalize">
                {key.replace(/([A-Z])/g, ' $1')}:
              </span>
              <span className="text-xs text-right flex-1 ml-2">
                {Array.isArray(value) ? value.join(', ') : String(value)}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

// Screen reader announcement utility
const announceToScreenReader = (message: string) => {
  const announcement = document.createElement('div');
  announcement.textContent = message;
  announcement.setAttribute('aria-live', 'polite');
  announcement.setAttribute('aria-atomic', 'true');
  announcement.style.position = 'absolute';
  announcement.style.left = '-10000px';
  announcement.style.width = '1px';
  announcement.style.height = '1px';
  announcement.style.overflow = 'hidden';
  
  document.body.appendChild(announcement);
  
  setTimeout(() => {
    document.body.removeChild(announcement);
  }, 1000);
};
```

### Solution 3: Enhanced Graph Canvas Focus
```typescript
// GraphCanvas.tsx - Add focus management for graph interactions
export const GraphCanvas = forwardRef<HTMLDivElement, GraphCanvasProps>((props, ref) => {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [focusedNodeIndex, setFocusedNodeIndex] = useState(0);
  
  const { moveFocusTo } = useFocusManagement(canvasRef, isFocused, {
    trapFocus: false,
    restoreOnUnmount: false
  });
  
  // Keyboard navigation for graph
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isFocused) return;
      
      switch (event.key) {
        case 'ArrowRight':
        case 'ArrowDown':
          event.preventDefault();
          setFocusedNodeIndex(prev => 
            prev < nodes.length - 1 ? prev + 1 : 0
          );
          announceNodeFocus(nodes[focusedNodeIndex + 1] || nodes[0]);
          break;
          
        case 'ArrowLeft':
        case 'ArrowUp':
          event.preventDefault();
          setFocusedNodeIndex(prev => 
            prev > 0 ? prev - 1 : nodes.length - 1
          );
          announceNodeFocus(nodes[focusedNodeIndex - 1] || nodes[nodes.length - 1]);
          break;
          
        case 'Enter':
        case ' ':
          event.preventDefault();
          const focusedNode = nodes[focusedNodeIndex];
          if (focusedNode) {
            onNodeClick(focusedNode);
            announceToScreenReader(`Selected ${focusedNode.label || focusedNode.id}`);
          }
          break;
          
        case 'Escape':
          event.preventDefault();
          onClearSelection?.();
          announceToScreenReader('Selection cleared');
          break;
      }
    };
    
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isFocused, focusedNodeIndex, nodes, onNodeClick, onClearSelection]);
  
  const announceNodeFocus = (node: GraphNode) => {
    if (node) {
      announceToScreenReader(
        `Focused on ${node.label || node.id}, ${node.node_type}. Press Enter to select.`
      );
    }
  };
  
  return (
    <div 
      ref={canvasRef}
      className={`relative overflow-hidden focus:outline-none focus:ring-2 focus:ring-primary ${className}`}
      tabIndex={0}
      role="application"
      aria-label="Graph visualization. Use arrow keys to navigate nodes, Enter to select."
      aria-live="polite"
      onFocus={() => setIsFocused(true)}
      onBlur={() => setIsFocused(false)}
    >
      <Cosmograph
        onClick={handleClick}
        nodeColor={(node: GraphNode) => {
          const isHighlighted = highlightedNodes.includes(node.id);
          const isFocusedNode = isFocused && 
            nodes[focusedNodeIndex]?.id === node.id;
          
          if (isFocusedNode) {
            return '#fbbf24'; // Focus color
          }
          if (isHighlighted) {
            return 'rgba(255, 215, 0, 0.9)';
          }
          // ... rest of color logic
        }}
        // ... other props
      />
      
      {/* Focus indicator overlay */}
      {isFocused && nodes[focusedNodeIndex] && (
        <div className="absolute bottom-4 left-4 bg-black/80 text-white text-xs p-2 rounded">
          Focused: {nodes[focusedNodeIndex].label || nodes[focusedNodeIndex].id}
        </div>
      )}
    </div>
  );
});
```

### Solution 4: Skip Links and Navigation
```typescript
// src/components/SkipLinks.tsx
export const SkipLinks: React.FC = () => {
  return (
    <div className="skip-links">
      <a 
        href="#main-content"
        className="skip-link"
        onFocus={(e) => e.target.scrollIntoView()}
      >
        Skip to main content
      </a>
      <a 
        href="#graph-canvas"
        className="skip-link"
      >
        Skip to graph
      </a>
      <a 
        href="#search"
        className="skip-link"
      >
        Skip to search
      </a>
      
      <style>{`
        .skip-links {
          position: absolute;
          top: 0;
          left: 0;
          z-index: 1000;
        }
        
        .skip-link {
          position: absolute;
          top: -40px;
          left: 6px;
          background: #000;
          color: #fff;
          padding: 8px;
          text-decoration: none;
          border-radius: 0 0 4px 4px;
          transition: top 0.3s;
        }
        
        .skip-link:focus {
          top: 0;
        }
      `}</style>
    </div>
  );
};

// Usage in App.tsx
function App() {
  return (
    <>
      <SkipLinks />
      <main id="main-content">
        <GraphViz />
      </main>
    </>
  );
}
```

## Recommended Solution
**Combination of all solutions**: Implement focus management hook, enhance modals and interactive components, add keyboard navigation, and provide skip links.

### Benefits
- **Accessibility**: Proper focus management for all users
- **Keyboard Efficiency**: Predictable and efficient keyboard navigation
- **Screen Reader Support**: Proper announcements and focus handling
- **Consistency**: Standardized focus patterns across components

## Implementation Plan

### Phase 1: Focus Management Infrastructure (2-3 hours)
1. Create useFocusManagement hook
2. Add focus utility functions
3. Set up screen reader announcement system

### Phase 2: Modal Focus Management (2 hours)
1. Enhance NodeDetailsPanel with focus trap
2. Add proper focus restoration
3. Implement escape key handling

### Phase 3: Graph Canvas Focus (2-3 hours)
1. Add keyboard navigation to graph canvas
2. Implement focus indicators
3. Add screen reader announcements

### Phase 4: Navigation and Skip Links (1-2 hours)
1. Add skip links for major sections
2. Improve tab order throughout application
3. Add focus indicators for all interactive elements

## Testing Strategy
1. **Keyboard Testing**: Navigate entire application using only keyboard
2. **Screen Reader Testing**: Test with NVDA, JAWS, and VoiceOver
3. **Focus Flow Testing**: Verify focus moves logically through components
4. **Accessibility Auditing**: Use axe-core and other accessibility testing tools

## Priority Justification
This is Low Priority because:
- **Accessibility**: Important for some users but doesn't affect core functionality
- **Compliance**: May be required for certain markets but not blocking current development
- **User Segment**: Benefits keyboard and assistive technology users specifically
- **Polish Feature**: Improves experience but application is functional without it

## Related Issues
- [Issue #016: Missing Accessibility Attributes](./016-missing-accessibility-attributes.md)
- [Issue #022: Missing Keyboard Shortcuts](./022-missing-keyboard-shortcuts.md)
- [Issue #027: Accessibility Issues](./027-accessibility-issues.md)

## Dependencies
- Focus management utilities
- Screen reader announcement system
- Keyboard event handling
- ARIA attributes and roles

## Estimated Fix Time
**6-8 hours** for implementing comprehensive focus management across all interactive components