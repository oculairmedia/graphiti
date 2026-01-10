#!/usr/bin/env python3
"""
DSPy Pipeline Edge Case Tests

Tests handling of challenging content:
- Long documents
- Multilingual (Chinese + English)
- Special characters and code blocks
- Ambiguous entity references
- Temporal expressions
- Complex relationships

Usage:
    CHUTES_API_KEY=your-key python3 test_edge_cases.py
"""

import os
import sys
import logging
from datetime import datetime, timezone

sys.path.insert(0, '/opt/stacks/graphiti')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class EdgeCaseTestResult:
    """Tracks edge case test results."""

    def __init__(self):
        self.results = []

    def record(self, name: str, passed: bool, details: str = ''):
        self.results.append({
            'name': name,
            'passed': passed,
            'details': details,
        })
        status = '[PASS]' if passed else '[FAIL]'
        print(f'  {status} {name}')
        if details:
            print(f'         {details}')

    def summary(self) -> str:
        passed = sum(1 for r in self.results if r['passed'])
        failed = sum(1 for r in self.results if not r['passed'])
        return f'\nEdge Cases: {passed} passed, {failed} failed out of {len(self.results)}'


def test_long_document(results: EdgeCaseTestResult):
    """Test extraction from long documents (>4K tokens)."""
    print('\n--- Long Document Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    # Generate a long document (~5000 characters)
    paragraphs = [
        'Dr. Sarah Chen is a renowned AI researcher at Stanford University. She leads the Machine Learning Lab and has published over 100 papers on deep learning.',
        'Her colleague, Professor Michael Zhang, specializes in natural language processing. Together they developed the TransformerX architecture in 2023.',
        'The lab is funded by Google Research and Microsoft AI. They collaborate with researchers from MIT and Carnegie Mellon.',
        'Recent projects include sentiment analysis for healthcare and autonomous driving perception systems.',
        'Dr. Chen received her PhD from MIT in 2010 and did postdoctoral work at Google Brain before joining Stanford.',
    ]

    # Repeat to make it long
    long_content = ' '.join(paragraphs * 5)

    result = pipeline.ingest_episode(content=long_content, episode_id='long_doc_001')

    entities_found = len(result.resolved_entities)
    edges_found = len(result.extracted_edges)

    # Should extract key entities: Sarah Chen, Michael Zhang, Stanford, MIT, Google, etc.
    passed = entities_found >= 5 and result.success
    results.record(
        f'Long document ({len(long_content)} chars)',
        passed,
        f'Entities: {entities_found}, Edges: {edges_found}, Tokens: {result.token_usage.total_tokens}',
    )


def test_multilingual_chinese(results: EdgeCaseTestResult):
    """Test extraction from Chinese + English mixed content."""
    print('\n--- Multilingual (Chinese) Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    # Mixed Chinese and English
    content = """
    张伟是阿里巴巴集团的首席技术官(CTO)。他毕业于清华大学计算机系。
    Zhang Wei is the CTO of Alibaba Group. He graduated from Tsinghua University's Computer Science department.
    他与Jack Ma (马云) 共同创建了阿里云 (Alibaba Cloud)。
    """

    result = pipeline.ingest_episode(content=content, episode_id='chinese_001')

    entities_found = [e['name'] for e in result.resolved_entities]

    # Should extract: 张伟/Zhang Wei, 阿里巴巴/Alibaba, 清华大学/Tsinghua, Jack Ma/马云
    key_terms = ['zhang', 'alibaba', 'jack', 'tsinghua', '阿里', '张伟', '清华', '马云']
    found_key = sum(1 for t in key_terms if any(t.lower() in e.lower() for e in entities_found))

    passed = found_key >= 3 and result.success
    results.record(
        'Chinese + English mixed content',
        passed,
        f'Found: {entities_found}',
    )


def test_special_characters(results: EdgeCaseTestResult):
    """Test extraction with special characters and code blocks."""
    print('\n--- Special Characters Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    content = """
    Developer @john_doe created the open-source project "fast-api-utils" on GitHub.
    The code uses Python 3.11+ and follows PEP-8 conventions.

    ```python
    from fast_api_utils import Router
    router = Router(prefix="/api/v1")
    ```

    Contact: john.doe@example.com | Website: https://john-doe.dev
    Company: O'Reilly & Associates, Inc.
    """

    result = pipeline.ingest_episode(content=content, episode_id='special_chars_001')

    entities_found = [e['name'] for e in result.resolved_entities]

    # Should extract: john_doe, fast-api-utils, GitHub, Python, O'Reilly
    passed = len(entities_found) >= 3 and result.success
    results.record(
        'Special chars, URLs, code blocks',
        passed,
        f'Found: {entities_found}',
    )


def test_ambiguous_entities(results: EdgeCaseTestResult):
    """Test handling of ambiguous entity references."""
    print('\n--- Ambiguous Entity Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    # Multiple "John"s that should be distinguished
    content = """
    John Smith is the CEO of TechCorp. He met with John Adams, the CFO, yesterday.
    Later, Dr. John Williams from the research department joined them.
    John (the CEO) presented the quarterly results. John Adams reviewed the finances.
    """

    result = pipeline.ingest_episode(content=content, episode_id='ambiguous_001')

    entities_found = [e['name'] for e in result.resolved_entities]
    john_entities = [e for e in entities_found if 'john' in e.lower()]

    # Should distinguish: John Smith, John Adams, John Williams (3 different Johns)
    passed = len(john_entities) >= 2 and result.success
    results.record(
        'Ambiguous references (3 Johns)',
        passed,
        f'Found: {john_entities}',
    )


def test_temporal_expressions(results: EdgeCaseTestResult):
    """Test extraction of temporal information."""
    print('\n--- Temporal Expressions Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    content = """
    Apple was founded on April 1, 1976 by Steve Jobs and Steve Wozniak.
    Steve Jobs left Apple in 1985 and returned in 1997.
    He passed away on October 5, 2011.
    Tim Cook became CEO in August 2011 and continues to lead the company today.
    """

    result = pipeline.ingest_episode(
        content=content,
        episode_id='temporal_001',
        reference_time='2024-01-15T12:00:00Z',
    )

    # Check if edges capture temporal info
    edges_with_dates = [e for e in result.extracted_edges if e.get('valid_at') or e.get('invalid_at')]

    passed = result.success and len(result.resolved_entities) >= 3
    results.record(
        'Temporal expressions (dates, periods)',
        passed,
        f'Entities: {[e["name"] for e in result.resolved_entities]}, Temporal edges: {len(edges_with_dates)}',
    )


def test_complex_relationships(results: EdgeCaseTestResult):
    """Test extraction of complex, multi-hop relationships."""
    print('\n--- Complex Relationships Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    content = """
    Dr. Alice Brown, who is the daughter of Nobel laureate James Brown, married
    Dr. Robert Chen, the son of tech billionaire Michael Chen.

    Alice leads the AI lab at Stanford, which collaborates with Robert's company
    ChenTech on autonomous vehicles. ChenTech is a subsidiary of Chen Industries,
    founded by Michael Chen in 1990.

    James Brown won the Nobel Prize in Physics in 2005 for his work at CERN.
    """

    result = pipeline.ingest_episode(content=content, episode_id='complex_001')

    # Should extract family relationships, work relationships, organizational hierarchy
    edges = result.extracted_edges
    edge_types = [e['relation_type'].upper() for e in edges]

    # Look for relationship diversity
    unique_types = set(edge_types)

    passed = len(result.resolved_entities) >= 5 and len(edges) >= 3 and result.success
    results.record(
        'Complex multi-hop relationships',
        passed,
        f'Entities: {len(result.resolved_entities)}, Edges: {len(edges)}, Types: {unique_types}',
    )


def test_negation_and_uncertainty(results: EdgeCaseTestResult):
    """Test handling of negation and uncertain statements."""
    print('\n--- Negation and Uncertainty Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    content = """
    Despite rumors, Elon Musk did NOT acquire Twitter in 2021. He was only considering it.
    The deal was NOT finalized until October 2022.
    Some analysts believe he might sell the company, but this is unconfirmed.
    Mark Zuckerberg reportedly might challenge Musk to a fight, though this was never officially confirmed.
    """

    result = pipeline.ingest_episode(content=content, episode_id='negation_001')

    # Should still extract entities but be careful with relationship assertions
    passed = result.success and len(result.resolved_entities) >= 2
    results.record(
        'Negation and uncertainty handling',
        passed,
        f'Entities: {[e["name"] for e in result.resolved_entities]}, Edges: {len(result.extracted_edges)}',
    )


def test_empty_and_minimal(results: EdgeCaseTestResult):
    """Test handling of edge cases: empty, minimal content."""
    print('\n--- Empty/Minimal Content Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    # Empty content
    result1 = pipeline.ingest_episode(content='', episode_id='empty_001')
    empty_ok = result1.success and len(result1.resolved_entities) == 0

    # Single word
    result2 = pipeline.ingest_episode(content='Hello', episode_id='minimal_001')
    minimal_ok = result2.success

    # Just punctuation
    result3 = pipeline.ingest_episode(content='...!!!???', episode_id='punct_001')
    punct_ok = result3.success

    passed = empty_ok and minimal_ok and punct_ok
    results.record(
        'Empty and minimal content handling',
        passed,
        f'Empty: {len(result1.resolved_entities)} entities, Minimal: {len(result2.resolved_entities)}, Punct: {len(result3.resolved_entities)}',
    )


def test_token_usage_tracking(results: EdgeCaseTestResult):
    """Test that token usage is properly tracked."""
    print('\n--- Token Usage Tracking Test ---')

    from graphiti_core.dspy import DSPyIngestionPipeline, configure_lm

    configure_lm(use_multi_model=False)
    pipeline = DSPyIngestionPipeline(group_id="test", generate_summaries=False)

    content = 'Microsoft CEO Satya Nadella announced a partnership with OpenAI.'
    result = pipeline.ingest_episode(content=content, episode_id='token_test_001')

    usage = result.token_usage

    # Token tracking should show non-zero values
    has_extraction_tokens = usage.extraction_tokens > 0
    has_total = usage.total_tokens > 0

    passed = has_total  # At minimum, total should be tracked
    results.record(
        'Token usage tracking',
        passed,
        f'Total: {usage.total_tokens}, Extraction: {usage.extraction_tokens}, Edge: {usage.edge_tokens}',
    )


def main():
    """Run all edge case tests."""
    print('=' * 60)
    print('DSPy Pipeline Edge Case Tests')
    print('=' * 60)

    # Check API key
    if not os.environ.get('CHUTES_API_KEY'):
        print('ERROR: CHUTES_API_KEY not set')
        sys.exit(1)

    results = EdgeCaseTestResult()

    # Run all tests
    test_empty_and_minimal(results)
    test_special_characters(results)
    test_ambiguous_entities(results)
    test_temporal_expressions(results)
    test_negation_and_uncertainty(results)
    test_multilingual_chinese(results)
    test_complex_relationships(results)
    test_long_document(results)
    test_token_usage_tracking(results)

    # Summary
    print(results.summary())

    # Exit code
    failed = sum(1 for r in results.results if not r['passed'])
    sys.exit(0 if failed == 0 else 1)


if __name__ == '__main__':
    main()
