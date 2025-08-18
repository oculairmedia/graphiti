/**
 * NodeColorManager - Parametric color control system for graph nodes
 * 
 * Inspired by Houdini's node-based approach, this manager provides:
 * - Parametric color generation based on node metrics
 * - Smooth color animations and transitions
 * - Multiple color scheme strategies
 * - Real-time color updates without re-rendering
 * - Caching for performance
 */

import { interpolateColor, hexToRgba } from './colorCache';
import { generateNodeTypeColor } from './nodeTypeColors';

export interface ColorSchemeConfig {
  scheme: 'by-type' | 'by-centrality' | 'by-pagerank' | 'by-degree' | 'by-betweenness' | 'by-eigenvector' | 'by-community' | 'by-temporal' | 'custom';
  highColor?: string;
  lowColor?: string;
  midColor?: string;
  nodeTypeColors?: Record<string, string>;
  communityPalette?: string[];
  animationDuration?: number;
  normalizeMetrics?: boolean;
  gradientHighColor?: string;  // Add for compatibility with config
  gradientLowColor?: string;   // Add for compatibility with config
}

export interface NodeMetrics {
  id: string;
  node_type: string;
  degree_centrality?: number;
  pagerank_centrality?: number;
  betweenness_centrality?: number;
  eigenvector_centrality?: number;
  cluster?: string | number;
  created_at_timestamp?: number;
  [key: string]: any;
}

interface ColorTransition {
  nodeId: string;
  fromColor: string;
  toColor: string;
  startTime: number;
  duration: number;
}

interface MetricStats {
  min: number;
  max: number;
  mean: number;
  stdDev: number;
  percentiles: {
    p25: number;
    p50: number;
    p75: number;
    p90: number;
    p95: number;
    p99: number;
  };
}

/**
 * Main color manager class
 */
export class NodeColorManager {
  private config: ColorSchemeConfig;
  private nodes: NodeMetrics[] = [];
  private colorCache = new Map<string, string>();
  private transitions = new Map<string, ColorTransition>();
  private metricStats = new Map<string, MetricStats>();
  private animationFrame: number | null = null;
  private colorFunction: ((node: NodeMetrics) => string) | null = null;

  constructor(config: ColorSchemeConfig = { scheme: 'by-type' }) {
    this.config = config;
    this.buildColorFunction();
  }

  /**
   * Update configuration and rebuild color function
   */
  updateConfig(config: Partial<ColorSchemeConfig>) {
    this.config = { ...this.config, ...config };
    this.colorCache.clear();
    this.buildColorFunction();
  }

  /**
   * Set nodes and calculate statistics
   */
  setNodes(nodes: NodeMetrics[]) {
    this.nodes = nodes;
    this.calculateMetricStats();
    this.colorCache.clear();
  }

  /**
   * Calculate statistics for all metrics
   */
  private calculateMetricStats() {
    const metrics = [
      'degree_centrality',
      'pagerank_centrality',
      'betweenness_centrality',
      'eigenvector_centrality'
    ];

    metrics.forEach(metric => {
      const values = this.nodes
        .map(n => n[metric] as number)
        .filter(v => v !== undefined && v !== null)
        .sort((a, b) => a - b);

      if (values.length === 0) return;

      const stats: MetricStats = {
        min: values[0],
        max: values[values.length - 1],
        mean: values.reduce((a, b) => a + b, 0) / values.length,
        stdDev: 0,
        percentiles: {
          p25: this.getPercentile(values, 0.25),
          p50: this.getPercentile(values, 0.50),
          p75: this.getPercentile(values, 0.75),
          p90: this.getPercentile(values, 0.90),
          p95: this.getPercentile(values, 0.95),
          p99: this.getPercentile(values, 0.99)
        }
      };

      // Calculate standard deviation
      const variance = values.reduce((sum, v) => sum + Math.pow(v - stats.mean, 2), 0) / values.length;
      stats.stdDev = Math.sqrt(variance);

      this.metricStats.set(metric, stats);
    });
  }

