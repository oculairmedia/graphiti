// Count fields in the sanitized node from the log
const sampleNode = {
  index: 852, 
  id: '3a4d57e6-be45-48bf-aa0a-b840534fcfad', 
  label: 'Claude_Read_2025-08-13T16:19:24.465612', 
  node_type: 'Episodic', 
  summary: "claude_code(system): User request...",
  degree_centrality: 0,
  pagerank_centrality: 0,
  betweenness_centrality: 0,
  eigenvector_centrality: 0,
  x: null,
  y: null,
  color: '#somecolor',
  size: 5,
  created_at_timestamp: null,
  cluster: 'Episodic',
  clusterStrength: 0.7,
  idx: 852,
  name: 'Claude_Read_2025-08-13T16:19:24.465612',
  properties: {},
  created_at: ''
};

const fields = Object.keys(sampleNode);
console.log('Fields in sanitized node:', fields);
console.log('Total fields:', fields.length);

// Expected cosmograph_points fields from the view
const expectedFields = [
  'index',           // 1
  'id',              // 2
  'label',           // 3
  'node_type',       // 4
  'summary',         // 5
  'degree_centrality',     // 6
  'pagerank_centrality',   // 7
  'betweenness_centrality',// 8
  'eigenvector_centrality',// 9
  'x',               // 10
  'y',               // 11
  'color',           // 12
  'size',            // 13
  'created_at_timestamp', // 14
  'cluster',         // 15
  'clusterStrength'  // 16
];

console.log('\nExpected fields from cosmograph_points view:', expectedFields);
console.log('Expected count:', expectedFields.length);

// Find extra fields we're sending
const extraFields = fields.filter(f => !expectedFields.includes(f));
console.log('\nExtra fields we are sending:', extraFields);

// Find missing fields
const missingFields = expectedFields.filter(f => !fields.includes(f));
console.log('Missing fields:', missingFields);
