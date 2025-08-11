import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { GraphNode, GraphEdge } from '../../../api/types';

interface DataTransformation {
  id: string;
  name: string;
  type: 'filter' | 'map' | 'reduce' | 'aggregate' | 'compute' | 'normalize';
  priority: number;
  enabled: boolean;
  fn: (data: any, context?: TransformContext) => any;
  dependencies?: string[];
}

interface TransformContext {
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata?: Record<string, any>;
  cache?: Map<string, any>;
  timestamp: number;
}

interface DataPipeline {
  id: string;
  name: string;
  transformations: DataTransformation[];
  cacheStrategy?: 'none' | 'memory' | 'indexed-db';
  parallelizable?: boolean;
}

interface DataKitConfig {
  pipelines?: DataPipeline[];
  defaultCacheStrategy?: 'none' | 'memory' | 'indexed-db';
  enableParallelProcessing?: boolean;
  maxWorkers?: number;
  cacheExpiry?: number; // ms
  transformationTimeout?: number; // ms
}

interface DataKitCoordinatorProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  config?: DataKitConfig;
  onDataTransformed?: (data: TransformedData) => void;
  onPipelineComplete?: (pipelineId: string, result: any) => void;
  onError?: (error: Error, pipeline?: string, transformation?: string) => void;
  children?: React.ReactNode;
}

interface TransformedData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata: Record<string, any>;
  transformationsApplied: string[];
  timestamp: number;
}

interface CoordinatorState {
  isProcessing: boolean;
  currentPipeline: string | null;
  currentTransformation: string | null;
  progress: number;
  cache: Map<string, any>;
  errors: Array<{ pipeline: string; transformation: string; error: Error }>;
}

/**
 * DataKitCoordinator - Centralized data transformation pipeline
 * Manages complex data transformations with caching and parallel processing
 */
