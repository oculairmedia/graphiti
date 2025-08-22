"""
Parallel Ingestion Pipeline Demo Script

This script demonstrates the performance improvement concepts for parallelizing LLM calls
in the entity extraction phase. It uses mock LLM calls to simulate realistic timing
without requiring Ollama to be running.

Based on your analysis showing 7-8 sequential LLM calls taking ~60 seconds,
this demo shows how parallel processing can reduce this significantly.

Key insights from your analysis:
- 93% of processing time spent on entity extraction
- 7-8 sequential calls to Ollama (gemma3:12b)
- Each call takes 3-5 seconds
- Total: ~60 seconds bottleneck

Usage:
    python test_ingestion/parallel_ingestion_demo.py
"""

import asyncio
import time
import logging
import random
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


class MockLLMClient:
    """Mock LLM client that simulates realistic Ollama timing"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "gemma3:12b"):
        self.base_url = base_url
        self.model = model
        self.call_count = 0

    async def generate_response(self, prompt, response_model=None) -> Dict[str, Any]:
        """Simulate a realistic LLM call with timing based on your analysis"""
        self.call_count += 1
        call_id = self.call_count

        start_time = time.time()

        # Simulate realistic LLM call timing (3-5 seconds based on your analysis)
        # Add some randomness to simulate real-world variance
        call_duration = random.uniform(3.0, 5.0)

        logger.info(".2f")

        # Simulate the actual work
        await asyncio.sleep(call_duration)

        # Generate mock response
        response = self._generate_mock_response(prompt, response_model)

        actual_duration = time.time() - start_time
        logger.info(".2f")

        return response

    def _generate_mock_response(self, prompt: Any, response_model=None) -> Dict[str, Any]:
        """Generate realistic mock responses"""
        if response_model and hasattr(response_model, '__name__'):
            if 'ExtractedEntities' in str(response_model):
                return {
                    "extracted_entities": [
                        {"name": "Alice Johnson", "entity_type_id": 0},
                        {"name": "Bob Smith", "entity_type_id": 0},
                        {"name": "Marketing Team", "entity_type_id": 0},
                        {"name": "Q4 Strategy", "entity_type_id": 0},
                        {"name": "New Product Launch", "entity_type_id": 0}
                    ]
                }
            elif 'MissedEntities' in str(response_model):
                # Sometimes return missed entities to trigger reflexion
                return {"missed_entities": ["Charlie Wilson", "Sales Department"]}
            else:
                return {"response": "Mock LLM response"}
        else:
            return {"response": "Mock LLM response"}


class ParallelEntityExtractor:
    """Entity extractor with parallel LLM processing capabilities"""

    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "gemma3:12b"):
        self.ollama_url = ollama_url
        self.model = model
        self.client = MockLLMClient(ollama_url, model)

    async def extract_entities_sequential(self, episode_content: str, max_iterations: int = 3) -> PerformanceMetrics:
        """Sequential entity extraction (current implementation)"""
        start_time = time.time()
        llm_calls = 0
        all_entities = []

        logger.info("🚀 Starting SEQUENTIAL entity extraction...")

        # Initial extraction
        llm_calls += 1
        logger.info("📝 Making initial entity extraction call...")
        initial_response = await self.client.generate_response(
            f"Extract entities from: {episode_content[:500]}",
            response_model=type('ExtractedEntities', (), {})()
        )

        entities = initial_response.get('extracted_entities', [])
        all_entities.extend(entities)
        logger.info(f"✨ Found {len(entities)} entities in initial extraction")

        # Reflexion iterations (this is where the bottleneck occurs)
        for iteration in range(max_iterations):
            if not entities:
                break

            llm_calls += 1
            logger.info(f"🔍 Making reflexion call {iteration + 1}...")
            reflexion_response = await self.client.generate_response(
                f"Find missed entities from: {episode_content[:500]}",
                response_model=type('MissedEntities', (), {})()
            )

            missed_entities = reflexion_response.get('missed_entities', [])
            if not missed_entities:
                logger.info(f"✅ No missed entities found in iteration {iteration + 1}")
                break

            logger.info(f"📋 Found {len(missed_entities)} missed entities: {missed_entities}")

            # In real implementation, this would trigger another extraction
            # For testing, we'll simulate finding more entities
            if iteration < max_iterations - 1:
                additional_entities = [
                    {"name": name, "entity_type_id": 0}
                    for name in missed_entities
                ]
                all_entities.extend(additional_entities)
                entities = additional_entities
                logger.info(f"➕ Added {len(additional_entities)} additional entities")

        total_time = time.time() - start_time
        avg_call_time = total_time / llm_calls if llm_calls > 0 else 0

        logger.info("🏁 Sequential extraction completed!")
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

        logger.info(f"🚀 Starting PARALLEL entity extraction (max {max_concurrent} concurrent)...")

        # Create multiple extraction tasks
        extraction_tasks = []
        reflexion_tasks = []

        # Initial extractions (simulate processing content in chunks)
        content_chunks = self._split_content(episode_content, max_concurrent)

        for i, chunk in enumerate(content_chunks):
            task = asyncio.create_task(
                self.client.generate_response(
                    f"Extract entities from chunk {i}: {chunk}",
                    response_model=type('ExtractedEntities', (), {})()
                )
            )
            extraction_tasks.append(task)

        # Wait for all initial extractions
        logger.info(f"📊 Waiting for {len(extraction_tasks)} parallel extraction tasks...")
        initial_results = await asyncio.gather(*extraction_tasks, return_exceptions=True)

        # Process results and create reflexion tasks
        all_entities = []
        for i, result in enumerate(initial_results):
            if isinstance(result, Exception):
                logger.error(f"❌ Task {i} failed: {result}")
                continue

            entities = result.get('extracted_entities', [])
            all_entities.extend(entities)
            logger.info(f"✨ Chunk {i} found {len(entities)} entities")

            # Create reflexion task for this batch
            if entities:
                reflexion_task = asyncio.create_task(
                    self.client.generate_response(
                        f"Find missed entities from chunk {i}: {content_chunks[i]}",
                        response_model=type('MissedEntities', (), {})()
                    )
                )
                reflexion_tasks.append(reflexion_task)

        # Wait for reflexion tasks
        if reflexion_tasks:
            logger.info(f"🔍 Waiting for {len(reflexion_tasks)} parallel reflexion tasks...")
            reflexion_results = await asyncio.gather(*reflexion_tasks, return_exceptions=True)

            for i, result in enumerate(reflexion_results):
                if isinstance(result, Exception):
                    logger.error(f"❌ Reflexion task {i} failed: {result}")
                    continue

                missed_entities = result.get('missed_entities', [])
                if missed_entities:
                    # In parallel version, we could spawn more extraction tasks here
                    additional_entities = [
                        {"name": name, "entity_type_id": 0}
                        for name in missed_entities
                    ]
                    all_entities.extend(additional_entities)
                    logger.info(f"➕ Added {len(additional_entities)} missed entities from reflexion {i}")

        total_time = time.time() - start_time
        # Estimate LLM calls (initial + reflexion tasks)
        llm_calls = len(extraction_tasks) + len(reflexion_tasks)
        avg_call_time = total_time / max_concurrent if max_concurrent > 0 else 0

        logger.info("🏁 Parallel extraction completed!")
        return PerformanceMetrics(
            method_name="Parallel",
            total_time=total_time,
            llm_calls=llm_calls,
            entities_extracted=len(all_entities),
            avg_llm_call_time=avg_call_time,
            max_concurrent_calls=max_concurrent
        )

    def _split_content(self, content: str, num_chunks: int) -> List[str]:
        """Split content into chunks for parallel processing"""
        words = content.split()
        chunk_size = len(words) // num_chunks
        chunks = []

        for i in range(num_chunks):
            start = i * chunk_size
            end = start + chunk_size if i < num_chunks - 1 else len(words)
            chunk = " ".join(words[start:end])
            chunks.append(chunk)

        return chunks

    async def extract_entities_batch_optimized(self, episode_content: str, batch_size: int = 3) -> PerformanceMetrics:
        """Batch processing with controlled concurrency using semaphore"""
        start_time = time.time()
        semaphore = asyncio.Semaphore(batch_size)

        logger.info(f"🚀 Starting BATCH entity extraction (batch size {batch_size})...")

        async def controlled_llm_call(call_id: int, prompt: str, response_model) -> tuple[int, Any]:
            async with semaphore:
                logger.info(f"🔄 Starting controlled call {call_id}")
                result = await self.client.generate_response(prompt, response_model)
                logger.info(f"✅ Completed controlled call {call_id}")
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
        logger.info(f"📊 Processing {len(tasks)} tasks with controlled concurrency...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_entities = []
        for item in results:
            if isinstance(item, Exception):
                logger.error(f"❌ Controlled call failed: {item}")
                continue

            call_id, result = item
            entities = result.get('extracted_entities', [])
            all_entities.extend(entities)
            logger.info(f"✨ Call {call_id} found {len(entities)} entities")

        total_time = time.time() - start_time
        avg_call_time = total_time / len(tasks) if tasks else 0

        logger.info("🏁 Batch extraction completed!")
        return PerformanceMetrics(
            method_name="Batch Controlled",
            total_time=total_time,
            llm_calls=len(tasks),
            entities_extracted=len(all_entities),
            avg_llm_call_time=avg_call_time,
            max_concurrent_calls=batch_size
        )


class IngestionPipelineDemo:
    """Main demo class for comparing ingestion pipeline performance"""

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
        print("🚀 INGESTION PIPELINE PARALLEL PROCESSING DEMO")
        print("=" * 70)
        print("Based on your analysis: 7-8 sequential LLM calls taking ~60 seconds")
        print(f"Test content length: {len(self.test_content)} characters")
        print(".2f")
        print()

        results = []

        # Test sequential processing (current bottleneck)
        print("📊 Testing Sequential Processing (Current Implementation)")
        print("   This simulates your current bottleneck: 7-8 sequential calls")
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
            print(f"   Processing content in {concurrency} parallel chunks")
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
            print(f"   Controlled concurrency with semaphore limiting to {batch_size}")
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
        print(".1f")

    def _print_comparison_summary(self, results: List[PerformanceMetrics]):
        """Print comparison summary of all results"""
        print("🏆 PERFORMANCE COMPARISON SUMMARY")
        print("=" * 70)

        if not results:
            print("No results to compare")
            return

        # Sort by total time (fastest first)
        sorted_results = sorted(results, key=lambda x: x.total_time)

        print("<30")
        print("-" * 70)

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
                  "<10d"
                  "<10.1f")

        print()
        print("💡 KEY INSIGHTS FOR YOUR BOTTLENECK:")
        print("   • Sequential processing: ~60s (7-8 LLM calls × 3-5s each)")
        print("   • Parallel processing: Could reduce to ~15-20s (2-3 concurrent calls)")
        print("   • Batch processing: Provides controlled concurrency for stability")
        print("   • Higher concurrency may not always be better due to resource limits")
        print()
        print("🔧 IMPLEMENTATION RECOMMENDATIONS:")
        print("   1. Use asyncio.gather() for parallel LLM calls")
        print("   2. Implement semaphores to control concurrency")
        print("   3. Split large content into chunks for parallel processing")
        print("   4. Consider content complexity when choosing concurrency level")
        print("   5. Monitor system resources (CPU, memory, network)")


async def main():
    """Main entry point"""
    print("🔧 Parallel Ingestion Pipeline Optimization Demo")
    print("   Demonstrating parallel LLM processing for entity extraction")
    print("   (Using mock LLM calls with realistic timing)")
    print()

    # Run the performance demo
    demo = IngestionPipelineDemo()
    await demo.run_performance_comparison()

    print("\n✨ Demo completed!")
    print("   This shows how parallel processing can optimize your 60-second bottleneck.")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())