# Medium Priority Issue #011: Missing Prop Validation

## Severity
🟡 **Medium**

## Component
Multiple components throughout the application - Component interfaces lack runtime validation

## Issue Description
The React components use TypeScript interfaces for prop types but lack runtime validation. This means invalid props passed at runtime won't be caught, potentially causing crashes or unexpected behavior, especially when integrating with external systems or during development.

## Technical Details

### Current Implementation Without Validation
```typescript
// GraphSearch.tsx - Lines 7-14
interface GraphSearchProps {
  className?: string;                                    // No default value validation
  onNodeSelect?: (node: GraphNode) => void;             // No function signature validation
  onHighlightNodes?: (nodes: GraphNode[]) => void;      // No array content validation
  onSelectNodes?: (nodes: GraphNode[]) => void;         // No callback validation
  onClearSelection?: () => void;                         // No validation
  onFilterClick?: () => void;                            // No validation
}

// Component accepts props without runtime checks
export const GraphSearch: React.FC<GraphSearchProps> = ({ 
  className = '',      // ✅ Has default, but no validation
  onNodeSelect,        // ❌ No validation - could be anything
  onHighlightNodes,    // ❌ No validation - could be anything
  onSelectNodes,       // ❌ No validation
  onClearSelection,    // ❌ No validation
  onFilterClick        // ❌ No validation
}) => {
```

### Problems with Missing Validation

#### 1. Runtime Type Mismatches
```typescript
// TypeScript interface says this is valid:
<GraphSearch 
  onNodeSelect={(node: GraphNode) => console.log(node.id)}
  onHighlightNodes={(nodes: GraphNode[]) => nodes.map(n => n.id)}
/>

// But at runtime, these could fail:
// - onNodeSelect might receive null/undefined
// - onHighlightNodes might receive non-array
// - node.id might not exist on the object
// - Functions might not exist at all
```

#### 2. Integration Issues
```typescript
// When integrating with external systems:
const externalProps = {
  onNodeSelect: "not a function",           // ❌ String instead of function
  onHighlightNodes: null,                   // ❌ Null instead of function
  className: 123,                           // ❌ Number instead of string
  onSelectNodes: () => { throw new Error(); } // ❌ Function that throws
};

// TypeScript won't catch these at runtime
<GraphSearch {...externalProps} />
```

#### 3. Development Time Issues
```typescript
// During development, these errors are common:
<GraphSearch 
  onNodeSelect={handleNodeSelect}     // ❌ Function might be undefined
  onHighlightNodes={undefined}        // ❌ Accidentally passing undefined
  className={null}                    // ❌ Null instead of string
/>

// These cause runtime crashes instead of helpful error messages
```

#### 4. Data Integrity Issues
```typescript
// No validation of node objects passed to callbacks:
const malformedNode = {
  // Missing required fields
  // id: "missing",
  label: "Has label but no ID",
  node_type: null                     // ❌ Wrong type
};

onNodeSelect(malformedNode);          // ❌ Crashes later when accessing .id
```

## Root Cause Analysis

### 1. TypeScript Compile-Time Only
TypeScript interfaces only exist at compile time and provide no runtime protection against type mismatches.

### 2. No Defensive Programming
Components assume props are always correctly typed and don't validate inputs before using them.

### 3. Missing Development Guardrails
No runtime checks to catch common development mistakes or integration issues.

### 4. External Integration Vulnerability
When integrating with external systems (APIs, third-party components), there's no protection against malformed data.

## Impact Assessment

### Runtime Errors
```javascript
// Common runtime errors from missing validation:
TypeError: onNodeSelect is not a function
TypeError: Cannot read property 'id' of undefined
TypeError: nodes.map is not a function
TypeError: Cannot read property 'length' of null
```

### Development Issues
- **Debugging Difficulty**: Errors manifest far from their source
- **Integration Problems**: Silent failures when connecting components
- **Testing Complexity**: Hard to test edge cases without validation

### Production Stability
- **User Experience**: Application crashes instead of graceful degradation
- **Error Recovery**: No fallback behavior for invalid props
- **Monitoring**: Errors are generic and hard to trace

## Scenarios Where This Fails

