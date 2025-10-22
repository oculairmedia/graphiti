"""
Parallel Ingestion Pipeline Test Script - Fixed Version

This script demonstrates the performance improvement of parallelizing LLM calls
in the entity extraction phase, which is currently the main bottleneck in the
ingestion pipeline (taking ~60 seconds with 7-8 sequential calls).

The script compares:
1. Sequential processing (current implementation)
2. Parallel processing with asyncio.gather
3. Batch processing with controlled concurrency

Usage:
    python test_ingestion/parallel_ingestion_test_fixed.py

Requirements:
    - Ollama running locally with gemma3:12b model
    - graphiti_core dependencies
"""

import asyncio
import time
import logging
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Track performance metrics for different processing methods"""
    method_name: str
    total_time: float
    llm_calls: int
    entities_extracted: int
    avg_llm_call_time: float
    max_concurrent_calls: int = 1


class OllamaLLMClient:
    """Simplified Ollama client for testing parallel processing"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma3:12b"):
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.session = None

    async def __aenter__(self):
        import aiohttp
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def generate_response(self, prompt, response_model=None) -> Dict[str, Any]:
        """Make a single LLM call to Ollama"""
        import aiohttp

        if not self.session:
            raise RuntimeError("Client not initialized. Use with 'async with' context manager.")

        start_time = time.time()

        # Convert prompt to string if it's a list of Messages
        if hasattr(prompt, '__iter__') and not isinstance(prompt, str):
            # Convert list of messages to string
            prompt_text = ""
            for msg in prompt:
                if hasattr(msg, 'content'):
                    prompt_text += msg.content + "\n"
                else:
                    prompt_text += str(msg) + "\n"
        else:
            prompt_text = str(prompt)

        payload = {
            "model": self.model,
            "prompt": prompt_text,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 1000
            }
        }

        try:
            async with self.session.post(f"{self.base_url}/api/generate", json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                result = await response.json()
                call_time = time.time() - start_time

                logger.info(".2f")

                # Parse the response as JSON (assuming structured output)
                try:
                    content = result.get('response', '{}')
                    # Try to extract JSON from the response
                    if response_model and hasattr(response_model, '__name__'):
                        if 'ExtractedEntities' in str(response_model):
                            # Mock response for testing - in real implementation this would be parsed properly
                            return {
                                "extracted_entities": [
                                    {"name": "Test Entity 1", "entity_type_id": 0},
                                    {"name": "Test Entity 2", "entity_type_id": 0}
                                ]
                            }
                        elif 'MissedEntities' in str(response_model):
                            return {"missed_entities": []}
                        else:
                            return json.loads(content) if isinstance(content, str) else content
                    else:
                        return json.loads(content) if isinstance(content, str) else content

                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON response: {content}")
                    if response_model and 'ExtractedEntities' in str(response_model):
                        return {"extracted_entities": []}
                    else:
                        return {}

        except Exception as e:
            call_time = time.time() - start_time
            logger.error(".2f")
            raise


class ParallelEntityExtractor:
    """Entity extractor with parallel LLM processing capabilities"""

    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "gemma3:12b"):
        self.ollama_url = ollama_url
        self.model = model

    async def extract_entities_sequential(self, episode_content: str, max_iterations: int = 3) -> PerformanceMetrics:
        """Sequential entity extraction (current implementation)"""
        start_time = time.time()
        llm_calls = 0
        all_entities = []

        async with OllamaLLMClient(self.ollama_url, self.model) as client:
            context = {
                'episode_content': episode_content,
                'episode_timestamp': time.time(),
                'previous_episodes': [],
                'custom_prompt': '',
                'entity_types': [{'entity_type_id': 0, 'entity_type_name': 'Entity', 'entity_type_description': 'Default entity'}],
                'source_description': 'Test message'
            }

            # Initial extraction
            llm_calls += 1
            initial_response = await client.generate_response(
                f"Extract entities from: {episode_content[:500]}",  # Simplified prompt for testing
                response_model=type('ExtractedEntities', (), {})()
            )

            entities = [{"name": "Test Entity 1", "entity_type_id": 0}, {"name": "Test Entity 2", "entity_type_id": 0}]
            all_entities.extend(entities)

            # Reflexion iterations
            for iteration in range(max_iterations):
                if not entities:
                    break

                llm_calls += 1
                reflexion_response = await client.generate_response(
                    f"Find missed entities from: {episode_content[:500]}",  # Simplified prompt for testing
                    response_model=type('MissedEntities', (), {})()
                )

                missed_entities = []
                if not missed_entities:
                    break

                # In real implementation, this would trigger another extraction
                # For testing, we'll simulate finding more entities
                if iteration < max_iterations - 1:
                    additional_entities = [
                        {"name": f"Additional entity {iteration}", "entity_type_id": 0}
                        for _ in range(2)  # Limit for testing
                    ]
                    all_entities.extend(additional_entities)
                    entities = additional_entities

        total_time = time.time() - start_time
        avg_call_time = total_time / llm_calls if llm_calls > 0 else 0

        return PerformanceMetrics(
            method_name="Sequential",
            total_time=total_time,
            llm_calls=llm_calls,
            entities_extracted=len(all_entities),
            avg_llm_call_time=avg_call_time
        )

    async def extract_entities_parallel(self, episode_content: str, max_concurrent: int = 3) -> PerformanceMetrics:
        """Parallel entity extraction with concurrent LLM calls"""
        start_time = time.time()

        async with OllamaLLMClient(self.ollama_url, self.model) as client:
            # Create multiple extraction tasks
            extraction_tasks = []
            reflexion_tasks = []

            # Initial extractions (simulate multiple chunks or different prompts)
            for i in range(max_concurrent):
                task = asyncio.create_task(
                    client.generate_response(
                        f"Extract entities from chunk {i}: {episode_content[:500]}",
                        response_model=type('ExtractedEntities', (), {})()
                    )
                )
                extraction_tasks.append(task)

            # Wait for all initial extractions
            initial_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

            # Process results and create reflexion tasks
            all_entities = []
            for i, result in enumerate(initial_results):
                if isinstance(result, Exception):
                    logger.error(f"Task {i} failed: {result}")
                    continue

                entities = [{"name": f"Entity from task {i}", "entity_type_id": 0}]
                all_entities.extend(entities)

                # Create reflexion task for this batch
                if entities:
                    reflexion_task = asyncio.create_task(
                        client.generate_response(
                            f"Find missed entities from task {i}: {episode_content[:500]}",
                            response_model=type('MissedEntities', (), {})()
                        )
                    )
                    reflexion_tasks.append(reflexion_task)

            # Wait for reflexion tasks
            if reflexion_tasks:
                reflexion_results = await asyncio.gather(*reflexion_tasks, return_exceptions=True)

                for i, result in enumerate(reflexion_results):
                    if isinstance(result, Exception):
                        logger.error(f"Reflexion task {i} failed: {result}")
                        continue

                    missed_entities = []
                    if missed_entities:
                        # In parallel version, we could spawn more extraction tasks here
                        # For testing, we'll add simulated entities
                        additional_entities = [
                            {"name": f"Parallel entity {i}", "entity_type_id": 0}
                            for _ in range(2)
                        ]
                        all_entities.extend(additional_entities)

        total_time = time.time() - start_time
        # Estimate LLM calls (initial + reflexion tasks)
        llm_calls = len(extraction_tasks) + len(reflexion_tasks)
        avg_call_time = total_time / max_concurrent if max_concurrent > 0 else 0

        return PerformanceMetrics(
            method_name="Parallel",
            total_time=total_time,
            llm_calls=llm_calls,
            entities_extracted=len(all_entities),
            avg_llm_call_time=avg_call_time,
            max_concurrent_calls=max_concurrent
        )

    async def extract_entities_batch_optimized(self, episode_content: str, batch_size: int = 3) -> PerformanceMetrics:
        """Batch processing with controlled concurrency using semaphore"""
        start_time = time.time()
        semaphore = asyncio.Semaphore(batch_size)

        async with OllamaLLMClient(self.ollama_url, self.model) as client:
            async def controlled_llm_call(call_id: int, prompt: str, response_model) -> tuple[int, Any]:
                async with semaphore:
                    logger.info(f"Starting controlled call {call_id}")
                    result = await client.generate_response(prompt, response_model)
                    logger.info(f"Completed controlled call {call_id}")
                    return call_id, result

            # Create batch of controlled tasks
            tasks = []
            for i in range(5):  # Simulate 5 LLM calls that would happen in sequential processing
                task = asyncio.create_task(
                    controlled_llm_call(
                        i,
                        f"Extract entities batch {i}: {episode_content[:500]}",
                        type('ExtractedEntities', (), {})()
                    )
                )
                tasks.append(task)

            # Wait for all tasks with controlled concurrency
            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_entities = []
            for call_id, result in results:
                if isinstance(result, Exception):
                    logger.error(f"Controlled call {call_id} failed: {result}")
                    continue

                entities = [{"name": f"Entity from call {call_id}", "entity_type_id": 0}]
                all_entities.extend(entities)

        total_time = time.time() - start_time
        avg_call_time = total_time / len(tasks) if tasks else 0

        return PerformanceMetrics(
            method_name="Batch Controlled",
            total_time=total_time,
            llm_calls=len(tasks),
            entities_extracted=len(all_entities),
            avg_llm_call_time=avg_call_time,
            max_concurrent_calls=batch_size
        )


