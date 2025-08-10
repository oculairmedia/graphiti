import { GraphNode, GraphEdge } from '../api/types';

export interface LoadingPhase {
  name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  delay: number;
  priority: number;
}

export interface ProgressiveLoadingConfig {
  // Thresholds for different loading phases
  coreNodeThreshold?: number;      // Default: 0.5 eigenvector centrality
  secondaryThreshold?: number;      // Default: 0.2 eigenvector centrality
  degreeThreshold?: number;         // Default: 5 connections
  
  // Timing configuration
  phaseDelayMs?: number;            // Default: 50ms between phases
  chunkSize?: number;               // Default: 500 nodes per chunk
  
  // Visual configuration
  fadeInDuration?: number;          // Default: 500ms
  showPlaceholders?: boolean;       // Default: true
  
  // Performance configuration
  fpsThreshold?: number;            // Default: 30 fps minimum
  backpressureDelay?: number;      // Default: 50ms when FPS drops
}

export class ProgressiveLoader {
  private config: Required<ProgressiveLoadingConfig>;
  private loadingPhases: LoadingPhase[] = [];
  private currentPhase = 0;
  private isLoading = false;
  private abortController?: AbortController;
  
  constructor(config: ProgressiveLoadingConfig = {}) {
    this.config = {
      coreNodeThreshold: config.coreNodeThreshold ?? 0.5,
      secondaryThreshold: config.secondaryThreshold ?? 0.2,
      degreeThreshold: config.degreeThreshold ?? 5,
      phaseDelayMs: config.phaseDelayMs ?? 50,
      chunkSize: config.chunkSize ?? 500,
      fadeInDuration: config.fadeInDuration ?? 500,
      showPlaceholders: config.showPlaceholders ?? true,
      fpsThreshold: config.fpsThreshold ?? 30,
      backpressureDelay: config.backpressureDelay ?? 50,
    };
  }
  
  /**
   * Prepare nodes and edges for progressive loading
   */
  prepareLoadingPhases(
    nodes: GraphNode[], 
    edges: GraphEdge[]
  ): LoadingPhase[] {
    console.log('[ProgressiveLoader] Preparing loading phases for', nodes.length, 'nodes');
    
    // Create node ID sets for each phase
    const coreNodeIds = new Set<string>();
    const secondaryNodeIds = new Set<string>();
    const peripheralNodeIds = new Set<string>();
    
    // Phase 1: Core nodes (highest centrality)
    const coreNodes = nodes.filter(node => {
      const eigenvector = node.properties?.eigenvector_centrality || 0;
      const degree = node.properties?.degree_centrality || 0;
      
      // Include high eigenvector centrality OR high degree nodes
      if (eigenvector > this.config.coreNodeThreshold || degree > 30) {
        coreNodeIds.add(node.id);
        return true;
      }
      return false;
    });
    
    // Phase 2: Secondary nodes (medium importance)
    const secondaryNodes = nodes.filter(node => {
      if (coreNodeIds.has(node.id)) return false;
      
      const eigenvector = node.properties?.eigenvector_centrality || 0;
      const degree = node.properties?.degree_centrality || 0;
      
      if (eigenvector > this.config.secondaryThreshold || 
          degree > this.config.degreeThreshold) {
        secondaryNodeIds.add(node.id);
        return true;
      }
      return false;
    });
    
    // Phase 3: Peripheral nodes (everything else)
    const peripheralNodes = nodes.filter(node => {
      if (coreNodeIds.has(node.id) || secondaryNodeIds.has(node.id)) {
        return false;
      }
      peripheralNodeIds.add(node.id);
      return true;
    });
    
    // Filter edges for each phase
    const coreEdges = edges.filter(edge => 
      coreNodeIds.has(edge.from) && coreNodeIds.has(edge.to)
    );
    
    const secondaryEdges = edges.filter(edge => {
      const combinedIds = new Set([...coreNodeIds, ...secondaryNodeIds]);
      return combinedIds.has(edge.from) && combinedIds.has(edge.to) &&
             !(coreNodeIds.has(edge.from) && coreNodeIds.has(edge.to));
    });
    
    const peripheralEdges = edges.filter(edge => {
      return !(coreNodeIds.has(edge.from) && coreNodeIds.has(edge.to)) &&
             !(secondaryNodeIds.has(edge.from) && secondaryNodeIds.has(edge.to));
    });
    
    // Create loading phases
    this.loadingPhases = [
      {
        name: 'core',
        nodes: coreNodes,
        edges: coreEdges,
        delay: 0, // Immediate
        priority: 1
      },
      {
        name: 'secondary',
        nodes: secondaryNodes,
        edges: secondaryEdges,
        delay: this.config.phaseDelayMs,
        priority: 2
      },
      {
        name: 'peripheral',
        nodes: peripheralNodes,
        edges: peripheralEdges,
        delay: this.config.phaseDelayMs * 2,
        priority: 3
      }
    ].filter(phase => phase.nodes.length > 0); // Only include non-empty phases
    
    console.log('[ProgressiveLoader] Loading phases prepared:', {
      core: `${coreNodes.length} nodes, ${coreEdges.length} edges`,
      secondary: `${secondaryNodes.length} nodes, ${secondaryEdges.length} edges`,
      peripheral: `${peripheralNodes.length} nodes, ${peripheralEdges.length} edges`
    });
    
    return this.loadingPhases;
  }
  
