#!/bin/bash
# Script to calculate centrality and update visualization

echo "🔄 Calculating centrality scores..."
curl -X POST http://localhost:3003/centrality/all \
  -H "Content-Type: application/json" \
  -d '{"store_results": true, "max_iterations": 100}' \
  --silent --show-error

if [ $? -eq 0 ]; then
  echo "✅ Centrality calculation complete"
  
  echo "🔄 Reloading visualization server..."
  curl -X POST http://localhost:3000/api/data/reload \
    --silent --show-error
  
  if [ $? -eq 0 ]; then
    echo "✅ Visualization server reloaded successfully"
  else
    echo "❌ Failed to reload visualization server"
  fi
else
  echo "❌ Centrality calculation failed"
fi