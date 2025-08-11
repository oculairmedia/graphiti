/**
 * Memory leak detection and prevention utilities
 */

import { logger } from '../../../utils/logger';

interface LeakReport {
  component: string;
  type: 'event-listener' | 'timer' | 'subscription' | 'ref' | 'closure';
  description: string;
  stack?: string;
}

/**
 * LeakDetector - Tracks potential memory leaks in components
 */
export class LeakDetector {
  private static instance: LeakDetector | null = null;
  private eventListeners = new WeakMap<object, Set<string>>();
  private timers = new Map<string, Set<NodeJS.Timeout>>();
  private subscriptions = new Map<string, Set<() => void>>();
  private refs = new WeakMap<object, Set<any>>();
  private leaks: LeakReport[] = [];
  
  static getInstance(): LeakDetector {
    if (!LeakDetector.instance) {
      LeakDetector.instance = new LeakDetector();
    }
    return LeakDetector.instance;
  }
  
  // Track event listener
  trackEventListener(
    component: string,
    target: EventTarget,
    type: string,
    listener: EventListener
  ): () => void {
    const key = `${component}:${type}`;
    
    if (!this.eventListeners.has(target)) {
      this.eventListeners.set(target, new Set());
    }
    this.eventListeners.get(target)!.add(key);
    
    // Return cleanup function
    return () => {
      const listeners = this.eventListeners.get(target);
      if (listeners) {
        listeners.delete(key);
        if (listeners.size === 0) {
          this.eventListeners.delete(target);
        }
      }
    };
  }
  
  // Track timer
  trackTimer(component: string, timer: NodeJS.Timeout): () => void {
    if (!this.timers.has(component)) {
      this.timers.set(component, new Set());
    }
    this.timers.get(component)!.add(timer);
    
    return () => {
      const timers = this.timers.get(component);
      if (timers) {
        timers.delete(timer);
        clearTimeout(timer);
        if (timers.size === 0) {
          this.timers.delete(component);
        }
      }
    };
  }
  
  // Track subscription
  trackSubscription(component: string, unsubscribe: () => void): () => void {
    if (!this.subscriptions.has(component)) {
      this.subscriptions.set(component, new Set());
    }
    this.subscriptions.get(component)!.add(unsubscribe);
    
    return () => {
      const subs = this.subscriptions.get(component);
      if (subs) {
        subs.delete(unsubscribe);
        unsubscribe();
        if (subs.size === 0) {
          this.subscriptions.delete(component);
        }
      }
    };
  }
  
  // Check for leaks
  checkLeaks(component: string): LeakReport[] {
    const leaks: LeakReport[] = [];
    
    // Check timers
    const timers = this.timers.get(component);
    if (timers && timers.size > 0) {
      leaks.push({
        component,
        type: 'timer',
        description: `${timers.size} timer(s) not cleared`
      });
    }
    
    // Check subscriptions
    const subs = this.subscriptions.get(component);
    if (subs && subs.size > 0) {
      leaks.push({
        component,
        type: 'subscription',
        description: `${subs.size} subscription(s) not cleaned up`
      });
    }
    
    return leaks;
  }
  
  // Clean up component
  cleanup(component: string): void {
    // Clear timers
    const timers = this.timers.get(component);
    if (timers) {
      timers.forEach(timer => clearTimeout(timer));
      this.timers.delete(component);
    }
    
    // Clear subscriptions
    const subs = this.subscriptions.get(component);
    if (subs) {
      subs.forEach(unsub => unsub());
      this.subscriptions.delete(component);
    }
    
    logger.log(`LeakDetector: Cleaned up component ${component}`);
  }
  
  // Get report
  getReport(): string {
    const report: string[] = ['=== Memory Leak Report ==='];
    
    // Report timers
    this.timers.forEach((timers, component) => {
      if (timers.size > 0) {
        report.push(`${component}: ${timers.size} active timer(s)`);
      }
    });
    
    // Report subscriptions
    this.subscriptions.forEach((subs, component) => {
      if (subs.size > 0) {
        report.push(`${component}: ${subs.size} active subscription(s)`);
      }
    });
    
    // Report detected leaks
    if (this.leaks.length > 0) {
      report.push('\nDetected Leaks:');
      this.leaks.forEach(leak => {
        report.push(`- ${leak.component}: ${leak.type} - ${leak.description}`);
      });
    }
    
    return report.join('\n');
  }
}