class IngestionPipelineTest:
    """Main test class for comparing ingestion pipeline performance"""

    def __init__(self):
        self.test_content = self._generate_test_content()
        self.extractor = ParallelEntityExtractor()

    def _generate_test_content(self) -> str:
        """Generate test content similar to what causes the bottleneck"""
        return """
        In today's team meeting, Alice Johnson from marketing presented the Q4 strategy update.
        She discussed the new product launch timeline with Bob Smith, the engineering lead.
        Charlie Wilson from sales provided insights about customer feedback and market trends.
        The team also discussed integration with the new API developed by David Brown and his team.
        Emma Davis suggested improvements to the user interface based on recent user testing.
        Frank Miller outlined the budget requirements for the next quarter's initiatives.
        The meeting concluded with action items assigned to various team members including
        follow-ups with stakeholders and preparation for the upcoming conference in New York.
        Additional topics included supply chain optimization and partnership opportunities with
        several technology vendors including Microsoft, Google, and Amazon Web Services.
        """ * 3  # Make it longer to simulate real content

    async def run_performance_comparison(self):
        """Run performance comparison between sequential and parallel processing"""
        print("🚀 Starting Ingestion Pipeline Performance Test")
        print("=" * 60)
        print(f"Test content length: {len(self.test_content)} characters")
        print()

        results = []

        # Test sequential processing
        print("📊 Testing Sequential Processing (Current Implementation)")
        try:
            sequential_result = await self.extractor.extract_entities_sequential(self.test_content)
            results.append(sequential_result)
            self._print_metrics(sequential_result)
        except Exception as e:
            print(f"❌ Sequential test failed: {e}")
            logger.exception("Sequential test error")

        print()

        # Test parallel processing with different concurrency levels
        for concurrency in [2, 3, 5]:
            print(f"⚡ Testing Parallel Processing (Max {concurrency} concurrent)")
            try:
                parallel_result = await self.extractor.extract_entities_parallel(
                    self.test_content,
                    max_concurrent=concurrency
                )
                results.append(parallel_result)
                self._print_metrics(parallel_result)
            except Exception as e:
                print(f"❌ Parallel test (concurrency={concurrency}) failed: {e}")
                logger.exception(f"Parallel test error (concurrency={concurrency})")
            print()

        # Test batch processing
        for batch_size in [2, 3, 4]:
            print(f"📦 Testing Batch Processing (Batch size {batch_size})")
            try:
                batch_result = await self.extractor.extract_entities_batch_optimized(
                    self.test_content,
                    batch_size=batch_size
                )
                results.append(batch_result)
                self._print_metrics(batch_result)
            except Exception as e:
                print(f"❌ Batch test (batch_size={batch_size}) failed: {e}")
                logger.exception(f"Batch test error (batch_size={batch_size})")
            print()

        # Print comparison summary
        self._print_comparison_summary(results)

    def _print_metrics(self, metrics: PerformanceMetrics):
        """Print formatted metrics"""
        print(f"  Method: {metrics.method_name}")
        print(".2f")
        print(f"  LLM Calls: {metrics.llm_calls}")
        print(f"  Entities Extracted: {metrics.entities_extracted}")
        print(".2f")
        print(f"  Max Concurrent: {metrics.max_concurrent_calls}")
        print(".2f")

    def _print_comparison_summary(self, results: List[PerformanceMetrics]):
        """Print comparison summary of all results"""
        print("🏆 PERFORMANCE COMPARISON SUMMARY")
        print("=" * 60)

        if not results:
            print("No results to compare")
            return

        # Sort by total time (fastest first)
        sorted_results = sorted(results, key=lambda x: x.total_time)

        print("<30")
        print("-" * 60)

        baseline_time = None
        for i, result in enumerate(sorted_results, 1):
            if i == 1:
                baseline_time = result.total_time
                improvement = 0.0
            else:
                if baseline_time and baseline_time > 0:
                    improvement = (baseline_time - result.total_time) / baseline_time * 100
                else:
                    improvement = 0.0

            print("<30"
                  "<12.2f"
                  "<8d"
                  "<10.2f"
                  "<10d")

        print()
        print("💡 KEY INSIGHTS:")
        print("   - Parallel processing can significantly reduce total processing time")
        print("   - Higher concurrency may not always yield better results due to resource limits")
        print("   - Batch processing with semaphores provides controlled concurrency")
        print("   - Consider system resources (CPU, memory, network) when choosing concurrency level")


async def main():
    """Main entry point"""
    print("🔧 Parallel Ingestion Pipeline Optimization Test")
    print("   Testing parallel LLM processing to optimize entity extraction")
    print()

    # Check if Ollama is available
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:11434/api/tags") as response:
                if response.status == 200:
                    print("✅ Ollama service is available")
                else:
                    print("⚠️  Ollama service responded with status:", response.status)
    except Exception as e:
        print("❌ Cannot connect to Ollama service:", str(e))
        print("   Please ensure Ollama is running with: ollama serve")
        print("   And that gemma3:12b model is available")
        return

    # Run the performance test
    test = IngestionPipelineTest()
    await test.run_performance_comparison()

    print("\n✨ Test completed!")
    print("   Check the logs above for detailed performance metrics.")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())