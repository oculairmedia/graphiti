// WebWorker for heavy graph computations
self.addEventListener('message', async (event) => {
  const { type, data } = event.data;
  
  switch (type) {
    case 'PROCESS_LAYOUT':
      const layoutResult = await processLayout(data);
      self.postMessage({ type: 'LAYOUT_COMPLETE', data: layoutResult });
      break;
      
    case 'CALCULATE_CENTRALITY':
      const centralityResult = calculateCentrality(data);
      self.postMessage({ type: 'CENTRALITY_COMPLETE', data: centralityResult });
      break;
      
    case 'CLUSTER_DETECTION':
      const clusters = detectClusters(data);
      self.postMessage({ type: 'CLUSTERS_COMPLETE', data: clusters });
      break;
      
    case 'PATH_FINDING':
      const path = findShortestPath(data);
      self.postMessage({ type: 'PATH_COMPLETE', data: path });
      break;
      
    case 'FILTER_NODES':
      const filtered = filterNodesEfficiently(data);
      self.postMessage({ type: 'FILTER_COMPLETE', data: filtered });
      break;
  }
});

// Force-directed layout calculation
async function processLayout(data: {
  nodes: any[],
  edges: any[],
  iterations: number
}): Promise<{ positions: Float32Array }> {
  const { nodes, edges, iterations = 100 } = data;
  const positions = new Float32Array(nodes.length * 2);
  
  // Initialize random positions
  for (let i = 0; i < nodes.length; i++) {
    positions[i * 2] = (Math.random() - 0.5) * 1000;
    positions[i * 2 + 1] = (Math.random() - 0.5) * 1000;
  }
  
  // Build adjacency list
  const adjacency = new Map<number, Set<number>>();
  edges.forEach(edge => {
    const sourceIdx = edge.sourceidx;
    const targetIdx = edge.targetidx;
    
    if (!adjacency.has(sourceIdx)) adjacency.set(sourceIdx, new Set());
    if (!adjacency.has(targetIdx)) adjacency.set(targetIdx, new Set());
    
    adjacency.get(sourceIdx)!.add(targetIdx);
    adjacency.get(targetIdx)!.add(sourceIdx);
  });
  
  // Force-directed layout iterations
  const k = Math.sqrt(1000000 / nodes.length); // Optimal distance
  const temperature = 100;
  
  for (let iter = 0; iter < iterations; iter++) {
    const displacement = new Float32Array(nodes.length * 2);
    const t = temperature * (1 - iter / iterations);
    
    // Repulsive forces
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = positions[i * 2] - positions[j * 2];
        const dy = positions[i * 2 + 1] - positions[j * 2 + 1];
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        
        const force = (k * k) / dist;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        
        displacement[i * 2] += fx;
        displacement[i * 2 + 1] += fy;
        displacement[j * 2] -= fx;
        displacement[j * 2 + 1] -= fy;
      }
    }
    
    // Attractive forces for edges
    edges.forEach(edge => {
      const i = edge.sourceidx;
      const j = edge.targetidx;
      
      const dx = positions[i * 2] - positions[j * 2];
      const dy = positions[i * 2 + 1] - positions[j * 2 + 1];
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      
      const force = (dist * dist) / k;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      
      displacement[i * 2] -= fx * 0.5;
      displacement[i * 2 + 1] -= fy * 0.5;
      displacement[j * 2] += fx * 0.5;
      displacement[j * 2 + 1] += fy * 0.5;
    });
    
    // Apply displacement with temperature
    for (let i = 0; i < nodes.length; i++) {
      const dx = displacement[i * 2];
      const dy = displacement[i * 2 + 1];
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      
      const limitedDist = Math.min(dist, t);
      positions[i * 2] += (dx / dist) * limitedDist;
      positions[i * 2 + 1] += (dy / dist) * limitedDist;
    }
    
    // Report progress every 10 iterations
    if (iter % 10 === 0) {
      self.postMessage({
        type: 'LAYOUT_PROGRESS',
        data: { progress: iter / iterations }
      });
    }
  }
  
  return { positions };
}