export const DataKitCoordinator: React.FC<DataKitCoordinatorProps> = ({
  nodes,
  edges,
  config = {},
  onDataTransformed,
  onPipelineComplete,
  onError,
  children
}) => {
  const [state, setState] = useState<CoordinatorState>({
    isProcessing: false,
    currentPipeline: null,
    currentTransformation: null,
    progress: 0,
    cache: new Map(),
    errors: []
  });

  const workersRef = useRef<Worker[]>([]);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Default configuration
  const fullConfig: Required<DataKitConfig> = {
    pipelines: config.pipelines || getDefaultPipelines(),
    defaultCacheStrategy: config.defaultCacheStrategy ?? 'memory',
    enableParallelProcessing: config.enableParallelProcessing ?? true,
    maxWorkers: config.maxWorkers ?? (navigator.hardwareConcurrency || 4),
    cacheExpiry: config.cacheExpiry ?? 300000, // 5 minutes
    transformationTimeout: config.transformationTimeout ?? 10000 // 10 seconds
  };

  // Get default pipelines
  function getDefaultPipelines(): DataPipeline[] {
    return [
      {
        id: 'metrics',
        name: 'Metrics Computation',
        transformations: [
          createMetricsTransformation(),
          createNormalizationTransformation()
        ],
        cacheStrategy: 'memory',
        parallelizable: true
      },
      {
        id: 'filtering',
        name: 'Data Filtering',
        transformations: [
          createVisibilityFilter(),
          createTypeFilter()
        ],
        cacheStrategy: 'none',
        parallelizable: false
      },
      {
        id: 'enrichment',
        name: 'Data Enrichment',
        transformations: [
          createLabelEnrichment(),
          createColorEnrichment(),
          createSizeEnrichment()
        ],
        cacheStrategy: 'memory',
        parallelizable: true
      }
    ];
  }

  // Create metrics computation transformation
  function createMetricsTransformation(): DataTransformation {
    return {
      id: 'compute-metrics',
      name: 'Compute Graph Metrics',
      type: 'compute',
      priority: 1,
      enabled: true,
      fn: (data: TransformContext) => {
        const { nodes, edges } = data;
        
        // Calculate degree for each node
        const degreeMap = new Map<string, number>();
        edges.forEach(edge => {
          degreeMap.set(edge.from, (degreeMap.get(edge.from) || 0) + 1);
          degreeMap.set(edge.to, (degreeMap.get(edge.to) || 0) + 1);
        });

        // Add degree to nodes
        const enrichedNodes = nodes.map(node => ({
          ...node,
          degree: degreeMap.get(node.id) || 0,
          properties: {
            ...node.properties,
            computed_degree: degreeMap.get(node.id) || 0
          }
        }));

        return { ...data, nodes: enrichedNodes };
      }
    };
  }

  // Create normalization transformation
  function createNormalizationTransformation(): DataTransformation {
    return {
      id: 'normalize-values',
      name: 'Normalize Centrality Values',
      type: 'normalize',
      priority: 2,
      enabled: true,
      dependencies: ['compute-metrics'],
      fn: (data: TransformContext) => {
        const { nodes } = data;
        
        // Find min/max for normalization
        let minCentrality = Infinity;
        let maxCentrality = -Infinity;
        
        nodes.forEach(node => {
          const centrality = node.properties?.degree_centrality || 0;
          minCentrality = Math.min(minCentrality, centrality);
          maxCentrality = Math.max(maxCentrality, centrality);
        });

        const range = maxCentrality - minCentrality || 1;

        // Normalize values
        const normalizedNodes = nodes.map(node => ({
          ...node,
          properties: {
            ...node.properties,
            normalized_centrality: 
              ((node.properties?.degree_centrality || 0) - minCentrality) / range
          }
        }));

        return { ...data, nodes: normalizedNodes };
      }
    };
  }

  // Create visibility filter
  function createVisibilityFilter(): DataTransformation {
    return {
      id: 'filter-visible',
      name: 'Filter Visible Nodes',
      type: 'filter',
      priority: 1,
      enabled: true,
      fn: (data: TransformContext) => {
        const { nodes, edges } = data;
        
        // Filter nodes based on visibility
        const visibleNodes = nodes.filter(node => 
          node.properties?.visible !== false
        );
        
        const visibleNodeIds = new Set(visibleNodes.map(n => n.id));
        
        // Filter edges to only include those between visible nodes
        const visibleEdges = edges.filter(edge =>
          visibleNodeIds.has(edge.from) && visibleNodeIds.has(edge.to)
        );

        return { ...data, nodes: visibleNodes, edges: visibleEdges };
      }
    };
  }

  // Create type filter
  function createTypeFilter(): DataTransformation {
    return {
      id: 'filter-types',
      name: 'Filter by Node Type',
      type: 'filter',
      priority: 2,
      enabled: false, // Disabled by default
      fn: (data: TransformContext) => {
        const allowedTypes = data.metadata?.allowedTypes || [];
        if (allowedTypes.length === 0) return data;

        const { nodes, edges } = data;
        const filteredNodes = nodes.filter(node =>
          allowedTypes.includes(node.node_type)
        );
        
        const nodeIds = new Set(filteredNodes.map(n => n.id));
        const filteredEdges = edges.filter(edge =>
          nodeIds.has(edge.from) && nodeIds.has(edge.to)
        );

        return { ...data, nodes: filteredNodes, edges: filteredEdges };
      }
    };
  }

  // Create label enrichment
  function createLabelEnrichment(): DataTransformation {
    return {
      id: 'enrich-labels',
      name: 'Enrich Node Labels',
      type: 'map',
      priority: 1,
      enabled: true,
      fn: (data: TransformContext) => {
        const { nodes } = data;
        
        const enrichedNodes = nodes.map(node => ({
          ...node,
          label: node.label || node.name || node.id,
          displayLabel: formatLabel(node.label || node.name || node.id)
        }));

        return { ...data, nodes: enrichedNodes };
      }
    };
  }

  // Create color enrichment
  function createColorEnrichment(): DataTransformation {
    return {
      id: 'enrich-colors',
      name: 'Apply Color Schemes',
      type: 'map',
      priority: 2,
      enabled: true,
      fn: (data: TransformContext) => {
        const { nodes } = data;
        const colorScheme = data.metadata?.colorScheme || 'type';
        
        const enrichedNodes = nodes.map(node => ({
          ...node,
          color: getNodeColor(node, colorScheme)
        }));

        return { ...data, nodes: enrichedNodes };
      }
    };
  }

  // Create size enrichment
  function createSizeEnrichment(): DataTransformation {
    return {
      id: 'enrich-sizes',
      name: 'Calculate Node Sizes',
      type: 'map',
      priority: 3,
      enabled: true,
      dependencies: ['compute-metrics'],
      fn: (data: TransformContext) => {
        const { nodes } = data;
        const sizeStrategy = data.metadata?.sizeStrategy || 'degree';
        
        const enrichedNodes = nodes.map(node => ({
          ...node,
          size: getNodeSize(node, sizeStrategy)
        }));

        return { ...data, nodes: enrichedNodes };
      }
    };
  }

  // Format label helper
  function formatLabel(label: string): string {
    if (label.length > 20) {
      return label.substring(0, 17) + '...';
    }
    return label;
  }

  // Get node color based on scheme
  function getNodeColor(node: GraphNode, scheme: string): string {
    const typeColors: Record<string, string> = {
      'Entity': '#4F46E5',
      'Event': '#10B981',
      'Relation': '#F59E0B',
      'Episodic': '#EF4444',
      'default': '#6B7280'
    };

    switch (scheme) {
      case 'type':
        return typeColors[node.node_type] || typeColors.default;
      case 'centrality':
        const centrality = node.properties?.normalized_centrality || 0;
        return `hsl(${240 - centrality * 240}, 70%, 50%)`;
      case 'temporal':
        const age = Date.now() - new Date(node.created_at || 0).getTime();
        const ageNorm = Math.min(age / (30 * 24 * 60 * 60 * 1000), 1); // 30 days
        return `hsl(120, ${100 - ageNorm * 50}%, 50%)`;
      default:
        return typeColors.default;
    }
  }

  // Get node size based on strategy
  function getNodeSize(node: GraphNode, strategy: string): number {
    const baseSize = 5;
    
    switch (strategy) {
      case 'degree':
        const degree = node.degree || 0;
        return baseSize + Math.log(degree + 1) * 2;
      case 'centrality':
        const centrality = node.properties?.normalized_centrality || 0;
        return baseSize + centrality * 10;
      case 'uniform':
        return baseSize;
      default:
        return baseSize;
    }
  }

  // Execute a single transformation
  const executeTransformation = useCallback(async (
    transformation: DataTransformation,
    context: TransformContext
  ): Promise<TransformContext> => {
    const cacheKey = `${transformation.id}-${JSON.stringify(context.metadata)}`;
    
    // Check cache
    if (state.cache.has(cacheKey)) {
      const cached = state.cache.get(cacheKey);
      if (Date.now() - cached.timestamp < fullConfig.cacheExpiry) {
        return cached.result;
      }
    }

    // Execute with timeout
    const timeoutPromise = new Promise<never>((_, reject) => {
      setTimeout(() => reject(new Error('Transformation timeout')), 
        fullConfig.transformationTimeout);
    });

    try {
      const result = await Promise.race([
        Promise.resolve(transformation.fn(context)),
        timeoutPromise
      ]);

      // Cache result
      if (fullConfig.defaultCacheStrategy === 'memory') {
        state.cache.set(cacheKey, { result, timestamp: Date.now() });
      }

      return result;
    } catch (error) {
      console.error(`Transformation ${transformation.id} failed:`, error);
      throw error;
    }
  }, [state.cache, fullConfig]);

  // Execute a pipeline
  const executePipeline = useCallback(async (
    pipeline: DataPipeline
  ): Promise<TransformedData> => {
    setState(prev => ({
      ...prev,
      isProcessing: true,
      currentPipeline: pipeline.id,
      progress: 0
    }));

    const context: TransformContext = {
      nodes: [...nodes],
      edges: [...edges],
      metadata: {},
      cache: state.cache,
      timestamp: Date.now()
    };

    const transformationsApplied: string[] = [];
    let currentContext = context;

    try {
      // Sort transformations by priority and dependencies
      const sortedTransformations = sortTransformations(pipeline.transformations);
      
      for (let i = 0; i < sortedTransformations.length; i++) {
        const transformation = sortedTransformations[i];
        
        if (!transformation.enabled) continue;
        
        setState(prev => ({
          ...prev,
          currentTransformation: transformation.id,
          progress: ((i + 1) / sortedTransformations.length) * 100
        }));

        currentContext = await executeTransformation(transformation, currentContext);
        transformationsApplied.push(transformation.id);
      }

      const result: TransformedData = {
        nodes: currentContext.nodes,
        edges: currentContext.edges,
        metadata: currentContext.metadata || {},
        transformationsApplied,
        timestamp: Date.now()
      };

      onDataTransformed?.(result);
      onPipelineComplete?.(pipeline.id, result);

      return result;
    } catch (error) {
      const err = error as Error;
      setState(prev => ({
        ...prev,
        errors: [...prev.errors, {
          pipeline: pipeline.id,
          transformation: state.currentTransformation || 'unknown',
          error: err
        }]
      }));
      onError?.(err, pipeline.id, state.currentTransformation || undefined);
      throw error;
    } finally {
      setState(prev => ({
        ...prev,
        isProcessing: false,
        currentPipeline: null,
        currentTransformation: null
      }));
    }
  }, [nodes, edges, state.cache, state.currentTransformation, executeTransformation, onDataTransformed, onPipelineComplete, onError]);

  // Sort transformations by dependencies
  function sortTransformations(transformations: DataTransformation[]): DataTransformation[] {
    const sorted: DataTransformation[] = [];
    const visited = new Set<string>();
    const visiting = new Set<string>();

    const visit = (t: DataTransformation) => {
      if (visited.has(t.id)) return;
      if (visiting.has(t.id)) {
        throw new Error(`Circular dependency detected: ${t.id}`);
      }

      visiting.add(t.id);

      if (t.dependencies) {
        for (const depId of t.dependencies) {
          const dep = transformations.find(tr => tr.id === depId);
          if (dep) visit(dep);
        }
      }

      visiting.delete(t.id);
      visited.add(t.id);
      sorted.push(t);
    };

    // Sort by priority first
    const prioritySorted = [...transformations].sort((a, b) => a.priority - b.priority);
    
    // Then by dependencies
    prioritySorted.forEach(visit);
    
    return sorted;
  }

  // Execute all pipelines
  const executeAllPipelines = useCallback(async () => {
    abortControllerRef.current = new AbortController();
    
    for (const pipeline of fullConfig.pipelines) {
      if (abortControllerRef.current.signal.aborted) break;
      
      try {
        await executePipeline(pipeline);
      } catch (error) {
        console.error(`Pipeline ${pipeline.id} failed:`, error);
        // Continue with next pipeline
      }
    }
  }, [fullConfig.pipelines, executePipeline]);

  // Abort processing
  const abort = useCallback(() => {
    abortControllerRef.current?.abort();
    setState(prev => ({
      ...prev,
      isProcessing: false,
      currentPipeline: null,
      currentTransformation: null
    }));
  }, []);

  // Clear cache
  const clearCache = useCallback(() => {
    setState(prev => ({
      ...prev,
      cache: new Map()
    }));
  }, []);

  // Execute pipelines when data changes
  useEffect(() => {
    if (nodes.length === 0) return;
    
    executeAllPipelines();
    
    return () => {
      abort();
    };
  }, [nodes, edges]); // Only re-run on data changes

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      workersRef.current.forEach(worker => worker.terminate());
      abort();
    };
  }, [abort]);

  // Context value
  const contextValue = useMemo(() => ({
    ...state,
    executePipeline,
    executeTransformation,
    abort,
    clearCache,
    addPipeline: (pipeline: DataPipeline) => {
      fullConfig.pipelines.push(pipeline);
      executeAllPipelines();
    },
    removePipeline: (pipelineId: string) => {
      fullConfig.pipelines = fullConfig.pipelines.filter(p => p.id !== pipelineId);
    }
  }), [state, executePipeline, executeTransformation, abort, clearCache, executeAllPipelines, fullConfig]);

  return (
    <DataKitContext.Provider value={contextValue}>
      {children}
    </DataKitContext.Provider>
  );
};

// Context
const DataKitContext = React.createContext<{
  isProcessing: boolean;
  currentPipeline: string | null;
  currentTransformation: string | null;
  progress: number;
  cache: Map<string, any>;
  errors: Array<{ pipeline: string; transformation: string; error: Error }>;
  executePipeline: (pipeline: DataPipeline) => Promise<TransformedData>;
  executeTransformation: (transformation: DataTransformation, context: TransformContext) => Promise<TransformContext>;
  abort: () => void;
  clearCache: () => void;
  addPipeline: (pipeline: DataPipeline) => void;
  removePipeline: (pipelineId: string) => void;
}>({
  isProcessing: false,
  currentPipeline: null,
  currentTransformation: null,
  progress: 0,
  cache: new Map(),
  errors: [],
  executePipeline: async () => ({ nodes: [], edges: [], metadata: {}, transformationsApplied: [], timestamp: 0 }),
  executeTransformation: async () => ({ nodes: [], edges: [], metadata: {}, cache: new Map(), timestamp: 0 }),
  abort: () => {},
  clearCache: () => {},
  addPipeline: () => {},
  removePipeline: () => {}
});

export const useDataKit = () => React.useContext(DataKitContext);