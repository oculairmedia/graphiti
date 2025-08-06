// Utility to completely clear all caches
export async function clearAllCaches() {
  console.log('[ClearCache] Starting complete cache clear...');
  
  // Clear IndexedDB
  try {
    const databases = await indexedDB.databases();
    for (const db of databases) {
      if (db.name) {
        console.log(`[ClearCache] Deleting IndexedDB: ${db.name}`);
        await indexedDB.deleteDatabase(db.name);
      }
    }
  } catch (e) {
    console.log('[ClearCache] Could not enumerate databases, trying known names...');
    // Fallback for browsers that don't support databases()
    const knownDbs = ['GraphitiCache', 'cosmograph', 'duckdb-wasm'];
    for (const dbName of knownDbs) {
      try {
        await indexedDB.deleteDatabase(dbName);
        console.log(`[ClearCache] Deleted IndexedDB: ${dbName}`);
      } catch (e) {
        // Ignore if doesn't exist
      }
    }
  }
  
  // Clear localStorage
  try {
    localStorage.clear();
    console.log('[ClearCache] Cleared localStorage');
  } catch (e) {
    console.error('[ClearCache] Failed to clear localStorage:', e);
  }
  
  // Clear sessionStorage
  try {
    sessionStorage.clear();
    console.log('[ClearCache] Cleared sessionStorage');
  } catch (e) {
    console.error('[ClearCache] Failed to clear sessionStorage:', e);
  }
  
  // Clear all cookies
  try {
    document.cookie.split(";").forEach(function(c) { 
      document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
    });
    console.log('[ClearCache] Cleared cookies');
  } catch (e) {
    console.error('[ClearCache] Failed to clear cookies:', e);
  }
  
  console.log('[ClearCache] Complete cache clear finished');
  
  // Add to window for easy console access
  if (typeof window !== 'undefined') {
    (window as any).clearAllCaches = clearAllCaches;
  }
}

// Auto-expose to window
if (typeof window !== 'undefined') {
  (window as any).clearAllCaches = clearAllCaches;
}