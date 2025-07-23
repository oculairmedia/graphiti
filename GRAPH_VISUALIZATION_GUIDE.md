# 🎨 Interactive Graph Visualization Guide

## ✅ Quick Start

An interactive graph visualization has been created! To view it:

1. **Open the file**: `/opt/stacks/graphiti/falkordb_interactive_graph.html`
2. **Open in your browser**: 
   - If on the server: `python3 -m http.server 8000` then visit http://192.168.50.90:8000/falkordb_interactive_graph.html
   - Or download the HTML file to your local machine and open it

## 🎯 What You're Seeing

The visualization shows:
- **45 highly connected nodes** from your graph
- **195 relationships** between them
- **Color coding**:
  - 🔴 Red nodes = Entity type
  - 🟦 Teal nodes = Episodic type
  - 🟡 Yellow nodes = Agent type
  - 🟢 Green nodes = Other/Unknown type
- **Node size** = Degree centrality (bigger = more connected)

## 🖱️ Interactive Controls

- **Pan**: Click and drag the background
- **Zoom**: Scroll wheel or pinch
- **Select Node**: Click on any node
- **Node Details**: Hover over nodes to see:
  - Full name
  - Node type
  - Degree centrality score
- **Move Nodes**: Click and drag individual nodes
- **Navigation**: Use the zoom controls in the corner

## 📊 Featured Nodes

Your most connected nodes include:
- **Agent Meridian** (223 connections)
- **Agent companion-agent-1751865521474** (220 connections)  
- **Emmanuel's profile data** (125 connections)
- **Agent bombastic** (103 connections)
- Various source code files

## 🔧 Create Custom Visualizations

### Option 1: Quick Visualization (No Prompts)
```bash
python3 quick_visualize.py
```
This creates `falkordb_interactive_graph.html` instantly.

### Option 2: Interactive Script (Choose What to View)
```bash
python3 visualize_graph.py
```
This lets you choose:
1. High degree nodes (most connected)
2. Agent networks
3. Entity relationships  
4. Random sample

### Option 3: Custom Query
Edit `quick_visualize.py` and modify the query:

```python
# Example: Show only Agent nodes
query = """
    MATCH (n) 
    WHERE n.name CONTAINS 'Agent'
    WITH n LIMIT 30
    MATCH (n)-[r]-(m)
    RETURN DISTINCT n.uuid as source_id, n.name as source_name...
"""
```

## 📁 Files Created

- `/opt/stacks/graphiti/falkordb_interactive_graph.html` - The visualization
- `/opt/stacks/graphiti/quick_visualize.py` - Quick visualization script
- `/opt/stacks/graphiti/visualize_graph.py` - Interactive visualization script
- `/opt/stacks/graphiti/interactive_graph_queries.txt` - Example queries

## 🚀 Advanced Tips

### Serve the Visualization
To make it accessible from your browser:
```bash
cd /opt/stacks/graphiti
python3 -m http.server 8000
```
Then visit: http://192.168.50.90:8000/falkordb_interactive_graph.html

### Export for Sharing
The HTML file is self-contained. You can:
- Email it to others
- Upload to a web server
- Open locally on any computer

### Performance Tips
- Keep visualizations under 500 nodes for smooth interaction
- Use filters in queries to focus on specific subgraphs
- Increase node limit gradually if needed

## 🎨 Customization

To change colors, sizes, or physics in `quick_visualize.py`:

```python
# Change colors
color_map = {
    'Entity': '#your_color_here',
    'Episodic': '#another_color',
}

# Change physics
net.barnes_hut(
    gravity=-50000,  # Adjust spread
    spring_length=300,  # Adjust distance
)
```

Enjoy exploring your knowledge graph interactively! 🌐