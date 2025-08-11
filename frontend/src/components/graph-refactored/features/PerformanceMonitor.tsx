import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';

interface PerformanceMetrics {
  fps: number;
  frameTime: number;
  memoryUsed: number;
  memoryLimit: number;
  renderTime: number;
  updateTime: number;
  nodeCount: number;
  edgeCount: number;
  visibleNodes: number;
  visibleEdges: number;
}

interface PerformanceConfig {
  enableMonitoring?: boolean;
  sampleRate?: number; // ms between samples
  historySize?: number; // number of samples to keep
  warnThresholds?: {
    fps?: number;
    frameTime?: number;
    memoryUsage?: number; // percentage
    renderTime?: number;
  };
  criticalThresholds?: {
    fps?: number;
    frameTime?: number;
    memoryUsage?: number;
    renderTime?: number;
  };
}

interface PerformanceMonitorProps {
  config?: PerformanceConfig;
  onMetricsUpdate?: (metrics: PerformanceMetrics) => void;
  onPerformanceWarning?: (warning: PerformanceWarning) => void;
  onPerformanceCritical?: (critical: PerformanceWarning) => void;
  children?: React.ReactNode;
}

interface PerformanceWarning {
  type: 'fps' | 'memory' | 'render' | 'frame';
  severity: 'warning' | 'critical';
  value: number;
  threshold: number;
  message: string;
  timestamp: number;
}

interface MonitorState {
  metrics: PerformanceMetrics;
  history: PerformanceMetrics[];
  warnings: PerformanceWarning[];
  isMonitoring: boolean;
  lastFrameTime: number;
  frameCount: number;
}

/**
 * PerformanceMonitor - Real-time performance monitoring for graph visualization
 * Tracks FPS, memory usage, render times, and provides optimization suggestions
 */
