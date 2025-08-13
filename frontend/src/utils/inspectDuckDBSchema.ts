/**
 * Utility to inspect DuckDB schema directly from Cosmograph
 * Run this in the browser console to see what columns DuckDB actually has
 */

export async function inspectDuckDBSchema() {
  // Get Cosmograph instance from the DOM
  const cosmographElement = document.querySelector('[data-cosmograph]') as any;
  const cosmograph = cosmographElement?.__cosmograph || 
                    window['cosmographRef']?.current ||
                    document.querySelector('.cosmograph-container')?.__cosmograph;
  
  if (!cosmograph) {
    console.error('Could not find Cosmograph instance');
    return;
  }
  
  // Access internal DuckDB instance
  const duckdb = cosmograph._duckdb || cosmograph.duckdb;
  
  if (!duckdb) {
    console.error('DuckDB not initialized in Cosmograph');
    return;
  }
  
  try {
    // Query points schema
    console.log('=== COSMOGRAPH_POINTS TABLE SCHEMA ===');
    const pointsResult = await duckdb.query("DESCRIBE cosmograph_points");
    const pointColumns = pointsResult.toArray();
    console.log('Columns:');
    pointColumns.forEach((col: any, idx: number) => {
      console.log(`  ${idx + 1}. ${col.column_name} (${col.column_type})`);
    });
    console.log(`Total columns: ${pointColumns.length}`);
    
    // Query links schema
    console.log('\n=== COSMOGRAPH_LINKS TABLE SCHEMA ===');
    const linksResult = await duckdb.query("DESCRIBE cosmograph_links");
    const linkColumns = linksResult.toArray();
    console.log('Columns:');
    linkColumns.forEach((col: any, idx: number) => {
      console.log(`  ${idx + 1}. ${col.column_name} (${col.column_type})`);
    });
    console.log(`Total columns: ${linkColumns.length}`);
    
    // Sample data to see what's actually stored
    console.log('\n=== SAMPLE DATA ===');
    
    // Sample point
    const samplePoint = await duckdb.query("SELECT * FROM cosmograph_points LIMIT 1");
    const pointData = samplePoint.toArray()[0];
    if (pointData) {
      console.log('Sample point fields:');
      Object.keys(pointData).forEach(key => {
        const value = pointData[key];
        console.log(`  ${key}: ${value === null ? 'NULL' : typeof value}`);
      });
    }
    
    // Sample link
    const sampleLink = await duckdb.query("SELECT * FROM cosmograph_links LIMIT 1");
    const linkData = sampleLink.toArray()[0];
    if (linkData) {
      console.log('\nSample link fields:');
      Object.keys(linkData).forEach(key => {
        const value = linkData[key];
        console.log(`  ${key}: ${value === null ? 'NULL' : typeof value}`);
      });
    }
    
    return { pointColumns, linkColumns };
  } catch (error) {
    console.error('Error querying DuckDB:', error);
  }
}

// Make it available globally for browser console
if (typeof window !== 'undefined') {
  (window as any).inspectDuckDBSchema = inspectDuckDBSchema;
}