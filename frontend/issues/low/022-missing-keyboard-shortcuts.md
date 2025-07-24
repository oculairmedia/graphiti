# Low Priority Issue #022: Missing Keyboard Shortcuts

## Severity
🟢 **Low**

## Component
Application-wide - No keyboard shortcuts implemented for common actions

## Issue Description
The application lacks keyboard shortcuts for frequently used operations, forcing users to rely entirely on mouse interactions. This reduces productivity for power users, creates accessibility barriers, and provides a less efficient user experience compared to modern applications that support keyboard navigation.

## Technical Details

### Missing Keyboard Shortcuts

#### 1. Graph Navigation Shortcuts
```typescript
// Currently missing shortcuts for:
// Ctrl/Cmd + Plus     - Zoom in
// Ctrl/Cmd + Minus    - Zoom out  
// Ctrl/Cmd + 0        - Reset zoom / Fit to screen
// Space + Drag        - Pan graph
// Arrow keys          - Navigate between nodes
// Home/End            - Go to first/last node
// Page Up/Down        - Navigate node clusters
```

#### 2. Search and Selection Shortcuts
```typescript
// Currently missing shortcuts for:
// Ctrl/Cmd + F       - Focus search box
// Ctrl/Cmd + K       - Quick search command palette
// Ctrl/Cmd + A       - Select all nodes
// Ctrl/Cmd + D       - Deselect all
// Delete/Backspace   - Remove selected nodes from view
// Ctrl/Cmd + Click   - Multi-select nodes
// Shift + Click      - Range select nodes
```

#### 3. Panel and Modal Shortcuts
```typescript
// Currently missing shortcuts for:
// Escape             - Close modals/panels
// Tab/Shift+Tab      - Navigate between UI elements
// Enter              - Confirm actions
// Ctrl/Cmd + ,       - Open settings/preferences
// F1                 - Help/documentation
// Ctrl/Cmd + /       - Show keyboard shortcuts help
```

#### 4. Application State Shortcuts
```typescript
// Currently missing shortcuts for:
// Ctrl/Cmd + R       - Refresh/reload graph data
// Ctrl/Cmd + S       - Save current view/state
// Ctrl/Cmd + Z       - Undo last action
// Ctrl/Cmd + Y       - Redo action
// F5                 - Refresh application
// F11                - Toggle fullscreen
```

### Current Keyboard Interaction Limitations

#### 1. No Keyboard Event Handlers
```typescript
// GraphViz.tsx - No keyboard event handling
const GraphViz: React.FC<GraphVizProps> = ({ data, isLoading, className }) => {
  // ❌ No useEffect for keyboard event listeners
  // ❌ No key event handling in component
  // ❌ No keyboard navigation state
  
  return (
    <div className={`h-screen w-full bg-background ${className}`}>
      {/* Components without keyboard navigation */}
    </div>
  );
};
```

#### 2. Search Box Limited Navigation
```typescript
// GraphSearch.tsx - Only basic Enter key handling
const handleEnter = (input: string | any, accessor?: any) => {
  // ✅ Has Enter key for search
  // ❌ No Escape to clear
  // ❌ No Ctrl+A to select all results
  // ❌ No arrow keys to navigate results
  // ❌ No Tab to cycle through search suggestions
};
```

#### 3. Modal Navigation Gaps
```typescript
// NodeDetailsPanel.tsx - No keyboard navigation
export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose 
}) => {
  // ❌ No Escape key to close
  // ❌ No Tab navigation within modal
  // ❌ No Enter/Space for button interactions
  // ❌ No arrow keys to navigate content
  
  return (
    <Card className="glass-panel">
      {/* Modal content without keyboard support */}
    </Card>
  );
};
```

#### 4. Graph Canvas Keyboard Interaction
```typescript
// GraphCanvas.tsx - No keyboard support for graph operations
export const GraphCanvas = forwardRef<HTMLDivElement, GraphCanvasProps>((props, ref) => {
  // ❌ No keyboard event handlers
  // ❌ No focus management
  // ❌ No node navigation with arrow keys
  // ❌ No keyboard-triggered zoom/pan
  
  return (
    <div className="relative overflow-hidden">
      <Cosmograph onClick={handleClick} />
      {/* No keyboard interaction support */}
    </div>
  );
});
```

