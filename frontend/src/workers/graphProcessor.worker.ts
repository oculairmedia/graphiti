/**
 * Web Worker for heavy graph data processing
 * Offloads CPU-intensive tasks from the main thread
 */

import * as arrow from 'apache-arrow';

interface WorkerMessage {
  type: 'PROCESS_ARROW' | 'FILTER_NODES' | 'CALCULATE_LAYOUT' | 'BUILD_SPATIAL_INDEX' | 'TRANSFORM_DATA';
  payload: any;
  id: string;
}

interface WorkerResponse {
  type: string;
  result?: any;
  error?: string;
  id: string;
}

// Node filtering logic
function filterNodes(nodes: any[], filters: any): any[] {
  return nodes.filter(node => {
    // Type filter
    if (filters.nodeTypes?.length > 0 && !filters.nodeTypes.includes(node.node_type)) {
      return false;
    }

    // Degree filter
    if (filters.minDegree !== undefined || filters.maxDegree !== undefined) {
      const degree = node.properties?.degree_centrality || 0;
      if (filters.minDegree !== undefined && degree < filters.minDegree) return false;
      if (filters.maxDegree !== undefined && degree > filters.maxDegree) return false;
    }

    // Date range filter
    if (filters.startDate || filters.endDate) {
      const nodeDate = new Date(node.created_at || node.properties?.created || 0);
      if (filters.startDate && nodeDate < new Date(filters.startDate)) return false;
      if (filters.endDate && nodeDate > new Date(filters.endDate)) return false;
    }

    // Search filter
    if (filters.search) {
      const searchLower = filters.search.toLowerCase();
      const label = (node.label || node.name || '').toLowerCase();
      const summary = (node.summary || '').toLowerCase();
      if (!label.includes(searchLower) && !summary.includes(searchLower)) {
        return false;
      }
    }

    return true;
  });
}

// Process Arrow format data
function processArrowData(buffer: ArrayBuffer): { nodes: any[], edges: any[] } {
  try {
    const table = arrow.tableFromIPC(new Uint8Array(buffer));
    const data = table.toArray();
    
    // Determine if this is nodes or edges based on schema
    const schema = table.schema;
    const hasNodeFields = schema.fields.some(f => f.name === 'node_type' || f.name === 'label');
    
    if (hasNodeFields) {
      // Process as nodes
      return {
        nodes: data.map((row: any) => ({
          id: row.id,
          label: row.label || row.name || row.id,
          node_type: row.node_type || row.type || 'Unknown',
          properties: {
            degree_centrality: row.degree_centrality || row.degree || 0,
            pagerank: row.pagerank || 0,
            betweenness: row.betweenness || 0,
            created_at: row.created_at,
            ...row
          }
        })),
        edges: []
      };
    } else {
      // Process as edges
      return {
        nodes: [],
        edges: data.map((row: any) => ({
          source: row.source || row.from,
          target: row.target || row.to,
          edge_type: row.edge_type || row.type || 'RELATED',
          weight: row.weight || 1,
          properties: row
        }))
      };
    }
  } catch (error) {
    console.error('[Worker] Failed to process Arrow data:', error);
    throw error;
  }
}

