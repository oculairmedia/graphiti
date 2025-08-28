#!/usr/bin/env python3
"""
Test Cerebras with real Claude Code tool messages - the type that was causing production failures.
This uses actual message patterns from the Claude Code hook system to stress test Cerebras.
"""

import asyncio
import os
import json
import logging
from datetime import datetime, timezone

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set environment for Cerebras testing
os.environ['USE_CEREBRAS'] = 'true'
os.environ['CEREBRAS_API_KEY'] = 'csk-2dhe695kn8k6j2ck2n3jmx9hn2decfhjmf82xpk8v4yp5dr4'
os.environ['CEREBRAS_MODEL'] = 'qwen-3-coder-480b'
os.environ['CEREBRAS_SMALL_MODEL'] = 'qwen-3-coder-480b'
os.environ['ENABLE_FALLBACK'] = 'true'
os.environ['USE_OLLAMA'] = 'true'
os.environ['OLLAMA_BASE_URL'] = 'http://100.81.139.20:11434/v1'
os.environ['OLLAMA_MODEL'] = 'gemma3:12b'

# Sample Claude Code messages that represent the complex patterns causing production issues
CLAUDE_CODE_MESSAGES = [
    {
        "name": "Size multiplier bug investigation",
        "content": """User asked: "size multiplier still doesnt work"

I investigated the size multiplier control in the Node Styling tab and found the root cause:

**Problem**: The `pointSizeRange` calculation in `frontend/src/components/GraphCanvasV2.tsx` was ignoring `config.sizeMultiplier` completely.

**Root Cause Analysis**:
1. Missing multiplier extraction: No `const multiplier = config.sizeMultiplier || 1`
2. No multiplier application: Range returned `[baseMin, baseMax]` without multiplier
3. Missing dependency: `config.sizeMultiplier` not in useMemo dependency array

**Fix Applied**:
```typescript
const pointSizeRange = useMemo(() => {
  const baseMin = config.minNodeSize || 2;
  const baseMax = config.maxNodeSize || 8;
  const multiplier = config.sizeMultiplier || 1; // Extract multiplier
  
  let adjustedMin: number;
  let adjustedMax: number;
  
  // Size mapping logic...
  switch (config.sizeMapping) {
    case 'uniform':
      adjustedMin = uniformSize;
      adjustedMax = uniformSize + 0.1;
      break;
    // ... other cases
  }
  
  // Apply multiplier to final range
  return [adjustedMin * multiplier, adjustedMax * multiplier];
}, [config.sizeMapping, config.minNodeSize, config.maxNodeSize, config.sizeMultiplier]);
```

The fix ensures that adjusting the size multiplier slider from 0.1x to 3.0x now properly scales node sizes in the graph visualization."""
    },
    
    {
        "name": "Queue status production hardening",
        "content": """Implemented production-ready queue status UI improvements to eliminate the visual flicker issue:

**Problem**: Queue status panel would disappear and reappear every 5 seconds during refresh cycles, causing poor UX.

**Phase 1 Production Hardening Completed**:

1. **Eliminated perceived "reloads"**: Separated initial loading from background refresh states
   - `isLoading`: Initial-only state  
   - `isRefreshing`: Background refresh state
   - No more full panel disappearance

2. **Field-wise comparison**: Replaced JSON.stringify with granular field comparison
   ```typescript
   const fieldsEqual = 
     prev.status === status.status &&
     prev.visible_messages === status.visible_messages &&
     prev.invisible_messages === status.invisible_messages &&
     prev.total_processed === status.total_processed &&
     prev.total_failed === status.total_failed &&
     prev.success_rate === status.success_rate;
   ```

3. **Smooth numeric transitions**: Added motion-safe CSS transitions
   ```tsx
   <span className="text-primary font-mono motion-safe:transition-all motion-safe:duration-300 ease-out">
     {queueStatus.visible_messages}
   </span>
   ```

4. **Staleness indicators**: Added "Updated Xs ago" when data >60s old
   - Visual dimming (75% opacity) for stale data
   - Clear network issue indicators

5. **Adaptive polling with jitter**: ±10% randomization prevents synchronized network bursts

**Backend Fix**: Fixed Rust queue status parsing from Prometheus metrics format to properly return JSON for frontend consumption.

**Result**: Queue status now provides professional, production-ready UX with clear data freshness indicators and no visual flicker."""
    },
    
    {
        "name": "Complex tool usage and debugging session",
        "content": """Session involved complex multi-tool operations for Graphiti infrastructure management:

**Tools Used**:
- Read: Configuration files, source code analysis
- Edit/MultiEdit: Frontend components, environment variables  
- Bash: Docker operations, service management, git operations
- Grep/Glob: Codebase searches for patterns and files
- Task: Specialized agent operations for complex searches
- WebFetch: Documentation lookups and API validation

**Key Operations Performed**:

1. **Environment Configuration**:
   ```bash
   # Switched from Cerebras to Ollama-only
   USE_CEREBRAS=false → true
   USE_CHUTES=false
   ENABLE_FALLBACK=true
   ```

2. **Service Management**:
   ```bash
   NEO4J_PASSWORD=demodemo docker-compose restart graphiti-worker
   NEO4J_PASSWORD=demodemo docker-compose restart graphiti-mcp  
   docker pull ghcr.io/oculairmedia/graphiti-rust-visualizer:feature-chutes-ai-integration
   ```

3. **Frontend Development**:
   - Fixed useQueueStatus.ts hook implementation
   - Updated GraphCanvasV2.tsx size multiplier logic
   - Implemented motion-safe CSS transitions
   - Added comprehensive error handling

4. **Testing Infrastructure**:
   - Created parallel_ingestion_test.py for performance testing
   - Built safe mock-based test harnesses
   - Validated Cerebras integration without database writes
   - Implemented comprehensive LLM client testing

**Complex Data Structures Handled**:
- TypeScript interfaces and React component props
- Docker Compose service configurations  
- Git workflow and branch management
- Queue metrics and Prometheus data formats
- GraphQL-style nested configuration objects

**Outcome**: Successfully debugged and fixed multiple production issues while maintaining system stability through safe testing practices."""
    },

    {
        "name": "Infrastructure debugging with nested configurations",
        "content": """Emmanuel Umukoro debugging session focused on Graphiti knowledge graph infrastructure:

**Environment Context**:
- Platform: linux (Linux 6.5.11-8-pve)
- Working directory: /opt/stacks/graphiti  
- Git repository with multiple feature branches
- Docker Compose multi-service architecture

**Service Architecture**:
```yaml
services:
  graphiti-worker: 
    image: ghcr.io/oculairmedia/graphiti-queued:main
    environment:
      - USE_CEREBRAS=true
      - CEREBRAS_MODEL=qwen-3-coder-480b
      - USE_OLLAMA=true (fallback)
      - FALKORDB_HOST=falkordb
      - NEO4J_URI=bolt://neo4j:7687
  
  graph-visualizer-rust:
    image: ghcr.io/oculairmedia/graphiti-rust-visualizer
    ports: ["3000:3000"]
    depends_on: [falkordb]
    
  graphiti-mcp:
    environment: 
      - LETTA_API_URL=https://letta.oculair.ca
      - MCP server integration
```

**Complex Configuration Management**:
- Multi-provider LLM setup (Cerebras → Chutes → Ollama cascade)
- FalkorDB + Neo4j dual database configuration
- Queue-based ingestion with MessagePack serialization
- Rust-based visualization server with WebGL frontend
- MCP (Model Context Protocol) server integration

**Debugging Workflow**:
1. Queue status investigation (60,000+ messages)
2. LLM provider switching and validation
3. Frontend component debugging (React + TypeScript)
4. Container image management and deployment
5. Real-time log analysis across multiple services

**Technical Complexity**:
- Async/await patterns in TypeScript
- Docker multi-stage builds with feature branch tagging
- Git workflow with feature branches and automated CI/CD
- WebSocket connections for real-time updates
- Graph database query optimization
- Rate limiting and API key management across providers

This represents the type of complex, nested technical content that Graphiti processes during infrastructure debugging sessions with multiple interconnected services."""
    }
]


