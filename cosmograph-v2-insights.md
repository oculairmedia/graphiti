# Cosmograph v2.0 Implementation Insights

## Overview
This document captures key insights from studying the official Cosmograph v2.0 documentation to ensure proper implementation patterns and fix current integration issues.

## Core Architecture Pattern

### 1. Data Flow Pipeline
The correct Cosmograph v2.0 data flow follows this pattern:
```
Raw Data → Data Configuration → prepareCosmographData() → Cosmograph Component
```

**Key Principle**: Separation of concerns between data preparation and visualization.

### 2. Data Kit Workflow
The Data Kit (`prepareCosmographData`) is the canonical way to prepare data:

```javascript
import { prepareCosmographData } from '@cosmograph/cosmograph'

const config = {
  points: {
    pointIdBy: 'id',           // Required: unique identifier
    pointColorBy: 'type',      // Optional: color mapping
    pointSizeBy: 'centrality', // Optional: size mapping
    pointLabelBy: 'label'      // Optional: label mapping
  },
  links: {
    linkSourceBy: 'source',    // Required: link source field
    linkTargetsBy: ['target'], // Required: link target field(s)
    linkColorBy: 'edge_type',  // Optional: link color mapping
    linkWidthBy: 'weight'      // Optional: link width mapping
  }
}

const { data, config: finalConfig } = await prepareCosmographData(config, points, links)
```

## React Integration Patterns

### 1. Direct Props Pattern (Simple)
```jsx
<Cosmograph
  nodes={nodes}
  links={links}
  nodeColor={d => d.color}
  nodeSize={20}
  linkWidthBy={2}
/>
```

### 2. Data Kit Pattern (Recommended for Complex Data)
```jsx
const [cosmographData, setCosmographData] = useState(null)

useEffect(() => {
  prepareCosmographData(config, points, links)
    .then(result => setCosmographData(result))
}, [points, links])

if (!cosmographData) return <div>Loading...</div>

return <Cosmograph {...cosmographData.config} />
```

### 3. Ref Integration with Imperative Handle
```jsx
const GraphComponent = forwardRef((props, ref) => {
  const cosmographRef = useRef()
  
  useImperativeHandle(ref, () => ({
    zoomIn: () => cosmographRef.current?.setZoomLevel(zoom * 1.5),
    zoomOut: () => cosmographRef.current?.setZoomLevel(zoom * 0.7),
    fitView: () => cosmographRef.current?.fitView(),
    // ... other methods
  }))
  
  return <Cosmograph ref={cosmographRef} {...props} />
})
```

## Configuration Requirements

### Points Configuration
- **`pointIdBy`** (Required): Field containing unique point identifiers
- **`pointColorBy`** (Optional): Field for color mapping 
- **`pointSizeBy`** (Optional): Field for size mapping
- **`pointLabelBy`** (Optional): Field for label display
- **`pointXBy`**, **`pointYBy`** (Optional): Pre-calculated positions

### Links Configuration  
- **`linkSourceBy`** (Required): Field containing source point ID
- **`linkTargetsBy`** (Required): Array of fields containing target point IDs
- **`linkColorBy`** (Optional): Field for link color mapping
- **`linkWidthBy`** (Optional): Field for link width mapping
- **`linkStrengthBy`** (Optional): Field for simulation strength

### Data Format Requirements
Points array should contain objects like:
```javascript
{
  id: "unique_id",        // Used by pointIdBy
  label: "Display Name",  // Used by pointLabelBy
  type: "Entity",         // Used by pointColorBy
  centrality: 0.5,        // Used by pointSizeBy
  // ... other properties
}
```

Links array should contain objects like:
```javascript
{
  source: "point_id_1",   // Used by linkSourceBy
  target: "point_id_2",   // Used by linkTargetsBy
  weight: 1.0,            // Used by linkWidthBy
  edge_type: "CONNECTS",  // Used by linkColorBy
  // ... other properties
}
```

## Common Issues and Solutions

### 1. "Unable to infer Vector type from input values"
**Cause**: Data structure doesn't match configuration mapping
**Solution**: Ensure all fields referenced in config actually exist in data with expected types

### 2. "Missing required properties: pointIdBy, pointIndexBy" 
**Cause**: Configuration object incomplete or malformed
**Solution**: Always provide minimum required fields in configuration

### 3. Initial Load Fails, Refresh Works
**Cause**: Async data preparation timing issues or caching problems
**Solution**: Proper loading states and effect dependencies

## Best Practices

### 1. Type Safety
```typescript
interface GraphPoint {
  id: string
  label: string
  type: string
  centrality?: number
}

interface GraphLink {
  source: string
  target: string
  weight?: number
  edge_type?: string
}
```

### 2. Error Handling
```javascript
try {
  const result = await prepareCosmographData(config, points, links)
  setCosmographData(result)
} catch (error) {
  console.error('Data preparation failed:', error)
  setError(error.message)
}
```

### 3. Performance Optimization
- Use React.memo for expensive components
- Implement proper loading states
- Consider virtualization for large datasets
- Cache prepared data when possible

### 4. Lifecycle Management
```javascript
useEffect(() => {
  if (!points || !links) return
  
  let cancelled = false
  
  prepareCosmographData(config, points, links)
    .then(result => {
      if (!cancelled) setCosmographData(result)
    })
    .catch(error => {
      if (!cancelled) setError(error)
    })
    
  return () => { cancelled = true }
}, [points, links, config])
```

## Implementation Checklist

- [ ] Raw data matches expected structure (id, label, type fields present)
- [ ] Configuration object includes all required fields
- [ ] Field names in config match actual data properties
- [ ] Data types are consistent (strings for IDs, numbers for numeric fields)
- [ ] Async data preparation is properly handled
- [ ] Loading states prevent premature rendering
- [ ] Error boundaries catch preparation failures
- [ ] TypeScript interfaces align with runtime data
- [ ] Component lifecycle properly manages data updates

## API Reference Summary

### Core Cosmograph Methods
- `setZoomLevel(level, duration)`: Control zoom programmatically
- `fitView(duration, padding)`: Fit all points in view
- `start(alpha)`, `pause()`, `restart()`: Simulation control
- `selectPoint(index)`, `selectPoints(indices)`: Selection control
- `addPoints(points)`, `addLinks(links)`: Dynamic data updates

### React Component Props
- Direct data props: `nodes`, `links`
- Styling props: `nodeColor`, `nodeSize`, `linkWidth` 
- Configuration props: All Cosmograph configuration options
- Event props: `onPointClick`, `onPointHover`, etc.

## Conclusion

Cosmograph v2.0 emphasizes:
1. **Data Kit First**: Use `prepareCosmographData()` for reliable data transformation
2. **Configuration Driven**: Explicit field mapping over implicit assumptions  
3. **Type Safety**: Consistent data types and proper TypeScript integration
4. **Async Patterns**: Proper handling of data preparation lifecycle

The key to successful implementation is aligning backend data structure with frontend configuration expectations through the Data Kit API.