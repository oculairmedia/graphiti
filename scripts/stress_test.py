#!/usr/bin/env python3
"""
End-to-End Stress Test for Graphiti Memory System

Tests:
1. Episode ingestion throughput at controlled rates
2. Search latency under load
3. Mixed workload (concurrent ingestion + search)

Usage:
    # Basic ingestion stress test (10 eps/min for 5 min)
    python3 scripts/stress_test.py ingest --rate 10 --duration 5

    # Search latency test (5 qps for 2 min)
    python3 scripts/stress_test.py search --qps 5 --duration 2

    # Mixed workload test
    python3 scripts/stress_test.py mixed --ingest-rate 5 --search-qps 3 --duration 5

    # Full stress test with report
    python3 scripts/stress_test.py full --output stress_report.json
"""

import argparse
import asyncio
import json
import logging
import random
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiohttp

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Configuration
GRAPHITI_API_URL = 'http://localhost:8003'
GRAPHITI_MCP_URL = 'http://localhost:8003'  # MCP server shares port with API
QUEUE_API_URL = 'http://localhost:8093'
TEMPORAL_API_URL = 'http://192.168.50.90:8080'

# Sample episode content for stress testing
SAMPLE_EPISODES = [
    'User: I need to implement a new authentication system using OAuth2 with JWT tokens.',
    "Assistant: I'll help you implement OAuth2 authentication. First, let's set up the token endpoint.",
    "User: The database migration failed with error: relation 'users' does not exist.",
    'System: Deployment completed successfully. All services are healthy.',
    'User: Can you explain how the search algorithm works in this codebase?',
    'Assistant: The search uses a hybrid approach combining BM25 text search with semantic embeddings.',
    "User: I'm seeing high memory usage in the worker process. Can you investigate?",
    'System: Alert: CPU usage exceeded 90% threshold on graphiti-worker-1.',
    "User: Let's refactor the episode ingestion pipeline to improve throughput.",
    'Assistant: I recommend adding batching at the queue level and increasing worker concurrency.',
]

SAMPLE_QUERIES = [
    'authentication OAuth2',
    'database migration error',
    'search algorithm implementation',
    'memory usage worker',
    'episode ingestion throughput',
    'deployment status',
    'user authentication flow',
    'system alerts monitoring',
    'code refactoring patterns',
    'performance optimization',
]


@dataclass
class LatencyMetrics:
    """Track latency statistics"""

    samples: list[float] = field(default_factory=list)

    def add(self, latency_ms: float):
        self.samples.append(latency_ms)

    def get_stats(self) -> dict[str, float]:
        if not self.samples:
            return {'count': 0, 'p50': 0, 'p95': 0, 'p99': 0, 'avg': 0, 'min': 0, 'max': 0}

        sorted_samples = sorted(self.samples)
        n = len(sorted_samples)

        return {
            'count': n,
            'p50': sorted_samples[int(n * 0.5)] if n > 0 else 0,
            'p95': sorted_samples[int(n * 0.95)] if n > 0 else 0,
            'p99': sorted_samples[int(n * 0.99)] if n > 0 else 0,
            'avg': statistics.mean(sorted_samples),
            'min': min(sorted_samples),
            'max': max(sorted_samples),
        }