## Root Cause Analysis

### 1. Mouse-First Design
Application was designed primarily for mouse interaction without considering keyboard users.

### 2. Complex Canvas Interaction
Graph visualization makes keyboard navigation more challenging to implement than traditional UI elements.

### 3. No Keyboard Strategy
No systematic approach to defining which shortcuts should be supported and how they should work.

### 4. Accessibility Oversight
Keyboard navigation requirements not considered during initial development.

## Impact Assessment

### User Experience Issues
- **Power User Efficiency**: Advanced users can't work as quickly without shortcuts
- **Accessibility Barriers**: Users who rely on keyboard navigation cannot use the application effectively
- **Productivity Loss**: Simple actions require multiple mouse clicks instead of quick keystrokes
- **Learning Curve**: Users familiar with standard shortcuts expect them to work

### Competitive Disadvantage
- **Modern Expectations**: Users expect keyboard shortcuts in professional applications
- **Workflow Integration**: Doesn't integrate well with keyboard-heavy workflows
- **Professional Use**: Less suitable for enterprise environments where keyboard efficiency matters

### Market Reach
- **Accessibility Compliance**: Fails to meet keyboard navigation requirements
- **User Preferences**: Some users strongly prefer keyboard navigation
- **Use Cases**: Limits adoption in scenarios requiring rapid interaction

## Scenarios Where Missing Shortcuts Cause Issues

### Scenario 1: Data Analysis Workflow
```typescript
// Analyst reviewing large graph dataset:
// 1. Wants to quickly zoom in on cluster (Ctrl+Plus) - Must use mouse
// 2. Wants to pan to different area (Arrow keys) - Must drag with mouse
// 3. Wants to search for specific nodes (Ctrl+F) - Must click search box
// 4. Wants to select multiple nodes (Ctrl+Click) - Must click each individually
// 5. Workflow is 3x slower than with keyboard shortcuts
```

### Scenario 2: Accessibility User
```typescript
// User with limited mouse mobility:
// 1. Cannot efficiently navigate graph with mouse
// 2. No keyboard alternative for zoom/pan operations
// 3. Cannot quickly access search functionality
// 4. Cannot navigate between panels without mouse
// 5. Application is essentially unusable
```

### Scenario 3: Presentation/Demo Scenario
```typescript
// Developer demoing application:
// 1. Wants to quickly show different areas (keyboard navigation)
// 2. Wants to smoothly zoom in/out during presentation
// 3. Wants to quickly search for specific examples
// 4. Must fumble with mouse, disrupting presentation flow
// 5. Appears less professional due to inefficient interaction
```

## Proposed Solutions

