#!/usr/bin/env python3
"""
Test Ollama with debug logging enabled.
"""

import asyncio
import logging
import os
from datetime import datetime

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Set specific loggers to debug
logging.getLogger('graphiti_core').setLevel(logging.DEBUG)
logging.getLogger('openai').setLevel(logging.DEBUG)

from graphiti_core.nodes import EpisodeType
from use_ollama import Graphiti


async def test_with_logging():
    print('🦙 Testing Ollama with Debug Logging')
    print('=' * 50)

    graphiti = Graphiti(uri='bolt://localhost:6389', user='', password='')

    test_content = 'Bob is a data scientist. He works with Alice on the Graphiti project.'

    print('\n📝 Starting add_episode (watch the logs)...')
    try:
        await asyncio.wait_for(
            graphiti.add_episode(
                name='Bob joins the team',
                episode_body=test_content,
                source_description='Team announcement',
                reference_time=datetime.now(),
                source=EpisodeType.text,
                group_id='test_debug',
            ),
            timeout=60.0,  # 60 second timeout
        )
        print('✅ Success!')

    except asyncio.TimeoutError:
        print('⏱️ TIMEOUT after 60 seconds')
    except Exception as e:
        print(f'❌ Error: {e}')
        import traceback

        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(test_with_logging())
