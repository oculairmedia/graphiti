#!/usr/bin/env python3
"""
Test Cerebras API connection only - no database interaction.
"""

import asyncio
import os
import sys
from datetime import datetime

print('🧠 Cerebras API Only Test')
print('=' * 40)

# Check API key
cerebras_key = os.getenv('CEREBRAS_API_KEY')
print(f'CEREBRAS_API_KEY: {"Set" if cerebras_key else "Not set"}')

if not cerebras_key:
    print('❌ No CEREBRAS_API_KEY found')
    sys.exit(1)

# Import Cerebras components
try:
    from graphiti_core.llm_client.cerebras_client import CerebrasClient, DEFAULT_CEREBRAS_MODEL
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.prompts.models import Message
    print('✅ Imports successful')
    print(f'Default model: {DEFAULT_CEREBRAS_MODEL}')
except Exception as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)

async def test_cerebras_api():
    """Test Cerebras API connection and response."""
    
    print('\n🔌 Testing Cerebras API Connection...')
    
    try:
        # Create client
        config = LLMConfig(
            model=DEFAULT_CEREBRAS_MODEL,
            temperature=0.1,
            max_tokens=100,
        )
        
        client = CerebrasClient(config=config)
        print(f'✅ Client created with model: {DEFAULT_CEREBRAS_MODEL}')
        
        # Test simple message
        test_message = Message(
            role='user',
            content='Respond with exactly: "Cerebras API test successful"'
        )
        
        print('📡 Sending test message...')
        
        response = await asyncio.wait_for(
            client._generate_response([test_message], max_tokens=50),
            timeout=30.0
        )
        
        if response:
            print('✅ Response received!')
            response_str = str(response)
            preview = response_str[:200] + '...' if len(response_str) > 200 else response_str
            print(f'Response: {preview}')
            return True
        else:
            print('❌ No response received')
            return False
            
    except asyncio.TimeoutError:
        print('⏱️ Request timed out after 30 seconds')
        return False
    except Exception as e:
        print(f'❌ Error: {e}')
        
        # Check for specific error types
        error_str = str(e).lower()
        if 'quota' in error_str or 'limit' in error_str:
            print('💡 This appears to be a quota/rate limit issue')
        elif 'auth' in error_str or 'key' in error_str:
            print('💡 This appears to be an authentication issue')
        elif 'network' in error_str or 'connection' in error_str:
            print('💡 This appears to be a network connectivity issue')
            
        return False

async def main():
    """Run the API-only test."""
    
    print(f'\nTest start: {datetime.now().isoformat()}')
    
    success = await test_cerebras_api()
    
    print(f'\nTest end: {datetime.now().isoformat()}')
    
    if success:
        print('🎉 Cerebras API test PASSED!')
        sys.exit(0)
    else:
        print('❌ Cerebras API test FAILED!')
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())