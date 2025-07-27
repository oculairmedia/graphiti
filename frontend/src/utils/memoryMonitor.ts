// Memory monitoring utility for debugging memory leaks in production
// Only logs warnings when memory usage exceeds thresholds

interface MemorySnapshot {
  timestamp: number;
  usedJSHeapSize: number;
  totalJSHeapSize: number;
  jsHeapSizeLimit: number;
}

class MemoryMonitor {
  private snapshots: MemorySnapshot[] = [];
  private readonly maxSnapshots = 10;
  private readonly warningThreshold = 0.8; // Warn at 80% memory usage
  private readonly criticalThreshold = 0.9; // Critical at 90% memory usage
  private monitoringInterval: NodeJS.Timeout | null = null;
  private lastWarningTime = 0;
  private readonly warningCooldown = 60000; // Only warn once per minute

  start(intervalMs = 30000): void {
    // Only monitor if performance.memory is available (Chrome only)
    if (!this.isSupported()) {
      return;
    }

    this.stop(); // Clear any existing monitoring
    
    this.monitoringInterval = setInterval(() => {
      this.checkMemory();
    }, intervalMs);
    
    // Initial check
    this.checkMemory();
  }

  stop(): void {
    if (this.monitoringInterval) {
      clearInterval(this.monitoringInterval);
      this.monitoringInterval = null;
    }
    this.snapshots = [];
  }

  private isSupported(): boolean {
    return typeof performance !== 'undefined' && 
           'memory' in performance &&
           typeof (performance as any).memory === 'object';
  }

  private checkMemory(): void {
    if (!this.isSupported()) return;

    const memory = (performance as any).memory;
    const snapshot: MemorySnapshot = {
      timestamp: Date.now(),
      usedJSHeapSize: memory.usedJSHeapSize,
      totalJSHeapSize: memory.totalJSHeapSize,
      jsHeapSizeLimit: memory.jsHeapSizeLimit
    };

    this.snapshots.push(snapshot);
    if (this.snapshots.length > this.maxSnapshots) {
      this.snapshots.shift();
    }

    const usage = snapshot.usedJSHeapSize / snapshot.jsHeapSizeLimit;
    const now = Date.now();

    // Only log warnings if enough time has passed
    if (now - this.lastWarningTime < this.warningCooldown) {
      return;
    }

    if (usage > this.criticalThreshold) {
      console.error(`[MemoryMonitor] CRITICAL: Memory usage at ${(usage * 100).toFixed(1)}%`, {
        used: this.formatBytes(snapshot.usedJSHeapSize),
        limit: this.formatBytes(snapshot.jsHeapSizeLimit),
        trend: this.getMemoryTrend()
      });
      this.lastWarningTime = now;
    } else if (usage > this.warningThreshold) {
      console.warn(`[MemoryMonitor] WARNING: Memory usage at ${(usage * 100).toFixed(1)}%`, {
        used: this.formatBytes(snapshot.usedJSHeapSize),
        limit: this.formatBytes(snapshot.jsHeapSizeLimit),
        trend: this.getMemoryTrend()
      });
      this.lastWarningTime = now;
    }
  }

  private getMemoryTrend(): string {
    if (this.snapshots.length < 2) return 'insufficient data';

    const recent = this.snapshots.slice(-5);
    const first = recent[0];
    const last = recent[recent.length - 1];
    const growthRate = (last.usedJSHeapSize - first.usedJSHeapSize) / first.usedJSHeapSize;

    if (growthRate > 0.1) return 'increasing rapidly';
    if (growthRate > 0.05) return 'increasing';
    if (growthRate < -0.05) return 'decreasing';
    return 'stable';
  }

  private formatBytes(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  // Manual memory check for debugging
  logMemoryStats(): void {
    if (!this.isSupported()) {
      console.log('[MemoryMonitor] Memory monitoring not supported in this browser');
      return;
    }

    const memory = (performance as any).memory;
    const usage = memory.usedJSHeapSize / memory.jsHeapSizeLimit;

    console.log('[MemoryMonitor] Current memory stats:', {
      used: this.formatBytes(memory.usedJSHeapSize),
      total: this.formatBytes(memory.totalJSHeapSize),
      limit: this.formatBytes(memory.jsHeapSizeLimit),
      usage: `${(usage * 100).toFixed(1)}%`,
      trend: this.getMemoryTrend()
    });
  }
}

// Export singleton instance
export const memoryMonitor = new MemoryMonitor();

// Only start monitoring in production builds
if (import.meta.env.PROD) {
  memoryMonitor.start();
}