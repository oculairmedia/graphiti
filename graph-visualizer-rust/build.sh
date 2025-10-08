#!/bin/bash

# Build script with import validation

set -e  # Exit on error

echo "🔍 Running import validation..."
echo ""

# Make validation script executable
chmod +x validate-imports.js

# Run validation
if node validate-imports.js; then
    echo ""
    echo "✅ Import validation passed!"
else
    echo ""
    echo "❌ Import validation failed!"
    echo ""
    echo "To fix import issues:"
    echo "1. Add missing mappings to the import map in static/cosmograph.html"
    echo "2. Create wrapper modules for UMD/CommonJS packages"
    echo "3. Download missing dependencies to static/vendor/"
    echo ""
    echo "Run 'node fix-imports.js' to attempt automatic fixes"
    exit 1
fi

echo ""
echo "🔨 Building Rust application..."

# Build the Rust app
cargo build --release

echo ""
echo "🐳 Building Docker image..."

# Build Docker image without cache to ensure fresh build
docker-compose build --no-cache

echo ""
echo "✅ Build complete!"
echo ""
echo "To start the application:"
echo "  docker-compose up -d"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f"