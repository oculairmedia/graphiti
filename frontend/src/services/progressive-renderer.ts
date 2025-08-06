// Progressive rendering and Level-of-Detail (LOD) system for graph visualization

export interface LODLevel {
  minZoom: number;
  maxZoom: number;
  nodeDetail: 'minimal' | 'basic' | 'full';
  edgeDetail: 'hidden' | 'simple' | 'full';
  labelVisibility: 'none' | 'important' | 'all';
  maxNodes: number;
  maxEdges: number;
}

export class ProgressiveRenderer {
  private lodLevels: LODLevel[] = [
    {
      minZoom: 0,
      maxZoom: 0.5,
      nodeDetail: 'minimal',
      edgeDetail: 'hidden',
      labelVisibility: 'none',
      maxNodes: 100,
      maxEdges: 0
    },
    {
      minZoom: 0.5,
      maxZoom: 1,
      nodeDetail: 'minimal',
      edgeDetail: 'simple',
      labelVisibility: 'important',
      maxNodes: 500,
      maxEdges: 1000
    },
    {
      minZoom: 1,
      maxZoom: 2,
      nodeDetail: 'basic',
      edgeDetail: 'simple',
      labelVisibility: 'important',
      maxNodes: 1500,
      maxEdges: 3000
    },
    {
      minZoom: 2,
      maxZoom: 5,
      nodeDetail: 'full',
      edgeDetail: 'full',
      labelVisibility: 'all',
      maxNodes: 5000,
      maxEdges: 10000
    },
    {
      minZoom: 5,
      maxZoom: Infinity,
      nodeDetail: 'full',
      edgeDetail: 'full',
      labelVisibility: 'all',
      maxNodes: 10000,
      maxEdges: 20000
    }
  ];
  
  private renderQueue: Map<string, () => void> = new Map();
  private frameId: number | null = null;
  private lastRenderTime = 0;
  private targetFrameTime = 16.67; // 60 FPS
  
  getCurrentLOD(zoom: number): LODLevel {
    return this.lodLevels.find(
      level => zoom >= level.minZoom && zoom < level.maxZoom
    ) || this.lodLevels[this.lodLevels.length - 1];
  }
  
  async renderProgressive(
    nodes: any[],
    edges: any[],
    viewport: { x: number; y: number; width: number; height: number; zoom: number },
    callbacks: {
      onBatch: (batch: { nodes: any[], edges: any[] }) => void,
      onComplete: () => void,
      onProgress: (progress: number) => void
    }
  ): Promise<void> {
    const lod = this.getCurrentLOD(viewport.zoom);
    
    // Filter nodes based on viewport and importance
    const visibleNodes = this.filterVisibleNodes(nodes, viewport, lod);
    const importantNodes = this.prioritizeNodes(visibleNodes, lod.maxNodes);
    
    // Filter edges for visible nodes
    const nodeSet = new Set(importantNodes.map(n => n.id));
    const visibleEdges = edges.filter(
      e => nodeSet.has(e.source) && nodeSet.has(e.target)
    ).slice(0, lod.maxEdges);
    
    // Progressive rendering in chunks
    const nodeChunkSize = Math.min(100, Math.ceil(importantNodes.length / 10));
    const edgeChunkSize = Math.min(200, Math.ceil(visibleEdges.length / 10));
    
    let renderedNodes = 0;
    let renderedEdges = 0;
    
    // Render critical nodes first (highest centrality)
    for (let i = 0; i < importantNodes.length; i += nodeChunkSize) {
      const nodeChunk = importantNodes.slice(i, i + nodeChunkSize);
      const progress = (i + nodeChunk.length) / (importantNodes.length + visibleEdges.length);
      
      await this.scheduleRender(() => {
        callbacks.onBatch({ 
          nodes: this.applyLODToNodes(nodeChunk, lod),
          edges: []
        });
        callbacks.onProgress(progress * 0.5); // First 50% for nodes
      });
      
      renderedNodes += nodeChunk.length;
    }
    
    // Then render edges progressively
    for (let i = 0; i < visibleEdges.length; i += edgeChunkSize) {
      const edgeChunk = visibleEdges.slice(i, i + edgeChunkSize);
      const progress = 0.5 + (i + edgeChunk.length) / (visibleEdges.length * 2);
      
      await this.scheduleRender(() => {
        callbacks.onBatch({
          nodes: [],
          edges: this.applyLODToEdges(edgeChunk, lod)
        });
        callbacks.onProgress(progress);
      });
      
      renderedEdges += edgeChunk.length;
    }
    
    callbacks.onComplete();
  }
  