### Solution 1: Global Keyboard Shortcut System
```typescript
// src/hooks/useKeyboardShortcuts.ts
import { useEffect, useCallback, useRef } from 'react';

interface KeyboardShortcut {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  preventDefault?: boolean;
  action: () => void;
  description: string;
  category: string;
}

export const useKeyboardShortcuts = (shortcuts: KeyboardShortcut[]) => {
  const shortcutsRef = useRef(shortcuts);
  shortcutsRef.current = shortcuts;
  
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    const { key, ctrlKey, metaKey, shiftKey, altKey } = event;
    const isCtrl = ctrlKey || metaKey; // Handle both Ctrl and Cmd
    
    for (const shortcut of shortcutsRef.current) {
      const keyMatch = shortcut.key.toLowerCase() === key.toLowerCase();
      const ctrlMatch = !!shortcut.ctrl === isCtrl;
      const shiftMatch = !!shortcut.shift === shiftKey;
      const altMatch = !!shortcut.alt === altKey;
      
      if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
        if (shortcut.preventDefault !== false) {
          event.preventDefault();
          event.stopPropagation();
        }
        shortcut.action();
        break;
      }
    }
  }, []);
  
  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);
  
  return shortcutsRef.current;
};

// Usage in GraphViz
const GraphViz: React.FC<GraphVizProps> = ({ data, isLoading, className }) => {
  const graphCanvasRef = useRef<any>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  
  const shortcuts: KeyboardShortcut[] = [
    // Graph navigation
    {
      key: '=',
      ctrl: true,
      action: () => graphCanvasRef.current?.zoomIn(),
      description: 'Zoom in',
      category: 'Navigation'
    },
    {
      key: '-',
      ctrl: true,
      action: () => graphCanvasRef.current?.zoomOut(),
      description: 'Zoom out',
      category: 'Navigation'
    },
    {
      key: '0',
      ctrl: true,
      action: () => graphCanvasRef.current?.fitView(),
      description: 'Fit to screen',
      category: 'Navigation'
    },
    
    // Search shortcuts
    {
      key: 'f',
      ctrl: true,
      action: () => searchRef.current?.focus(),
      description: 'Focus search',
      category: 'Search'
    },
    {
      key: 'k',
      ctrl: true,
      action: () => openCommandPalette(),
      description: 'Command palette',
      category: 'Search'
    },
    
    // Selection shortcuts
    {
      key: 'a',
      ctrl: true,
      action: () => selectAllNodes(),
      description: 'Select all nodes',
      category: 'Selection'
    },
    {
      key: 'd',
      ctrl: true,
      action: () => clearAllSelections(),
      description: 'Clear selection',
      category: 'Selection'
    },
    
    // Panel shortcuts
    {
      key: 'Escape',
      action: () => closeActivePanel(),
      description: 'Close panel/modal',
      category: 'Interface'
    },
    {
      key: '/',
      ctrl: true,
      action: () => showKeyboardHelp(),
      description: 'Show keyboard shortcuts',
      category: 'Help'
    }
  ];
  
  useKeyboardShortcuts(shortcuts);
  
  return (
    <div className={`h-screen w-full bg-background ${className}`}>
      {/* Component content */}
    </div>
  );
};
```

### Solution 2: Graph Canvas Keyboard Navigation
```typescript
// GraphCanvas.tsx - Add keyboard navigation support
export const GraphCanvas = forwardRef<HTMLDivElement, GraphCanvasProps>((props, ref) => {
  const [focusedNodeIndex, setFocusedNodeIndex] = useState<number>(0);
  const [isGraphFocused, setIsGraphFocused] = useState(false);
  
  // Keyboard navigation within graph
  const handleGraphKeyDown = useCallback((event: KeyboardEvent) => {
    if (!isGraphFocused || !nodes.length) return;
    
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        event.preventDefault();
        setFocusedNodeIndex(prev => 
          prev < nodes.length - 1 ? prev + 1 : 0
        );
        break;
        
      case 'ArrowLeft':
      case 'ArrowUp':
        event.preventDefault();
        setFocusedNodeIndex(prev => 
          prev > 0 ? prev - 1 : nodes.length - 1
        );
        break;
        
      case 'Enter':
      case ' ':
        event.preventDefault();
        const focusedNode = nodes[focusedNodeIndex];
        if (focusedNode) {
          onNodeClick(focusedNode);
          onNodeSelect(focusedNode.id);
        }
        break;
        
      case 'Home':
        event.preventDefault();
        setFocusedNodeIndex(0);
        break;
        
      case 'End':
        event.preventDefault();
        setFocusedNodeIndex(nodes.length - 1);
        break;
    }
  }, [isGraphFocused, nodes, focusedNodeIndex, onNodeClick, onNodeSelect]);
  
  useEffect(() => {
    if (isGraphFocused) {
      document.addEventListener('keydown', handleGraphKeyDown);
      return () => document.removeEventListener('keydown', handleGraphKeyDown);
    }
  }, [handleGraphKeyDown, isGraphFocused]);
  
  // Focus the currently selected node
  useEffect(() => {
    if (isGraphFocused && nodes[focusedNodeIndex] && cosmographRef.current) {
      const node = nodes[focusedNodeIndex];
      // Highlight the focused node
      cosmographRef.current.focusNode?.(node);
    }
  }, [focusedNodeIndex, isGraphFocused, nodes]);
  
  return (
    <div 
      className="relative overflow-hidden"
      tabIndex={0}
      onFocus={() => setIsGraphFocused(true)}
      onBlur={() => setIsGraphFocused(false)}
      role="application"
      aria-label="Graph visualization - use arrow keys to navigate nodes"
    >
      <Cosmograph
        ref={cosmographRef}
        onClick={handleClick}
        nodeColor={(node: GraphNode) => {
          const isHighlighted = highlightedNodes.includes(node.id);
          const isFocused = isGraphFocused && 
            nodes[focusedNodeIndex]?.id === node.id;
          
          if (isFocused) {
            return '#fbbf24'; // Gold for keyboard focus
          }
          if (isHighlighted) {
            return 'rgba(255, 215, 0, 0.9)';
          }
          // ... rest of color logic
        }}
        // ... other props
      />
      
      {/* Keyboard navigation help overlay */}
      {isGraphFocused && (
        <div className="absolute bottom-4 left-4 bg-black/80 text-white text-xs p-2 rounded">
          Use arrow keys to navigate • Enter to select • Escape to exit
        </div>
      )}
    </div>
  );
});
```