### Scenario 1: API Integration
```typescript
// API returns unexpected node format
const apiNode = {
  identifier: "node_123",        // ❌ 'identifier' instead of 'id'
  type: "entity",               // ❌ 'type' instead of 'node_type'  
  title: "Node Title"           // ❌ 'title' instead of 'label'
};

// Component crashes when trying to access node.id
onNodeSelect(apiNode);          // TypeError: Cannot read property 'id' of undefined
```

### Scenario 2: Dynamic Component Loading
```typescript
// Props loaded dynamically from configuration
const dynamicProps = JSON.parse(configString);
// configString might be malformed or have wrong types

<GraphSearch {...dynamicProps} />  // Runtime type errors
```

### Scenario 3: Third-party Integration
```typescript
// Third-party system passes incorrect callback signatures
const thirdPartyCallbacks = {
  onNodeSelect: (nodeId) => {},        // ❌ Expects string, gets object
  onHighlightNodes: (node) => {},      // ❌ Expects array, gets single node
};
```

## Proposed Solutions

### Solution 1: Runtime Type Validation with PropTypes
```typescript
import PropTypes from 'prop-types';

// Define PropTypes for runtime validation
GraphSearch.propTypes = {
  className: PropTypes.string,
  onNodeSelect: PropTypes.func,
  onHighlightNodes: PropTypes.func,
  onSelectNodes: PropTypes.func,
  onClearSelection: PropTypes.func,
  onFilterClick: PropTypes.func,
};

GraphSearch.defaultProps = {
  className: '',
  onNodeSelect: () => {},
  onHighlightNodes: () => {},
  onSelectNodes: () => {},
  onClearSelection: () => {},
  onFilterClick: () => {},
};
```

### Solution 2: Custom Validation Hook
```typescript
// src/hooks/useValidatedProps.ts
import { useEffect } from 'react';

interface ValidationSchema<T> {
  [K in keyof T]: (value: T[K]) => boolean | string;
}

export const useValidatedProps = <T>(props: T, schema: ValidationSchema<T>) => {
  useEffect(() => {
    for (const [key, validator] of Object.entries(schema)) {
      const value = props[key as keyof T];
      const result = validator(value);
      
      if (result !== true) {
        const message = typeof result === 'string' ? result : `Invalid prop: ${key}`;
        console.warn(`PropValidation: ${message}`, { key, value });
        
        // In development, throw error for immediate feedback
        if (process.env.NODE_ENV === 'development') {
          throw new Error(message);
        }
      }
    }
  }, [props, schema]);
};

// Usage in GraphSearch component
const GraphSearch: React.FC<GraphSearchProps> = (props) => {
  useValidatedProps(props, {
    className: (value) => typeof value === 'string' || 'className must be a string',
    onNodeSelect: (value) => 
      value === undefined || typeof value === 'function' || 'onNodeSelect must be a function',
    onHighlightNodes: (value) => 
      value === undefined || typeof value === 'function' || 'onHighlightNodes must be a function',
    // ... other validations
  });
  
  // Rest of component logic
};
```

### Solution 3: Zod Schema Validation
```typescript
import { z } from 'zod';

// Define Zod schemas for complex validation
const GraphNodeSchema = z.object({
  id: z.string().min(1, 'Node ID is required'),
  label: z.string().optional(),
  node_type: z.enum(['Entity', 'Episodic', 'Agent', 'Community']),
  properties: z.record(z.any()).optional(),
});

const GraphSearchPropsSchema = z.object({
  className: z.string().optional(),
  onNodeSelect: z.function()
    .args(GraphNodeSchema)
    .returns(z.void())
    .optional(),
  onHighlightNodes: z.function()
    .args(z.array(GraphNodeSchema))
    .returns(z.void())
    .optional(),
  onSelectNodes: z.function()
    .args(z.array(GraphNodeSchema))
    .returns(z.void())
    .optional(),
  onClearSelection: z.function()
    .args()
    .returns(z.void())
    .optional(),
  onFilterClick: z.function()
    .args()
    .returns(z.void())
    .optional(),
});

// Validation hook
const useValidatedProps = <T>(props: T, schema: z.ZodSchema<T>) => {
  useEffect(() => {
    try {
      schema.parse(props);
    } catch (error) {
      console.warn('Prop validation failed:', error);
      if (process.env.NODE_ENV === 'development') {
        throw error;
      }
    }
  }, [props, schema]);
};

// Usage
const GraphSearch: React.FC<GraphSearchProps> = (props) => {
  useValidatedProps(props, GraphSearchPropsSchema);
  // Component logic
};
```

