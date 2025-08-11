/**
 * Performance monitoring and optimization utilities
 */

import { logger } from '../../../utils/logger';

// Performance metrics collector
export class PerformanceMetrics {
  private metrics = new Map<string, number[]>();
  private marks = new Map<string, number>();
  
  startMeasure(name: string): void {
    this.marks.set(name, performance.now());
  }
  
  endMeasure(name: string): number {
    const startTime = this.marks.get(name);
    if (!startTime) {
      logger.warn(`PerformanceMetrics: No start mark for ${name}`);
      return 0;
    }
    
    const duration = performance.now() - startTime;
    this.marks.delete(name);
    
    // Store metric
    if (!this.metrics.has(name)) {
      this.metrics.set(name, []);
    }
    this.metrics.get(name)!.push(duration);
    
    // Keep only last 100 measurements
    const measurements = this.metrics.get(name)!;
    if (measurements.length > 100) {
      measurements.shift();
    }
    
    return duration;
  }
  
  getAverageMetric(name: string): number {
    const measurements = this.metrics.get(name);
    if (!measurements || measurements.length === 0) return 0;
    
    const sum = measurements.reduce((a, b) => a + b, 0);
    return sum / measurements.length;
  }
  
  getMetricStats(name: string): {
    avg: number;
    min: number;
    max: number;
    count: number;
  } {
    const measurements = this.metrics.get(name) || [];
    
    if (measurements.length === 0) {
      return { avg: 0, min: 0, max: 0, count: 0 };
    }
    
    const sum = measurements.reduce((a, b) => a + b, 0);
    const avg = sum / measurements.length;
    const min = Math.min(...measurements);
    const max = Math.max(...measurements);
    
    return { avg, min, max, count: measurements.length };
  }
  
  clear(name?: string): void {
    if (name) {
      this.metrics.delete(name);
      this.marks.delete(name);
    } else {
      this.metrics.clear();
      this.marks.clear();
    }
  }
  
  logSummary(): void {
    console.table(
      Array.from(this.metrics.keys()).map(name => ({
        name,
        ...this.getMetricStats(name)
      }))
    );
  }
}

// FPS counter
export class FPSCounter {
  private frameTimes: number[] = [];
  private lastTime = performance.now();
  private rafId: number | null = null;
  
  start(callback?: (fps: number) => void): void {
    if (this.rafId !== null) return;
    
    const frame = () => {
      const currentTime = performance.now();
      const delta = currentTime - this.lastTime;
      
      this.frameTimes.push(delta);
      if (this.frameTimes.length > 60) {
        this.frameTimes.shift();
      }
      
      // Calculate FPS
      const avgDelta = this.frameTimes.reduce((a, b) => a + b, 0) / this.frameTimes.length;
      const fps = 1000 / avgDelta;
      
      callback?.(fps);
      
      this.lastTime = currentTime;
      this.rafId = requestAnimationFrame(frame);
    };
    
    this.rafId = requestAnimationFrame(frame);
  }
  
  stop(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
    this.frameTimes = [];
  }
  
  getCurrentFPS(): number {
    if (this.frameTimes.length === 0) return 0;
    
    const avgDelta = this.frameTimes.reduce((a, b) => a + b, 0) / this.frameTimes.length;
    return 1000 / avgDelta;
  }
}

// Render performance observer
export class RenderObserver {
  private observer: PerformanceObserver | null = null;
  private renderMetrics: Array<{ duration: number; timestamp: number }> = [];
  
  start(callback?: (metrics: any) => void): void {
    if (!('PerformanceObserver' in window)) {
      logger.warn('RenderObserver: PerformanceObserver not supported');
      return;
    }
    
    try {
      this.observer = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (entry.entryType === 'measure' || entry.entryType === 'navigation') {
            this.renderMetrics.push({
              duration: entry.duration,
              timestamp: entry.startTime
            });
            
            // Keep only last 100 entries
            if (this.renderMetrics.length > 100) {
              this.renderMetrics.shift();
            }
            
            callback?.(entry);
          }
        }
      });
      
      this.observer.observe({ entryTypes: ['measure', 'navigation'] });
    } catch (error) {
      logger.error('RenderObserver: Failed to start:', error);
    }
  }
  
  stop(): void {
    if (this.observer) {
      this.observer.disconnect();
      this.observer = null;
    }
    this.renderMetrics = [];
  }
  
  getAverageRenderTime(): number {
    if (this.renderMetrics.length === 0) return 0;
    
    const sum = this.renderMetrics.reduce((a, b) => a + b.duration, 0);
    return sum / this.renderMetrics.length;
  }
}

// Memory usage tracker
export function getMemoryUsage(): {
  used: number;
  total: number;
  percent: number;
} | null {
  if (!('memory' in performance)) {
    return null;
  }
  
  const memory = (performance as any).memory;
  const used = memory.usedJSHeapSize;
  const total = memory.jsHeapSizeLimit;
  const percent = (used / total) * 100;
  
  return { used, total, percent };
}

// Adaptive quality controller
export class AdaptiveQuality {
  private targetFPS: number;
  private currentQuality: number = 1; // 0-1 scale
  private fpsHistory: number[] = [];
  
  constructor(targetFPS: number = 30) {
    this.targetFPS = targetFPS;
  }
  
  update(currentFPS: number): number {
    this.fpsHistory.push(currentFPS);
    
    if (this.fpsHistory.length > 10) {
      this.fpsHistory.shift();
    }
    
    const avgFPS = this.fpsHistory.reduce((a, b) => a + b, 0) / this.fpsHistory.length;
    
    if (avgFPS < this.targetFPS * 0.8) {
      // Reduce quality
      this.currentQuality = Math.max(0.1, this.currentQuality - 0.1);
    } else if (avgFPS > this.targetFPS * 1.2 && this.currentQuality < 1) {
      // Increase quality
      this.currentQuality = Math.min(1, this.currentQuality + 0.05);
    }
    
    return this.currentQuality;
  }
  
  getQuality(): number {
    return this.currentQuality;
  }
  
  reset(): void {
    this.currentQuality = 1;
    this.fpsHistory = [];
  }
}

// Performance budget checker
export class PerformanceBudget {
  private budgets: Map<string, number> = new Map();
  
  setBudget(metric: string, maxMs: number): void {
    this.budgets.set(metric, maxMs);
  }
  
  check(metric: string, actualMs: number): boolean {
    const budget = this.budgets.get(metric);
    if (!budget) return true;
    
    const withinBudget = actualMs <= budget;
    
    if (!withinBudget) {
      logger.warn(`PerformanceBudget: ${metric} exceeded budget: ${actualMs.toFixed(2)}ms > ${budget}ms`);
    }
    
    return withinBudget;
  }
  
  checkAll(metrics: Map<string, number>): boolean {
    let allWithinBudget = true;
    
    for (const [metric, actualMs] of metrics) {
      if (!this.check(metric, actualMs)) {
        allWithinBudget = false;
      }
    }
    
    return allWithinBudget;
  }
}