  /**
   * Execute progressive loading with callbacks
   */
  async load(
    onPhaseLoad: (phase: LoadingPhase, progress: number) => Promise<void>,
    onProgress?: (phase: string, loaded: number, total: number) => void
  ): Promise<void> {
    if (this.isLoading) {
      console.warn('[ProgressiveLoader] Already loading, skipping duplicate call');
      return;
    }
    
    this.isLoading = true;
    this.abortController = new AbortController();
    
    try {
      for (let i = 0; i < this.loadingPhases.length; i++) {
        if (this.abortController.signal.aborted) {
          console.log('[ProgressiveLoader] Loading aborted');
          break;
        }
        
        const phase = this.loadingPhases[i];
        console.log(`[ProgressiveLoader] Loading phase ${i + 1}/${this.loadingPhases.length}: ${phase.name}`);
        
        // Wait for phase delay (except for first phase)
        if (phase.delay > 0) {
          await this.sleep(phase.delay);
        }
        
        // Load in chunks for large phases
        if (phase.nodes.length > this.config.chunkSize) {
          await this.loadInChunks(phase, onPhaseLoad, onProgress);
        } else {
          // Load entire phase at once
          onProgress?.(phase.name, phase.nodes.length, phase.nodes.length);
          await onPhaseLoad(phase, 1.0);
        }
        
        this.currentPhase = i + 1;
      }
      
      console.log('[ProgressiveLoader] All phases loaded successfully');
    } catch (error) {
      console.error('[ProgressiveLoader] Loading error:', error);
      throw error;
    } finally {
      this.isLoading = false;
      this.abortController = undefined;
    }
  }
  
  /**
   * Load a phase in chunks for better performance
   */
  private async loadInChunks(
    phase: LoadingPhase,
    onPhaseLoad: (phase: LoadingPhase, progress: number) => Promise<void>,
    onProgress?: (phase: string, loaded: number, total: number) => void
  ): Promise<void> {
    const chunks = Math.ceil(phase.nodes.length / this.config.chunkSize);
    console.log(`[ProgressiveLoader] Loading ${phase.name} in ${chunks} chunks`);
    
    for (let i = 0; i < chunks; i++) {
      if (this.abortController?.signal.aborted) break;
      
      const start = i * this.config.chunkSize;
      const end = Math.min(start + this.config.chunkSize, phase.nodes.length);
      
      const chunkPhase: LoadingPhase = {
        ...phase,
        nodes: phase.nodes.slice(start, end),
        edges: phase.edges.filter(edge => {
          const nodeIds = new Set(phase.nodes.slice(start, end).map(n => n.id));
          return nodeIds.has(edge.from) || nodeIds.has(edge.to);
        })
      };
      
      const progress = (i + 1) / chunks;
      onProgress?.(phase.name, end, phase.nodes.length);
      await onPhaseLoad(chunkPhase, progress);
      
      // Small delay between chunks to prevent blocking
      if (i < chunks - 1) {
        await this.sleep(10);
      }
    }
  }
  
  /**
   * Abort ongoing loading
   */
  abort(): void {
    if (this.abortController) {
      this.abortController.abort();
      this.isLoading = false;
      console.log('[ProgressiveLoader] Loading aborted by user');
    }
  }
  
  /**
   * Get loading statistics
   */
  getStats(): {
    totalPhases: number;
    currentPhase: number;
    isLoading: boolean;
    phases: Array<{ name: string; nodeCount: number; edgeCount: number }>;
  } {
    return {
      totalPhases: this.loadingPhases.length,
      currentPhase: this.currentPhase,
      isLoading: this.isLoading,
      phases: this.loadingPhases.map(p => ({
        name: p.name,
        nodeCount: p.nodes.length,
        edgeCount: p.edges.length
      }))
    };
  }
  
  /**
   * Utility sleep function
   */
  private sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
  
  /**
   * Reset loader state
   */
  reset(): void {
    this.abort();
    this.loadingPhases = [];
    this.currentPhase = 0;
  }
}

/**
 * Create loading phases based on viewport visibility
 */
export function createViewportBasedPhases(
  nodes: GraphNode[],
  edges: GraphEdge[],
  viewport: { x: number; y: number; zoom: number }
): LoadingPhase[] {
  const viewRadius = 1000 / viewport.zoom;
  
  // Calculate distance from viewport center for each node
  const nodesWithDistance = nodes.map(node => ({
    node,
    distance: Math.sqrt(
      Math.pow((node.x || 0) - viewport.x, 2) + 
      Math.pow((node.y || 0) - viewport.y, 2)
    )
  }));
  
  // Sort by distance
  nodesWithDistance.sort((a, b) => a.distance - b.distance);
  
  // Create phases based on distance rings
  const phases: LoadingPhase[] = [];
  const ringSize = viewRadius;
  let currentRing = 0;
  
  while (currentRing * ringSize < Math.max(...nodesWithDistance.map(n => n.distance))) {
    const ringNodes = nodesWithDistance
      .filter(n => 
        n.distance >= currentRing * ringSize && 
        n.distance < (currentRing + 1) * ringSize
      )
      .map(n => n.node);
    
    if (ringNodes.length > 0) {
      const nodeIds = new Set(ringNodes.map(n => n.id));
      phases.push({
        name: `ring-${currentRing}`,
        nodes: ringNodes,
        edges: edges.filter(e => nodeIds.has(e.from) && nodeIds.has(e.to)),
        delay: currentRing * 50,
        priority: currentRing + 1
      });
    }
    
    currentRing++;
  }
  
  return phases;
}