  /**
   * Get percentile value from sorted array
   */
  private getPercentile(sortedArray: number[], percentile: number): number {
    const index = Math.ceil(sortedArray.length * percentile) - 1;
    return sortedArray[Math.max(0, Math.min(index, sortedArray.length - 1))];
  }

  /**
   * Build the color function based on current scheme
   */
  private buildColorFunction() {
    switch (this.config.scheme) {
      case 'by-type':
        this.colorFunction = this.buildTypeColorFunction();
        break;
      case 'by-centrality':
        this.colorFunction = this.buildMetricColorFunction('degree_centrality');
        break;
      case 'by-pagerank':
        this.colorFunction = this.buildMetricColorFunction('pagerank_centrality');
        break;
      case 'by-degree':
        this.colorFunction = this.buildMetricColorFunction('degree_centrality');
        break;
      case 'by-betweenness':
        this.colorFunction = this.buildMetricColorFunction('betweenness_centrality');
        break;
      case 'by-eigenvector':
        this.colorFunction = this.buildMetricColorFunction('eigenvector_centrality');
        break;
      case 'by-community':
        this.colorFunction = this.buildCommunityColorFunction();
        break;
      case 'by-temporal':
        this.colorFunction = this.buildTemporalColorFunction();
        break;
      case 'custom':
        this.colorFunction = this.buildCustomColorFunction();
        break;
      default:
        this.colorFunction = this.buildTypeColorFunction();
    }
  }

  /**
   * Build type-based color function
   */
  private buildTypeColorFunction() {
    return (node: NodeMetrics): string => {
      const nodeType = node.node_type || 'Unknown';
      if (this.config.nodeTypeColors?.[nodeType]) {
        return this.config.nodeTypeColors[nodeType];
      }
      // Generate color based on type index
      const typeIndex = Array.from(new Set(this.nodes.map(n => n.node_type))).indexOf(nodeType);
      return generateNodeTypeColor(nodeType, typeIndex);
    };
  }

  /**
   * Build metric-based color function with advanced normalization
   */
  private buildMetricColorFunction(metricName: string) {
    return (node: NodeMetrics): string => {
      const value = node[metricName] as number || 0;
      const stats = this.metricStats.get(metricName);
      
      if (!stats || stats.max === stats.min) {
        return this.config.lowColor || '#4ECDC4';
      }

      let normalized: number;
      
      if (this.config.normalizeMetrics) {
        // Use percentile-based normalization for better distribution
        if (value <= stats.percentiles.p25) {
          normalized = 0.25 * (value - stats.min) / (stats.percentiles.p25 - stats.min);
        } else if (value <= stats.percentiles.p50) {
          normalized = 0.25 + 0.25 * (value - stats.percentiles.p25) / (stats.percentiles.p50 - stats.percentiles.p25);
        } else if (value <= stats.percentiles.p75) {
          normalized = 0.5 + 0.25 * (value - stats.percentiles.p50) / (stats.percentiles.p75 - stats.percentiles.p50);
        } else {
          normalized = 0.75 + 0.25 * (value - stats.percentiles.p75) / (stats.max - stats.percentiles.p75);
        }
      } else {
        // Simple linear normalization
        normalized = (value - stats.min) / (stats.max - stats.min);
      }

      // Apply color gradient - use gradientHighColor/gradientLowColor first, then fallback
      const highColor = this.config.gradientHighColor || this.config.highColor || this.getDefaultHighColor(metricName);
      const lowColor = this.config.gradientLowColor || this.config.lowColor || this.getDefaultLowColor(metricName);
      
      if (this.config.midColor) {
        // Three-color gradient
        if (normalized < 0.5) {
          return interpolateColor(lowColor, this.config.midColor, normalized * 2);
        } else {
          return interpolateColor(this.config.midColor, highColor, (normalized - 0.5) * 2);
        }
      } else {
        // Two-color gradient
        return interpolateColor(lowColor, highColor, normalized);
      }
    };
  }