### Solution 4: Defensive Programming Pattern
```typescript
// Add defensive checks throughout the component
export const GraphSearch: React.FC<GraphSearchProps> = ({ 
  className = '',
  onNodeSelect,
  onHighlightNodes,
  onSelectNodes,
  onClearSelection,
  onFilterClick
}) => {
  // Defensive callback wrappers
  const safeOnNodeSelect = useCallback((node: GraphNode) => {
    if (typeof onNodeSelect !== 'function') {
      console.warn('onNodeSelect is not a function');
      return;
    }
    
    if (!node || typeof node.id !== 'string') {
      console.warn('Invalid node passed to onNodeSelect:', node);
      return;
    }
    
    try {
      onNodeSelect(node);
    } catch (error) {
      console.error('Error in onNodeSelect callback:', error);
    }
  }, [onNodeSelect]);

  const safeOnHighlightNodes = useCallback((nodes: GraphNode[]) => {
    if (typeof onHighlightNodes !== 'function') {
      console.warn('onHighlightNodes is not a function');
      return;
    }
    
    if (!Array.isArray(nodes)) {
      console.warn('onHighlightNodes expects an array, got:', typeof nodes);
      return;
    }
    
    const validNodes = nodes.filter(node => 
      node && typeof node.id === 'string'
    );
    
    if (validNodes.length !== nodes.length) {
      console.warn('Some invalid nodes filtered out:', {
        original: nodes.length,
        valid: validNodes.length
      });
    }
    
    try {
      onHighlightNodes(validNodes);
    } catch (error) {
      console.error('Error in onHighlightNodes callback:', error);
    }
  }, [onHighlightNodes]);

  // Use safe wrappers instead of direct callbacks
  const handleSelectResult = (node: GraphNode) => {
    safeOnNodeSelect(node);
  };
};
```

## Recommended Solution
**Combination of Solutions 2 and 4**: Use custom validation hook for development feedback with defensive programming for production resilience.

### Benefits
- **Development Experience**: Immediate feedback on prop validation issues
- **Production Stability**: Graceful handling of invalid props
- **Performance**: Validation only in development mode
- **Flexibility**: Easy to add/modify validation rules
- **Type Safety**: Maintains TypeScript benefits with runtime protection

## Implementation Plan

### Phase 1: Create Validation Infrastructure
1. Create `useValidatedProps` hook
2. Define common validation schemas
3. Add development/production mode handling

### Phase 2: Add Validation to Critical Components
1. Start with GraphSearch, GraphCanvas, NodeDetailsPanel
2. Add prop validation to each component
3. Test with invalid props

### Phase 3: Defensive Programming
1. Add defensive checks to callback functions
2. Implement graceful error handling
3. Add meaningful warning messages

### Phase 4: Comprehensive Coverage
1. Add validation to all components
2. Create validation utilities for common patterns
3. Document validation patterns

## Testing Strategy
1. **Invalid Props Testing**: Test components with intentionally invalid props
2. **Callback Error Testing**: Test error handling in callback functions
3. **Integration Testing**: Test with external data sources
4. **Performance Testing**: Verify validation doesn't impact performance

## Priority Justification
This is Medium Priority because:
- **Stability**: Prevents runtime crashes from invalid props
- **Development Experience**: Provides better error messages during development
- **Integration Safety**: Protects against external system integration issues
- **Code Quality**: Encourages defensive programming practices

## Related Issues
- [Issue #003: Type Safety Issues](../critical/003-type-safety-issues.md)
- [Issue #021: Incomplete Error Handling](../low/021-incomplete-error-handling.md)
- [Issue #010: Inconsistent State Management](./010-inconsistent-state-management.md)

## Dependencies
- Validation library (Zod or custom)
- Development/production environment detection
- Console warning/error handling
- TypeScript interfaces for compile-time checking

## Estimated Fix Time
**3-4 hours** for implementing validation hook and adding prop validation to major components