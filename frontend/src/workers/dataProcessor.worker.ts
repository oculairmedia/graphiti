/**
 * Web Worker for heavy data processing operations
 * 
 * GRAPH-82: Uses canonical types from @/types/graph
 */

// Note: Workers can't use path aliases, so we define minimal interfaces
// that match the canonical types. These should stay in sync with types/graph.ts

interface GraphNode {
  id: string;
  label?: string;
  name?: string;
  node_type: string;
  properties?: Record<string, unknown>;
  size?: number;
  created_at?: string;
  x?: number;
  y?: number;
}

interface GraphLink {
  source?: string;
  target?: string;
  from?: string;
  to?: string;
  edge_type?: string;
  weight?: number;
  created_at?: string;
  updated_at?: string;
}

interface ProcessDataMessage {
  type: 'TRANSFORM_DATA';
  data: {
    nodes: GraphNode[];
    links: GraphLink[];
    filterConfig: Record<string, unknown>;
  };
}

interface TransformedNode extends GraphNode {
  index: number;
  centrality: number;
  cluster: string;
  clusterStrength: number;
  degree_centrality: number;
  pagerank_centrality: number;
  betweenness_centrality: number;
  eigenvector_centrality: number;
  created_at_timestamp: number | null;
}

interface TransformedLink {
  source: string;
  sourceIndex: number;
  target: string;
  targetIndex: number;
  edge_type: string;
  weight: number;
  created_at?: string;
  updated_at?: string;
}

interface ProcessDataResponse {
  type: 'DATA_TRANSFORMED';
  data: {
    nodes: TransformedNode[];
    links: TransformedLink[];
    nodeIndexMap: [string, number][];
  };
}

/**
 * Transform a raw node into an indexed node with computed properties
 */
function transformNode(node: GraphNode, index: number): TransformedNode {
  const props = node.properties || {};
  const createdAt = (props.created_at as string) || node.created_at || (props.created as string) || null;
  const degree = Number(props.degree_centrality || 0);
  
  return {
    id: String(node.id),
    index,
    label: String(node.label || node.name || node.id),
    node_type: String(node.node_type || 'Unknown'),
    centrality: Number(props.degree_centrality || props.pagerank_centrality || node.size || 1),
    cluster: String(node.node_type || 'Unknown'),
    clusterStrength: 0.7,
    degree_centrality: degree,
    pagerank_centrality: Number(props.pagerank_centrality || 0),
    betweenness_centrality: Number(props.betweenness_centrality || 0),
    eigenvector_centrality: Number(props.eigenvector_centrality || 0),
    created_at: createdAt,
    created_at_timestamp: createdAt ? new Date(createdAt).getTime() : null,
    // Preserve original properties
    properties: node.properties,
    size: node.size,
    x: node.x,
    y: node.y,
  };
}

/**
 * Transform a raw link into an indexed link
 */
function transformLink(link: GraphLink, nodeIndexMap: Map<string, number>): TransformedLink | null {
  const source = String(link.source || link.from);
  const target = String(link.target || link.to);
  
  const sourceIndex = nodeIndexMap.get(source);
  const targetIndex = nodeIndexMap.get(target);
  
  if (sourceIndex === undefined || targetIndex === undefined) {
    return null;
  }
  
  return {
    source,
    sourceIndex,
    target,
    targetIndex,
    edge_type: String(link.edge_type || 'default'),
    weight: Number(link.weight || 1),
    created_at: link.created_at,
    updated_at: link.updated_at,
  };
}

/**
 * Process large datasets in chunks to avoid blocking the worker thread
 */
async function processDataInChunks(
  nodes: GraphNode[],
  links: GraphLink[]
): Promise<ProcessDataResponse['data']> {
  const CHUNK_SIZE = 1000;
  const transformedNodes: TransformedNode[] = [];
  const nodeIndexMap = new Map<string, number>();
  
  // Process nodes in chunks
  for (let i = 0; i < nodes.length; i += CHUNK_SIZE) {
    const chunk = nodes.slice(i, i + CHUNK_SIZE);
    const transformed = chunk.map((node, idx) => {
      const globalIndex = i + idx;
      const transformedNode = transformNode(node, globalIndex);
      nodeIndexMap.set(transformedNode.id, globalIndex);
      return transformedNode;
    });
    transformedNodes.push(...transformed);
    
    // Yield to allow other operations
    if (i % (CHUNK_SIZE * 10) === 0) {
      await new Promise(resolve => setTimeout(resolve, 0));
    }
  }
  
  // Process links in chunks
  const transformedLinks: TransformedLink[] = [];
  for (let i = 0; i < links.length; i += CHUNK_SIZE) {
    const chunk = links.slice(i, i + CHUNK_SIZE);
    const transformed = chunk
      .map(link => transformLink(link, nodeIndexMap))
      .filter((link): link is TransformedLink => link !== null);
    transformedLinks.push(...transformed);
    
    // Yield to allow other operations
    if (i % (CHUNK_SIZE * 10) === 0) {
      await new Promise(resolve => setTimeout(resolve, 0));
    }
  }
  
  return {
    nodes: transformedNodes,
    links: transformedLinks,
    nodeIndexMap: Array.from(nodeIndexMap.entries()),
  };
}

// Handle messages from main thread
self.addEventListener('message', async (event: MessageEvent<ProcessDataMessage>) => {
  const { type, data } = event.data;
  
  switch (type) {
    case 'TRANSFORM_DATA':
      try {
        const result = await processDataInChunks(data.nodes, data.links);
        
        self.postMessage({
          type: 'DATA_TRANSFORMED',
          data: result,
        });
      } catch (error) {
        self.postMessage({
          type: 'ERROR',
          error: error instanceof Error ? error.message : 'Unknown error',
        });
      }
      break;
  }
});

export {};
