import { useRef, useCallback, useEffect, useState } from 'react';

export interface PerformanceMetrics {
  fps: number;
  frameTime: number;
  renderTime: number;
  updateTime: number;
  memoryUsage: number;
  nodeCount: number;
  edgeCount: number;
  visibleNodes: number;
  visibleEdges: number;
}

export interface PerformanceStats {
  current: PerformanceMetrics;
  average: PerformanceMetrics;
  peak: PerformanceMetrics;
  history: PerformanceMetrics[];
}

export interface PerformanceMonitorConfig {
  enabled?: boolean;
  sampleRate?: number; // ms between samples
  historySize?: number;
  onThreshold?: (metric: keyof PerformanceMetrics, value: number) => void;
  thresholds?: Partial<Record<keyof PerformanceMetrics, number>>;
}

/**
 * Custom hook for monitoring graph rendering performance
 */
export function usePerformanceMonitor(config: PerformanceMonitorConfig = {}) {
  const {
    enabled = true,
    sampleRate = 1000, // Sample every second
    historySize = 60, // Keep 1 minute of history
    onThreshold,
    thresholds = {
      fps: 30, // Alert if FPS drops below 30
      frameTime: 33, // Alert if frame time exceeds 33ms (30fps)
      renderTime: 16, // Alert if render time exceeds 16ms (60fps)
      memoryUsage: 500 * 1024 * 1024 // Alert if memory exceeds 500MB
    }
  } = config;

  // State
  const [stats, setStats] = useState<PerformanceStats>({
    current: createEmptyMetrics(),
    average: createEmptyMetrics(),
    peak: createEmptyMetrics(),
    history: []
  });

  // Refs for performance tracking
  const frameCountRef = useRef(0);
  const lastFrameTimeRef = useRef(performance.now());
  const fpsHistoryRef = useRef<number[]>([]);
  const renderTimesRef = useRef<number[]>([]);
  const updateTimesRef = useRef<number[]>([]);
  const metricsHistoryRef = useRef<PerformanceMetrics[]>([]);
  const rafIdRef = useRef<number | null>(null);
  const intervalIdRef = useRef<NodeJS.Timeout | null>(null);

  // Create empty metrics object
  function createEmptyMetrics(): PerformanceMetrics {
    return {
      fps: 0,
      frameTime: 0,
      renderTime: 0,
      updateTime: 0,
      memoryUsage: 0,
      nodeCount: 0,
      edgeCount: 0,
      visibleNodes: 0,
      visibleEdges: 0
    };
  }

  // Calculate FPS
  const calculateFPS = useCallback(() => {
    const now = performance.now();
    const deltaTime = now - lastFrameTimeRef.current;
    
    if (deltaTime >= 1000) {
      const fps = (frameCountRef.current / deltaTime) * 1000;
      fpsHistoryRef.current.push(fps);
      
      if (fpsHistoryRef.current.length > 10) {
        fpsHistoryRef.current.shift();
      }
      
      frameCountRef.current = 0;
      lastFrameTimeRef.current = now;
      
      return fps;
    }
    
    frameCountRef.current++;
    return fpsHistoryRef.current[fpsHistoryRef.current.length - 1] || 0;
  }, []);

  // Get memory usage (if available)
  const getMemoryUsage = useCallback((): number => {
    if ('memory' in performance) {
      // @ts-ignore - performance.memory is not in TypeScript types
      return performance.memory.usedJSHeapSize || 0;
    }
    return 0;
  }, []);

  // Start render timing
  const startRenderTiming = useCallback((): () => void => {
    const startTime = performance.now();
    
    return () => {
      const renderTime = performance.now() - startTime;
      renderTimesRef.current.push(renderTime);
      
      if (renderTimesRef.current.length > 10) {
        renderTimesRef.current.shift();
      }
    };
  }, []);

  // Start update timing
  const startUpdateTiming = useCallback((): () => void => {
    const startTime = performance.now();
    
    return () => {
      const updateTime = performance.now() - startTime;
      updateTimesRef.current.push(updateTime);
      
      if (updateTimesRef.current.length > 10) {
        updateTimesRef.current.shift();
      }
    };
  }, []);

  // Update graph counts
  const updateCounts = useCallback((
    nodeCount: number,
    edgeCount: number,
    visibleNodes: number,
    visibleEdges: number
  ) => {
    setStats(prev => ({
      ...prev,
      current: {
        ...prev.current,
        nodeCount,
        edgeCount,
        visibleNodes,
        visibleEdges
      }
    }));
  }, []);

  // Calculate average of array
  const average = (arr: number[]): number => {
    if (arr.length === 0) return 0;
    return arr.reduce((a, b) => a + b, 0) / arr.length;
  };

  // Collect metrics
  const collectMetrics = useCallback((): PerformanceMetrics => {
    const fps = calculateFPS();
    const frameTime = fps > 0 ? 1000 / fps : 0;
    const renderTime = average(renderTimesRef.current);
    const updateTime = average(updateTimesRef.current);
    const memoryUsage = getMemoryUsage();
    
    return {
      fps: Math.round(fps),
      frameTime: Math.round(frameTime * 100) / 100,
      renderTime: Math.round(renderTime * 100) / 100,
      updateTime: Math.round(updateTime * 100) / 100,
      memoryUsage,
      nodeCount: stats.current.nodeCount,
      edgeCount: stats.current.edgeCount,
      visibleNodes: stats.current.visibleNodes,
      visibleEdges: stats.current.visibleEdges
    };
  }, [calculateFPS, getMemoryUsage, stats.current]);

  // Check thresholds
  const checkThresholds = useCallback((metrics: PerformanceMetrics) => {
    if (!onThreshold) return;
    
    Object.entries(thresholds).forEach(([key, threshold]) => {
      const metricKey = key as keyof PerformanceMetrics;
      const value = metrics[metricKey];
      
      if (typeof value === 'number' && typeof threshold === 'number') {
        // For FPS, alert if below threshold; for others, alert if above
        const shouldAlert = metricKey === 'fps' 
          ? value < threshold 
          : value > threshold;
        
        if (shouldAlert) {
          onThreshold(metricKey, value);
        }
      }
    });
  }, [thresholds, onThreshold]);

  // Update stats
  const updateStats = useCallback(() => {
    const currentMetrics = collectMetrics();
    
    // Update history
    metricsHistoryRef.current.push(currentMetrics);
    if (metricsHistoryRef.current.length > historySize) {
      metricsHistoryRef.current.shift();
    }
    
    // Calculate averages
    const avgMetrics = createEmptyMetrics();
    metricsHistoryRef.current.forEach(metrics => {
      Object.keys(avgMetrics).forEach(key => {
        const metricKey = key as keyof PerformanceMetrics;
        avgMetrics[metricKey] += metrics[metricKey];
      });
    });
    
    Object.keys(avgMetrics).forEach(key => {
      const metricKey = key as keyof PerformanceMetrics;
      avgMetrics[metricKey] /= metricsHistoryRef.current.length;
    });
    
    // Update peaks
    const peakMetrics = { ...stats.peak };
    Object.keys(currentMetrics).forEach(key => {
      const metricKey = key as keyof PerformanceMetrics;
      if (metricKey === 'fps') {
        // For FPS, track minimum as peak (worst performance)
        if (peakMetrics[metricKey] === 0 || currentMetrics[metricKey] < peakMetrics[metricKey]) {
          peakMetrics[metricKey] = currentMetrics[metricKey];
        }
      } else {
        // For other metrics, track maximum as peak
        if (currentMetrics[metricKey] > peakMetrics[metricKey]) {
          peakMetrics[metricKey] = currentMetrics[metricKey];
        }
      }
    });
    
    // Check thresholds
    checkThresholds(currentMetrics);
    
    // Update state
    setStats({
      current: currentMetrics,
      average: avgMetrics,
      peak: peakMetrics,
      history: [...metricsHistoryRef.current]
    });
  }, [collectMetrics, historySize, checkThresholds, stats.peak]);

  // Animation frame loop for FPS tracking
  const frameLoop = useCallback(() => {
    if (!enabled) return;
    
    frameCountRef.current++;
    rafIdRef.current = requestAnimationFrame(frameLoop);
  }, [enabled]);

  // Start monitoring
  useEffect(() => {
    if (!enabled) return;
    
    // Start animation frame loop
    rafIdRef.current = requestAnimationFrame(frameLoop);
    
    // Start metrics collection interval
    intervalIdRef.current = setInterval(updateStats, sampleRate);
    
    return () => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
      }
      if (intervalIdRef.current) {
        clearInterval(intervalIdRef.current);
      }
    };
  }, [enabled, frameLoop, updateStats, sampleRate]);

  // Reset stats
  const reset = useCallback(() => {
    frameCountRef.current = 0;
    lastFrameTimeRef.current = performance.now();
    fpsHistoryRef.current = [];
    renderTimesRef.current = [];
    updateTimesRef.current = [];
    metricsHistoryRef.current = [];
    
    setStats({
      current: createEmptyMetrics(),
      average: createEmptyMetrics(),
      peak: createEmptyMetrics(),
      history: []
    });
  }, []);

  // Export data for analysis
  const exportMetrics = useCallback((): string => {
    const data = {
      timestamp: new Date().toISOString(),
      stats,
      config: {
        sampleRate,
        historySize,
        thresholds
      }
    };
    
    return JSON.stringify(data, null, 2);
  }, [stats, sampleRate, historySize, thresholds]);

  // Generate performance report
  const generateReport = useCallback((): string => {
    const report = [
      '=== Performance Report ===',
      `Generated: ${new Date().toLocaleString()}`,
      '',
      '--- Current Metrics ---',
      `FPS: ${stats.current.fps} (${stats.current.frameTime}ms frame time)`,
      `Render Time: ${stats.current.renderTime}ms`,
      `Update Time: ${stats.current.updateTime}ms`,
      `Memory: ${(stats.current.memoryUsage / (1024 * 1024)).toFixed(2)}MB`,
      `Nodes: ${stats.current.visibleNodes}/${stats.current.nodeCount} visible`,
      `Edges: ${stats.current.visibleEdges}/${stats.current.edgeCount} visible`,
      '',
      '--- Average Metrics ---',
      `FPS: ${stats.average.fps.toFixed(1)}`,
      `Render Time: ${stats.average.renderTime.toFixed(2)}ms`,
      `Update Time: ${stats.average.updateTime.toFixed(2)}ms`,
      '',
      '--- Peak Metrics ---',
      `Lowest FPS: ${stats.peak.fps}`,
      `Highest Render Time: ${stats.peak.renderTime.toFixed(2)}ms`,
      `Highest Update Time: ${stats.peak.updateTime.toFixed(2)}ms`,
      `Peak Memory: ${(stats.peak.memoryUsage / (1024 * 1024)).toFixed(2)}MB`,
    ].join('\n');
    
    return report;
  }, [stats]);

  return {
    stats,
    startRenderTiming,
    startUpdateTiming,
    updateCounts,
    reset,
    exportMetrics,
    generateReport,
    isMonitoring: enabled
  };
}