### Solution 3: Modal Keyboard Navigation
```typescript
// NodeDetailsPanel.tsx - Add keyboard navigation
export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose 
}) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const [focusedElementIndex, setFocusedElementIndex] = useState(0);
  
  // Handle Escape key to close modal
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [onClose]);
  
  // Focus trap within modal
  useEffect(() => {
    const modal = modalRef.current;
    if (!modal) return;
    
    const focusableElements = modal.querySelectorAll(
      'button, input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    
    const firstElement = focusableElements[0] as HTMLElement;
    const lastElement = focusableElements[focusableElements.length - 1] as HTMLElement;
    
    const handleTabKey = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      
      if (event.shiftKey) {
        if (document.activeElement === firstElement) {
          event.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          event.preventDefault();
          firstElement?.focus();
        }
      }
    };
    
    modal.addEventListener('keydown', handleTabKey);
    firstElement?.focus();
    
    return () => {
      modal.removeEventListener('keydown', handleTabKey);
    };
  }, []);
  
  return (
    <Card 
      ref={modalRef}
      className="glass-panel w-96 max-h-[80vh] overflow-hidden flex flex-col"
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
    >
      <CardHeader className="flex-shrink-0">
        <div className="flex items-start justify-between">
          <CardTitle className="text-lg leading-tight mb-2">
            {data.name}
          </CardTitle>
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={onClose}
            aria-label="Close (Esc)"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      
      <CardContent className="flex-1 overflow-y-auto space-y-4 min-h-0">
        {/* Modal content with proper tabindex and keyboard navigation */}
      </CardContent>
    </Card>
  );
};
```