async def test_cerebras_with_claude_code_content():
    """Test Cerebras with actual Claude Code message content that caused production issues."""
    
    try:
        print("=" * 80)
        print("CEREBRAS CLAUDE CODE MESSAGE TESTING")
        print("Testing with real content patterns that caused production failures")
        print("=" * 80)
        
        from graphiti_core.client_factory import GraphitiClientFactory
        from graphiti_core.llm_client.config import ModelSize
        from graphiti_core.prompts.models import Message
        
        # Create LLM client
        print("\n🧠 Creating Cerebras LLM client...")
        llm_client = GraphitiClientFactory.create_llm_client()
        print(f"✅ LLM Client: {type(llm_client).__name__}")
        print(f"   Primary: {llm_client.model}")
        print(f"   Fallback: Ollama available")
        
        # Test each Claude Code message
        results = []
        
        for i, test_case in enumerate(CLAUDE_CODE_MESSAGES, 1):
            print(f"\n" + "─" * 60)
            print(f"TEST {i}/4: {test_case['name']}")
            print(f"Content length: {len(test_case['content'])} characters")
            print("─" * 60)
            
            # Test entity extraction with the complex content
            entity_messages = [
                Message(role="system", content="""You are an expert entity extractor. Extract key entities from the given text and return them as JSON.
                
Focus on:
- Technical components (files, services, databases)
- People and roles  
- Tools and technologies
- Problems and solutions
- Configuration values

Return format:
{
  "entities": [
    {"name": "entity_name", "type": "entity_type", "description": "brief_description"}
  ]
}"""),
                Message(role="user", content=f"Extract entities from this Claude Code session content:\n\n{test_case['content']}")
            ]
            
            try:
                print("🧠 Testing entity extraction...")
                start_time = asyncio.get_event_loop().time()
                
                response = await llm_client._generate_response(
                    messages=entity_messages,
                    model_size=ModelSize.medium,
                    max_tokens=4000
                )
                
                end_time = asyncio.get_event_loop().time()
                response_time = end_time - start_time
                
                # Analyze response
                if isinstance(response, dict):
                    entities = response.get('entities', [])
                    print(f"✅ SUCCESS - Extracted {len(entities)} entities in {response_time:.2f}s")
                    
                    # Show sample entities
                    for entity in entities[:5]:  # Show first 5
                        name = entity.get('name', 'N/A')[:30]
                        entity_type = entity.get('type', 'N/A')[:15]  
                        print(f"   • {name:<30} ({entity_type})")
                    
                    if len(entities) > 5:
                        print(f"   ... and {len(entities) - 5} more entities")
                        
                    results.append({
                        'test': test_case['name'],
                        'status': 'SUCCESS',
                        'entities_count': len(entities),
                        'response_time': response_time,
                        'content_length': len(test_case['content'])
                    })
                        
                else:
                    print(f"⚠️  Unexpected response format: {type(response)}")
                    results.append({
                        'test': test_case['name'],
                        'status': 'UNEXPECTED_FORMAT',
                        'response_time': response_time,
                        'content_length': len(test_case['content'])
                    })
                    
            except Exception as e:
                print(f"❌ FAILED: {type(e).__name__}: {str(e)[:100]}...")
                results.append({
                    'test': test_case['name'],
                    'status': 'FAILED',
                    'error': str(e)[:200],
                    'content_length': len(test_case['content'])
                })
                
            # Add delay between tests to respect rate limits
            print("⏳ Rate limit delay...")
            await asyncio.sleep(5)
        
        # Print summary
        print(f"\n" + "=" * 80)
        print("CLAUDE CODE MESSAGE TEST SUMMARY")
        print("=" * 80)
        
        successful = sum(1 for r in results if r['status'] == 'SUCCESS')
        failed = sum(1 for r in results if r['status'] == 'FAILED')
        
        print(f"📊 Results: {successful}/{len(results)} successful")
        print(f"   ✅ Successful: {successful}")
        print(f"   ❌ Failed: {failed}")
        print(f"   ⚠️  Other: {len(results) - successful - failed}")
        
        if successful > 0:
            print(f"\n🏆 SUCCESS: Cerebras can handle complex Claude Code content!")
            avg_entities = sum(r.get('entities_count', 0) for r in results if r['status'] == 'SUCCESS') / successful
            avg_time = sum(r.get('response_time', 0) for r in results if r['status'] == 'SUCCESS') / successful
            avg_length = sum(r.get('content_length', 0) for r in results if r['status'] == 'SUCCESS') / successful
            
            print(f"   📈 Average entities extracted: {avg_entities:.1f}")
            print(f"   ⏱️  Average response time: {avg_time:.2f}s")
            print(f"   📄 Average content length: {avg_length:.0f} chars")
        
        if failed > 0:
            print(f"\n⚠️  {failed} tests failed - check error details above")
            print("   This might indicate the types of content causing production issues")
            
        print(f"\n" + "=" * 80)
        print("CEREBRAS CLAUDE CODE TEST COMPLETE")
        print("=" * 80)
        
    except Exception as e:
        print(f"Test setup failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_cerebras_with_claude_code_content())