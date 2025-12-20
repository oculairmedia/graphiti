#!/usr/bin/env python3

"""Benchmark Graphiti ingestion LLM steps.

This script calls Graphiti's production ingestion functions (entity extraction and
optional attribute/summary extraction) without requiring a running DB.

It is meant to reproduce and benchmark model-specific failure modes (invalid JSON,
list-vs-dict responses, schema-echo, slow responses) in isolation.

Example (Anthropic Haiku):
  USE_ANTHROPIC=true ANTHROPIC_API_KEY=... ANTHROPIC_MODEL=claude-3-5-haiku-latest \
    python3 testing/benchmarks/ingestion_llm_benchmark.py --enable-attributes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from graphiti_core.client_factory import GraphitiClientFactory
from graphiti_core.graphiti_types import GraphitiClients
from graphiti_core.nodes import EpisodeType, EpisodicNode
from graphiti_core.utils.maintenance.node_operations import (
    extract_attributes_from_node,
    extract_nodes,
)

from noop_clients import DeterministicNoopEmbedder, NoopDriver


@dataclass
class Case:
    case_id: str
    episode_type: str
    content: str
    name: str = 'Benchmark Episode'
    source_description: str = 'ingestion_llm_benchmark'
    group_id: str = 'bench'


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_episode(case: Case) -> EpisodicNode:
    return EpisodicNode(
        name=case.name,
        group_id=case.group_id,
        source=EpisodeType.from_str(case.episode_type),
        source_description=case.source_description,
        content=case.content,
        valid_at=_utc_now(),
    )


def _default_cases() -> list[Case]:
    return [
        Case(
            case_id='simple-message',
            episode_type='message',
            content='user: Alice met Bob at the coffee shop to discuss the project roadmap.',
        ),
        Case(
            case_id='dense-text',
            episode_type='text',
            content=(
                'On 2025-12-01, the Graphiti team reviewed ingestion failures across multiple models. '
                'Key issues included invalid JSON, schema-echo responses, and missing required fields. '
                'They decided to benchmark entity extraction and summary generation to isolate regressions.'
            ),
        ),
        Case(
            case_id='json-episode',
            episode_type='json',
            content=json.dumps(
                {
                    'title': 'Incident report',
                    'actors': ['Alice', 'Bob'],
                    'events': [
                        {
                            'ts': '2025-12-01T12:00:00Z',
                            'text': 'Alice asked Bob to investigate schema-echo parsing issues.',
                        },
                        {
                            'ts': '2025-12-01T12:30:00Z',
                            'text': 'Bob confirmed the model sometimes returns a JSON schema instead of values.',
                        },
                    ],
                }
            ),
        ),
    ]


def _load_cases(path: str) -> list[Case]:
    with open(path, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError('cases file must be a JSON list')

    cases: list[Case] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError('each case must be a JSON object')
        cases.append(Case(**item))
    return cases


async def _run_case(
    clients: GraphitiClients,
    case: Case,
    enable_attributes: bool,
) -> dict[str, Any]:
    episode = _build_episode(case)

    started_at = time.perf_counter()
    entities = await extract_nodes(clients, episode=episode, previous_episodes=[])
    extract_ms = int((time.perf_counter() - started_at) * 1000)

    nodes_out: list[dict[str, Any]] = []

    attr_ms_total = 0
    if enable_attributes:
        for node in entities:
            t0 = time.perf_counter()
            updated = await extract_attributes_from_node(
                clients.llm_client, node=node, episode=episode, previous_episodes=[]
            )
            attr_ms_total += int((time.perf_counter() - t0) * 1000)
            nodes_out.append(
                {
                    'uuid': updated.uuid,
                    'name': updated.name,
                    'labels': updated.labels,
                    'summary_len': len(updated.summary or ''),
                    'attributes_keys': sorted(list(updated.attributes.keys())),
                }
            )
    else:
        for node in entities:
            nodes_out.append(
                {
                    'uuid': node.uuid,
                    'name': node.name,
                    'labels': node.labels,
                    'summary_len': len(node.summary or ''),
                    'attributes_keys': sorted(list(node.attributes.keys())),
                }
            )

    return {
        'case': asdict(case),
        'timings_ms': {
            'extract_nodes_ms': extract_ms,
            'extract_attributes_ms_total': attr_ms_total,
        },
        'result': {
            'extracted_nodes_count': len(entities),
            'nodes': nodes_out,
        },
    }


async def _amain(args: argparse.Namespace) -> int:
    llm_client = GraphitiClientFactory.create_llm_client()
    if llm_client is None:
        raise RuntimeError('GraphitiClientFactory.create_llm_client() returned None')

    embedder = DeterministicNoopEmbedder()

    clients = GraphitiClients(
        driver=NoopDriver(),
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=None,
    )

    cases = _load_cases(args.cases) if args.cases else _default_cases()

    enable_attributes = bool(args.enable_attributes)
    if args.force_enable_attribute_extraction:
        os.environ['ENABLE_ATTRIBUTE_EXTRACTION'] = 'true'

    report: dict[str, Any] = {
        'meta': {
            'started_at': _utc_now().isoformat(),
            'runs': args.runs,
            'enable_attributes': enable_attributes,
            'llm_client': type(llm_client).__name__,
            'model': getattr(llm_client, 'model', None),
            'small_model': getattr(llm_client, 'small_model', None),
        },
        'cases': [],
    }

    for i in range(args.runs):
        run_results = []
        for case in cases:
            try:
                run_results.append(
                    {
                        'run_index': i,
                        'status': 'ok',
                        **(await _run_case(clients, case, enable_attributes)),
                    }
                )
            except Exception as e:
                run_results.append(
                    {
                        'run_index': i,
                        'status': 'error',
                        'case': asdict(case),
                        'error': f'{type(e).__name__}: {e}',
                    }
                )
        report['cases'].extend(run_results)

    output_text = json.dumps(report, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_text)
    else:
        print(output_text)

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Benchmark Graphiti ingestion LLM steps')

    parser.add_argument('--cases', help='Path to JSON cases file')
    parser.add_argument('--runs', type=int, default=1, help='Number of times to run all cases')
    parser.add_argument(
        '--enable-attributes',
        action='store_true',
        help='Also run attribute/summary extraction (calls the LLM again per entity)',
    )
    parser.add_argument(
        '--force-enable-attribute-extraction',
        action='store_true',
        help='Set ENABLE_ATTRIBUTE_EXTRACTION=true (overrides env) for this run',
    )
    parser.add_argument('--output', help='Write report JSON to this file')

    args = parser.parse_args()

    if args.runs < 1:
        raise SystemExit('--runs must be >= 1')

    return asyncio.run(_amain(args))


if __name__ == '__main__':
    raise SystemExit(main())