// Calculate force-directed layout (simplified)
function calculateLayout(nodes: any[], edges: any[], options: any = {}): Map<string, { x: number, y: number }> {
  const positions = new Map<string, { x: number, y: number }>();
  
  // Initialize random positions
  nodes.forEach(node => {
    positions.set(node.id, {
      x: (Math.random() - 0.5) * 1000,
      y: (Math.random() - 0.5) * 1000
    });
  });

  // Simple force simulation (very basic)
  const iterations = options.iterations || 50;
  const repulsion = options.repulsion || 100;
  const attraction = options.attraction || 0.01;
  
  for (let iter = 0; iter < iterations; iter++) {
    const forces = new Map<string, { fx: number, fy: number }>();
    
    // Initialize forces
    nodes.forEach(node => {
      forces.set(node.id, { fx: 0, fy: 0 });
    });

    // Repulsion between all nodes
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const node1 = nodes[i];
        const node2 = nodes[j];
        const pos1 = positions.get(node1.id)!;
        const pos2 = positions.get(node2.id)!;
        
        const dx = pos2.x - pos1.x;
        const dy = pos2.y - pos1.y;
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.1;
        
        const force = repulsion / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        
        const f1 = forces.get(node1.id)!;
        const f2 = forces.get(node2.id)!;
        
        f1.fx -= fx;
        f1.fy -= fy;
        f2.fx += fx;
        f2.fy += fy;
      }
    }

    // Attraction along edges
    edges.forEach(edge => {
      const pos1 = positions.get(edge.source);
      const pos2 = positions.get(edge.target);
      
      if (pos1 && pos2) {
        const dx = pos2.x - pos1.x;
        const dy = pos2.y - pos1.y;
        const dist = Math.sqrt(dx * dx + dy * dy) + 0.1;
        
        const force = dist * attraction;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        
        const f1 = forces.get(edge.source);
        const f2 = forces.get(edge.target);
        
        if (f1) {
          f1.fx += fx;
          f1.fy += fy;
        }
        if (f2) {
          f2.fx -= fx;
          f2.fy -= fy;
        }
      }
    });

    // Apply forces
    nodes.forEach(node => {
      const pos = positions.get(node.id)!;
      const force = forces.get(node.id)!;
      
      // Apply with damping
      pos.x += force.fx * 0.1;
      pos.y += force.fy * 0.1;
    });
  }

  return positions;
}

// Build spatial index (simplified quadtree)
function buildSpatialIndex(nodes: any[], positions: Map<string, { x: number, y: number }>): any {
  // Calculate bounds
  let minX = Infinity, maxX = -Infinity;
  let minY = Infinity, maxY = -Infinity;

  nodes.forEach(node => {
    const pos = positions.get(node.id);
    if (pos) {
      minX = Math.min(minX, pos.x);
      maxX = Math.max(maxX, pos.x);
      minY = Math.min(minY, pos.y);
      maxY = Math.max(maxY, pos.y);
    }
  });

  // Build quadtree structure
  const quadtree = {
    bounds: { minX, maxX, minY, maxY },
    nodes: nodes.map(node => ({
      ...node,
      position: positions.get(node.id)
    })),
    depth: 0
  };

  return quadtree;
}

// Transform data for visualization
function transformData(data: any, options: any = {}): any {
  const { nodes, edges } = data;
  
  // Add indices for fast lookup
  const nodeIndex = new Map(nodes.map((n: any, i: number) => [n.id, i]));
  
  // Transform edges to use indices
  const transformedEdges = edges.map((e: any) => ({
    ...e,
    sourceIndex: nodeIndex.get(e.source),
    targetIndex: nodeIndex.get(e.target)
  }));

  // Calculate statistics
  const stats = {
    nodeCount: nodes.length,
    edgeCount: edges.length,
    nodeTypes: new Set(nodes.map((n: any) => n.node_type)).size,
    avgDegree: edges.length > 0 ? (edges.length * 2) / nodes.length : 0
  };

  return {
    nodes,
    edges: transformedEdges,
    stats
  };
}

// Message handler
self.addEventListener('message', async (event: MessageEvent<WorkerMessage>) => {
  const { type, payload, id } = event.data;
  
  try {
    let result: any;
    
    switch (type) {
      case 'PROCESS_ARROW':
        result = processArrowData(payload.buffer);
        break;
        
      case 'FILTER_NODES':
        result = filterNodes(payload.nodes, payload.filters);
        break;
        
      case 'CALCULATE_LAYOUT':
        result = calculateLayout(payload.nodes, payload.edges, payload.options);
        // Convert Map to plain object for serialization
        const layoutObj: any = {};
        result.forEach((pos: any, nodeId: string) => {
          layoutObj[nodeId] = pos;
        });
        result = layoutObj;
        break;
        
      case 'BUILD_SPATIAL_INDEX':
        result = buildSpatialIndex(payload.nodes, new Map(Object.entries(payload.positions)));
        break;
        
      case 'TRANSFORM_DATA':
        result = transformData(payload.data, payload.options);
        break;
        
      default:
        throw new Error(`Unknown message type: ${type}`);
    }
    
    const response: WorkerResponse = {
      type: type + '_COMPLETE',
      result,
      id
    };
    
    self.postMessage(response);
  } catch (error) {
    const response: WorkerResponse = {
      type: type + '_ERROR',
      error: error instanceof Error ? error.message : String(error),
      id
    };
    
    self.postMessage(response);
  }
});

// Export for TypeScript
export {};