export const PerformanceMonitor: React.FC<PerformanceMonitorProps> = ({
  config = {},
  onMetricsUpdate,
  onPerformanceWarning,
  onPerformanceCritical,
  children
}) => {
  const [state, setState] = useState<MonitorState>({
    metrics: getDefaultMetrics(),
    history: [],
    warnings: [],
    isMonitoring: false,
    lastFrameTime: 0,
    frameCount: 0
  });

  const rafRef = useRef<number | null>(null);
  const intervalRef = useRef<NodeJS.Timeout | null>(null);
  const observerRef = useRef<PerformanceObserver | null>(null);

  // Default configuration
  const fullConfig: Required<PerformanceConfig> = {
    enableMonitoring: config.enableMonitoring ?? true,
    sampleRate: config.sampleRate ?? 100,
    historySize: config.historySize ?? 100,
    warnThresholds: {
      fps: config.warnThresholds?.fps ?? 30,
      frameTime: config.warnThresholds?.frameTime ?? 33,
      memoryUsage: config.warnThresholds?.memoryUsage ?? 70,
      renderTime: config.warnThresholds?.renderTime ?? 50
    },
    criticalThresholds: {
      fps: config.criticalThresholds?.fps ?? 15,
      frameTime: config.criticalThresholds?.frameTime ?? 66,
      memoryUsage: config.criticalThresholds?.memoryUsage ?? 90,
      renderTime: config.criticalThresholds?.renderTime ?? 100
    }
  };

  // Get default metrics
  function getDefaultMetrics(): PerformanceMetrics {
    return {
      fps: 60,
      frameTime: 16.67,
      memoryUsed: 0,
      memoryLimit: 0,
      renderTime: 0,
      updateTime: 0,
      nodeCount: 0,
      edgeCount: 0,
      visibleNodes: 0,
      visibleEdges: 0
    };
  }

  // Measure FPS
  const measureFPS = useCallback((timestamp: number) => {
    setState(prev => {
      const deltaTime = timestamp - prev.lastFrameTime;
      const fps = prev.lastFrameTime === 0 ? 60 : Math.round(1000 / deltaTime);
      
      return {
        ...prev,
        lastFrameTime: timestamp,
        frameCount: prev.frameCount + 1,
        metrics: {
          ...prev.metrics,
          fps,
          frameTime: deltaTime
        }
      };
    });
  }, []);

  // Measure memory usage
  const measureMemory = useCallback(() => {
    if ('memory' in performance) {
      const memory = (performance as any).memory;
      return {
        memoryUsed: Math.round(memory.usedJSHeapSize / 1048576), // MB
        memoryLimit: Math.round(memory.jsHeapSizeLimit / 1048576) // MB
      };
    }
    return { memoryUsed: 0, memoryLimit: 0 };
  }, []);

  // Measure render performance
  const measureRenderPerformance = useCallback(() => {
    const entries = performance.getEntriesByType('measure');
    const renderEntry = entries.find(e => e.name === 'graph-render');
    const updateEntry = entries.find(e => e.name === 'graph-update');
    
    return {
      renderTime: renderEntry ? renderEntry.duration : 0,
      updateTime: updateEntry ? updateEntry.duration : 0
    };
  }, []);

  // Collect all metrics
  const collectMetrics = useCallback(() => {
    const memory = measureMemory();
    const render = measureRenderPerformance();
    
    setState(prev => {
      const metrics: PerformanceMetrics = {
        ...prev.metrics,
        ...memory,
        ...render
      };
      
      // Update history
      const history = [...prev.history, metrics];
      if (history.length > fullConfig.historySize) {
        history.shift();
      }
      
      // Check for warnings
      const warnings = checkThresholds(metrics);
      
      // Notify listeners
      onMetricsUpdate?.(metrics);
      warnings.forEach(warning => {
        if (warning.severity === 'critical') {
          onPerformanceCritical?.(warning);
        } else {
          onPerformanceWarning?.(warning);
        }
      });
      
      return {
        ...prev,
        metrics,
        history,
        warnings: [...prev.warnings, ...warnings].slice(-10) // Keep last 10 warnings
      };
    });
  }, [measureMemory, measureRenderPerformance, fullConfig.historySize, onMetricsUpdate, onPerformanceWarning, onPerformanceCritical]);

  // Check performance thresholds
  function checkThresholds(metrics: PerformanceMetrics): PerformanceWarning[] {
    const warnings: PerformanceWarning[] = [];
    const now = Date.now();
    
    // Check FPS
    if (metrics.fps < fullConfig.criticalThresholds.fps!) {
      warnings.push({
        type: 'fps',
        severity: 'critical',
        value: metrics.fps,
        threshold: fullConfig.criticalThresholds.fps!,
        message: `Critical: FPS dropped to ${metrics.fps}`,
        timestamp: now
      });
    } else if (metrics.fps < fullConfig.warnThresholds.fps!) {
      warnings.push({
        type: 'fps',
        severity: 'warning',
        value: metrics.fps,
        threshold: fullConfig.warnThresholds.fps!,
        message: `Warning: FPS is ${metrics.fps}`,
        timestamp: now
      });
    }
    
    // Check frame time
    if (metrics.frameTime > fullConfig.criticalThresholds.frameTime!) {
      warnings.push({
        type: 'frame',
        severity: 'critical',
        value: metrics.frameTime,
        threshold: fullConfig.criticalThresholds.frameTime!,
        message: `Critical: Frame time is ${metrics.frameTime.toFixed(2)}ms`,
        timestamp: now
      });
    } else if (metrics.frameTime > fullConfig.warnThresholds.frameTime!) {
      warnings.push({
        type: 'frame',
        severity: 'warning',
        value: metrics.frameTime,
        threshold: fullConfig.warnThresholds.frameTime!,
        message: `Warning: Frame time is ${metrics.frameTime.toFixed(2)}ms`,
        timestamp: now
      });
    }
    
    // Check memory usage
    if (metrics.memoryLimit > 0) {
      const memoryUsage = (metrics.memoryUsed / metrics.memoryLimit) * 100;
      
      if (memoryUsage > fullConfig.criticalThresholds.memoryUsage!) {
        warnings.push({
          type: 'memory',
          severity: 'critical',
          value: memoryUsage,
          threshold: fullConfig.criticalThresholds.memoryUsage!,
          message: `Critical: Memory usage at ${memoryUsage.toFixed(1)}%`,
          timestamp: now
        });
      } else if (memoryUsage > fullConfig.warnThresholds.memoryUsage!) {
        warnings.push({
          type: 'memory',
          severity: 'warning',
          value: memoryUsage,
          threshold: fullConfig.warnThresholds.memoryUsage!,
          message: `Warning: Memory usage at ${memoryUsage.toFixed(1)}%`,
          timestamp: now
        });
      }
    }
    
    // Check render time
    if (metrics.renderTime > fullConfig.criticalThresholds.renderTime!) {
      warnings.push({
        type: 'render',
        severity: 'critical',
        value: metrics.renderTime,
        threshold: fullConfig.criticalThresholds.renderTime!,
        message: `Critical: Render time is ${metrics.renderTime.toFixed(2)}ms`,
        timestamp: now
      });
    } else if (metrics.renderTime > fullConfig.warnThresholds.renderTime!) {
      warnings.push({
        type: 'render',
        severity: 'warning',
        value: metrics.renderTime,
        threshold: fullConfig.warnThresholds.renderTime!,
        message: `Warning: Render time is ${metrics.renderTime.toFixed(2)}ms`,
        timestamp: now
      });
    }
    
    return warnings;
  }

  // Start monitoring
  const startMonitoring = useCallback(() => {
    setState(prev => ({ ...prev, isMonitoring: true }));
    
    // Start FPS monitoring
    const monitorFrame = (timestamp: number) => {
      measureFPS(timestamp);
      rafRef.current = requestAnimationFrame(monitorFrame);
    };
    rafRef.current = requestAnimationFrame(monitorFrame);
    
    // Start metrics collection
    intervalRef.current = setInterval(collectMetrics, fullConfig.sampleRate);
    
    // Set up Performance Observer for detailed metrics
    if ('PerformanceObserver' in window) {
      observerRef.current = new PerformanceObserver((list) => {
        // Process performance entries
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'measure') {
            console.log(`Performance: ${entry.name} took ${entry.duration}ms`);
          }
        }
      });
      
      observerRef.current.observe({ entryTypes: ['measure', 'navigation'] });
    }
  }, [measureFPS, collectMetrics, fullConfig.sampleRate]);

  // Stop monitoring
  const stopMonitoring = useCallback(() => {
    setState(prev => ({ ...prev, isMonitoring: false }));
    
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    
    if (observerRef.current) {
      observerRef.current.disconnect();
      observerRef.current = null;
    }
  }, []);

  // Calculate statistics from history
  const getStatistics = useCallback(() => {
    const { history } = state;
    if (history.length === 0) return null;
    
    const stats = {
      avgFPS: 0,
      minFPS: Infinity,
      maxFPS: -Infinity,
      avgFrameTime: 0,
      avgMemory: 0,
      avgRenderTime: 0
    };
    
    history.forEach(metrics => {
      stats.avgFPS += metrics.fps;
      stats.minFPS = Math.min(stats.minFPS, metrics.fps);
      stats.maxFPS = Math.max(stats.maxFPS, metrics.fps);
      stats.avgFrameTime += metrics.frameTime;
      stats.avgMemory += metrics.memoryUsed;
      stats.avgRenderTime += metrics.renderTime;
    });
    
    const count = history.length;
    stats.avgFPS /= count;
    stats.avgFrameTime /= count;
    stats.avgMemory /= count;
    stats.avgRenderTime /= count;
    
    return stats;
  }, [state.history]);

  // Get optimization suggestions
  const getOptimizationSuggestions = useCallback((): string[] => {
    const suggestions: string[] = [];
    const { metrics } = state;
    
    if (metrics.fps < 30) {
      suggestions.push('Consider reducing the number of visible nodes');
      suggestions.push('Enable progressive loading for large graphs');
      suggestions.push('Disable animations temporarily');
    }
    
    if (metrics.memoryLimit > 0) {
      const memoryUsage = (metrics.memoryUsed / metrics.memoryLimit) * 100;
      if (memoryUsage > 70) {
        suggestions.push('Clear unused data from cache');
        suggestions.push('Reduce history size in settings');
        suggestions.push('Consider paginating large datasets');
      }
    }
    
    if (metrics.renderTime > 50) {
      suggestions.push('Simplify node rendering');
      suggestions.push('Use simpler color schemes');
      suggestions.push('Reduce edge complexity');
    }
    
    if (metrics.nodeCount > 5000) {
      suggestions.push('Use clustering to group related nodes');
      suggestions.push('Implement viewport culling');
      suggestions.push('Consider server-side filtering');
    }
    
    return suggestions;
  }, [state.metrics]);

  // Auto-start monitoring if enabled
  useEffect(() => {
    if (fullConfig.enableMonitoring && !state.isMonitoring) {
      startMonitoring();
    }
    
    return () => {
      stopMonitoring();
    };
  }, [fullConfig.enableMonitoring, state.isMonitoring, startMonitoring, stopMonitoring]);

  // Context value
  const contextValue = useMemo(() => ({
    ...state,
    startMonitoring,
    stopMonitoring,
    getStatistics,
    getOptimizationSuggestions,
    clearHistory: () => setState(prev => ({ ...prev, history: [] })),
    clearWarnings: () => setState(prev => ({ ...prev, warnings: [] })),
    updateNodeCount: (count: number) => setState(prev => ({
      ...prev,
      metrics: { ...prev.metrics, nodeCount: count }
    })),
    updateEdgeCount: (count: number) => setState(prev => ({
      ...prev,
      metrics: { ...prev.metrics, edgeCount: count }
    }))
  }), [state, startMonitoring, stopMonitoring, getStatistics, getOptimizationSuggestions]);

  return (
    <PerformanceContext.Provider value={contextValue}>
      {children}
    </PerformanceContext.Provider>
  );
};

// Context
const PerformanceContext = React.createContext<any>({});

export const usePerformance = () => React.useContext(PerformanceContext);