  /**
   * Build community-based color function
   */
  private buildCommunityColorFunction() {
    const defaultPalette = [
      '#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
      '#1abc9c', '#34495e', '#e67e22', '#95a5a6', '#d35400',
      '#16a085', '#27ae60', '#2980b9', '#8e44ad', '#2c3e50',
      '#f1c40f', '#e74c3c', '#ecf0f1', '#95a5a6', '#34495e'
    ];
    
    const palette = this.config.communityPalette || defaultPalette;
    const communityMap = new Map<string, string>();
    
    return (node: NodeMetrics): string => {
      const cluster = String(node.cluster || '0');
      
      if (!communityMap.has(cluster)) {
        const index = communityMap.size;
        communityMap.set(cluster, palette[index % palette.length]);
      }
      
      return communityMap.get(cluster)!;
    };
  }

  /**
   * Build temporal color function (color by age)
   */
  private buildTemporalColorFunction() {
    return (node: NodeMetrics): string => {
      const timestamp = node.created_at_timestamp || Date.now();
      const now = Date.now();
      const age = now - timestamp;
      const maxAge = 30 * 24 * 60 * 60 * 1000; // 30 days in milliseconds
      
      const normalized = Math.min(1, age / maxAge);
      
      // New nodes are bright, old nodes fade
      const highColor = this.config.highColor || '#FFD700'; // Gold for new
      const lowColor = this.config.lowColor || '#4A5568'; // Gray for old
      
      return interpolateColor(highColor, lowColor, normalized);
    };
  }

  /**
   * Build custom color function
   */
  private buildCustomColorFunction() {
    // Allow for custom logic injection
    return (node: NodeMetrics): string => {
      // Default to type-based coloring
      return this.buildTypeColorFunction()(node);
    };
  }

  /**
   * Get default high color for metric
   */
  private getDefaultHighColor(metric: string): string {
    const defaults: Record<string, string> = {
      degree_centrality: '#FF6B6B',
      pagerank_centrality: '#FF9F43',
      betweenness_centrality: '#E74C3C',
      eigenvector_centrality: '#C0392B'
    };
    return defaults[metric] || '#FF6B6B';
  }

  /**
   * Get default low color for metric
   */
  private getDefaultLowColor(metric: string): string {
    const defaults: Record<string, string> = {
      degree_centrality: '#4ECDC4',
      pagerank_centrality: '#3498DB',
      betweenness_centrality: '#AED6F1',
      eigenvector_centrality: '#EBF5FB'
    };
    return defaults[metric] || '#4ECDC4';
  }

  /**
   * Get color for a specific node
   */
  getNodeColor(node: NodeMetrics): string {
    const cacheKey = `${node.id}-${this.config.scheme}`;
    
    if (this.colorCache.has(cacheKey)) {
      return this.colorCache.get(cacheKey)!;
    }

    if (!this.colorFunction) {
      this.buildColorFunction();
    }

    const color = this.colorFunction!(node);
    this.colorCache.set(cacheKey, color);
    
    // Debug logging for development
    if (this.config.scheme !== 'by-type' && Math.random() < 0.01) { // Log 1% of nodes
      console.log(`[NodeColorManager] Node color:`, {
        scheme: this.config.scheme,
        nodeId: node.id,
        nodeType: node.node_type,
        metrics: {
          degree: node.degree_centrality,
          pagerank: node.pagerank_centrality,
          betweenness: node.betweenness_centrality,
          eigenvector: node.eigenvector_centrality
        },
        color,
        stats: this.metricStats.get(
          this.config.scheme === 'by-centrality' ? 'degree_centrality' :
          this.config.scheme === 'by-pagerank' ? 'pagerank_centrality' :
          this.config.scheme === 'by-betweenness' ? 'betweenness_centrality' :
          this.config.scheme === 'by-eigenvector' ? 'eigenvector_centrality' :
          'degree_centrality'
        )
      });
    }
    
    return color;
  }

  /**
   * Get color for a node by ID
   */
  getNodeColorById(nodeId: string): string | null {
    const node = this.nodes.find(n => n.id === nodeId);
    return node ? this.getNodeColor(node) : null;
  }

