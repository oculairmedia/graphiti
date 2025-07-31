#!/usr/bin/env python3
"""
Compare different models on the node deduplication task.
Tests both regular and structured output formats.
"""

import asyncio
import os
import sys
import json
from datetime import datetime

# Models to test
MODELS_TO_TEST = [
    "qwen3-30b-a3b:iq4_nl",      # Current model
    "llama3.2:3b",                # Smaller, faster model
    "phi3:medium",                # Microsoft's model, good at structured tasks
    "mistral:7b",                 # Good general purpose
    "qwen2.5:7b",                 # Newer Qwen version
    "gemma2:9b",                  # Google's model
    "deepseek-r1:8b",             # DeepSeek reasoning model
]

async def test_model(model: str):
    """Test a single model with both test scripts"""
    print(f"\n{'='*80}")
    print(f"TESTING MODEL: {model}")
    print(f"{'='*80}")
    
    # Check if model exists
    check_cmd = f"ollama list | grep -q '{model.split(':')[0]}'"
    check_result = os.system(check_cmd)
    
    if check_result != 0:
        print(f"⚠️  Model {model} not found. Pulling...")
        pull_result = os.system(f"ollama pull {model}")
        if pull_result != 0:
            print(f"❌ Failed to pull {model}")
            return None
    
    results = {"model": model}
    
    # Test 1: Regular format
    print(f"\n--- Testing regular format ---")
    os.environ['TEST_MODEL'] = model
    regular_result = os.system("cd /opt/stacks/graphiti/llm_tests && python3 test_node_deduplication.py > /dev/null 2>&1")
    
    # Parse the results file
    try:
        files = [f for f in os.listdir("/opt/stacks/graphiti/llm_tests") if f.startswith(f"dedup_test_results_{model.replace(':', '_')}")]
        if files:
            latest_file = sorted(files)[-1]
            with open(f"/opt/stacks/graphiti/llm_tests/{latest_file}", 'r') as f:
                regular_data = json.load(f)
                results["regular_format"] = {
                    "success": True,
                    "accuracy": sum(r['percentage'] for r in regular_data) / len(regular_data),
                    "bounds_errors": sum(1 for r in regular_data if r.get('has_bounds_errors', False))
                }
    except Exception as e:
        results["regular_format"] = {"success": False, "error": str(e)}
    
    # Test 2: Structured output format
    print(f"\n--- Testing structured output format ---")
    structured_result = os.system("cd /opt/stacks/graphiti/llm_tests && python3 test_dedup_structured_output.py > /dev/null 2>&1")
    
    # Parse the structured results
    try:
        files = [f for f in os.listdir("/opt/stacks/graphiti/llm_tests") if f.startswith(f"structured_dedup_results_{model.replace(':', '_')}")]
        if files:
            latest_file = sorted(files)[-1]
            with open(f"/opt/stacks/graphiti/llm_tests/{latest_file}", 'r') as f:
                structured_data = json.load(f)
                results["structured_format"] = {
                    "success": True,
                    "accuracy": sum(r['percentage'] for r in structured_data['results']) / len(structured_data['results']),
                    "bounds_errors": sum(1 for r in structured_data['results'] if r.get('has_bounds_errors', False))
                }
    except Exception as e:
        results["structured_format"] = {"success": False, "error": str(e)}
    
    return results

async def main():
    print("🔍 Model Comparison for Node Deduplication Task")
    print("=" * 80)
    
    all_results = []
    
    for model in MODELS_TO_TEST:
        result = await test_model(model)
        if result:
            all_results.append(result)
    
    # Print summary
    print(f"\n{'='*80}")
    print("📊 FINAL COMPARISON SUMMARY")
    print(f"{'='*80}")
    print(f"{'Model':<25} {'Regular Format':<20} {'Structured Format':<20} {'Bounds Errors'}")
    print(f"{'-'*25} {'-'*20} {'-'*20} {'-'*15}")
    
    for result in all_results:
        model = result['model']
        
        regular = result.get('regular_format', {})
        if regular.get('success'):
            regular_str = f"{regular['accuracy']:.1f}%"
            regular_bounds = regular.get('bounds_errors', 0)
        else:
            regular_str = "Failed"
            regular_bounds = "N/A"
        
        structured = result.get('structured_format', {})
        if structured.get('success'):
            structured_str = f"{structured['accuracy']:.1f}%"
            structured_bounds = structured.get('bounds_errors', 0)
        else:
            structured_str = "Failed"
            structured_bounds = "N/A"
        
        total_bounds = f"{regular_bounds}/{structured_bounds}" if regular_bounds != "N/A" else "N/A"
        
        print(f"{model:<25} {regular_str:<20} {structured_str:<20} {total_bounds}")
    
    # Save comparison results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    comparison_file = f"/opt/stacks/graphiti/llm_tests/model_comparison_{timestamp}.json"
    with open(comparison_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "models_tested": len(all_results),
            "results": all_results
        }, f, indent=2)
    
    print(f"\n💾 Full results saved to: {comparison_file}")
    
    # Recommendations
    print(f"\n{'='*80}")
    print("🎯 RECOMMENDATIONS")
    print(f"{'='*80}")
    
    # Find best model
    best_accuracy = 0
    best_model = None
    for result in all_results:
        avg_accuracy = 0
        count = 0
        for format_type in ['regular_format', 'structured_format']:
            if result.get(format_type, {}).get('success'):
                avg_accuracy += result[format_type]['accuracy']
                count += 1
        if count > 0:
            avg_accuracy /= count
            if avg_accuracy > best_accuracy:
                best_accuracy = avg_accuracy
                best_model = result['model']
    
    if best_model:
        print(f"✅ Best overall model: {best_model} ({best_accuracy:.1f}% average accuracy)")
    
    # Find models with no bounds errors
    no_bounds_models = []
    for result in all_results:
        total_bounds = 0
        for format_type in ['regular_format', 'structured_format']:
            if result.get(format_type, {}).get('success'):
                total_bounds += result[format_type].get('bounds_errors', 0)
        if total_bounds == 0 and any(result.get(f, {}).get('success') for f in ['regular_format', 'structured_format']):
            no_bounds_models.append(result['model'])
    
    if no_bounds_models:
        print(f"✅ Models with no bounds errors: {', '.join(no_bounds_models)}")
    
    print("\n💡 For the deduplication task in Graphiti:")
    print("   - Structured output format provides better reliability")
    print("   - Consider models with high accuracy AND no bounds errors")
    print("   - Smaller models may be sufficient if they perform well")

if __name__ == "__main__":
    asyncio.run(main())