// Predictive prefetching service for anticipating user interactions

export interface PrefetchStrategy {
  type: 'hover' | 'viewport' | 'interaction' | 'pattern';
  priority: number;
  maxItems: number;
}

export class PredictivePrefetcher {
  private interactionHistory: Array<{
    type: string;
    target: string;
    timestamp: number;
    viewport?: any;
  }> = [];
  
  private prefetchQueue = new Map<string, Promise<any>>();
  private cache = new Map<string, { data: any; timestamp: number }>();
  private cacheTimeout = 60000; // 1 minute
  private maxHistorySize = 100;
  private maxCacheSize = 50;
  
  // Interaction patterns for prediction
  private patterns = {
    nodeExpansion: new Set<string>(),
    frequentPaths: new Map<string, string[]>(),
    viewportMovement: { dx: 0, dy: 0, count: 0 }
  };
  
  recordInteraction(
    type: 'click' | 'hover' | 'pan' | 'zoom',
    target?: string,
    viewport?: any
  ): void {
    const interaction = {
      type,
      target: target || '',
      timestamp: Date.now(),
      viewport
    };
    
    this.interactionHistory.push(interaction);
    
    // Keep history size manageable
    if (this.interactionHistory.length > this.maxHistorySize) {
      this.interactionHistory.shift();
    }
    
    // Update patterns
    this.updatePatterns(interaction);
    
    // Trigger predictive prefetching
    this.predictAndPrefetch(interaction);
  }
  
  private updatePatterns(interaction: any): void {
    // Track node expansion patterns
    if (interaction.type === 'click' && interaction.target) {
      this.patterns.nodeExpansion.add(interaction.target);
      
      // Track sequential clicks (paths)
      const recentClicks = this.interactionHistory
        .filter(i => i.type === 'click' && i.target)
        .slice(-5)
        .map(i => i.target);
      
      if (recentClicks.length >= 2) {
        const pathKey = recentClicks.slice(0, -1).join('->');
        if (!this.patterns.frequentPaths.has(pathKey)) {
          this.patterns.frequentPaths.set(pathKey, []);
        }
        this.patterns.frequentPaths.get(pathKey)!.push(interaction.target);
      }
    }
    
    // Track viewport movement patterns
    if (interaction.type === 'pan' && interaction.viewport) {
      const lastPan = this.interactionHistory
        .filter(i => i.type === 'pan' && i.viewport)
        .slice(-2)[0];
      
      if (lastPan && lastPan.viewport) {
        this.patterns.viewportMovement.dx += 
          interaction.viewport.x - lastPan.viewport.x;
        this.patterns.viewportMovement.dy += 
          interaction.viewport.y - lastPan.viewport.y;
        this.patterns.viewportMovement.count++;
      }
    }
  }
  
  private async predictAndPrefetch(interaction: any): Promise<void> {
    const predictions = this.generatePredictions(interaction);
    
    // Sort by priority and prefetch
    predictions.sort((a, b) => b.priority - a.priority);
    
    for (const prediction of predictions.slice(0, 5)) {
      this.prefetch(prediction.key, prediction.fetcher, prediction.priority);
    }
  }
  
  private generatePredictions(interaction: any): Array<{
    key: string;
    fetcher: () => Promise<any>;
    priority: number;
  }> {
    const predictions: Array<{
      key: string;
      fetcher: () => Promise<any>;
      priority: number;
    }> = [];
    
    // Predict based on interaction type
    switch (interaction.type) {
      case 'hover':
        if (interaction.target) {
          // Prefetch node details and neighbors
          predictions.push({
            key: `node-details-${interaction.target}`,
            fetcher: () => this.fetchNodeDetails(interaction.target),
            priority: 0.9
          });
          
          predictions.push({
            key: `node-neighbors-${interaction.target}`,
            fetcher: () => this.fetchNodeNeighbors(interaction.target),
            priority: 0.8
          });
        }
        break;
        
      case 'click':
        if (interaction.target) {
          // Prefetch expanded data
          predictions.push({
            key: `node-expansion-${interaction.target}`,
            fetcher: () => this.fetchExpandedData(interaction.target),
            priority: 1.0
          });
          
          // Predict next likely clicks based on patterns
          const path = this.getRecentPath();
          const likelyNext = this.patterns.frequentPaths.get(path);
          
          if (likelyNext && likelyNext.length > 0) {
            // Get most frequent next node
            const frequency = new Map<string, number>();
            likelyNext.forEach(node => {
              frequency.set(node, (frequency.get(node) || 0) + 1);
            });
            
            const sorted = Array.from(frequency.entries())
              .sort((a, b) => b[1] - a[1]);
            
            if (sorted[0]) {
              predictions.push({
                key: `node-likely-${sorted[0][0]}`,
                fetcher: () => this.fetchNodeDetails(sorted[0][0]),
                priority: 0.7
              });
            }
          }
        }
        break;
        
      case 'pan':
        if (interaction.viewport) {
          // Predict viewport movement direction
          const avgDx = this.patterns.viewportMovement.count > 0
            ? this.patterns.viewportMovement.dx / this.patterns.viewportMovement.count
            : 0;
          const avgDy = this.patterns.viewportMovement.count > 0
            ? this.patterns.viewportMovement.dy / this.patterns.viewportMovement.count
            : 0;
          
          // Prefetch data in the predicted direction
          const predictedViewport = {
            x: interaction.viewport.x + avgDx * 2,
            y: interaction.viewport.y + avgDy * 2,
            width: interaction.viewport.width,
            height: interaction.viewport.height
          };
          
          predictions.push({
            key: `viewport-${predictedViewport.x}-${predictedViewport.y}`,
            fetcher: () => this.fetchViewportData(predictedViewport),
            priority: 0.6
          });
        }
        break;
        
      case 'zoom':
        if (interaction.viewport) {
          // Prefetch appropriate LOD data
          const zoomLevel = interaction.viewport.zoom || 1;
          
          if (zoomLevel > 2) {
            // Zooming in - prefetch details
            predictions.push({
              key: `lod-details-${zoomLevel}`,
              fetcher: () => this.fetchLODDetails(interaction.viewport),
              priority: 0.8
            });
          } else {
            // Zooming out - prefetch overview
            predictions.push({
              key: `lod-overview-${zoomLevel}`,
              fetcher: () => this.fetchLODOverview(interaction.viewport),
              priority: 0.7
            });
          }
        }
        break;
    }
    
    return predictions;
  }
  
