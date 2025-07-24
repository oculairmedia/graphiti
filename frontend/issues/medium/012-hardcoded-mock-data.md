# Medium Priority Issue #012: Hardcoded Mock Data

## Severity
🟡 **Medium**

## Component
`GraphViz.tsx` - Lines 75-98, `NodeDetailsPanel.tsx` - Lines 38-63, `StatsPanel.tsx`

## Issue Description
Several components contain hardcoded mock data instead of using real API data or proper data integration. This creates inconsistencies between what users see and actual data, makes testing difficult, and prevents proper functionality in production environments.

## Technical Details

### Current Mock Data Implementation

#### 1. GraphViz Mock Node Data
```typescript
// GraphViz.tsx - Lines 75-98
const mockNodeData = {
  id: 'node_123',
  name: 'Neural Network Research',
  type: 'Entity',
  summary: 'Comprehensive research on neural network architectures and their applications in modern AI systems.',
  properties: {
    field: 'Artificial Intelligence',
    author: 'Dr. Sarah Chen',
    citations: 342,
    year: 2024
  },
  centrality: {
    degree: 0.85,
    betweenness: 0.72,
    pagerank: 0.91,
    eigenvector: 0.78
  },
  timestamps: {
    created: '2024-01-15T10:30:00Z',
    updated: '2024-01-20T14:45:00Z'
  },
  connections: 23
};

// ❌ This mock data is created but never used consistently
```

#### 2. NodeDetailsPanel Mock Data
```typescript
// NodeDetailsPanel.tsx - Lines 38-63
const mockData = {
  id: 'node_12345',
  name: 'Neural Network Research',
  type: 'Entity',
  summary: 'Comprehensive research on neural network architectures...',
  properties: {
    field: 'Artificial Intelligence',
    author: 'Dr. Sarah Chen',
    citations: 342,
    year: 2024,
    institution: 'MIT AI Lab',           // ❌ Additional fields not in API
    keywords: ['Neural Networks', 'Deep Learning', 'AI']
  },
  centrality: {
    degree: 0.85,
    betweenness: 0.72,
    pagerank: 0.91,
    eigenvector: 0.78
  },
  timestamps: {
    created: '2024-01-15T10:30:00Z',
    updated: '2024-01-20T14:45:00Z'
  },
  connections: 23
};

// ❌ Mock data is merged with real data, causing inconsistencies
const data = { ...mockData, ...node };
```

#### 3. StatsPanel Mock Data (Inferred)
```typescript
// StatsPanel likely contains similar mock data for:
// - Graph statistics
// - Performance metrics  
// - Usage analytics
// - Node/edge counts
```

### Problems with Mock Data

#### 1. Data Inconsistency
```typescript
// Real API node structure:
{
  id: "actual_node_id",
  label: "Actual Label",
  node_type: "Entity",
  properties: {
    degree_centrality: 0.25,
    pagerank_centrality: 0.15
    // ... actual API fields
  }
}

// Mock data structure:
{
  id: 'node_123',
  name: 'Neural Network Research',    // ❌ 'name' vs 'label'
  type: 'Entity',                     // ❌ 'type' vs 'node_type'
  citations: 342,                     // ❌ Field not in real API
  institution: 'MIT AI Lab'           // ❌ Field not in real API
}

// → Data structure mismatch causes runtime errors
```

#### 2. UI Shows Incorrect Information
```typescript
// NodeDetailsPanel always shows mock data:
<div>Author: Dr. Sarah Chen</div>      // ❌ Always shows same author
<div>Citations: 342</div>             // ❌ Always shows same citations
<div>Institution: MIT AI Lab</div>    // ❌ Always shows same institution

// Users see fake data instead of real node information
```

#### 3. Testing and Development Issues
```typescript
// Mock data makes it hard to test:
// 1. Real API integration testing is impossible
// 2. Edge cases with missing fields not covered
// 3. Performance testing with realistic data sizes not possible
// 4. UI behavior with various data types not tested
```

#### 4. Production Readiness Problems
```typescript
// In production:
// 1. Users see obviously fake data (Dr. Sarah Chen everywhere)
// 2. Real API fields might be missing from UI
// 3. Error handling for missing data not implemented
// 4. Performance characteristics unknown with real data
```

## Root Cause Analysis

### 1. Development Convenience
Mock data was added for easier development without setting up complete API integration, but never removed.

### 2. Incomplete API Integration
Components were partially integrated with real APIs but still fall back to mock data for missing fields.

### 3. Missing Data Transformation Layer
No proper data transformation layer to handle differences between API response format and UI expectations.

### 4. Lack of Loading/Error States
Mock data masks the need for proper loading states and error handling when real data is unavailable.

## Impact Assessment

### User Experience Issues
- **Misleading Information**: Users see fake data that doesn't represent their actual graph
- **Inconsistent Behavior**: Some data is real, some is mock, creating confusion
- **Trust Issues**: Obviously fake data makes the application appear unprofessional

### Development Problems
- **Testing Difficulty**: Can't properly test with real data scenarios
- **Integration Issues**: Hard to identify API integration problems
- **Performance Unknown**: Real-world performance characteristics hidden