  private filterVisibleNodes(
    nodes: any[],
    viewport: { x: number; y: number; width: number; height: number; zoom: number },
    lod: LODLevel
  ): any[] {
    const padding = 100; // Extra padding around viewport
    const minX = viewport.x - padding;
    const maxX = viewport.x + viewport.width + padding;
    const minY = viewport.y - padding;
    const maxY = viewport.y + viewport.height + padding;
    
    return nodes.filter(node => {
      // If no position, include if important
      if (!node.x || !node.y) {
        return node.degree_centrality > 0.5;
      }
      
      // Check if in viewport
      return node.x >= minX && node.x <= maxX &&
             node.y >= minY && node.y <= maxY;
    });
  }
  
  private prioritizeNodes(nodes: any[], maxCount: number): any[] {
    // Sort by importance (centrality, connections, etc.)
    const sorted = [...nodes].sort((a, b) => {
      // Priority factors
      const aCentrality = a.degree_centrality || 0;
      const bCentrality = b.degree_centrality || 0;
      
      // Prioritize by centrality first
      if (aCentrality !== bCentrality) {
        return bCentrality - aCentrality;
      }
      
      // Then by node type importance
      const typeOrder = ['GroupNode', 'EntityNode', 'EpisodicNode'];
      const aTypeIndex = typeOrder.indexOf(a.node_type) ?? 999;
      const bTypeIndex = typeOrder.indexOf(b.node_type) ?? 999;
      
      return aTypeIndex - bTypeIndex;
    });
    
    return sorted.slice(0, maxCount);
  }
  
  private applyLODToNodes(nodes: any[], lod: LODLevel): any[] {
    return nodes.map(node => {
      const lodNode = { ...node };
      
      switch (lod.nodeDetail) {
        case 'minimal':
          // Only render as dots
          lodNode.renderMode = 'dot';
          lodNode.size = 3;
          delete lodNode.label;
          delete lodNode.summary;
          break;
          
        case 'basic':
          // Render with basic shape and color
          lodNode.renderMode = 'shape';
          lodNode.size = 5;
          if (lod.labelVisibility === 'none') {
            delete lodNode.label;
          } else if (lod.labelVisibility === 'important' && lodNode.degree_centrality < 0.3) {
            delete lodNode.label;
          }
          delete lodNode.summary;
          break;
          
        case 'full':
          // Full detail
          lodNode.renderMode = 'full';
          if (lod.labelVisibility === 'none') {
            delete lodNode.label;
          } else if (lod.labelVisibility === 'important' && lodNode.degree_centrality < 0.2) {
            delete lodNode.label;
          }
          break;
      }
      
      return lodNode;
    });
  }
  
  private applyLODToEdges(edges: any[], lod: LODLevel): any[] {
    return edges.map(edge => {
      const lodEdge = { ...edge };
      
      switch (lod.edgeDetail) {
        case 'hidden':
          return null;
          
        case 'simple':
          // Render as simple lines
          lodEdge.renderMode = 'line';
          lodEdge.width = 0.5;
          lodEdge.opacity = 0.3;
          delete lodEdge.label;
          break;
          
        case 'full':
          // Full detail with curves and labels
          lodEdge.renderMode = 'curve';
          lodEdge.width = edge.weight || 1;
          lodEdge.opacity = 0.6;
          break;
      }
      
      return lodEdge;
    }).filter(Boolean);
  }
  
  private scheduleRender(callback: () => void): Promise<void> {
    return new Promise((resolve) => {
      const render = () => {
        const now = performance.now();
        const deltaTime = now - this.lastRenderTime;
        
        // If we have time in this frame, execute
        if (deltaTime >= this.targetFrameTime) {
          callback();
          this.lastRenderTime = now;
          resolve();
        } else {
          // Schedule for next frame
          this.frameId = requestAnimationFrame(render);
        }
      };
      
      render();
    });
  }
  
  cancelRendering(): void {
    if (this.frameId !== null) {
      cancelAnimationFrame(this.frameId);
      this.frameId = null;
    }
    this.renderQueue.clear();
  }
}

// Occlusion culling for performance
export class OcclusionCuller {
  private quadtree: QuadTree;
  
