# Bug Fix: Size Multiplier Not Working in Graph Controls

## Issue Description

The size multiplier control in the graph's Node Styling tab was not functioning properly. Users could adjust the slider, and the UI would show the updated value, but the actual node sizes in the graph visualization remained unchanged.

## Root Cause Analysis

### Problem Location
The issue was in `frontend/src/components/GraphCanvasV2.tsx` in the `pointSizeRange` calculation.

### What Was Wrong
1. **Missing Multiplier Application**: The `pointSizeRange` calculation was using `config.minNodeSize` and `config.maxNodeSize` but completely ignoring `config.sizeMultiplier`.

2. **Incomplete Dependency Array**: The `useMemo` dependency array was missing `config.sizeMultiplier`, so even if the multiplier was applied, the calculation wouldn't re-run when the multiplier changed.

### Code Analysis
The problematic code was:

```typescript
const pointSizeRange = useMemo(() => {
  const baseMin = config.minNodeSize || 2;
  const baseMax = config.maxNodeSize || 8;

  // Size mapping logic...
  switch (config.sizeMapping) {
    case 'uniform':
      return [uniformSize, uniformSize + 0.1];
    case 'degree':
      return [baseMin, baseMax]; // ❌ No multiplier applied
    // ... other cases
  }
}, [config.sizeMapping, config.minNodeSize, config.maxNodeSize]); // ❌ Missing sizeMultiplier
```

## Solution Implemented

### Changes Made
1. **Added Multiplier Extraction**: Extract the multiplier value with fallback to 1.
2. **Restructured Calculation**: Separate the size mapping logic from the final multiplier application.
3. **Applied Multiplier**: Apply the multiplier to both min and max values of the final range.
4. **Updated Dependencies**: Added `config.sizeMultiplier` to the dependency array.

### Fixed Code
```typescript
const pointSizeRange = useMemo(() => {
  const baseMin = config.minNodeSize || 2;
  const baseMax = config.maxNodeSize || 8;
  const multiplier = config.sizeMultiplier || 1; // ✅ Extract multiplier

  let adjustedMin: number;
  let adjustedMax: number;

  // Size mapping logic (unchanged)
  switch (config.sizeMapping) {
    case 'uniform':
      const uniformSize = (baseMin + baseMax) / 2;
      adjustedMin = uniformSize;
      adjustedMax = uniformSize + 0.1;
      break;
    case 'degree':
    case 'connections':
      adjustedMin = baseMin;
      adjustedMax = baseMax;
      break;
    // ... other cases
  }

  // ✅ Apply size multiplier to the final range
  return [adjustedMin * multiplier, adjustedMax * multiplier];
}, [config.sizeMapping, config.minNodeSize, config.maxNodeSize, config.sizeMultiplier]); // ✅ Added sizeMultiplier
```

## Cleanup Scripts for Unconnected Points

### Location of Cleanup Scripts
Based on the codebase analysis, the cleanup scripts for unconnected points are located in several places:

#### 1. **Main Maintenance Scripts** (Root Directory)
- `maintenance_dedupe_entities.py` - Main deduplication script that can remove duplicate nodes
- `run_deduplication.py` - Script to find and resolve duplicate entities
- Scripts referenced in settings but may be missing:
  - `scripts/check_duplicates.py`
  - `scripts/deduplicate_and_merge.py`
  - `scripts/merge_duplicates_simple.py`
  - `scripts/cleanup_all_duplicates.py`
  - `scripts/clear_database.py`

#### 2. **Core Maintenance Utilities** (`graphiti_core/utils/maintenance/`)
- `graph_data_operations.py` - Contains `clear_data()` function for database cleanup
- `node_operations.py` - Contains node merging and deletion functions
- `edge_operations.py` - Contains edge cleanup and orphaned edge removal
- `community_operations.py` - Contains `remove_communities()` function

