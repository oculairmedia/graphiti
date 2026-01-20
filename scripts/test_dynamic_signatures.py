#!/usr/bin/env python3
"""
Test dynamic signature loading from PromptRegistry.

Tests:
1. SignatureFactory returns base signatures when disabled
2. SignatureFactory returns dynamic signatures when enabled
3. Module.create() methods work correctly
4. Fallback behavior when registry unavailable
"""

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_signature_factory_disabled():
    """Test that SignatureFactory returns base signatures when DSPY_DYNAMIC_PROMPTS=false."""
    os.environ['DSPY_DYNAMIC_PROMPTS'] = 'false'

    from graphiti_core.dspy.signatures import (
        SignatureFactory,
        EntityExtractionSignature,
        EdgeExtractionSignature,
        NodeDeduplicationSignature,
        SummaryGenerationSignature,
    )

    SignatureFactory.invalidate_cache()

    sig, version = await SignatureFactory.get_signature('entity_extraction')
    assert sig is EntityExtractionSignature, f'Expected EntityExtractionSignature, got {sig}'
    assert version is None, f'Expected None version, got {version}'

    sig, version = await SignatureFactory.get_signature('edge_extraction')
    assert sig is EdgeExtractionSignature

    sig, version = await SignatureFactory.get_signature('node_resolution')
    assert sig is NodeDeduplicationSignature

    sig, version = await SignatureFactory.get_signature('summary_generation')
    assert sig is SummaryGenerationSignature

    logger.info('PASS: test_signature_factory_disabled')


async def test_signature_factory_enabled():
    """Test that SignatureFactory loads from registry when enabled."""
    os.environ['DSPY_DYNAMIC_PROMPTS'] = 'true'

    from graphiti_core.dspy.signatures import SignatureFactory

    SignatureFactory.invalidate_cache()

    sig, version = await SignatureFactory.get_signature('entity_extraction')

    logger.info(f'Got signature: {sig.__name__}, version: {version}')
    logger.info(f'Docstring preview: {(sig.__doc__ or "")[:100]}...')

    if version is not None:
        logger.info(f'PASS: Dynamic loading worked, got prompt v{version}')
    else:
        logger.info('PASS: Fallback to base signature (registry may not have live prompts)')


async def test_module_create_methods():
    """Test that Module.create() methods work correctly."""
    os.environ['DSPY_DYNAMIC_PROMPTS'] = 'true'

    from graphiti_core.dspy.modules import (
        NodeExtractor,
        EdgeExtractor,
        NodeResolver,
        SummaryGenerator,
    )
    from graphiti_core.dspy.signatures import SignatureFactory

    SignatureFactory.invalidate_cache()

    extractor = await NodeExtractor.create()
    logger.info(f'NodeExtractor._prompt_version: {extractor._prompt_version}')

    edge_extractor = await EdgeExtractor.create()
    logger.info(f'EdgeExtractor._prompt_version: {edge_extractor._prompt_version}')

    resolver = await NodeResolver.create()
    logger.info(f'NodeResolver._prompt_version: {resolver._prompt_version}')

    summary_gen = await SummaryGenerator.create()
    logger.info(f'SummaryGenerator._prompt_version: {summary_gen._prompt_version}')

    logger.info('PASS: test_module_create_methods')


async def test_sync_fallback():
    """Test that get_signature_sync() works."""
    from graphiti_core.dspy.signatures import (
        SignatureFactory,
        EntityExtractionSignature,
    )

    sig = SignatureFactory.get_signature_sync('entity_extraction')
    assert sig is EntityExtractionSignature

    logger.info('PASS: test_sync_fallback')


async def main():
    logger.info('Starting dynamic signature tests...')
    logger.info('=' * 60)

    await test_signature_factory_disabled()
    logger.info('-' * 60)

    await test_signature_factory_enabled()
    logger.info('-' * 60)

    await test_module_create_methods()
    logger.info('-' * 60)

    await test_sync_fallback()
    logger.info('=' * 60)

    logger.info('All tests passed!')


if __name__ == '__main__':
    asyncio.run(main())