/**
 * Hook for leak-safe component lifecycle
 */
export function useLeakSafe(componentName: string) {
  const detector = LeakDetector.getInstance();
  const cleanupFns: Array<() => void> = [];
  
  const trackEventListener = (
    target: EventTarget,
    type: string,
    listener: EventListener,
    options?: any
  ) => {
    target.addEventListener(type, listener, options);
    const cleanup = detector.trackEventListener(componentName, target, type, listener);
    cleanupFns.push(() => {
      target.removeEventListener(type, listener, options);
      cleanup();
    });
  };
  
  const trackTimer = (callback: () => void, delay: number): NodeJS.Timeout => {
    const timer = setTimeout(callback, delay);
    const cleanup = detector.trackTimer(componentName, timer);
    cleanupFns.push(cleanup);
    return timer;
  };
  
  const trackInterval = (callback: () => void, delay: number): NodeJS.Timeout => {
    const timer = setInterval(callback, delay);
    const cleanup = detector.trackTimer(componentName, timer);
    cleanupFns.push(() => {
      clearInterval(timer);
      cleanup();
    });
    return timer;
  };
  
  const trackSubscription = (unsubscribe: () => void) => {
    const cleanup = detector.trackSubscription(componentName, unsubscribe);
    cleanupFns.push(cleanup);
    return unsubscribe;
  };
  
  const cleanup = () => {
    cleanupFns.forEach(fn => fn());
    cleanupFns.length = 0;
    detector.cleanup(componentName);
  };
  
  return {
    trackEventListener,
    trackTimer,
    trackInterval,
    trackSubscription,
    cleanup
  };
}

/**
 * Resource manager for automatic cleanup
 */
export class ResourceManager {
  private resources = new Map<string, Set<() => void>>();
  
  register(id: string, cleanup: () => void): void {
    if (!this.resources.has(id)) {
      this.resources.set(id, new Set());
    }
    this.resources.get(id)!.add(cleanup);
  }
  
  unregister(id: string, cleanup: () => void): void {
    const cleanups = this.resources.get(id);
    if (cleanups) {
      cleanups.delete(cleanup);
      if (cleanups.size === 0) {
        this.resources.delete(id);
      }
    }
  }
  
  cleanup(id?: string): void {
    if (id) {
      const cleanups = this.resources.get(id);
      if (cleanups) {
        cleanups.forEach(cleanup => {
          try {
            cleanup();
          } catch (error) {
            logger.error(`ResourceManager: Error during cleanup of ${id}:`, error);
          }
        });
        this.resources.delete(id);
      }
    } else {
      // Cleanup all
      this.resources.forEach((cleanups, resourceId) => {
        cleanups.forEach(cleanup => {
          try {
            cleanup();
          } catch (error) {
            logger.error(`ResourceManager: Error during cleanup of ${resourceId}:`, error);
          }
        });
      });
      this.resources.clear();
    }
  }
  
  getActiveResources(): string[] {
    return Array.from(this.resources.keys());
  }
}

/**
 * Weak reference holder for preventing strong references
 */
export class WeakRefHolder<T extends object> {
  private ref: WeakRef<T> | null = null;
  
  set(value: T): void {
    this.ref = new WeakRef(value);
  }
  
  get(): T | undefined {
    return this.ref?.deref();
  }
  
  clear(): void {
    this.ref = null;
  }
}

/**
 * Safe RAF manager
 */
export class SafeRAF {
  private rafId: number | null = null;
  
  request(callback: FrameRequestCallback): void {
    this.cancel();
    this.rafId = requestAnimationFrame(callback);
  }
  
  cancel(): void {
    if (this.rafId !== null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }
  
  isActive(): boolean {
    return this.rafId !== null;
  }
}