// Calculate various centrality metrics
function calculateCentrality(data: {
  nodes: any[],
  edges: any[]
}): any {
  const { nodes, edges } = data;
  
  // Build adjacency list
  const adjacency = new Map<string, Set<string>>();
  const degrees = new Map<string, number>();
  
  nodes.forEach(node => {
    adjacency.set(node.id, new Set());
    degrees.set(node.id, 0);
  });
  
  edges.forEach(edge => {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
    degrees.set(edge.source, (degrees.get(edge.source) || 0) + 1);
    degrees.set(edge.target, (degrees.get(edge.target) || 0) + 1);
  });
  
  // Degree centrality
  const degreeCentrality = new Map<string, number>();
  const maxDegree = Math.max(...degrees.values());
  
  degrees.forEach((degree, nodeId) => {
    degreeCentrality.set(nodeId, degree / maxDegree);
  });
  
  // Betweenness centrality (simplified)
  const betweenness = new Map<string, number>();
  nodes.forEach(node => betweenness.set(node.id, 0));
  
  // Sample calculation for performance
  const sampleSize = Math.min(100, nodes.length);
  const sampledNodes = nodes.slice(0, sampleSize);
  
  sampledNodes.forEach(source => {
    const visited = new Set<string>();
    const queue = [source.id];
    const paths = new Map<string, number>();
    paths.set(source.id, 1);
    
    while (queue.length > 0) {
      const current = queue.shift()!;
      if (visited.has(current)) continue;
      visited.add(current);
      
      adjacency.get(current)?.forEach(neighbor => {
        if (!visited.has(neighbor)) {
          queue.push(neighbor);
          paths.set(neighbor, (paths.get(neighbor) || 0) + (paths.get(current) || 1));
        }
      });
    }
    
    // Update betweenness
    paths.forEach((count, nodeId) => {
      if (nodeId !== source.id) {
        betweenness.set(nodeId, (betweenness.get(nodeId) || 0) + count);
      }
    });
  });
  
  return {
    degree: Object.fromEntries(degreeCentrality),
    betweenness: Object.fromEntries(betweenness)
  };
}

// Cluster detection using connected components
function detectClusters(data: {
  nodes: any[],
  edges: any[]
}): any {
  const { nodes, edges } = data;
  
  // Build adjacency list
  const adjacency = new Map<string, Set<string>>();
  nodes.forEach(node => adjacency.set(node.id, new Set()));
  edges.forEach(edge => {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  });
  
  // Find connected components
  const visited = new Set<string>();
  const clusters: string[][] = [];
  
  nodes.forEach(node => {
    if (!visited.has(node.id)) {
      const cluster: string[] = [];
      const queue = [node.id];
      
      while (queue.length > 0) {
        const current = queue.shift()!;
        if (visited.has(current)) continue;
        
        visited.add(current);
        cluster.push(current);
        
        adjacency.get(current)?.forEach(neighbor => {
          if (!visited.has(neighbor)) {
            queue.push(neighbor);
          }
        });
      }
      
      if (cluster.length > 0) {
        clusters.push(cluster);
      }
    }
  });
  
  // Sort clusters by size
  clusters.sort((a, b) => b.length - a.length);
  
  return {
    clusters,
    clusterCount: clusters.length,
    largestClusterSize: clusters[0]?.length || 0
  };
}

// Find shortest path using BFS
function findShortestPath(data: {
  nodes: any[],
  edges: any[],
  sourceId: string,
  targetId: string
}): any {
  const { nodes, edges, sourceId, targetId } = data;
  
  // Build adjacency list
  const adjacency = new Map<string, Set<string>>();
  nodes.forEach(node => adjacency.set(node.id, new Set()));
  edges.forEach(edge => {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  });
  
  // BFS
  const visited = new Set<string>();
  const queue: { id: string, path: string[] }[] = [
    { id: sourceId, path: [sourceId] }
  ];
  
  while (queue.length > 0) {
    const { id, path } = queue.shift()!;
    
    if (id === targetId) {
      return { path, length: path.length - 1 };
    }
    
    if (visited.has(id)) continue;
    visited.add(id);
    
    adjacency.get(id)?.forEach(neighbor => {
      if (!visited.has(neighbor)) {
        queue.push({ id: neighbor, path: [...path, neighbor] });
      }
    });
  }
  
  return { path: null, length: -1 };
}

// Efficient node filtering
function filterNodesEfficiently(data: {
  nodes: any[],
  filters: {
    type?: string[],
    minCentrality?: number,
    maxCentrality?: number,
    searchTerm?: string
  }
}): any {
  const { nodes, filters } = data;
  const { type, minCentrality, maxCentrality, searchTerm } = filters;
  
  let filtered = nodes;
  
  if (type && type.length > 0) {
    const typeSet = new Set(type);
    filtered = filtered.filter(node => typeSet.has(node.node_type));
  }
  
  if (minCentrality !== undefined) {
    filtered = filtered.filter(node => 
      (node.degree_centrality || 0) >= minCentrality
    );
  }
  
  if (maxCentrality !== undefined) {
    filtered = filtered.filter(node => 
      (node.degree_centrality || 0) <= maxCentrality
    );
  }
  
  if (searchTerm) {
    const term = searchTerm.toLowerCase();
    filtered = filtered.filter(node => 
      node.label?.toLowerCase().includes(term) ||
      node.summary?.toLowerCase().includes(term) ||
      node.id?.toLowerCase().includes(term)
    );
  }
  
  return {
    nodes: filtered,
    count: filtered.length
  };
}

export {};