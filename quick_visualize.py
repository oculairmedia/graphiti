#!/usr/bin/env python3
"""
Quick graph visualization - creates an HTML file immediately without prompts
"""

from falkordb import FalkorDB
from pyvis.network import Network
from datetime import datetime

# Connect to FalkorDB
print("Connecting to FalkorDB...")
db = FalkorDB(host='localhost', port=6389)
graph = db.select_graph('graphiti_migration')

# Query for high-degree nodes
print("Querying graph data...")
query = """
    MATCH (n) 
    WHERE n.degree_centrality > 30 
    WITH n ORDER BY n.degree_centrality DESC LIMIT 50
    MATCH (n)-[r]-(m) 
    WHERE m.degree_centrality > 20
    RETURN DISTINCT n.uuid as source_id, n.name as source_name, 
           type(r) as rel_type, 
           m.uuid as target_id, m.name as target_name,
           labels(n)[0] as source_label, labels(m)[0] as target_label,
           n.degree_centrality as source_degree, m.degree_centrality as target_degree
    LIMIT 200
"""

result = graph.query(query)
data = result.result_set

# Create network
print("Creating visualization...")
net = Network(
    height="900px", 
    width="100%", 
    bgcolor="#222222", 
    font_color="white",
    notebook=False,
    directed=True
)

# Configure physics
net.barnes_hut(
    gravity=-80000,
    central_gravity=0.3,
    spring_length=250,
    spring_strength=0.001,
    damping=0.09
)

# Color mapping
color_map = {
    'Entity': '#ff6b6b',      # Red
    'Episodic': '#4ecdc4',    # Teal
    'Agent': '#ffe66d',       # Yellow
    'None': '#95e1d3'         # Light green
}

# Track nodes
nodes_added = set()

# Add nodes and edges
for row in data:
    source_id = row[0]
    source_name = row[1] or f"Node {source_id[:8]}"
    rel_type = row[2]
    target_id = row[3]
    target_name = row[4] or f"Node {target_id[:8]}"
    source_label = row[5] or 'None'
    target_label = row[6] or 'None'
    source_degree = row[7] or 0
    target_degree = row[8] or 0
    
    # Add source node
    if source_id not in nodes_added:
        net.add_node(
            source_id, 
            label=source_name[:30],
            color=color_map.get(source_label, '#95e1d3'),
            size=min(15 + source_degree * 0.3, 50),
            title=f"{source_name}\nType: {source_label}\nDegree: {source_degree:.1f}",
            borderWidth=2
        )
        nodes_added.add(source_id)
    
    # Add target node
    if target_id not in nodes_added:
        net.add_node(
            target_id, 
            label=target_name[:30],
            color=color_map.get(target_label, '#95e1d3'),
            size=min(15 + target_degree * 0.3, 50),
            title=f"{target_name}\nType: {target_label}\nDegree: {target_degree:.1f}",
            borderWidth=2
        )
        nodes_added.add(target_id)
    
    # Add edge
    net.add_edge(source_id, target_id, title=rel_type, color='#666666')

# Set options
net.set_options("""
var options = {
    "nodes": {
        "font": {
            "size": 14,
            "color": "white"
        }
    },
    "edges": {
        "smooth": {
            "type": "continuous"
        }
    },
    "interaction": {
        "hover": true,
        "navigationButtons": true,
        "keyboard": true
    }
}
""")

# Save visualization
output_file = "falkordb_interactive_graph.html"
# Use save_graph instead of show to avoid template issues
net.save_graph(output_file)

print(f"\n✅ Success! Interactive graph visualization created:")
print(f"   File: {output_file}")
print(f"   Nodes: {len(nodes_added)}")
print(f"   Edges: {len(data)}")
print(f"\nOpen the HTML file in your web browser to explore the graph!")
print("\nControls:")
print("- Drag to pan, scroll to zoom")
print("- Click nodes to select")
print("- Hover for node details")
print("- Use navigation buttons")