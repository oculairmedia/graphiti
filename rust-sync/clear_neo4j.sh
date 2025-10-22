#!/bin/bash
# Clear all data from Neo4j database

echo "Clearing Neo4j database at 192.168.50.90:7687..."

cypher-shell -a bolt://192.168.50.90:7687 -u neo4j -p graphiti123 "MATCH (n) DETACH DELETE n" 2>/dev/null || \
  echo "Note: Install cypher-shell or use Neo4j browser to run: MATCH (n) DETACH DELETE n"

echo "Done!"
