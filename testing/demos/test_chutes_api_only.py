#!/usr/bin/env python3
"""
Test Chutes AI API connection only - no database interaction.
"""

import asyncio
import os
import sys
from datetime import datetime

print('🚀 Chutes AI API Only Test')
print('=' * 40)

# Check API key
chutes_key = os.getenv('CHUTES_API_KEY')
print(f'CHUTES_API_KEY: {"Set" if chutes_key else "Not set"}')

if not chutes_key:
    print('❌ No CHUTES_API_KEY found')
    sys.exit(1)

# Import Chutes components
try:
    from graphiti_core.llm_client.chutes_client import ChutesClient, DEFAULT_MODEL, DEFAULT_BASE_URL
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.prompts.models import Message
    print('✅ Imports successful')
    print(f'Default model: {DEFAULT_MODEL}')
    print(f'Default base URL: {DEFAULT_BASE_URL}')
except Exception as e:
    print(f'❌ Import failed: {e}')
    sys.exit(1)

async def test_chutes_api():
    """Test Chutes AI API connection and response."""
    
    print('\n🔌 Testing Chutes AI API Connection...')
    
    try:
        # Create client
        config = LLMConfig(
            api_key=chutes_key,
            base_url=DEFAULT_BASE_URL,
            model=DEFAULT_MODEL,
            temperature=0.1,
            max_tokens=100,
        )
        
        client = ChutesClient(config=config)
        print(f'✅ Client created with model: {DEFAULT_MODEL}')
        
        # Test simple message
        test_message = Message(
            role='user',
            content='Respond with exactly this JSON: {"message": "Chutes AI test successful", "status": "ok"}'
        )
        
        print('📡 Sending test message...')
        
        response = await asyncio.wait_for(
            client._generate_response([test_message], max_tokens=100),
            timeout=60.0  # Chutes can be slower
        )
        
        if response:
            print('✅ Response received!')
            if isinstance(response, dict):
                print(f'Response keys: {list(response.keys())}')
                if 'message' in response:
                    print(f'Message: {response["message"]}')
                if 'status' in response:
                    print(f'Status: {response["status"]}')
            else:
                response_str = str(response)
                preview = response_str[:200] + '...' if len(response_str) > 200 else response_str
                print(f'Response: {preview}')
            return True
        else:
            print('❌ No response received')
            return False
            
    except asyncio.TimeoutError:
        print('⏱️ Request timed out after 60 seconds')
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
        elif 'timeout' in error_str:
            print('💡 Chutes AI can be slower - try increasing timeout')
            
        return False

async def main():
    """Run the API-only test."""
    
    print(f'\nTest start: {datetime.now().isoformat()}')
    
    success = await test_chutes_api()
    
    print(f'\nTest end: {datetime.now().isoformat()}')
    
    if success:
        print('🎉 Chutes AI API test PASSED!')
        sys.exit(0)
    else:
        print('❌ Chutes AI API test FAILED!')
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())