/**
 * Performance monitor display component
 */
export const PerformanceMonitor: React.FC<{ stats: PerformanceStats }> = ({ stats }) => {
  const getStatusColor = (fps: number): string => {
    if (fps >= 50) return 'text-green-500';
    if (fps >= 30) return 'text-yellow-500';
    return 'text-red-500';
  };

  return (
    <div className="fixed bottom-4 left-4 bg-black/80 text-white p-3 rounded-lg text-xs font-mono space-y-1 min-w-[200px]">
      <div className={`font-bold ${getStatusColor(stats.current.fps)}`}>
        FPS: {stats.current.fps} ({stats.current.frameTime.toFixed(1)}ms)
      </div>
      <div>Render: {stats.current.renderTime.toFixed(1)}ms</div>
      <div>Update: {stats.current.updateTime.toFixed(1)}ms</div>
      <div>Memory: {(stats.current.memoryUsage / (1024 * 1024)).toFixed(1)}MB</div>
      <div className="border-t border-gray-600 pt-1 mt-1">
        <div>Nodes: {stats.current.visibleNodes}/{stats.current.nodeCount}</div>
        <div>Edges: {stats.current.visibleEdges}/{stats.current.edgeCount}</div>
      </div>
      {stats.history.length > 0 && (
        <div className="border-t border-gray-600 pt-1 mt-1">
          <div className="h-8">
            <svg width="100%" height="100%" viewBox="0 0 100 32">
              <polyline
                points={stats.history
                  .slice(-20)
                  .map((m, i) => `${(i / 19) * 100},${32 - (m.fps / 60) * 32}`)
                  .join(' ')}
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
                className={getStatusColor(stats.average.fps)}
              />
            </svg>
          </div>
        </div>
      )}
    </div>
  );
};