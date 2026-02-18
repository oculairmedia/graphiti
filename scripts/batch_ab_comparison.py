#!/usr/bin/env python3
"""
A/B comparison: individual vs batched LLM calls for attribute extraction and edge resolution.

Uses real training data from FalkorDB as test fixtures. Runs real LLM calls.
Compares outputs to detect quality regressions from batching.

Usage:
    python3 scripts/batch_ab_comparison.py --task attributes --batch-size 5 --num-samples 20
    python3 scripts/batch_ab_comparison.py --task edges --batch-size 3 --num-samples 15
    python3 scripts/batch_ab_comparison.py --task all --batch-size 5 --num-samples 10
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.prompts.models import Message

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('openai').setLevel(logging.WARNING)
logging.getLogger('litellm').setLevel(logging.WARNING)
logging.getLogger('dspy').setLevel(logging.WARNING)


@dataclass
class ComparisonResult:
    entity_name: str
    individual_summary: str
    batched_summary: str
    ground_truth_summary: str
    similarity_ind_vs_batch: float
    similarity_ind_vs_truth: float
    similarity_batch_vs_truth: float
    individual_latency_ms: float
    batched_latency_ms: float


@dataclass
class EdgeComparisonResult:
    edge_fact: str
    individual_duplicates: list[int]
    batched_duplicates: list[int]
    individual_contradictions: list[int]
    batched_contradictions: list[int]
    duplicates_match: bool
    contradictions_match: bool
    individual_latency_ms: float
    batched_latency_ms: float


@dataclass
class BatchReport:
    task: str
    batch_size: int
    num_samples: int
    results: list = field(default_factory=list)
    total_individual_latency_ms: float = 0.0
    total_batched_latency_ms: float = 0.0

    def summary(self) -> dict:
        if not self.results:
            return {'task': self.task, 'error': 'no results'}

        if self.task == 'attributes':
            ind_vs_batch = [r.similarity_ind_vs_batch for r in self.results]
            ind_vs_truth = [r.similarity_ind_vs_truth for r in self.results]
            batch_vs_truth = [r.similarity_batch_vs_truth for r in self.results]

            return {
                'task': self.task,
                'batch_size': self.batch_size,
                'num_samples': len(self.results),
                'individual_vs_batched': {
                    'mean_similarity': sum(ind_vs_batch) / len(ind_vs_batch),
                    'min_similarity': min(ind_vs_batch),
                    'max_similarity': max(ind_vs_batch),
                    'below_90pct': sum(1 for s in ind_vs_batch if s < 0.9),
                },
                'individual_vs_ground_truth': {
                    'mean_similarity': sum(ind_vs_truth) / len(ind_vs_truth),
                },
                'batched_vs_ground_truth': {
                    'mean_similarity': sum(batch_vs_truth) / len(batch_vs_truth),
                },
                'latency': {
                    'total_individual_ms': self.total_individual_latency_ms,
                    'total_batched_ms': self.total_batched_latency_ms,
                    'speedup': (
                        self.total_individual_latency_ms / self.total_batched_latency_ms
                        if self.total_batched_latency_ms > 0
                        else 0
                    ),
                },
                'regression_detected': any(
                    (bt < it - 0.15) for it, bt in zip(ind_vs_truth, batch_vs_truth)
                ),
                'pass': (sum(batch_vs_truth) / len(batch_vs_truth))
                >= (sum(ind_vs_truth) / len(ind_vs_truth)) * 0.8,
            }
        else:
            dup_matches = [r.duplicates_match for r in self.results]
            contra_matches = [r.contradictions_match for r in self.results]

            return {
                'task': self.task,
                'batch_size': self.batch_size,
                'num_samples': len(self.results),
                'duplicate_agreement': sum(dup_matches) / len(dup_matches),
                'contradiction_agreement': sum(contra_matches) / len(contra_matches),
                'latency': {
                    'total_individual_ms': self.total_individual_latency_ms,
                    'total_batched_ms': self.total_batched_latency_ms,
                    'speedup': (
                        self.total_individual_latency_ms / self.total_batched_latency_ms
                        if self.total_batched_latency_ms > 0
                        else 0
                    ),
                },
                'pass': (sum(dup_matches) / len(dup_matches)) >= 0.85,
            }


def text_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


async def get_llm_client():
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_client import OpenAIClient

    use_chutes = os.getenv('USE_CHUTES', 'false').lower() == 'true'
    if use_chutes:
        api_key = os.getenv('CHUTES_API_KEY', '')
        base_url = os.getenv('CHUTES_BASE_URL', 'https://api.z.ai/api/coding/paas/v4')
        model = os.getenv('CHUTES_SMALL_MODEL', 'glm-4.5-air')
        config = LLMConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
            small_model=model,
        )
    else:
        base_url = os.getenv('OLLAMA_BASE_URL', 'http://192.168.50.90:8082/v1')
        model = os.getenv('OLLAMA_MODEL', 'haiku-4-5')
        config = LLMConfig(
            api_key=os.getenv('OPENAI_API_KEY', 'ollama'),
            base_url=base_url,
            model=model,
            small_model=model,
        )

    return OpenAIClient(config)


async def load_attribute_test_data(limit: int = 50) -> list[dict]:
    from graphiti_core.dspy.training_storage import get_training_examples

    examples = await get_training_examples('summary_generation', limit=limit * 3)
    if not examples:
        logger.warning('No summary_generation training data found, trying entity_extraction')
        examples = await get_training_examples('entity_extraction', limit=limit * 3)

    if not examples:
        return []

    test_data = []
    for ex in examples:
        inputs = ex.inputs
        output = ex.output
        msg = inputs.get('current_message', '')
        entity_name = inputs.get('entity_name', '')
        existing_summary = inputs.get('existing_summary', '')

        if not msg or not entity_name:
            continue

        # Skip dev tool noise (file paths, tool names, code artifacts)
        if any(
            indicator in entity_name
            for indicator in ['.py', '.js', '.ts', 'Search', 'Output', 'Background', 'mcp_']
        ):
            continue

        ground_truth = ''
        if isinstance(output, dict):
            summary_data = output.get('summary', {})
            if isinstance(summary_data, dict):
                ground_truth = summary_data.get('summary', '')
            elif isinstance(summary_data, str):
                ground_truth = summary_data

        if not ground_truth:
            continue

        test_data.append(
            {
                'current_message': msg,
                'entity_name': entity_name,
                'existing_summary': existing_summary,
                'previous_messages': inputs.get('previous_messages', '[]'),
                'ground_truth_summary': ground_truth,
            }
        )

        if len(test_data) >= limit:
            break

    return test_data


async def load_edge_test_data(limit: int = 50) -> list[dict]:
    from graphiti_core.dspy.training_storage import get_training_examples

    examples = await get_training_examples('edge_extraction', limit=limit * 3)
    if not examples:
        return []

    test_data = []
    for ex in examples:
        inputs = ex.inputs
        output = ex.output
        msg = inputs.get('current_message', '')
        entities = inputs.get('entities', '[]')

        if not msg:
            continue

        edges_output = output.get('extracted_edges', {})
        if isinstance(edges_output, dict):
            edges = edges_output.get('edges', [])
        elif isinstance(edges_output, list):
            edges = edges_output
        else:
            continue

        if not edges or len(edges) < 2:
            continue

        test_data.append(
            {
                'current_message': msg,
                'entities': entities,
                'edges': edges,
                'reference_time': inputs.get('reference_time', ''),
            }
        )

        if len(test_data) >= limit:
            break

    return test_data


def build_individual_attribute_prompt(
    entity_name: str,
    existing_summary: str,
    episode_content: str,
    previous_messages: str,
) -> list[Message]:
    prev = (
        previous_messages if isinstance(previous_messages, str) else json.dumps(previous_messages)
    )

    return [
        Message(
            role='system',
            content=(
                'You are a JSON extraction assistant. You MUST respond with ONLY a valid JSON object.\n'
                'Output ONLY a single JSON object - no explanations, no markdown, no extra text.'
            ),
        ),
        Message(
            role='user',
            content=(
                f'Extract entity properties from the provided text and return them as a JSON object.\n\n'
                f'<MESSAGES>\n{prev}\n{episode_content}\n</MESSAGES>\n\n'
                f'Given the above MESSAGES and the following ENTITY, update any of its attributes.\n'
                f'The summary attribute should be updated with new information. Max 250 words.\n\n'
                f'<ENTITY>\n{{"name": "{entity_name}", "summary": "{existing_summary}"}}\n</ENTITY>'
            ),
        ),
    ]


def build_batched_attribute_prompt(
    entities: list[dict],
    episode_content: str,
    previous_messages: str,
) -> list[Message]:
    prev = (
        previous_messages if isinstance(previous_messages, str) else json.dumps(previous_messages)
    )

    entities_block = '\n'.join(
        f'  {i + 1}. Name: "{e["entity_name"]}", Current Summary: "{e.get("existing_summary", "")}"'
        for i, e in enumerate(entities)
    )

    return [
        Message(
            role='system',
            content=(
                'You are a JSON extraction assistant. You MUST respond with ONLY a valid JSON object.\n'
                'Output ONLY a single JSON object - no explanations, no markdown, no extra text.'
            ),
        ),
        Message(
            role='user',
            content=(
                f'Extract entity properties from the provided text for EACH entity listed below.\n'
                f'Return a JSON object with entity names as keys and their attributes as values.\n\n'
                f'<MESSAGES>\n{prev}\n{episode_content}\n</MESSAGES>\n\n'
                f'<ENTITIES>\n{entities_block}\n</ENTITIES>\n\n'
                f'For each entity, update its summary with new information from MESSAGES. Max 250 words per summary.\n\n'
                f'Return format: {{"<entity_name>": {{"summary": "<updated summary>"}}, ...}}\n'
                f'Include ALL {len(entities)} entities in the response.'
            ),
        ),
    ]


async def run_attribute_comparison(
    llm_client,
    test_data: list[dict],
    batch_size: int,
) -> BatchReport:
    report = BatchReport(task='attributes', batch_size=batch_size, num_samples=len(test_data))

    # Group test data into batches by shared episode content
    # In production, entities from the same episode share context
    batches = []
    for i in range(0, len(test_data), batch_size):
        batches.append(test_data[i : i + batch_size])

    for batch_idx, batch in enumerate(batches):
        logger.info(f'Batch {batch_idx + 1}/{len(batches)} ({len(batch)} entities)')

        # --- Individual calls ---
        individual_results = {}
        ind_start = time.time()

        for item in batch:
            prompt = build_individual_attribute_prompt(
                item['entity_name'],
                item.get('existing_summary', ''),
                item['current_message'],
                item.get('previous_messages', '[]'),
            )
            try:
                # Use raw JSON mode (no response_model) to avoid markdown fence parsing issues
                resp = await llm_client.generate_response(prompt)
                individual_results[item['entity_name']] = resp.get('summary', '')
            except Exception as e:
                logger.warning(f'Individual call failed for {item["entity_name"]}: {e}')
                individual_results[item['entity_name']] = ''
            await asyncio.sleep(1.0)

        ind_elapsed = (time.time() - ind_start) * 1000
        report.total_individual_latency_ms += ind_elapsed

        # --- Batched call ---
        batch_start = time.time()
        batched_prompt = build_batched_attribute_prompt(
            batch,
            batch[0]['current_message'],
            batch[0].get('previous_messages', '[]'),
        )

        # For batched, we need a dynamic response model
        try:
            resp = await llm_client.generate_response(batched_prompt)
            batched_results = {}
            if isinstance(resp, dict):
                for name, attrs in resp.items():
                    if isinstance(attrs, dict):
                        batched_results[name] = attrs.get('summary', '')
                    elif isinstance(attrs, str):
                        batched_results[name] = attrs
        except Exception as e:
            logger.warning(f'Batched call failed: {e}')
            batched_results = {}

        batch_elapsed = (time.time() - batch_start) * 1000
        report.total_batched_latency_ms += batch_elapsed

        # --- Compare ---
        for item in batch:
            name = item['entity_name']
            ind_summary = individual_results.get(name, '')
            bat_summary = batched_results.get(name, '')
            truth = item.get('ground_truth_summary', '')

            result = ComparisonResult(
                entity_name=name,
                individual_summary=ind_summary,
                batched_summary=bat_summary,
                ground_truth_summary=truth,
                similarity_ind_vs_batch=text_similarity(ind_summary, bat_summary),
                similarity_ind_vs_truth=text_similarity(ind_summary, truth),
                similarity_batch_vs_truth=text_similarity(bat_summary, truth),
                individual_latency_ms=ind_elapsed / len(batch),
                batched_latency_ms=batch_elapsed / len(batch),
            )
            report.results.append(result)

            logger.info(
                f'  {name}: ind_vs_batch={result.similarity_ind_vs_batch:.2f} '
                f'ind_vs_truth={result.similarity_ind_vs_truth:.2f} '
                f'batch_vs_truth={result.similarity_batch_vs_truth:.2f}'
            )

    return report


async def run_edge_comparison(
    llm_client,
    test_data: list[dict],
    batch_size: int,
) -> BatchReport:
    report = BatchReport(task='edges', batch_size=batch_size, num_samples=len(test_data))

    # For edge resolution, each edge has its own context (related edges)
    # Batching means resolving multiple new edges against the same existing edges in one call

    batches = []
    for i in range(0, len(test_data), batch_size):
        batches.append(test_data[i : i + batch_size])

    for batch_idx, batch in enumerate(batches):
        logger.info(f'Edge batch {batch_idx + 1}/{len(batches)} ({len(batch)} episodes)')

        for item in batch:
            edges = item.get('edges', [])
            if len(edges) < 2:
                continue

            # Use first edge as "existing", rest as "new" edges to resolve
            existing_edges = [{'id': i, 'fact': e.get('fact', '')} for i, e in enumerate(edges[:1])]
            new_edges = edges[1 : batch_size + 1]

            # --- Individual calls ---
            ind_start = time.time()
            individual_results = []

            for edge in new_edges:
                fact = edge.get('fact', '')
                prompt = [
                    Message(role='system', content='You are a fact deduplication assistant.'),
                    Message(
                        role='user',
                        content=(
                            f'<NEW FACT>\n{fact}\n</NEW FACT>\n\n'
                            f'<EXISTING FACTS>\n{json.dumps(existing_edges)}\n</EXISTING FACTS>\n\n'
                            f'Is the NEW FACT a duplicate of any EXISTING FACT? '
                            f'Return duplicate_facts (list of ids) and contradicted_facts (list of ids).'
                        ),
                    ),
                ]
                try:
                    resp = await llm_client.generate_response(prompt)
                    individual_results.append(
                        {
                            'duplicate_facts': resp.get('duplicate_facts', []),
                            'contradicted_facts': resp.get('contradicted_facts', []),
                        }
                    )
                except Exception as e:
                    logger.warning(f'Individual edge call failed: {e}')
                    individual_results.append({'duplicate_facts': [], 'contradicted_facts': []})
                await asyncio.sleep(1.0)

            ind_elapsed = (time.time() - ind_start) * 1000
            report.total_individual_latency_ms += ind_elapsed

            # --- Batched call ---
            batch_start = time.time()
            new_facts_block = '\n'.join(
                f'  Fact {i + 1}: {e.get("fact", "")}' for i, e in enumerate(new_edges)
            )

            batched_prompt = [
                Message(
                    role='system',
                    content='You are a fact deduplication assistant. Respond with JSON only.',
                ),
                Message(
                    role='user',
                    content=(
                        f'<EXISTING FACTS>\n{json.dumps(existing_edges)}\n</EXISTING FACTS>\n\n'
                        f'<NEW FACTS>\n{new_facts_block}\n</NEW FACTS>\n\n'
                        f'For EACH new fact, determine if it duplicates or contradicts any existing fact.\n'
                        f'Return a JSON object: {{"results": [{{"fact_index": 1, "duplicate_facts": [], "contradicted_facts": []}}, ...]}}'
                    ),
                ),
            ]

            batched_results = []
            try:
                resp = await llm_client.generate_response(batched_prompt)
                if isinstance(resp, dict):
                    for r in resp.get('results', []):
                        batched_results.append(
                            {
                                'duplicate_facts': r.get('duplicate_facts', []),
                                'contradicted_facts': r.get('contradicted_facts', []),
                            }
                        )
            except Exception as e:
                logger.warning(f'Batched edge call failed: {e}')

            batch_elapsed = (time.time() - batch_start) * 1000
            report.total_batched_latency_ms += batch_elapsed

            # --- Compare ---
            for i, edge in enumerate(new_edges):
                ind = individual_results[i] if i < len(individual_results) else {}
                bat = batched_results[i] if i < len(batched_results) else {}

                ind_dups = sorted(ind.get('duplicate_facts', []))
                bat_dups = sorted(bat.get('duplicate_facts', []))
                ind_contra = sorted(ind.get('contradicted_facts', []))
                bat_contra = sorted(bat.get('contradicted_facts', []))

                result = EdgeComparisonResult(
                    edge_fact=edge.get('fact', ''),
                    individual_duplicates=ind_dups,
                    batched_duplicates=bat_dups,
                    individual_contradictions=ind_contra,
                    batched_contradictions=bat_contra,
                    duplicates_match=ind_dups == bat_dups,
                    contradictions_match=ind_contra == bat_contra,
                    individual_latency_ms=ind_elapsed / max(len(new_edges), 1),
                    batched_latency_ms=batch_elapsed / max(len(new_edges), 1),
                )
                report.results.append(result)

    return report


async def main():
    parser = argparse.ArgumentParser(description='A/B comparison: individual vs batched LLM calls')
    parser.add_argument(
        '--task',
        choices=['attributes', 'edges', 'all'],
        default='attributes',
        help='Which task to compare',
    )
    parser.add_argument('--batch-size', type=int, default=5, help='Entities/edges per batch')
    parser.add_argument('--num-samples', type=int, default=20, help='Total samples to test')
    parser.add_argument('--verbose', action='store_true', help='Show per-item details')
    args = parser.parse_args()

    llm_client = await get_llm_client()
    reports = []

    if args.task in ('attributes', 'all'):
        logger.info(f'=== Attribute Extraction A/B (batch_size={args.batch_size}) ===')
        test_data = await load_attribute_test_data(args.num_samples)
        if test_data:
            logger.info(f'Loaded {len(test_data)} test examples from FalkorDB')
            report = await run_attribute_comparison(llm_client, test_data, args.batch_size)
            reports.append(report)
        else:
            logger.error('No attribute test data available')

    if args.task in ('edges', 'all'):
        logger.info(f'=== Edge Resolution A/B (batch_size={args.batch_size}) ===')
        test_data = await load_edge_test_data(args.num_samples)
        if test_data:
            logger.info(f'Loaded {len(test_data)} test examples from FalkorDB')
            report = await run_edge_comparison(llm_client, test_data, args.batch_size)
            reports.append(report)
        else:
            logger.error('No edge test data available')

    # Final report
    print('\n' + '=' * 70)
    print('FINAL REPORT')
    print('=' * 70)

    for report in reports:
        summary = report.summary()
        print(f'\n--- {summary["task"].upper()} ---')
        print(json.dumps(summary, indent=2))

        passed = summary.get('pass', False)
        print(f'\nResult: {"PASS" if passed else "FAIL"}')

        if summary['task'] == 'attributes':
            mean_sim = summary['individual_vs_batched']['mean_similarity']
            speedup = summary['latency']['speedup']
            print(f'Mean individual vs batched similarity: {mean_sim:.2%}')
            print(f'Latency speedup: {speedup:.1f}x')
            below_90 = summary['individual_vs_batched']['below_90pct']
            if below_90:
                print(f'WARNING: {below_90} samples below 90% similarity')
        else:
            dup_agree = summary.get('duplicate_agreement', 0)
            speedup = summary['latency']['speedup']
            print(f'Duplicate agreement: {dup_agree:.2%}')
            print(f'Latency speedup: {speedup:.1f}x')


if __name__ == '__main__':
    asyncio.run(main())
