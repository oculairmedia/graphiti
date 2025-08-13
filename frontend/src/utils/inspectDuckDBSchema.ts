/**
 * Utility to inspect DuckDB schema directly from Cosmograph
 * Run this in the browser console to see what columns DuckDB actually has
 */

export async function inspectDuckDBSchema() {
  // Get Cosmograph instance from the DOM or window
  const cosmograph = window['cosmographRef']?.current ||
                    document.querySelector('[data-cosmograph]')?.__cosmograph || 
                    document.querySelector('.cosmograph-container')?.__cosmograph ||
                    (document.querySelector('canvas') as any)?._cosmograph;
  
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

/**
 * Compare what we're sending vs what DuckDB expects
 */
export function compareSchemaWithData(sampleLink: any) {
  console.log('=== LINK DATA ANALYSIS ===');
  console.log('Fields we are sending:', Object.keys(sampleLink));
  console.log('Field count:', Object.keys(sampleLink).length);
  
  console.log('\nField values:');
  Object.entries(sampleLink).forEach(([key, value]) => {
    console.log(`  ${key}: ${value} (${typeof value})`);
  });
  
  // Check for nulls
  const nullFields = Object.entries(sampleLink)
    .filter(([_, v]) => v === null || v === undefined)
    .map(([k]) => k);
  
  if (nullFields.length > 0) {
    console.log('\nNULL/UNDEFINED fields:', nullFields);
  }
  
  // DuckDB only counts non-null values
  const nonNullCount = Object.values(sampleLink)
    .filter(v => v !== null && v !== undefined).length;
  console.log('\nNon-null field count:', nonNullCount);
  
  console.log('\nDuckDB says: "table has 9 columns but 5 values were supplied"');
  console.log('This means DuckDB only sees 5 non-null values out of our', nonNullCount, 'non-null fields');
  console.log('Possible reasons:');
  console.log('1. Some fields are being filtered out before reaching DuckDB');
  console.log('2. DuckDB expects different field names');
  console.log('3. Type conversion is failing for some fields');
}

// Make them available globally for browser console
if (typeof window !== 'undefined') {
  (window as any).inspectDuckDBSchema = inspectDuckDBSchema;
  (window as any).compareSchemaWithData = compareSchemaWithData;
}