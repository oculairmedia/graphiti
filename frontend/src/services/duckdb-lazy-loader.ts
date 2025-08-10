/**
 * Lazy loader for DuckDB WASM to reduce initial bundle size
 */

let duckdbModule: typeof import('@duckdb/duckdb-wasm') | null = null;
let loadPromise: Promise<typeof import('@duckdb/duckdb-wasm')> | null = null;

export async function loadDuckDB(): Promise<typeof import('@duckdb/duckdb-wasm')> {
  // Return cached module if already loaded
  if (duckdbModule) {
    return duckdbModule;
  }
  
  // Return existing promise if already loading
  if (loadPromise) {
    return loadPromise;
  }
  
  // Start loading
  console.log('[DuckDB Lazy] Starting lazy load of DuckDB WASM...');
  const startTime = performance.now();
  
  loadPromise = import('@duckdb/duckdb-wasm').then(module => {
    const elapsed = performance.now() - startTime;
    console.log(`[DuckDB Lazy] DuckDB WASM loaded in ${elapsed.toFixed(2)}ms`);
    duckdbModule = module;
    return module;
  });
  
  return loadPromise;
}

/**
 * Preload DuckDB in the background (non-blocking)
 */
export function preloadDuckDB(): void {
  // Use requestIdleCallback if available, otherwise setTimeout
  const schedulePreload = (callback: () => void) => {
    if ('requestIdleCallback' in window) {
      (window as any).requestIdleCallback(callback, { timeout: 2000 });
    } else {
      setTimeout(callback, 100);
    }
  };
  
  schedulePreload(() => {
    console.log('[DuckDB Lazy] Starting background preload...');
    loadDuckDB().catch(err => {
      console.error('[DuckDB Lazy] Background preload failed:', err);
    });
  });
}