  /**
   * Get color map for all nodes
   */
  getColorMap(): Map<string, string> {
    const map = new Map<string, string>();
    this.nodes.forEach(node => {
      map.set(node.id, this.getNodeColor(node));
    });
    return map;
  }

  /**
   * Get color map by node type (for Cosmograph compatibility)
   */
  getTypeColorMap(): Record<string, string> {
    const map: Record<string, string> = {};
    
    if (this.config.scheme === 'by-type') {
      // For type-based coloring, use the configured colors directly
      const nodeTypes = new Set(this.nodes.map(n => n.node_type));
      let index = 0;
      nodeTypes.forEach(nodeType => {
        if (this.config.nodeTypeColors?.[nodeType]) {
          map[nodeType] = this.config.nodeTypeColors[nodeType];
        } else {
          map[nodeType] = generateNodeTypeColor(nodeType, index);
        }
        index++;
      });
    } else {
      // For metric-based coloring, get a representative color per type
      const typeNodes = new Map<string, NodeMetrics>();
      
      // Get one representative node per type (with median metric value)
      this.nodes.forEach(node => {
        if (!typeNodes.has(node.node_type)) {
          typeNodes.set(node.node_type, node);
        }
      });
      
      // Generate color for each type based on representative node
      typeNodes.forEach((node, type) => {
        map[type] = this.getNodeColor(node);
      });
    }
    
    return map;
  }

  /**
   * Animate color transition
   */
  animateColorTransition(nodeId: string, toColor: string, duration?: number) {
    const fromColor = this.getNodeColorById(nodeId) || '#999999';
    const transitionDuration = duration || this.config.animationDuration || 300;
    
    this.transitions.set(nodeId, {
      nodeId,
      fromColor,
      toColor,
      startTime: Date.now(),
      duration: transitionDuration
    });
    
    if (!this.animationFrame) {
      this.startAnimationLoop();
    }
  }

  /**
   * Start animation loop
   */
  private startAnimationLoop() {
    const animate = () => {
      const now = Date.now();
      let hasActiveTransitions = false;
      
      this.transitions.forEach((transition, nodeId) => {
        const elapsed = now - transition.startTime;
        const progress = Math.min(1, elapsed / transition.duration);
        
        if (progress >= 1) {
          // Transition complete
          this.colorCache.set(`${nodeId}-${this.config.scheme}`, transition.toColor);
          this.transitions.delete(nodeId);
        } else {
          // Interpolate color
          const currentColor = interpolateColor(transition.fromColor, transition.toColor, progress);
          this.colorCache.set(`${nodeId}-${this.config.scheme}`, currentColor);
          hasActiveTransitions = true;
        }
      });
      
      if (hasActiveTransitions) {
        this.animationFrame = requestAnimationFrame(animate);
      } else {
        this.animationFrame = null;
      }
    };
    
    this.animationFrame = requestAnimationFrame(animate);
  }

  /**
   * Stop all animations
   */
  stopAnimations() {
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }
    this.transitions.clear();
  }

  /**
   * Clear cache
   */
  clearCache() {
    this.colorCache.clear();
  }

  /**
   * Get metric statistics
   */
  getMetricStats(metric: string): MetricStats | undefined {
    return this.metricStats.get(metric);
  }

  /**
   * Create a color function for Cosmograph
   */
  createCosmographColorFunction(): (node: any) => string {
    return (node: any) => {
      return this.getNodeColor(node as NodeMetrics);
    };
  }
}

// Singleton instance for global access
let globalManager: NodeColorManager | null = null;

export function getGlobalColorManager(config?: ColorSchemeConfig): NodeColorManager {
  if (!globalManager) {
    globalManager = new NodeColorManager(config);
  } else if (config) {
    globalManager.updateConfig(config);
  }
  return globalManager;
}

export function resetGlobalColorManager(): void {
  if (globalManager) {
    globalManager.stopAnimations();
  }
  globalManager = null;
}