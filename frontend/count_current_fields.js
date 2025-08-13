// Count fields in the current sanitized node
const currentNode = {
  index: 868,
  id: 'da4ae915-323c-43f4-8f13-887217435823',
  label: 'Claude_BashOutput_2025-08-13T16:21:40.999425',
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
  clusterStrength: 0.7
};

const fields = Object.keys(currentNode);
console.log('Current node fields:', fields);
console.log('Field count:', fields.length);

// This is 16 fields, but Cosmograph expects 14 now?
// It seems Cosmograph is dynamically changing its schema
console.log('\nCosmograph is expecting 14 columns but we are sending', fields.length);
console.log('We need to send exactly 14 fields');

// Most likely fields to keep (14)
const coreFields = [
  'index',
  'id', 
  'label',
  'node_type',
  'summary',
  'degree_centrality',
  'pagerank_centrality',
  'betweenness_centrality',
  'eigenvector_centrality',
  'x',
  'y',
  'color',
  'size',
  'created_at_timestamp'
  // Leaving out: cluster, clusterStrength
];

console.log('\nCore 14 fields:', coreFields);
console.log('Fields to remove:', fields.filter(f => !coreFields.includes(f)));
