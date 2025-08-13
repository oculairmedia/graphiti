/**
 * Debug utility to inspect Cosmograph's internal DuckDB schema
 */

export async function inspectCosmographSchema(cosmographRef: any) {
  if (!cosmographRef?.current) {
    console.log('[Schema Debug] No cosmograph instance');
    return;
  }

  const cosmograph = cosmographRef.current;
  
  // Try to access internal DuckDB instance
  const internalKeys = Object.keys(cosmograph);
  console.log('[Schema Debug] Cosmograph internal keys:', internalKeys);
  
  // Look for DuckDB-related properties
  const duckdbKeys = internalKeys.filter(key => 
    key.includes('duck') || 
    key.includes('db') || 
    key.includes('sql') ||
    key.includes('_conn') ||
    key.includes('_connection')
  );
  
  console.log('[Schema Debug] Potential DuckDB keys:', duckdbKeys);
  
  // Try to access the upload data method to see what it expects
  if (cosmograph.addPoints) {
    console.log('[Schema Debug] addPoints signature:', cosmograph.addPoints.toString().substring(0, 200));
  }
  
  // Log a sample point to see what Cosmograph expects
  const samplePoint = {
    index: 999,
    id: 'test-node',
    label: 'Test Node',
    node_type: 'Test',
    summary: null,
    degree_centrality: 0,
    pagerank_centrality: 0,
    betweenness_centrality: 0,
    eigenvector_centrality: 0,
    x: null,
    y: null,
    color: '#ff0000',
    size: 5,
    created_at_timestamp: null,
    cluster: 'Test',
    clusterStrength: 0.7,
    idx: 999,
    name: 'Test Node'
  };
  
  console.log('[Schema Debug] Sample point fields:', Object.keys(samplePoint));
  console.log('[Schema Debug] Sample point field count:', Object.keys(samplePoint).length);
  
  // Try to trace what happens when we add a point
  try {
    // Create a proxy to intercept property access
    const trackedPoint = new Proxy(samplePoint, {
      get(target, prop) {
        console.log(`[Schema Debug] Cosmograph accessed field: ${String(prop)}`);
        return target[prop as keyof typeof target];
      }
    });
    
    // This will fail but we'll see what fields Cosmograph tries to access
    // cosmograph.addPoints([trackedPoint]);
  } catch (error) {
    console.log('[Schema Debug] Expected error during tracing:', error);
  }
  
  return {
    internalKeys,
    duckdbKeys,
    sampleFieldCount: Object.keys(samplePoint).length
  };
}

// Export a function to attach to window for debugging
export function attachSchemaDebugger() {
  if (typeof window !== 'undefined') {
    (window as any).debugCosmographSchema = inspectCosmographSchema;
    console.log('[Schema Debug] Attached debugger to window.debugCosmographSchema');
  }
}