### Production Risks
- **Data Quality**: No validation of real API data structure
- **Error Handling**: Missing error cases not discovered until production
- **Scalability**: Performance with real data sizes unknown

## Scenarios Where This Causes Issues

### Scenario 1: Real Node Lacks Mock Fields
```typescript
// Real API node:
{
  id: "real_node_123",
  label: "Actual Research Paper",
  node_type: "Entity",
  properties: {
    degree_centrality: 0.25
    // No 'author', 'citations', 'institution' fields
  }
}

// NodeDetailsPanel tries to display:
<div>Author: {data.properties.author}</div>     // → undefined
<div>Citations: {data.properties.citations}</div> // → undefined

// UI shows "Author: undefined" instead of handling missing data gracefully
```

### Scenario 2: API Field Name Mismatch
```typescript
// Mock expects 'name', API provides 'label'
const data = { ...mockData, ...node };

// If real node has 'label' but mock has 'name':
// UI still shows mock 'name' instead of real 'label'
```

### Scenario 3: Production Deployment
```typescript
// Production users see:
// - Every node authored by "Dr. Sarah Chen"
// - Every node from "MIT AI Lab"  
// - Every node has exactly 342 citations
// - All timestamps from January 2024

// Obviously fake data destroys credibility
```

## Proposed Solutions

### Solution 1: Remove Mock Data and Handle Missing Fields
```typescript
// NodeDetailsPanel.tsx - Remove mock data entirely
export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose 
}) => {
  // Use only real node data
  const nodeData = node;
  
  // Helper function to safely get nested properties
  const getProperty = (path: string, defaultValue: any = 'N/A') => {
    return path.split('.').reduce((obj, key) => obj?.[key], nodeData) ?? defaultValue;
  };

  return (
    <Card className="glass-panel w-96 max-h-[80vh] overflow-hidden">
      <CardHeader>
        <CardTitle>{nodeData.label || nodeData.id}</CardTitle>
        <Badge className={getNodeTypeColor(nodeData.node_type)}>
          {nodeData.node_type}
        </Badge>
      </CardHeader>
      
      <CardContent>
        {/* Summary - only show if exists */}
        {nodeData.properties?.summary && (
          <div>
            <h4>Summary</h4>
            <p>{nodeData.properties.summary}</p>
          </div>
        )}
        
        {/* Properties - only show existing properties */}
        <div>
          <h4>Properties</h4>
          {Object.entries(nodeData.properties || {}).map(([key, value]) => (
            <div key={key}>
              <span>{formatPropertyName(key)}:</span>
              <span>{formatPropertyValue(value)}</span>
            </div>
          ))}
        </div>
        
        {/* Centrality - only show if exists */}
        {nodeData.properties && hasCentralityData(nodeData.properties) && (
          <div>
            <h4>Centrality Metrics</h4>
            {renderCentralityMetrics(nodeData.properties)}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
```

### Solution 2: Create Data Transformation Layer
```typescript
// src/utils/dataTransforms.ts
interface NodeDisplayData {
  id: string;
  title: string;
  type: string;
  summary?: string;
  properties: Record<string, any>;
  centrality: Record<string, number>;
  timestamps?: {
    created?: string;
    updated?: string;
  };
  connectionCount?: number;
}

export const transformNodeForDisplay = (apiNode: GraphNode): NodeDisplayData => {
  return {
    id: apiNode.id,
    title: apiNode.label || apiNode.id,
    type: apiNode.node_type,
    summary: apiNode.properties?.summary || apiNode.properties?.description,
    properties: extractDisplayProperties(apiNode.properties || {}),
    centrality: extractCentralityMetrics(apiNode.properties || {}),
    timestamps: {
      created: apiNode.properties?.created_at || apiNode.properties?.timestamp,
      updated: apiNode.properties?.updated_at
    },
    connectionCount: apiNode.properties?.degree_centrality 
      ? Math.round(apiNode.properties.degree_centrality * 100)
      : undefined
  };
};

const extractDisplayProperties = (properties: Record<string, any>) => {
  const displayProps: Record<string, any> = {};
  
  // Map known properties to display names
  const propertyMappings = {
    'author': 'Author',
    'year': 'Year',
    'field': 'Field',
    'category': 'Category',
    'source': 'Source'
  };
  
  for (const [key, value] of Object.entries(properties)) {
    if (propertyMappings[key] && value !== undefined) {
      displayProps[propertyMappings[key]] = value;
    }
  }
  
  return displayProps;
};

const extractCentralityMetrics = (properties: Record<string, any>) => {
  const metrics: Record<string, number> = {};
  
  const centralityMappings = {
    'degree_centrality': 'Degree',
    'betweenness_centrality': 'Betweenness', 
    'pagerank_centrality': 'PageRank',
    'eigenvector_centrality': 'Eigenvector'
  };
  
  for (const [key, displayName] of Object.entries(centralityMappings)) {
    if (typeof properties[key] === 'number') {
      metrics[displayName] = properties[key];
    }
  }
  
  return metrics;
};
```