#### 3. **Frontend Utilities** (`frontend/src/utils/`)
- `graphNodeOperations.ts` - Contains `findIsolatedNodes()` function for client-side detection

#### 4. **Cron Scripts** (`scripts/`)
- `deduplication_cron.sh` - Automated deduplication maintenance
- `entity_extraction_cron.sh` - Entity extraction maintenance

### Key Functions for Cleanup
```python
# Remove orphaned edges
async def remove_orphaned_edges(driver: GraphDriver, group_id: str = None) -> int

# Clear all data or specific groups
async def clear_data(driver: GraphDriver, group_ids: list[str] | None = None)

# Find isolated nodes (frontend)
function findIsolatedNodes(nodes: GraphNode[], links: any[]): GraphNode[]

# Merge duplicate nodes
async def merge_node_into(driver, canonical_uuid: str, duplicate_uuid: str, delete_duplicate: bool = True)
```

## Technical Details

### Component Architecture
- **UI Control**: `frontend/src/components/ControlPanel/NodeStylingTab.tsx` - Contains the size multiplier slider
- **Config Management**: The multiplier value is stored in the config object and passed down through props
- **Rendering**: `frontend/src/components/GraphCanvasV2.tsx` - Uses the multiplier in `pointSizeRange` calculation
- **Graph Library**: The `pointSizeRange` is passed to the Cosmograph component which handles the actual node rendering

### Data Flow
1. User adjusts size multiplier slider in NodeStylingTab
2. `onConfigUpdate({ sizeMultiplier: value })` is called
3. Config is updated and passed to GraphCanvasV2
4. `pointSizeRange` useMemo recalculates with new multiplier
5. New range is passed to Cosmograph component
6. Nodes are re-rendered with scaled sizes

### Usage Examples
```bash
# Run main deduplication script
python maintenance_dedupe_entities.py

# Run deduplication with specific group
python run_deduplication.py --group-id "your-group-id"

# Clear all data (use with caution!)
python -c "
import asyncio
from graphiti_core.utils.maintenance.graph_data_operations import clear_data
from graphiti_core.driver import GraphDriver
async def main():
    driver = GraphDriver()
    await clear_data(driver)
asyncio.run(main())
"

# Run automated cleanup via cron
./scripts/deduplication_cron.sh
```

## Testing Recommendations

### Manual Testing
1. Open the graph visualization
2. Navigate to the Node Styling tab in the control panel
3. Locate the "Size Multiplier" slider
4. Adjust the slider from 0.1x to 3.0x
5. Verify that node sizes change proportionally in real-time
6. Test with different size mapping strategies (uniform, degree, betweenness, pagerank)
7. Confirm that relative size differences are maintained while overall scale changes

### Edge Cases to Test
- Multiplier at minimum value (0.1x)
- Multiplier at maximum value (3.0x)
- Multiplier at default value (1.0x)
- Switching size mapping strategies while multiplier is not 1.0x
- Large graphs with many nodes
- Graphs with extreme centrality value distributions

## Related Files Modified
- `frontend/src/components/GraphCanvasV2.tsx` - Fixed the pointSizeRange calculation

## Related Files (No Changes Needed)
- `frontend/src/components/ControlPanel/NodeStylingTab.tsx` - UI control (working correctly)
- `frontend/src/components/ControlPanel.tsx` - Config management (working correctly)

## Impact
- ✅ Size multiplier now works as expected
- ✅ Real-time updates when slider is adjusted
- ✅ Maintains compatibility with all size mapping strategies
- ✅ No breaking changes to existing functionality
- ✅ Performance impact minimal (just multiplication in existing calculation)
- ✅ Documented cleanup script locations for future maintenance

## Future Considerations
- Consider adding visual feedback when multiplier is not at default (1.0x)
- Could add preset multiplier buttons (0.5x, 1x, 2x) for quick access
- Might want to persist multiplier value in user preferences
- Create missing cleanup scripts referenced in settings
- Add automated isolated node detection and cleanup functionality
