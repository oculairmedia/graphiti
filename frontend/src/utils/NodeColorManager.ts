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
import { scaleQuantile, scaleThreshold, ScaleQuantile, ScaleThreshold } from 'd3-scale';

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
  useQuantileScaling?: boolean; // Enable D3 quantile-based color mapping
  quantileBins?: number;       // Number of quantile bins (default: 5)
  useThresholdScaling?: boolean; // Enable D3 threshold-based color mapping
  customThresholds?: number[];  // Custom thresholds for threshold scaling
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
  median: number;
  q1: number;
  q3: number;
  iqr: number;
  mad: number;
  stdDev: number;
  scalingMax: number;
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
  private quantileScales = new Map<string, ScaleQuantile<string, never>>();
  private thresholdScales = new Map<string, ScaleThreshold<number, string, never>>();
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
    this.quantileScales.clear();
    this.thresholdScales.clear();
    this.buildColorFunction();
  }

  /**
   * Set nodes and calculate statistics
   */
  setNodes(nodes: NodeMetrics[]) {
    this.nodes = nodes;
    this.calculateMetricStats();
    this.colorCache.clear();
    this.quantileScales.clear();
    this.thresholdScales.clear();
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

      // Basic statistics
      const min = values[0];
      const max = values[values.length - 1];
      const mean = values.reduce((a, b) => a + b, 0) / values.length;
      const median = this.getPercentile(values, 0.50);
      const q1 = this.getPercentile(values, 0.25);
      const q3 = this.getPercentile(values, 0.75);
      const iqr = q3 - q1;
      
      // MAD calculation
      const deviations = values.map(val => Math.abs(val - median)).sort((a, b) => a - b);
      const mad = this.getPercentile(deviations, 0.5);
      
      // Use IQR-based scaling (Q3 + 1.5 * IQR) as default
      const scalingMax = Math.max(q3 + 1.5 * iqr, min + 0.000001);

      const stats: MetricStats = {
        min,
        max,
        mean,
        median,
        q1,
        q3,
        iqr,
        mad,
        stdDev: 0,
        scalingMax,
        percentiles: {
          p25: q1,
          p50: median,
          p75: q3,
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
    
    // Build D3 quantile and threshold scales
    this.buildD3Scales();
  }

  /**
   * Build D3 quantile and threshold scales for metrics
   */
  private buildD3Scales() {
    const metrics = [
      'degree_centrality',
      'pagerank_centrality',
      'betweenness_centrality',
      'eigenvector_centrality'
    ];

    metrics.forEach(metric => {
      const values = this.nodes
        .map(n => n[metric] as number)
        .filter(v => v !== undefined && v !== null);

      if (values.length === 0) return;

      // Create color range for quantile/threshold scales
      const bins = this.config.quantileBins || 5;
      const colorRange = this.generateColorRange(bins);

      // Build quantile scale
      if (this.config.useQuantileScaling) {
        const quantileScale = scaleQuantile<string>()
          .domain(values)
          .range(colorRange);
        this.quantileScales.set(metric, quantileScale);
      }

      // Build threshold scale
      if (this.config.useThresholdScaling && this.config.customThresholds) {
        const thresholdScale = scaleThreshold<number, string>()
          .domain(this.config.customThresholds)
          .range(colorRange);
        this.thresholdScales.set(metric, thresholdScale);
      } else if (this.config.useThresholdScaling) {
        // Auto-generate thresholds using percentiles
        const stats = this.metricStats.get(metric);
        if (stats) {
          const thresholds = [stats.percentiles.p25, stats.percentiles.p50, stats.percentiles.p75, stats.percentiles.p90];
          const thresholdScale = scaleThreshold<number, string>()
            .domain(thresholds)
            .range(colorRange);
          this.thresholdScales.set(metric, thresholdScale);
        }
      }
    });
  }

  /**
   * Generate color range for D3 scales
   */
  private generateColorRange(bins: number): string[] {
    const lowColor = this.config.gradientLowColor || this.config.lowColor || '#4ECDC4';
    const highColor = this.config.gradientHighColor || this.config.highColor || '#E63946';
    
    const colors: string[] = [];
    for (let i = 0; i < bins; i++) {
      const ratio = i / (bins - 1);
      colors.push(interpolateColor(lowColor, highColor, ratio));
    }
    
    return colors;
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
      
      // Check for D3 quantile scaling first
      if (this.config.useQuantileScaling && this.quantileScales.has(metricName)) {
        const quantileScale = this.quantileScales.get(metricName)!;
        return quantileScale(value);
      }
      
      // Check for D3 threshold scaling
      if (this.config.useThresholdScaling && this.thresholdScales.has(metricName)) {
        const thresholdScale = this.thresholdScales.get(metricName)!;
        return thresholdScale(value);
      }
      
      // Fall back to traditional scaling
      const stats = this.metricStats.get(metricName);
      
      if (!stats || stats.scalingMax === stats.min) {
        return this.config.lowColor || '#4ECDC4';
      }

      let normalized: number;
      
      // Special handling for eigenvector centrality with very small values
      if (metricName === 'eigenvector_centrality' && stats.scalingMax < 0.1) {
        // Use logarithmic scaling for better visual differentiation of small values
        const epsilon = 0.000001; // Small constant to avoid log(0)
        const logValue = Math.log10(Math.max(value, epsilon));
        const logMin = Math.log10(Math.max(stats.min, epsilon));
        const logMax = Math.log10(Math.max(stats.scalingMax, epsilon));
        
        if (logMax === logMin) {
          normalized = 0.5; // Fallback for edge case
        } else {
          normalized = Math.max(0, Math.min(1, (logValue - logMin) / (logMax - logMin)));
        }
      } else if (this.config.normalizeMetrics) {
        // Use percentile-based normalization for better distribution
        if (value <= stats.percentiles.p25) {
          normalized = 0.25 * (value - stats.min) / (stats.percentiles.p25 - stats.min);
        } else if (value <= stats.percentiles.p50) {
          normalized = 0.25 + 0.25 * (value - stats.percentiles.p25) / (stats.percentiles.p50 - stats.percentiles.p25);
        } else if (value <= stats.percentiles.p75) {
          normalized = 0.5 + 0.25 * (value - stats.percentiles.p50) / (stats.percentiles.p75 - stats.percentiles.p50);
        } else {
          normalized = 0.75 + 0.25 * (value - stats.percentiles.p75) / (stats.scalingMax - stats.percentiles.p75);
        }
      } else {
        // Simple linear normalization using moving average of top 10%
        normalized = Math.min(1, (value - stats.min) / (stats.scalingMax - stats.min));
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