### Solution 3: Add Proper Loading and Error States
```typescript
// NodeDetailsPanel.tsx - Handle missing data gracefully
export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose 
}) => {
  const displayData = useMemo(() => transformNodeForDisplay(node), [node]);
  
  if (!node) {
    return (
      <Card className="glass-panel w-96">
        <CardContent>
          <div className="text-muted-foreground">No node data available</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="glass-panel w-96 max-h-[80vh] overflow-hidden">
      {/* Node Title and Type */}
      <CardHeader>
        <CardTitle>{displayData.title}</CardTitle>
        <Badge className={getNodeTypeColor(displayData.type)}>
          {displayData.type}
        </Badge>
      </CardHeader>
      
      <CardContent>
        {/* Summary - with fallback */}
        {displayData.summary ? (
          <div>
            <h4>Summary</h4>
            <p>{displayData.summary}</p>
          </div>
        ) : (
          <div className="text-muted-foreground text-sm">
            No summary available for this node
          </div>
        )}
        
        {/* Properties - handle empty state */}
        <div>
          <h4>Properties</h4>
          {Object.keys(displayData.properties).length > 0 ? (
            Object.entries(displayData.properties).map(([key, value]) => (
              <div key={key} className="flex justify-between">
                <span className="text-muted-foreground">{key}:</span>
                <span>{String(value)}</span>
              </div>
            ))
          ) : (
            <div className="text-muted-foreground text-sm">
              No additional properties available
            </div>
          )}
        </div>
        
        {/* Centrality - handle missing metrics */}
        {Object.keys(displayData.centrality).length > 0 && (
          <div>
            <h4>Centrality Metrics</h4>
            {Object.entries(displayData.centrality).map(([metric, value]) => (
              <div key={metric}>
                <div className="flex justify-between">
                  <span>{metric}</span>
                  <span>{(value * 100).toFixed(1)}%</span>
                </div>
                <Progress value={value * 100} className="h-1.5" />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
```

### Solution 4: Environment-Based Data Strategy
```typescript
// src/utils/dataProvider.ts
const isDevelopment = process.env.NODE_ENV === 'development';
const ENABLE_MOCK_DATA = process.env.REACT_APP_ENABLE_MOCK_DATA === 'true';

export const getNodeDisplayData = (node: GraphNode | null): NodeDisplayData | null => {
  if (!node) {
    if (isDevelopment && ENABLE_MOCK_DATA) {
      return getDevMockNode();
    }
    return null;
  }
  
  const transformedData = transformNodeForDisplay(node);
  
  // In development, optionally augment with mock data for missing fields
  if (isDevelopment && ENABLE_MOCK_DATA) {
    return augmentWithMockData(transformedData);
  }
  
  return transformedData;
};

const getDevMockNode = (): NodeDisplayData => ({
  id: 'dev_mock_node',
  title: '[DEV] Mock Node Data',
  type: 'Entity',
  summary: '[DEV] This is mock data for development',
  properties: {
    'Status': 'Development Mock Data'
  },
  centrality: {},
  timestamps: {
    created: new Date().toISOString()
  }
});
```

## Recommended Solution
**Combination of Solutions 1, 2, and 3**: Remove mock data, create data transformation layer, and handle missing data gracefully.

### Benefits
- **Data Accuracy**: Users see real data from their graph
- **Production Ready**: No fake data in production
- **Robust**: Handles missing/malformed data gracefully
- **Maintainable**: Clear separation between API data and display logic
- **Testable**: Can test with various real data scenarios

## Implementation Plan

### Phase 1: Data Transformation Layer
1. Create `transformNodeForDisplay` utility
2. Map API fields to display fields
3. Handle missing data scenarios

### Phase 2: Remove Mock Data
1. Remove hardcoded mock objects from components
2. Update components to use transformation layer
3. Add proper fallbacks for missing data

### Phase 3: Improve Error Handling
1. Add loading states for data fetch
2. Add error states for failed data
3. Add empty states for missing properties

### Phase 4: Testing with Real Data
1. Test with various API response formats
2. Test with missing/incomplete data
3. Verify performance with real data sizes

## Testing Strategy
1. **API Integration Testing**: Test with real API responses
2. **Missing Data Testing**: Test components with incomplete data
3. **Error Scenario Testing**: Test with malformed API responses
4. **Visual Testing**: Verify UI handles all data scenarios correctly

## Priority Justification
This is Medium Priority because:
- **User Trust**: Fake data undermines application credibility
- **Production Readiness**: Prevents proper production deployment
- **Development Quality**: Makes testing and integration difficult
- **Data Integrity**: Real vs fake data inconsistencies cause confusion

## Related Issues
- [Issue #011: Missing Prop Validation](./011-missing-prop-validation.md)
- [Issue #014: Missing Loading States](./014-missing-loading-states.md)
- [Issue #021: Incomplete Error Handling](../low/021-incomplete-error-handling.md)

## Dependencies
- API data structure understanding
- Data transformation utilities
- Error handling patterns
- Loading state management

## Estimated Fix Time
**3-4 hours** for removing mock data and implementing proper data transformation with error handling