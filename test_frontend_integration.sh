#!/bin/bash

echo "🚀 Testing Frontend-Rust Integration"
echo "==================================="

# Check if Rust server is running
echo -n "1. Checking Rust server at localhost:3000... "
if curl -s http://localhost:3000/api/stats > /dev/null; then
    echo "✅ Running"
else
    echo "❌ Not running"
    echo "   Please start the Rust server with:"
    echo "   cd graph-visualizer-rust && cargo run --release"
    exit 1
fi

# Start the frontend
echo ""
echo "2. Starting React frontend..."
echo "   The frontend will be available at http://localhost:8080"
echo "   Press Ctrl+C to stop"
echo ""

cd frontend && npm run dev