  constructor(bounds: { x: number, y: number, width: number, height: number }) {
    this.quadtree = new QuadTree(bounds, 4, 10);
  }
  
  cullOccluded(
    nodes: any[],
    viewport: { x: number, y: number, width: number, height: number, zoom: number }
  ): any[] {
    // Build quadtree
    this.quadtree.clear();
    nodes.forEach(node => {
      if (node.x !== undefined && node.y !== undefined) {
        this.quadtree.insert({
          x: node.x,
          y: node.y,
          width: node.size || 10,
          height: node.size || 10,
          data: node
        });
      }
    });
    
    // Query visible nodes
    const visible = this.quadtree.retrieve({
      x: viewport.x,
      y: viewport.y,
      width: viewport.width,
      height: viewport.height
    });
    
    return visible.map(item => item.data);
  }
}

// Simple QuadTree implementation for spatial indexing
class QuadTree {
  private objects: any[] = [];
  private nodes: QuadTree[] = [];
  private level: number;
  private bounds: any;
  private maxObjects: number;
  private maxLevels: number;
  
  constructor(bounds: any, maxObjects = 10, maxLevels = 5, level = 0) {
    this.bounds = bounds;
    this.maxObjects = maxObjects;
    this.maxLevels = maxLevels;
    this.level = level;
  }
  
  clear(): void {
    this.objects = [];
    this.nodes.forEach(node => node.clear());
    this.nodes = [];
  }
  
  split(): void {
    const subWidth = this.bounds.width / 2;
    const subHeight = this.bounds.height / 2;
    const x = this.bounds.x;
    const y = this.bounds.y;
    
    this.nodes[0] = new QuadTree({
      x: x + subWidth,
      y: y,
      width: subWidth,
      height: subHeight
    }, this.maxObjects, this.maxLevels, this.level + 1);
    
    this.nodes[1] = new QuadTree({
      x: x,
      y: y,
      width: subWidth,
      height: subHeight
    }, this.maxObjects, this.maxLevels, this.level + 1);
    
    this.nodes[2] = new QuadTree({
      x: x,
      y: y + subHeight,
      width: subWidth,
      height: subHeight
    }, this.maxObjects, this.maxLevels, this.level + 1);
    
    this.nodes[3] = new QuadTree({
      x: x + subWidth,
      y: y + subHeight,
      width: subWidth,
      height: subHeight
    }, this.maxObjects, this.maxLevels, this.level + 1);
  }
  
  getIndex(rect: any): number {
    const verticalMidpoint = this.bounds.x + this.bounds.width / 2;
    const horizontalMidpoint = this.bounds.y + this.bounds.height / 2;
    
    const topQuadrant = rect.y < horizontalMidpoint && rect.y + rect.height < horizontalMidpoint;
    const bottomQuadrant = rect.y > horizontalMidpoint;
    
    if (rect.x < verticalMidpoint && rect.x + rect.width < verticalMidpoint) {
      if (topQuadrant) return 1;
      if (bottomQuadrant) return 2;
    } else if (rect.x > verticalMidpoint) {
      if (topQuadrant) return 0;
      if (bottomQuadrant) return 3;
    }
    
    return -1;
  }
  
  insert(rect: any): void {
    if (this.nodes.length > 0) {
      const index = this.getIndex(rect);
      if (index !== -1) {
        this.nodes[index].insert(rect);
        return;
      }
    }
    
    this.objects.push(rect);
    
    if (this.objects.length > this.maxObjects && this.level < this.maxLevels) {
      if (this.nodes.length === 0) {
        this.split();
      }
      
      let i = 0;
      while (i < this.objects.length) {
        const index = this.getIndex(this.objects[i]);
        if (index !== -1) {
          this.nodes[index].insert(this.objects.splice(i, 1)[0]);
        } else {
          i++;
        }
      }
    }
  }
  
  retrieve(rect: any): any[] {
    const returnObjects = [...this.objects];
    
    if (this.nodes.length > 0) {
      const index = this.getIndex(rect);
      if (index !== -1) {
        returnObjects.push(...this.nodes[index].retrieve(rect));
      } else {
        this.nodes.forEach(node => {
          returnObjects.push(...node.retrieve(rect));
        });
      }
    }
    
    return returnObjects;
  }
}

export const progressiveRenderer = new ProgressiveRenderer();
export const occlusionCuller = new OcclusionCuller({
  x: -5000,
  y: -5000,
  width: 10000,
  height: 10000
});