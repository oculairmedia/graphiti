// Extract Cosmograph's internal DuckDB schema
const extractSchema = `
  // Get the Cosmograph instance
  const cosmograph = document.querySelector('.cosmograph-container')?.__cosmograph;
  
  if (cosmograph && cosmograph._duckdb) {
    // Query the schema
    cosmograph._duckdb.query("DESCRIBE cosmograph_points").then(result => {
      console.log('=== COSMOGRAPH_POINTS SCHEMA ===');
      const columns = result.toArray();
      columns.forEach((col, idx) => {
        console.log(\`Column \${idx + 1}: \${col.column_name} - \${col.column_type}\`);
      });
      console.log(\`Total columns: \${columns.length}\`);
    }).catch(err => {
      console.error('Error querying schema:', err);
    });
  } else {
    console.log('Cosmograph instance not found or DuckDB not initialized');
  }
`;

console.log(extractSchema);