  private getRecentPath(): string {
    const recentClicks = this.interactionHistory
      .filter(i => i.type === 'click' && i.target)
      .slice(-4)
      .map(i => i.target);
    
    return recentClicks.join('->');
  }
  
  async prefetch(
    key: string,
    fetcher: () => Promise<any>,
    priority: number
  ): Promise<any> {
    // Check cache first
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
      return cached.data;
    }
    
    // Check if already prefetching
    if (this.prefetchQueue.has(key)) {
      return this.prefetchQueue.get(key);
    }
    
    // Start prefetch with priority-based delay
    const delay = Math.max(0, (1 - priority) * 100);
    
    const prefetchPromise = new Promise(async (resolve, reject) => {
      await new Promise(r => setTimeout(r, delay));
      
      try {
        const data = await fetcher();
        
        // Cache the result
        this.cache.set(key, { data, timestamp: Date.now() });
        
        // Manage cache size
        if (this.cache.size > this.maxCacheSize) {
          const oldest = Array.from(this.cache.entries())
            .sort((a, b) => a[1].timestamp - b[1].timestamp)[0];
          if (oldest) {
            this.cache.delete(oldest[0]);
          }
        }
        
        resolve(data);
      } catch (error) {
        reject(error);
      } finally {
        this.prefetchQueue.delete(key);
      }
    });
    
    this.prefetchQueue.set(key, prefetchPromise);
    return prefetchPromise;
  }
  
  getCached(key: string): any | null {
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
      return cached.data;
    }
    return null;
  }
  
  // Stub fetcher methods - implement based on your API
  private async fetchNodeDetails(nodeId: string): Promise<any> {
    const response = await fetch(`/api/nodes/${nodeId}/details`);
    return response.json();
  }
  
  private async fetchNodeNeighbors(nodeId: string): Promise<any> {
    const response = await fetch(`/api/nodes/${nodeId}/neighbors`);
    return response.json();
  }
  
  private async fetchExpandedData(nodeId: string): Promise<any> {
    const response = await fetch(`/api/nodes/${nodeId}/expand`);
    return response.json();
  }
  
  private async fetchViewportData(viewport: any): Promise<any> {
    const response = await fetch('/api/viewport', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(viewport)
    });
    return response.json();
  }
  
  private async fetchLODDetails(viewport: any): Promise<any> {
    const response = await fetch('/api/lod/details', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(viewport)
    });
    return response.json();
  }
  
  private async fetchLODOverview(viewport: any): Promise<any> {
    const response = await fetch('/api/lod/overview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(viewport)
    });
    return response.json();
  }
  
  clearCache(): void {
    this.cache.clear();
    this.prefetchQueue.clear();
  }
  
  getStats(): {
    cacheSize: number;
    prefetchQueueSize: number;
    historySize: number;
    patterns: any;
  } {
    return {
      cacheSize: this.cache.size,
      prefetchQueueSize: this.prefetchQueue.size,
      historySize: this.interactionHistory.length,
      patterns: {
        expandedNodes: this.patterns.nodeExpansion.size,
        frequentPaths: this.patterns.frequentPaths.size,
        avgMovement: this.patterns.viewportMovement.count > 0 ? {
          dx: this.patterns.viewportMovement.dx / this.patterns.viewportMovement.count,
          dy: this.patterns.viewportMovement.dy / this.patterns.viewportMovement.count
        } : { dx: 0, dy: 0 }
      }
    };
  }
}

export const predictivePrefetcher = new PredictivePrefetcher();