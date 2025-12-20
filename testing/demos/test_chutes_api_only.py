#!/usr/bin/env python3
"""Test Chutes AI API connection only - no database interaction.

Note: This file doubles as a quick manual demo script and a pytest-able
integration test. It must not `sys.exit()` at import time.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

import pytest

pytestmark = pytest.mark.integration


def _get_chutes_key_or_skip() -> str:
    chutes_key = os.getenv('CHUTES_API_KEY')
    if not chutes_key:
        pytest.skip('CHUTES_API_KEY not set', allow_module_level=True)
    return chutes_key


def _import_chutes_components_or_skip():
    try:
        from graphiti_core.llm_client.chutes_client import (
            DEFAULT_BASE_URL,
            DEFAULT_MODEL,
            ChutesClient,
        )
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.prompts.models import Message

        return ChutesClient, LLMConfig, Message, DEFAULT_MODEL, DEFAULT_BASE_URL
    except Exception as exc:
        pytest.skip(f'Chutes client import failed: {exc}', allow_module_level=True)


@pytest.mark.asyncio
async def test_chutes_api():
    """Test Chutes AI API connection and response."""

    chutes_key = _get_chutes_key_or_skip()
    ChutesClient, LLMConfig, Message, DEFAULT_MODEL, DEFAULT_BASE_URL = (
        _import_chutes_components_or_skip()
    )

    config = LLMConfig(
        api_key=chutes_key,
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        temperature=0.1,
        max_tokens=100,
    )

    client = ChutesClient(config=config)

    test_message = Message(
        role='user',
        content='Respond with exactly this JSON: {"message": "Chutes AI test successful", "status": "ok"}',
    )

    response = await asyncio.wait_for(
        client._generate_response([test_message], max_tokens=100),
        timeout=60.0,
    )

    assert response is not None


async def main() -> int:
    """Run the API-only test (manual script mode)."""

    print('🚀 Chutes AI API Only Test')
    print('=' * 40)

    chutes_key = os.getenv('CHUTES_API_KEY')
    print(f'CHUTES_API_KEY: {"Set" if chutes_key else "Not set"}')

    if not chutes_key:
        print('❌ No CHUTES_API_KEY found')
        return 1

    try:
        from graphiti_core.llm_client.chutes_client import (
            DEFAULT_BASE_URL,
            DEFAULT_MODEL,
            ChutesClient,
        )
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.prompts.models import Message

        print('✅ Imports successful')
        print(f'Default model: {DEFAULT_MODEL}')
        print(f'Default base URL: {DEFAULT_BASE_URL}')
    except Exception as exc:
        print(f'❌ Import failed: {exc}')
        return 1

    print(f'\nTest start: {datetime.now().isoformat()}')

    config = LLMConfig(
        api_key=chutes_key,
        base_url=DEFAULT_BASE_URL,
        model=DEFAULT_MODEL,
        temperature=0.1,
        max_tokens=100,
    )
    client = ChutesClient(config=config)

    test_message = Message(
        role='user',
        content='Respond with exactly this JSON: {"message": "Chutes AI test successful", "status": "ok"}',
    )

    try:
        response = await asyncio.wait_for(
            client._generate_response([test_message], max_tokens=100),
            timeout=60.0,
        )
        ok = response is not None
    except Exception as exc:
        print(f'❌ Error: {exc}')
        ok = False

    print(f'\nTest end: {datetime.now().isoformat()}')

    if ok:
        print('🎉 Chutes AI API test PASSED!')
        return 0

    print('❌ Chutes AI API test FAILED!')
    return 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
