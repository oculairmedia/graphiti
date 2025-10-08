#!/usr/bin/env python3
"""
Interactive Graph Visualization for FalkorDB using PyVis
Creates beautiful, interactive HTML visualizations of your graph data
"""

import sys
from datetime import datetime

import networkx as nx
from falkordb import FalkorDB
from pyvis.network import Network


def query_graph_subset(graph, query_type='high_degree', limit=100):
    """Query FalkorDB for a subset of the graph."""

    queries = {
        'high_degree': f"""
            MATCH (n) 
            WHERE n.degree_centrality > 20 
            WITH n ORDER BY n.degree_centrality DESC LIMIT {limit // 2}
            MATCH (n)-[r]-(m) 
            WHERE m.degree_centrality > 10
            RETURN DISTINCT n.uuid as source_id, n.name as source_name, 
                   type(r) as rel_type, 
                   m.uuid as target_id, m.name as target_name,
                   labels(n)[0] as source_label, labels(m)[0] as target_label,
                   n.degree_centrality as source_degree, m.degree_centrality as target_degree
            LIMIT {limit}
        """,
        'agents': f"""
            MATCH (n) 
            WHERE n.name CONTAINS 'Agent' 
            WITH n LIMIT {limit // 3}
            MATCH (n)-[r]-(m)
            RETURN DISTINCT n.uuid as source_id, n.name as source_name, 
                   type(r) as rel_type, 
                   m.uuid as target_id, m.name as target_name,
                   labels(n)[0] as source_label, labels(m)[0] as target_label,
                   n.degree_centrality as source_degree, m.degree_centrality as target_degree
            LIMIT {limit}
        """,
        'entities': f"""
            MATCH (n:Entity)-[r]-(m:Entity)
            RETURN DISTINCT n.uuid as source_id, n.name as source_name, 
                   type(r) as rel_type, 
                   m.uuid as target_id, m.name as target_name,
                   'Entity' as source_label, 'Entity' as target_label,
                   n.degree_centrality as source_degree, m.degree_centrality as target_degree
            LIMIT {limit}
        """,
        'sample': f"""
            MATCH (n)-[r]-(m)
            RETURN DISTINCT n.uuid as source_id, n.name as source_name, 
                   type(r) as rel_type, 
                   m.uuid as target_id, m.name as target_name,
                   labels(n)[0] as source_label, labels(m)[0] as target_label,
                   n.degree_centrality as source_degree, m.degree_centrality as target_degree
            LIMIT {limit}
        """,
    }

    result = graph.query(queries.get(query_type, queries['sample']))
    return result.result_set


def create_interactive_visualization(
    data, output_file='graph_visualization.html', title='FalkorDB Graph'
):
    """Create an interactive PyVis visualization."""

    # Create network
    net = Network(
        height='900px',
        width='100%',
        bgcolor='#222222',
        font_color='white',
        notebook=False,
        directed=True,
    )

    # Configure physics for better layout
    net.barnes_hut(
        gravity=-80000,
        central_gravity=0.3,
        spring_length=250,
        spring_strength=0.001,
        damping=0.09,
        overlap=0,
    )

    # Track unique nodes
    nodes_added = set()

    # Color mapping for different node types
    color_map = {
        'Entity': '#ff6b6b',  # Red
        'Episodic': '#4ecdc4',  # Teal
        'Agent': '#ffe66d',  # Yellow
        'None': '#95e1d3',  # Light green
    }

    # Add nodes and edges
    for row in data:
        source_id = row[0]
        source_name = row[1] or f'Node {source_id[:8]}'
        rel_type = row[2]
        target_id = row[3]
        target_name = row[4] or f'Node {target_id[:8]}'
        source_label = row[5] or 'None'
        target_label = row[6] or 'None'
        source_degree = row[7] or 0
        target_degree = row[8] or 0

        # Add source node
        if source_id not in nodes_added:
            net.add_node(
                source_id,
                label=source_name[:50],  # Truncate long names
                color=color_map.get(source_label, '#95e1d3'),
                size=min(10 + source_degree * 0.5, 50),  # Size based on degree
                title=f'{source_name}\nType: {source_label}\nDegree: {source_degree:.1f}',
                borderWidth=2,
            )
            nodes_added.add(source_id)

        # Add target node
        if target_id not in nodes_added:
            net.add_node(
                target_id,
                label=target_name[:50],
                color=color_map.get(target_label, '#95e1d3'),
                size=min(10 + target_degree * 0.5, 50),
                title=f'{target_name}\nType: {target_label}\nDegree: {target_degree:.1f}',
                borderWidth=2,
            )
            nodes_added.add(target_id)

        # Add edge
        net.add_edge(source_id, target_id, title=rel_type, color='#666666')

    # Add interaction options
    net.set_options("""
    var options = {
        "nodes": {
            "borderWidth": 2,
            "borderWidthSelected": 4,
            "font": {
                "size": 16
            }
        },
        "edges": {
            "color": {
                "inherit": false
            },
            "smooth": {
                "type": "continuous"
            }
        },
        "interaction": {
            "hover": true,
            "tooltipDelay": 200,
            "navigationButtons": true,
            "keyboard": true
        }
    }
    """)

    # Generate HTML
    net.show(output_file)
    print(f'\nVisualization saved to: {output_file}')
    print(f'Total nodes: {len(nodes_added)}')
    print(f'Total edges: {len(data)}')


def main():
    """Main function to create graph visualizations."""

    print('=== FalkorDB Interactive Graph Visualization ===\n')

    # Connect to FalkorDB
    db = FalkorDB(host='localhost', port=6389)
    graph = db.select_graph('graphiti_migration')

    # Get graph statistics
    stats = graph.query('MATCH (n) RETURN count(n) as nodes')
    total_nodes = stats.result_set[0][0]

    stats = graph.query('MATCH ()-[r]->() RETURN count(r) as edges')
    total_edges = stats.result_set[0][0]

    print(f'Total graph size: {total_nodes:,} nodes, {total_edges:,} edges\n')

    # Visualization options
    print('Select visualization type:')
    print('1. High degree nodes (most connected)')
    print('2. Agent networks')
    print('3. Entity relationships')
    print('4. Random sample')

    choice = input('\nEnter choice (1-4) [default: 1]: ').strip() or '1'

    query_types = {'1': 'high_degree', '2': 'agents', '3': 'entities', '4': 'sample'}

    query_type = query_types.get(choice, 'high_degree')

    # Get node limit
    limit = input('Number of relationships to visualize [default: 200]: ').strip()
    limit = int(limit) if limit.isdigit() else 200

    print(f'\nQuerying {query_type} relationships (limit: {limit})...')

    # Query data
    data = query_graph_subset(graph, query_type, limit)

    if not data:
        print('No data returned from query!')
        return

    # Create visualization
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'falkordb_graph_{query_type}_{timestamp}.html'

    print('\nCreating interactive visualization...')
    create_interactive_visualization(data, output_file, f'FalkorDB - {query_type.title()} View')

    print(f"\n✅ Success! Open '{output_file}' in your web browser to explore the graph.")
    print('\nVisualization controls:')
    print('- Click and drag to pan')
    print('- Scroll to zoom')
    print('- Click nodes to select')
    print('- Hover for details')
    print('- Use navigation buttons for zoom/fit')


if __name__ == '__main__':
    main()