@dataclass
class StressTestResult:
    """Results from a stress test run"""

    test_type: str
    started_at: str
    ended_at: str
    duration_seconds: float

    # Ingestion metrics
    episodes_submitted: int = 0
    episodes_succeeded: int = 0
    episodes_failed: int = 0
    ingestion_latency: dict = field(default_factory=dict)
    actual_ingest_rate: float = 0.0

    # Search metrics
    searches_submitted: int = 0
    searches_succeeded: int = 0
    searches_failed: int = 0
    search_latency: dict = field(default_factory=dict)
    actual_search_rate: float = 0.0

    # System metrics
    queue_depth_samples: list[int] = field(default_factory=list)
    workflow_count_samples: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class StressTester:
    """Graphiti memory system stress tester"""

    def __init__(self, group_id: str = 'stress-test'):
        self.group_id = group_id
        self.session: Optional[aiohttp.ClientSession] = None
        self.ingestion_latency = LatencyMetrics()
        self.search_latency = LatencyMetrics()
        self.errors: list[str] = []
        self.queue_depths: list[int] = []
        self.workflow_counts: list[int] = []

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    def _generate_episode_content(self) -> str:
        """Generate realistic episode content"""
        base = random.choice(SAMPLE_EPISODES)
        # Add unique identifier to prevent deduplication
        return f'{base} [test-{uuid.uuid4().hex[:8]}]'

    async def submit_episode(self) -> tuple[bool, float]:
        """Submit a single episode and return (success, latency_ms)"""
        if self.session is None:
            raise RuntimeError('Session not initialized')

        content = self._generate_episode_content()
        now = datetime.now(timezone.utc)

        # API expects AddMessagesRequest format
        payload = {
            'group_id': self.group_id,
            'messages': [
                {
                    'content': content,
                    'role_type': 'user',
                    'role': 'stress_tester',
                    'name': f'Stress Test {now.strftime("%H:%M:%S")}',
                    'timestamp': now.isoformat(),
                    'source_description': 'stress_test',
                }
            ],
        }

        start = time.perf_counter()
        try:
            async with self.session.post(
                f'{GRAPHITI_API_URL}/messages',
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                latency_ms = (time.perf_counter() - start) * 1000
                if resp.status == 200 or resp.status == 202:
                    return True, latency_ms
                else:
                    error = await resp.text()
                    self.errors.append(f'Ingest error {resp.status}: {error[:200]}')
                    return False, latency_ms
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self.errors.append(f'Ingest exception: {str(e)[:200]}')
            return False, latency_ms

    async def search_memory(self, query: str) -> tuple[bool, float, int]:
        """Search memory and return (success, latency_ms, result_count)"""
        if self.session is None:
            raise RuntimeError('Session not initialized')

        payload = {
            'query': query,
            'group_ids': [self.group_id],
            'max_facts': 10,
        }

        start = time.perf_counter()
        try:
            async with self.session.post(
                f'{GRAPHITI_API_URL}/search',
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                latency_ms = (time.perf_counter() - start) * 1000
                if resp.status == 200:
                    data = await resp.json()
                    result_count = len(data.get('edges', []))
                    return True, latency_ms, result_count
                else:
                    error = await resp.text()
                    self.errors.append(f'Search error {resp.status}: {error[:200]}')
                    return False, latency_ms, 0
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            self.errors.append(f'Search exception: {str(e)[:200]}')
            return False, latency_ms, 0

    async def get_queue_depth(self) -> int:
        """Get current queue depth"""
        if self.session is None:
            return -1
        try:
            async with self.session.get(
                f'{QUEUE_API_URL}/queue/ingestion/metrics', timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('visible', 0) + data.get('invisible', 0)
        except Exception:
            pass
        return -1

    async def get_workflow_count(self) -> int:
        """Get count of running Temporal workflows"""
        if self.session is None:
            return -1
        try:
            # Query Temporal for running workflows
            async with self.session.get(
                f'{TEMPORAL_API_URL}/api/v1/namespaces/graphiti/workflows?status=RUNNING',
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return len(data.get('executions', []))
        except Exception:
            pass
        return -1

    async def monitor_system(self, stop_event: asyncio.Event, interval: float = 5.0):
        """Background task to monitor system metrics"""
        while not stop_event.is_set():
            queue_depth = await self.get_queue_depth()
            workflow_count = await self.get_workflow_count()

            if queue_depth >= 0:
                self.queue_depths.append(queue_depth)
            if workflow_count >= 0:
                self.workflow_counts.append(workflow_count)

            logger.debug(f'Queue depth: {queue_depth}, Workflows: {workflow_count}')

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def run_ingestion_test(
        self, rate_per_minute: float, duration_minutes: float, warmup_seconds: float = 10.0
    ) -> StressTestResult:
        """Run ingestion stress test at specified rate"""
        logger.info(
            f'Starting ingestion test: {rate_per_minute} eps/min for {duration_minutes} min'
        )

        started_at = datetime.now(timezone.utc)
        stop_event = asyncio.Event()

        # Start monitoring
        monitor_task = asyncio.create_task(self.monitor_system(stop_event))

        # Calculate interval between episodes
        interval_seconds = 60.0 / rate_per_minute
        total_episodes = int(rate_per_minute * duration_minutes)

        episodes_submitted = 0
        episodes_succeeded = 0
        episodes_failed = 0

        # Warmup
        logger.info(f'Warmup: {warmup_seconds}s')
        await asyncio.sleep(warmup_seconds)

        # Main test loop
        test_start = time.perf_counter()

        for i in range(total_episodes):
            loop_start = time.perf_counter()

            success, latency_ms = await self.submit_episode()
            episodes_submitted += 1

            if success:
                episodes_succeeded += 1
                self.ingestion_latency.add(latency_ms)
            else:
                episodes_failed += 1

            # Progress logging
            if (i + 1) % 10 == 0:
                elapsed = time.perf_counter() - test_start
                actual_rate = episodes_submitted / (elapsed / 60) if elapsed > 0 else 0
                logger.info(
                    f'Progress: {episodes_submitted}/{total_episodes} episodes, '
                    f'rate: {actual_rate:.1f}/min, '
                    f'success: {episodes_succeeded}, failed: {episodes_failed}'
                )

            # Rate limiting
            elapsed_this_loop = time.perf_counter() - loop_start
            sleep_time = max(0, interval_seconds - elapsed_this_loop)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        # Stop monitoring
        stop_event.set()
        await monitor_task

        ended_at = datetime.now(timezone.utc)
        total_duration = (ended_at - started_at).total_seconds()

        return StressTestResult(
            test_type='ingestion',
            started_at=started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            duration_seconds=total_duration,
            episodes_submitted=episodes_submitted,
            episodes_succeeded=episodes_succeeded,
            episodes_failed=episodes_failed,
            ingestion_latency=self.ingestion_latency.get_stats(),
            actual_ingest_rate=episodes_submitted / (total_duration / 60)
            if total_duration > 0
            else 0,
            queue_depth_samples=self.queue_depths,
            workflow_count_samples=self.workflow_counts,
            errors=self.errors[:50],  # Limit errors
        )

    async def run_search_test(
        self, qps: float, duration_minutes: float, warmup_seconds: float = 5.0
    ) -> StressTestResult:
        """Run search latency test at specified QPS"""
        logger.info(f'Starting search test: {qps} qps for {duration_minutes} min')

        started_at = datetime.now(timezone.utc)
        stop_event = asyncio.Event()

        # Start monitoring
        monitor_task = asyncio.create_task(self.monitor_system(stop_event))

        # Calculate interval between searches
        interval_seconds = 1.0 / qps
        total_searches = int(qps * 60 * duration_minutes)

        searches_submitted = 0
        searches_succeeded = 0
        searches_failed = 0
        total_results = 0

        # Warmup
        logger.info(f'Warmup: {warmup_seconds}s')
        await asyncio.sleep(warmup_seconds)

        # Main test loop
        test_start = time.perf_counter()

        for i in range(total_searches):
            loop_start = time.perf_counter()

            query = random.choice(SAMPLE_QUERIES)
            success, latency_ms, result_count = await self.search_memory(query)
            searches_submitted += 1

            if success:
                searches_succeeded += 1
                self.search_latency.add(latency_ms)
                total_results += result_count
            else:
                searches_failed += 1

            # Progress logging
            if (i + 1) % 50 == 0:
                elapsed = time.perf_counter() - test_start
                actual_qps = searches_submitted / elapsed if elapsed > 0 else 0
                stats = self.search_latency.get_stats()
                logger.info(
                    f'Progress: {searches_submitted}/{total_searches} searches, '
                    f'qps: {actual_qps:.1f}, p50: {stats["p50"]:.1f}ms, p99: {stats["p99"]:.1f}ms'
                )

            # Rate limiting
            elapsed_this_loop = time.perf_counter() - loop_start
            sleep_time = max(0, interval_seconds - elapsed_this_loop)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

        # Stop monitoring
        stop_event.set()
        await monitor_task

        ended_at = datetime.now(timezone.utc)
        total_duration = (ended_at - started_at).total_seconds()

        return StressTestResult(
            test_type='search',
            started_at=started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            duration_seconds=total_duration,
            searches_submitted=searches_submitted,
            searches_succeeded=searches_succeeded,
            searches_failed=searches_failed,
            search_latency=self.search_latency.get_stats(),
            actual_search_rate=searches_submitted / total_duration if total_duration > 0 else 0,
            queue_depth_samples=self.queue_depths,
            workflow_count_samples=self.workflow_counts,
            errors=self.errors[:50],
        )

    async def run_mixed_test(
        self, ingest_rate: float, search_qps: float, duration_minutes: float
    ) -> StressTestResult:
        """Run mixed workload test with concurrent ingestion and search"""
        logger.info(
            f'Starting mixed test: {ingest_rate} eps/min + {search_qps} qps '
            f'for {duration_minutes} min'
        )

        started_at = datetime.now(timezone.utc)
        stop_event = asyncio.Event()

        # Start monitoring
        monitor_task = asyncio.create_task(self.monitor_system(stop_event))

        # Run ingestion and search concurrently
        async def ingest_worker():
            nonlocal episodes_submitted, episodes_succeeded, episodes_failed
            interval = 60.0 / ingest_rate
            end_time = time.perf_counter() + (duration_minutes * 60)

            while time.perf_counter() < end_time:
                loop_start = time.perf_counter()
                success, latency_ms = await self.submit_episode()
                episodes_submitted += 1
                if success:
                    episodes_succeeded += 1
                    self.ingestion_latency.add(latency_ms)
                else:
                    episodes_failed += 1

                elapsed = time.perf_counter() - loop_start
                await asyncio.sleep(max(0, interval - elapsed))

        async def search_worker():
            nonlocal searches_submitted, searches_succeeded, searches_failed
            interval = 1.0 / search_qps
            end_time = time.perf_counter() + (duration_minutes * 60)

            while time.perf_counter() < end_time:
                loop_start = time.perf_counter()
                query = random.choice(SAMPLE_QUERIES)
                success, latency_ms, _ = await self.search_memory(query)
                searches_submitted += 1
                if success:
                    searches_succeeded += 1
                    self.search_latency.add(latency_ms)
                else:
                    searches_failed += 1

                elapsed = time.perf_counter() - loop_start
                await asyncio.sleep(max(0, interval - elapsed))

        episodes_submitted = 0
        episodes_succeeded = 0
        episodes_failed = 0
        searches_submitted = 0
        searches_succeeded = 0
        searches_failed = 0

        # Run both workers
        await asyncio.gather(ingest_worker(), search_worker())

        # Stop monitoring
        stop_event.set()
        await monitor_task

        ended_at = datetime.now(timezone.utc)
        total_duration = (ended_at - started_at).total_seconds()

        return StressTestResult(
            test_type='mixed',
            started_at=started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            duration_seconds=total_duration,
            episodes_submitted=episodes_submitted,
            episodes_succeeded=episodes_succeeded,
            episodes_failed=episodes_failed,
            ingestion_latency=self.ingestion_latency.get_stats(),
            actual_ingest_rate=episodes_submitted / (total_duration / 60)
            if total_duration > 0
            else 0,
            searches_submitted=searches_submitted,
            searches_succeeded=searches_succeeded,
            searches_failed=searches_failed,
            search_latency=self.search_latency.get_stats(),
            actual_search_rate=searches_submitted / total_duration if total_duration > 0 else 0,
            queue_depth_samples=self.queue_depths,
            workflow_count_samples=self.workflow_counts,
            errors=self.errors[:50],
        )


def print_results(result: StressTestResult):
    """Pretty print test results"""
    print('\n' + '=' * 60)
    print(f'STRESS TEST RESULTS: {result.test_type.upper()}')
    print('=' * 60)
    print(f'Duration: {result.duration_seconds:.1f}s')
    print(f'Started: {result.started_at}')
    print(f'Ended: {result.ended_at}')

    if result.episodes_submitted > 0:
        print(f'\n--- INGESTION ---')
        print(f'Episodes submitted: {result.episodes_submitted}')
        print(f'Episodes succeeded: {result.episodes_succeeded}')
        print(f'Episodes failed: {result.episodes_failed}')
        print(f'Success rate: {result.episodes_succeeded / result.episodes_submitted * 100:.1f}%')
        print(f'Actual rate: {result.actual_ingest_rate:.2f} eps/min')

        lat = result.ingestion_latency
        if lat.get('count', 0) > 0:
            print(
                f'Latency (ms): p50={lat["p50"]:.1f}, p95={lat["p95"]:.1f}, p99={lat["p99"]:.1f}, max={lat["max"]:.1f}'
            )

    if result.searches_submitted > 0:
        print(f'\n--- SEARCH ---')
        print(f'Searches submitted: {result.searches_submitted}')
        print(f'Searches succeeded: {result.searches_succeeded}')
        print(f'Searches failed: {result.searches_failed}')
        print(f'Success rate: {result.searches_succeeded / result.searches_submitted * 100:.1f}%')
        print(f'Actual rate: {result.actual_search_rate:.2f} qps')

        lat = result.search_latency
        if lat.get('count', 0) > 0:
            print(
                f'Latency (ms): p50={lat["p50"]:.1f}, p95={lat["p95"]:.1f}, p99={lat["p99"]:.1f}, max={lat["max"]:.1f}'
            )

    if result.queue_depth_samples:
        avg_depth = statistics.mean(result.queue_depth_samples)
        max_depth = max(result.queue_depth_samples)
        print(f'\n--- QUEUE ---')
        print(f'Avg depth: {avg_depth:.1f}')
        print(f'Max depth: {max_depth}')

    if result.errors:
        print(f'\n--- ERRORS ({len(result.errors)} total) ---')
        for err in result.errors[:5]:
            print(f'  - {err}')
        if len(result.errors) > 5:
            print(f'  ... and {len(result.errors) - 5} more')

    print('=' * 60)


async def main():
    parser = argparse.ArgumentParser(description='Graphiti Memory System Stress Tester')
    subparsers = parser.add_subparsers(dest='command', help='Test type')

    # Ingestion test
    ingest_parser = subparsers.add_parser('ingest', help='Run ingestion stress test')
    ingest_parser.add_argument('--rate', type=float, default=10, help='Episodes per minute')
    ingest_parser.add_argument('--duration', type=float, default=5, help='Duration in minutes')
    ingest_parser.add_argument(
        '--group-id', default='stress-test-ingest', help='Group ID for episodes'
    )
    ingest_parser.add_argument('--output', help='Output file for results (JSON)')

    # Search test
    search_parser = subparsers.add_parser('search', help='Run search latency test')
    search_parser.add_argument('--qps', type=float, default=5, help='Queries per second')
    search_parser.add_argument('--duration', type=float, default=2, help='Duration in minutes')
    search_parser.add_argument(
        '--group-id', default='stress-test-search', help='Group ID to search'
    )
    search_parser.add_argument('--output', help='Output file for results (JSON)')

    # Mixed test
    mixed_parser = subparsers.add_parser('mixed', help='Run mixed workload test')
    mixed_parser.add_argument('--ingest-rate', type=float, default=5, help='Episodes per minute')
    mixed_parser.add_argument('--search-qps', type=float, default=3, help='Searches per second')
    mixed_parser.add_argument('--duration', type=float, default=5, help='Duration in minutes')
    mixed_parser.add_argument('--group-id', default='stress-test-mixed', help='Group ID')
    mixed_parser.add_argument('--output', help='Output file for results (JSON)')

    # Full test
    full_parser = subparsers.add_parser('full', help='Run comprehensive stress test suite')
    full_parser.add_argument('--output', default='stress_report.json', help='Output file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'ingest':
        async with StressTester(group_id=args.group_id) as tester:
            result = await tester.run_ingestion_test(
                rate_per_minute=args.rate, duration_minutes=args.duration
            )
            print_results(result)
            if args.output:
                Path(args.output).write_text(json.dumps(result.to_dict(), indent=2))
                print(f'\nResults saved to: {args.output}')

    elif args.command == 'search':
        async with StressTester(group_id=args.group_id) as tester:
            result = await tester.run_search_test(qps=args.qps, duration_minutes=args.duration)
            print_results(result)
            if args.output:
                Path(args.output).write_text(json.dumps(result.to_dict(), indent=2))
                print(f'\nResults saved to: {args.output}')

    elif args.command == 'mixed':
        async with StressTester(group_id=args.group_id) as tester:
            result = await tester.run_mixed_test(
                ingest_rate=args.ingest_rate,
                search_qps=args.search_qps,
                duration_minutes=args.duration,
            )
            print_results(result)
            if args.output:
                Path(args.output).write_text(json.dumps(result.to_dict(), indent=2))
                print(f'\nResults saved to: {args.output}')

    elif args.command == 'full':
        print('Running full stress test suite...')
        all_results = []

        # Test 1: Light ingestion
        print('\n[1/4] Light ingestion test (5 eps/min, 2 min)')
        async with StressTester(group_id='stress-test-1') as tester:
            result = await tester.run_ingestion_test(rate_per_minute=5, duration_minutes=2)
            print_results(result)
            all_results.append({'test': 'light_ingest', **result.to_dict()})

        # Test 2: Heavy ingestion
        print('\n[2/4] Heavy ingestion test (20 eps/min, 2 min)')
        async with StressTester(group_id='stress-test-2') as tester:
            result = await tester.run_ingestion_test(rate_per_minute=20, duration_minutes=2)
            print_results(result)
            all_results.append({'test': 'heavy_ingest', **result.to_dict()})

        # Test 3: Search under load
        print('\n[3/4] Search test (10 qps, 1 min)')
        async with StressTester(group_id='stress-test-3') as tester:
            result = await tester.run_search_test(qps=10, duration_minutes=1)
            print_results(result)
            all_results.append({'test': 'search', **result.to_dict()})

        # Test 4: Mixed workload
        print('\n[4/4] Mixed workload (10 eps/min + 5 qps, 2 min)')
        async with StressTester(group_id='stress-test-4') as tester:
            result = await tester.run_mixed_test(ingest_rate=10, search_qps=5, duration_minutes=2)
            print_results(result)
            all_results.append({'test': 'mixed', **result.to_dict()})

        # Save full report
        report = {
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'tests': all_results,
        }
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f'\n{"=" * 60}')
        print(f'Full report saved to: {args.output}')
        print(f'{"=" * 60}')


if __name__ == '__main__':
    asyncio.run(main())
