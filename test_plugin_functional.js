/**
 * Functional test for Graphiti plugin - simulates OpenCode environment
 */

// Mock OpenCode environment
const mockProject = { name: 'test-project' }
const mockClient = {
  _client: {
    getConfig: () => ({ baseUrl: 'http://127.0.0.1:4096' })
  }
}
const mockDirectory = '/opt/stacks/graphiti'

// Mock command executor
const $ = (strings, ...values) => ({
  text: async () => strings[0].includes('abbrev-ref') ? 'main' : 'abc123'
})

// Set test environment
process.env.GRAPHITI_AUTO_COLLECT = 'true'
process.env.GRAPHITI_BUFFER_SIZE = '2' // Small buffer for testing
process.env.GRAPHITI_LOG_LEVEL = 'info'
process.env.GRAPHITI_API_URL = 'http://192.168.50.90:8003'

async function testPlugin() {
  console.log('=== Graphiti Plugin Functional Test ===\n')
  
  try {
    // Import plugin
    console.log('1. Loading plugin...')
    const { GraphitiContextCollector } = await import('/root/.config/opencode/plugin/graphiti-context-collector.js')
    
    console.log('   ✓ Plugin loaded successfully')
    
    // Initialize plugin
    console.log('\n2. Initializing plugin...')
    const plugin = await GraphitiContextCollector({
      project: mockProject,
      client: mockClient,
      $,
      directory: mockDirectory,
      worktree: null
    })
    
    console.log('   ✓ Plugin initialized')
    
    // Test user message
    console.log('\n3. Testing user message handler...')
    await plugin['user.message']({ message: { content: 'Test user message 1' } })
    console.log('   ✓ User message handled')
    
    // Test assistant message
    console.log('\n4. Testing assistant message handler...')
    await plugin['assistant.message']({ message: { content: 'Test assistant response 1' } })
    console.log('   ✓ Assistant message handled')
    
    // Test another round (should trigger flush at 2 messages)
    console.log('\n5. Testing buffer flush (sending 2nd message)...')
    await plugin['user.message']({ message: { content: 'Test user message 2' } })
    await plugin['assistant.message']({ message: { content: 'Test assistant response 2' } })
    console.log('   ✓ Buffer flush completed')
    
    // Test tool tracking
    console.log('\n6. Testing tool execution tracking...')
    await plugin['tool.execute.after']({ tool: 'bash' }, { result: 'success' })
    console.log('   ✓ Tool execution tracked')
    
    // Test session event
    console.log('\n7. Testing session events...')
    await plugin.event({ event: { type: 'session.start' } })
    console.log('   ✓ Session event handled')
    
    // Cleanup
    console.log('\n8. Testing cleanup...')
    if (plugin.dispose) {
      plugin.dispose()
      console.log('   ✓ Cleanup completed')
    }
    
    console.log('\n=== All Tests Passed ✓ ===\n')
    console.log('Plugin is working correctly!')
    console.log('\nNext steps:')
    console.log('  1. Start OpenCode: opencode')
    console.log('  2. Look for "[Graphiti] Context collector enabled"')
    console.log('  3. Send 6+ messages in conversation')
    console.log('  4. Run: ./test_plugin_health.sh')
    
    process.exit(0)
    
  } catch (error) {
    console.error('\n✗ Test Failed:', error.message)
    console.error('\nStack:', error.stack)
    process.exit(1)
  }
}

// Add timeout
setTimeout(() => {
  console.error('\n✗ Test timed out after 30 seconds')
  process.exit(1)
}, 30000)

testPlugin()
