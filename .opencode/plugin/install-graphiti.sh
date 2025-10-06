#!/bin/bash

# Graphiti OpenCode Plugin Installation Script
# This script installs the Graphiti OpenCode integration plugin

echo "🚀 Installing Graphiti OpenCode Integration Plugin..."

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if we're in the right directory
if [ ! -d ".opencode" ]; then
    echo -e "${YELLOW}📁 Creating .opencode directory...${NC}"
    mkdir -p .opencode
fi

# Check for Bun installation
if ! command -v bun &> /dev/null; then
    print_warning "Bun not found. Installing Bun..."
    curl -fsSL https://bun.sh/install | bash
    
    # Add Bun to PATH for this session
    export PATH="$HOME/.bun/bin:$PATH"
    
    if ! command -v bun &> /dev/null; then
        print_error "Failed to install Bun. Please install manually: https://bun.sh"
        exit 1
    fi
fi

print_status "Bun found: $(bun --version)"

# Create plugin directory structure
echo "📁 Creating plugin directory structure..."
mkdir -p .opencode/plugin/graphiti/{handlers,config,analysis,learning,privacy,types,clients}

# Copy plugin files
echo "📋 Copying plugin files..."
if [ -d "/opt/stacks/graphiti/.opencode/plugin/graphiti" ]; then
    cp -r /opt/stacks/graphiti/.opencode/plugin/graphiti/* .opencode/plugin/graphiti/
    print_status "Plugin files copied successfully"
else
    print_error "Source plugin files not found. Please ensure you're running this from the correct directory."
    exit 1
fi

# Navigate to plugin directory
cd .opencode/plugin/graphiti

# Install dependencies
echo "📦 Installing plugin dependencies..."
if bun install; then
    print_status "Dependencies installed successfully"
else
    print_error "Failed to install dependencies"
    exit 1
fi

# Go back to project root
cd ../../..

# Create or update configuration file
if [ ! -f ".opencode/graphiti-config.json" ]; then
    echo "⚙️  Creating default configuration..."
    cp /opt/stacks/graphiti/.opencode/graphiti-config.json .opencode/ 2>/dev/null || {
        cat > .opencode/graphiti-config.json << 'EOF'
{
  "endpoint": "http://localhost:3010/mcp",
  "groupId": "auto-detect",
  "preResponseSearch": {
    "enabled": true,
    "relevanceThreshold": 0.3,
    "maxResults": 5,
    "entityTypes": ["Requirement", "Preference", "Procedure"]
  },
  "interCallSearch": {
    "enabled": true,
    "toolWhitelist": ["read", "write", "edit", "bash", "glob", "grep", "task", "todowrite"],
    "confidenceThreshold": 0.5
  },
  "knowledgePersistence": {
    "enabled": true,
    "autoSaveInsights": true,
    "episodeRetention": 30
  },
  "contextSubmission": {
    "enabled": true,
    "realTimeSubmission": {
      "enabled": true,
      "threshold": 0.6,
      "maxQueueSize": 100
    },
    "batchSubmission": {
      "enabled": true,
      "intervalMs": 30000,
      "batchSize": 10
    },
    "privacy": {
      "enableFiltering": true,
      "maxFileSize": 1048576,
      "allowedExtensions": [".js", ".ts", ".jsx", ".tsx", ".py", ".java", ".cpp", ".md", ".json", ".yaml", ".yml"],
      "blockedDirectories": ["node_modules", ".git", ".env", "dist", "build", "coverage", ".cache"]
    }
  }
}
EOF
    }
    print_status "Configuration file created"
else
    print_warning "Configuration file already exists. Not overwriting."
fi

# Set environment variables if they don't exist
if [ ! -f ".env" ]; then
    echo "🔧 Creating environment file..."
    cat > .env << 'EOF'
# Graphiti OpenCode Plugin Configuration
GRAPHITI_MCP_ENDPOINT=http://localhost:3010/mcp
GRAPHITI_GROUP_ID=auto-detect
GRAPHITI_PRIVACY_FILTERING=true
GRAPHITI_STRICT_MODE=false
GRAPHITI_AUDIT_LOGGING=false

# Add your Graphiti MCP server endpoint and other configurations here
EOF
    print_status "Environment file created"
else
    print_warning "Environment file already exists. Please manually add Graphiti configuration."
fi

# Test plugin installation
echo "🧪 Testing plugin installation..."
cd .opencode/plugin/graphiti

if bun run build > /dev/null 2>&1; then
    print_status "Plugin builds successfully"
else
    print_warning "Plugin build test failed, but installation may still work"
fi

cd ../../..

# Check for Graphiti MCP server
echo "🔍 Checking Graphiti MCP server connectivity..."
if curl -s http://localhost:3010/health > /dev/null 2>&1; then
    print_status "Graphiti MCP server is running"
elif curl -s http://localhost:3010/mcp > /dev/null 2>&1; then
    print_status "Graphiti MCP server is accessible"
else
    print_warning "Graphiti MCP server not accessible at http://localhost:3010"
    echo "   Please ensure your Graphiti MCP server is running before using the plugin."
fi

echo ""
echo "🎉 Graphiti OpenCode Plugin Installation Complete!"
echo ""
echo "📋 Next Steps:"
echo "   1. Ensure your Graphiti MCP server is running on port 3010"
echo "   2. Edit .opencode/graphiti-config.json to customize behavior"
echo "   3. Set environment variables in .env if needed"
echo "   4. Start using OpenCode - the plugin will activate automatically"
echo ""
echo "🔧 Available Tools:"
echo "   • searchMemory - Search knowledge graph for information"
echo "   • saveInsight - Save insights to the knowledge graph"  
echo "   • queryKnowledge - Comprehensive knowledge queries"
echo "   • submitContext - Manually submit current context"
echo ""
echo "📚 Documentation:"
echo "   • Configuration: .opencode/graphiti-config.json"
echo "   • Environment: .env"
echo "   • Plugin docs: .opencode/plugin/graphiti/README.md"
echo ""
print_status "Installation completed successfully! 🚀"

# Verify OpenCode can load the plugin
if command -v opencode &> /dev/null; then
    echo ""
    echo "🔍 Testing OpenCode plugin loading..."
    if opencode --test-plugins 2>/dev/null | grep -q "graphiti" 2>/dev/null; then
        print_status "Plugin loaded successfully in OpenCode"
    else
        print_warning "Plugin may not be loaded. Try restarting OpenCode."
    fi
else
    print_warning "OpenCode CLI not found. Install OpenCode to use the plugin."
fi

echo ""
echo "Happy coding with Graphiti! 🧠💡"