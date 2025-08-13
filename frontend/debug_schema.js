// Debug the actual fields being sent
const sampleNode = {
  index: 860,
  id: 'bbf5421f-99b0-4c95-ae5a-355e039aec50',
  label: 'Claude_Bash_2025-08-13T16:20:55.418795',
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
  idx: 860,
  name: 'Claude_Bash_2025-08-13T16:20:55.418795'
};

const sampleLink = {
  source: 'aa03bc31-b7e6-4cba-8411-011b4b80d337',
  target: 'b6e1b31b-9cb7-448f-a6a1-89a769a1944a',
  sourceIndex: 553,
  targetIndex: 599,
  sourceidx: 553,
  targetidx: 599,
  weight: 1,
  edge_type: 'default',
  created_at: ''
};

console.log('Node fields count:', Object.keys(sampleNode).length);
console.log('Node fields:', Object.keys(sampleNode));

console.log('\nLink fields count:', Object.keys(sampleLink).length);
console.log('Link fields:', Object.keys(sampleLink));

// Expected link fields from cosmograph_links view
const expectedLinkFields = [
  'source',       // 1
  'sourceIndex',  // 2
  'target',       // 3
  'targetIndex',  // 4
  'edge_type',    // 5
  'weight',       // 6
  'color',        // 7
  'strength'      // 8
  // Plus maybe one more internal field = 9
];

console.log('\nExpected link fields:', expectedLinkFields);
console.log('Expected link count:', expectedLinkFields.length);

const missingLinkFields = expectedLinkFields.filter(f => !(f in sampleLink));
console.log('Missing link fields:', missingLinkFields);
