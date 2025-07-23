#!/usr/bin/env python3
"""
FalkorDB Graph Visualizer - Flask Web Application
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from falkordb import FalkorDB
from pyvis.network import Network
import json
import os
import tempfile

app = Flask(__name__)
CORS(app)

# Configuration
FALKORDB_HOST = os.environ.get('FALKORDB_HOST', 'falkordb')
FALKORDB_PORT = int(os.environ.get('FALKORDB_PORT', 6379))
GRAPH_NAME = os.environ.get('GRAPH_NAME', 'graphiti_migration')

@app.route('/')
def index():
    """Main page with visualization controls."""
    return render_template('index.html')

@app.route('/api/graph_stats')
def graph_stats():
    """Get graph statistics."""
    try:
        db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        graph = db.select_graph(GRAPH_NAME)
        
        # Get counts
        nodes = graph.query("MATCH (n) RETURN count(n) as count").result_set[0][0]
        edges = graph.query("MATCH ()-[r]->() RETURN count(r) as count").result_set[0][0]
        
        # Get node type distribution
        types = graph.query("MATCH (n) RETURN labels(n)[0] as type, count(n) as count ORDER BY count DESC LIMIT 10")
        type_dist = [{"type": row[0] or "Unknown", "count": row[1]} for row in types.result_set]
        
        return jsonify({
            "nodes": nodes,
            "edges": edges,
            "types": type_dist
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/visualize', methods=['POST'])
def visualize():
    """Generate graph visualization based on query type."""
    try:
        data = request.json
        query_type = data.get('query_type', 'high_degree')
        limit = int(data.get('limit', 100))
        
        db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        graph = db.select_graph(GRAPH_NAME)
        
        # Query templates
        queries = {
            'high_degree': f"""
                MATCH (n) 
                WHERE n.degree_centrality > 20 
                WITH n ORDER BY n.degree_centrality DESC LIMIT {limit//2}
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
                WITH n LIMIT {limit//3}
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
            'custom': data.get('custom_query', '')
        }
        
        # Execute query
        query = queries.get(query_type, queries['high_degree'])
        result = graph.query(query)
        
        # Build graph data
        nodes = {}
        edges = []
        
        color_map = {
            'Entity': '#ff6b6b',
            'Episodic': '#4ecdc4',
            'Agent': '#ffe66d',
            'None': '#95e1d3'
        }
        
        for row in result.result_set:
            source_id = row[0]
            source_name = row[1] or f"Node {source_id[:8]}"
            rel_type = row[2]
            target_id = row[3]
            target_name = row[4] or f"Node {target_id[:8]}"
            source_label = row[5] or 'None'
            target_label = row[6] or 'None'
            source_degree = row[7] or 0
            target_degree = row[8] or 0
            
            # Add nodes
            if source_id not in nodes:
                nodes[source_id] = {
                    'id': source_id,
                    'label': source_name[:50],
                    'title': f"{source_name}\\nType: {source_label}\\nDegree: {source_degree:.1f}",
                    'color': color_map.get(source_label, '#95e1d3'),
                    'size': min(15 + source_degree * 0.3, 50),
                    'type': source_label,
                    'degree': source_degree
                }
            
            if target_id not in nodes:
                nodes[target_id] = {
                    'id': target_id,
                    'label': target_name[:50],
                    'title': f"{target_name}\\nType: {target_label}\\nDegree: {target_degree:.1f}",
                    'color': color_map.get(target_label, '#95e1d3'),
                    'size': min(15 + target_degree * 0.3, 50),
                    'type': target_label,
                    'degree': target_degree
                }
            
            # Add edge
            edges.append({
                'from': source_id,
                'to': target_id,
                'title': rel_type,
                'color': '#666666'
            })
        
        return jsonify({
            'nodes': list(nodes.values()),
            'edges': edges
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/search', methods=['POST'])
def search():
    """Search for specific nodes."""
    try:
        data = request.json
        search_term = data.get('search', '')
        
        if not search_term:
            return jsonify({"error": "Search term required"}), 400
        
        db = FalkorDB(host=FALKORDB_HOST, port=FALKORDB_PORT)
        graph = db.select_graph(GRAPH_NAME)
        
        # Search query
        query = f"""
            MATCH (n) 
            WHERE n.name CONTAINS '{search_term}'
            WITH n LIMIT 1
            MATCH (n)-[r]-(m)
            RETURN DISTINCT n.uuid as source_id, n.name as source_name, 
                   type(r) as rel_type, 
                   m.uuid as target_id, m.name as target_name,
                   labels(n)[0] as source_label, labels(m)[0] as target_label,
                   n.degree_centrality as source_degree, m.degree_centrality as target_degree
            LIMIT 100
        """
        
        result = graph.query(query)
        
        # Build response (same as visualize)
        nodes = {}
        edges = []
        
        color_map = {
            'Entity': '#ff6b6b',
            'Episodic': '#4ecdc4',
            'Agent': '#ffe66d',
            'None': '#95e1d3'
        }
        
        for row in result.result_set:
            source_id = row[0]
            source_name = row[1] or f"Node {source_id[:8]}"
            rel_type = row[2]
            target_id = row[3]
            target_name = row[4] or f"Node {target_id[:8]}"
            source_label = row[5] or 'None'
            target_label = row[6] or 'None'
            source_degree = row[7] or 0
            target_degree = row[8] or 0
            
            if source_id not in nodes:
                nodes[source_id] = {
                    'id': source_id,
                    'label': source_name[:50],
                    'title': f"{source_name}\\nType: {source_label}\\nDegree: {source_degree:.1f}",
                    'color': color_map.get(source_label, '#95e1d3'),
                    'size': min(15 + source_degree * 0.3, 50),
                    'type': source_label,
                    'degree': source_degree
                }
            
            if target_id not in nodes:
                nodes[target_id] = {
                    'id': target_id,
                    'label': target_name[:50],
                    'title': f"{target_name}\\nType: {target_label}\\nDegree: {target_degree:.1f}",
                    'color': color_map.get(target_label, '#95e1d3'),
                    'size': min(15 + target_degree * 0.3, 50),
                    'type': target_label,
                    'degree': target_degree
                }
            
            edges.append({
                'from': source_id,
                'to': target_id,
                'title': rel_type,
                'color': '#666666'
            })
        
        return jsonify({
            'nodes': list(nodes.values()),
            'edges': edges
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)