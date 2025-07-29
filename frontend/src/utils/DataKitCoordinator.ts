/**
 * Global singleton to coordinate Data Kit usage across all component instances.
 * This ensures that only one Data Kit operation runs at a time, preventing
 * concurrency issues and improving performance.
 */
export class DataKitCoordinator {
  private static instance: DataKitCoordinator;
  private isBusy = false;
  private queue: Array<() => Promise<void>> = [];
  private processTimeoutId: NodeJS.Timeout | null = null;
  
  static getInstance(): DataKitCoordinator {
    if (!DataKitCoordinator.instance) {
      DataKitCoordinator.instance = new DataKitCoordinator();
    }
    return DataKitCoordinator.instance;
  }
  
  async executeDataKit(task: () => Promise<void>): Promise<void> {
    return new Promise((resolve, reject) => {
      this.queue.push(async () => {
        try {
          await task();
          resolve();
        } catch (error) {
          reject(error);
        }
      });
      
      this.processQueue();
    });
  }
  
  private async processQueue(): Promise<void> {
    if (this.isBusy || this.queue.length === 0) {
      return;
    }
    
    this.isBusy = true;
    const task = this.queue.shift()!;
    
    try {
      await task();
    } finally {
      this.isBusy = false;
      // Clear any existing timeout before setting new one
      if (this.processTimeoutId) {
        clearTimeout(this.processTimeoutId);
      }
      // Process next item in queue
      this.processTimeoutId = setTimeout(() => {
        this.processTimeoutId = null;
        this.processQueue();
      }, 10);
    }
  }
  
  // Method to clean up pending operations
  cleanup(): void {
    if (this.processTimeoutId) {
      clearTimeout(this.processTimeoutId);
      this.processTimeoutId = null;
    }
    this.queue = [];
    this.isBusy = false;
  }
}

// Export singleton instance
export const dataKitCoordinator = DataKitCoordinator.getInstance();