/**
 * Reset DuckDB to fix schema mismatches
 * This clears the DuckDB storage and forces a fresh table creation
 */

export async function resetDuckDBStorage() {
  console.log('=== RESETTING DUCKDB STORAGE ===');
  
  try {
    // Clear IndexedDB (where DuckDB stores its data)
    const databases = await indexedDB.databases();
    for (const db of databases) {
      if (db.name && (db.name.includes('duckdb') || db.name.includes('cosmograph'))) {
        console.log(`Deleting database: ${db.name}`);
        await indexedDB.deleteDatabase(db.name);
      }
    }
    
    // Clear localStorage items related to Cosmograph/DuckDB
    const keysToRemove: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && (key.includes('duckdb') || key.includes('cosmograph'))) {
        keysToRemove.push(key);
      }
    }
    keysToRemove.forEach(key => {
      console.log(`Removing localStorage: ${key}`);
      localStorage.removeItem(key);
    });
    
    // Clear sessionStorage as well
    const sessionKeysToRemove: string[] = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key && (key.includes('duckdb') || key.includes('cosmograph'))) {
        sessionKeysToRemove.push(key);
      }
    }
    sessionKeysToRemove.forEach(key => {
      console.log(`Removing sessionStorage: ${key}`);
      sessionStorage.removeItem(key);
    });
    
    console.log('DuckDB storage cleared. Please refresh the page to reinitialize with correct schema.');
    console.log('The new table will be created with only the fields Cosmograph actually uses.');
    
    return true;
  } catch (error) {
    console.error('Error resetting DuckDB:', error);
    return false;
  }
}

// Make it available globally
if (typeof window !== 'undefined') {
  (window as any).resetDuckDBStorage = resetDuckDBStorage;
}