### Solution 4: Keyboard Shortcuts Help System
```typescript
// src/components/KeyboardShortcutsHelp.tsx
interface ShortcutCategory {
  name: string;
  shortcuts: Array<{
    keys: string[];
    description: string;
  }>;
}

export const KeyboardShortcutsHelp: React.FC<{
  isOpen: boolean;
  onClose: () => void;
}> = ({ isOpen, onClose }) => {
  const categories: ShortcutCategory[] = [
    {
      name: 'Navigation',
      shortcuts: [
        { keys: ['Ctrl', '+'], description: 'Zoom in' },
        { keys: ['Ctrl', '-'], description: 'Zoom out' },
        { keys: ['Ctrl', '0'], description: 'Fit to screen' },
        { keys: ['Arrow Keys'], description: 'Navigate nodes' },
        { keys: ['Home'], description: 'First node' },
        { keys: ['End'], description: 'Last node' }
      ]
    },
    {
      name: 'Search & Selection',
      shortcuts: [
        { keys: ['Ctrl', 'F'], description: 'Focus search' },
        { keys: ['Ctrl', 'K'], description: 'Command palette' },
        { keys: ['Ctrl', 'A'], description: 'Select all' },
        { keys: ['Ctrl', 'D'], description: 'Clear selection' },
        { keys: ['Enter'], description: 'Select focused node' }
      ]
    },
    {
      name: 'Interface',
      shortcuts: [
        { keys: ['Esc'], description: 'Close panel/modal' },
        { keys: ['Tab'], description: 'Navigate UI elements' },
        { keys: ['Ctrl', '/'], description: 'Show this help' },
        { keys: ['F1'], description: 'Documentation' }
      ]
    }
  ];
  
  if (!isOpen) return null;
  
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[80vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-xl font-semibold">Keyboard Shortcuts</h2>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
        
        <div className="grid gap-6 md:grid-cols-2">
          {categories.map((category) => (
            <div key={category.name}>
              <h3 className="font-medium text-lg mb-3">{category.name}</h3>
              <div className="space-y-2">
                {category.shortcuts.map((shortcut, index) => (
                  <div key={index} className="flex justify-between items-center">
                    <span className="text-sm">{shortcut.description}</span>
                    <div className="flex gap-1">
                      {shortcut.keys.map((key, keyIndex) => (
                        <kbd 
                          key={keyIndex}
                          className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 rounded border"
                        >
                          {key}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        
        <div className="mt-6 pt-4 border-t text-sm text-gray-600 dark:text-gray-400">
          <p>Press <kbd className="px-1 bg-gray-100 dark:bg-gray-700 rounded">Esc</kbd> to close this help.</p>
        </div>
      </div>
    </div>
  );
};
```

## Recommended Solution
**Combination of all solutions**: Implement global shortcut system, graph keyboard navigation, modal navigation, and help system.

### Benefits
- **Power User Efficiency**: Significantly faster interaction for experienced users
- **Accessibility**: Makes application usable for keyboard-only users
- **Professional Feel**: Meets modern application standards
- **Discoverability**: Help system teaches users available shortcuts

## Implementation Plan

### Phase 1: Global Shortcut Infrastructure (2-3 hours)
1. Create useKeyboardShortcuts hook
2. Define standard shortcut patterns
3. Set up global event handling system

### Phase 2: Basic Navigation Shortcuts (2-3 hours)
1. Implement zoom shortcuts (Ctrl +/-, Ctrl 0)
2. Add search focus shortcut (Ctrl F)
3. Add panel closing (Escape)
4. Add help shortcut (Ctrl /)

### Phase 3: Graph Navigation (3-4 hours)
1. Implement arrow key node navigation
2. Add Enter/Space for node selection
3. Add focus management for graph canvas
4. Visual indicators for keyboard focus

### Phase 4: Advanced Shortcuts (2-3 hours)
1. Selection shortcuts (Ctrl A, Ctrl D)
2. Multi-select with Ctrl+Click
3. Tab navigation in modals
4. Command palette implementation

### Phase 5: Help and Documentation (1-2 hours)
1. Create keyboard shortcuts help modal
2. Add contextual keyboard hints
3. Document all shortcuts
4. Add onboarding for shortcuts

## Testing Strategy
1. **Keyboard-Only Testing**: Navigate entire application using only keyboard
2. **Shortcut Testing**: Verify all shortcuts work as expected
3. **Accessibility Testing**: Test with screen readers and assistive technology
4. **Cross-platform Testing**: Verify Ctrl vs Cmd key handling

## Priority Justification
This is Low Priority because:
- **Mouse Functionality**: Application fully functional with mouse
- **User Segment**: Benefits power users but not essential for all users
- **Accessibility**: Important for some users but not blocking for most
- **Polish Feature**: Improves experience but doesn't fix core functionality

## Related Issues
- [Issue #016: Missing Accessibility Attributes](./016-missing-accessibility-attributes.md)
- [Issue #025: Inconsistent Focus Management](./025-inconsistent-focus-management.md)
- [Issue #027: Accessibility Issues](./027-accessibility-issues.md)

## Dependencies
- Keyboard event handling system
- Focus management utilities
- Accessibility attributes implementation
- Help system UI components

## Estimated Fix Time
**8-12 hours** for implementing comprehensive keyboard shortcut system with navigation, selection, and help features