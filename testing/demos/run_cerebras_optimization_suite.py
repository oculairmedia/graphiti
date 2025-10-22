"""
Orchestrator script for running the complete Cerebras optimization test suite.
Coordinates all optimization tests and generates a comprehensive report.
"""

import asyncio
import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import subprocess
import os

# Import test frameworks
from test_cerebras_extraction_optimizations import TestFramework as OptimizationFramework
from test_cerebras_multi_model_consensus import MultiModelConsensus

class OptimizationSuiteOrchestrator:
    """Orchestrates all Cerebras optimization tests"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("CEREBRAS_API_KEY")
        if not self.api_key:
            raise ValueError("CEREBRAS_API_KEY is required")
        
        self.results_dir = Path("optimization_results")
        self.results_dir.mkdir(exist_ok=True)
        
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
    def run_optimization_tests(self) -> Dict:
        """Run comprehensive extraction optimization tests"""
        print("=" * 80)
        print("CEREBRAS EXTRACTION OPTIMIZATION SUITE")
        print("=" * 80)
        print(f"Timestamp: {self.timestamp}")
        print(f"Model: qwen-3-coder-480b")
        print()
        
        framework = OptimizationFramework()
        
        # Run optimization tests
        strategy_scores, all_results = asyncio.run(framework.run_comprehensive_test())
        
        return {
            "test_type": "extraction_optimizations",
            "strategy_scores": strategy_scores,
            "detailed_results": all_results,
            "timestamp": self.timestamp
        }
    
    def run_consensus_tests(self) -> Dict:
        """Run multi-model consensus tests"""
        print("\n" + "=" * 80)
        print("MULTI-MODEL CONSENSUS TESTING")
        print("=" * 80)
        
        consensus_tester = MultiModelConsensus()
        
        # Test scenarios
        test_scenarios = [
            {
                "name": "business_scenario",
                "text": "Sarah Chen, CEO of QuantumTech Industries, announced a breakthrough in quantum computing at the International Tech Summit in San Francisco."
            },
            {
                "name": "academic_scenario", 
                "text": "Dr. Alice Wang from MIT collaborated with Professor Bob Zhang at Stanford on quantum computing research funded by NSF."
            },
            {
                "name": "technical_scenario",
                "text": "The GraphRAG system developed by Anthropic uses LLaMA-3 embeddings and integrates with FalkorDB for storage."
            }
        ]
        
        consensus_results = []
        for scenario in test_scenarios:
            print(f"\nTesting scenario: {scenario['name']}")
            results = asyncio.run(consensus_tester.test_consensus_strategies(scenario['text']))
            consensus_results.append({
                "scenario": scenario['name'],
                "text": scenario['text'],
                "results": results
            })
        
        return {
            "test_type": "consensus_strategies",
            "scenarios": consensus_results,
            "timestamp": self.timestamp
        }
    
    def run_baseline_comparison(self) -> Dict:
        """Run baseline comparisons with previous test results"""
        print("\n" + "=" * 80)
        print("BASELINE COMPARISON")
        print("=" * 80)
        
        # Look for previous test results
        baseline_files = [
            "cerebras_optimization_20250830_133441.json",
            "cerebras_enhanced_prompts_20250830_125508.json",
            "cerebras_recommended_config_20250830_123036.json"
        ]
        
        baseline_data = {}
        for filename in baseline_files:
            filepath = Path(filename)
            if filepath.exists():
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        baseline_data[filename] = {
                            "timestamp": data.get("timestamp"),
                            "best_f1_score": data.get("best_f1_score", 0),
                            "test_type": data.get("test_type", "unknown")
                        }
                        print(f"  Found baseline: {filename} (F1: {data.get('best_f1_score', 0):.3f})")
                except Exception as e:
                    print(f"  Error reading {filename}: {e}")
            else:
                print(f"  Baseline not found: {filename}")
        
        return {
            "test_type": "baseline_comparison",
            "baselines": baseline_data,
            "timestamp": self.timestamp
        }
    
    def calculate_improvement_summary(self, optimization_results: Dict, consensus_results: Dict, baseline_results: Dict) -> Dict:
        """Calculate overall improvement summary"""
        summary = {
            "optimization_improvements": {},
            "consensus_benefits": {},
            "recommendations": []
        }
        
        # Analyze optimization improvements
        strategy_scores = optimization_results.get("strategy_scores", {})
        baseline_f1 = strategy_scores.get("baseline", {}).get("avg_f1", 0)
        
        for strategy, scores in strategy_scores.items():
            if strategy != "baseline" and baseline_f1 > 0:
                improvement = ((scores["avg_f1"] - baseline_f1) / baseline_f1) * 100
                summary["optimization_improvements"][strategy] = {
                    "f1_score": scores["avg_f1"],
                    "improvement_percent": improvement,
                    "entity_f1": scores.get("avg_entity_f1", 0),
                    "relationship_f1": scores.get("avg_rel_f1", 0)
                }
        
        # Find best strategies
        best_optimization = max(
            summary["optimization_improvements"].items(),
            key=lambda x: x[1]["improvement_percent"],
            default=(None, {"improvement_percent": 0})
        )
        
        # Generate recommendations
        if best_optimization[0] and best_optimization[1]["improvement_percent"] > 10:
            summary["recommendations"].append(
                f"Implement {best_optimization[0]} strategy for {best_optimization[1]['improvement_percent']:.1f}% improvement"
            )
        
        # Analyze consensus benefits
        consensus_scenarios = consensus_results.get("scenarios", [])
        if consensus_scenarios:
            avg_agreement_rates = []
            for scenario in consensus_scenarios:
                for result in scenario.get("results", []):
                    if "variance" in result:
                        entity_agreement = result["variance"]["entity_variance"]["avg_agreement"]
                        avg_agreement_rates.append(entity_agreement)
            
            if avg_agreement_rates:
                summary["consensus_benefits"]["avg_agreement"] = sum(avg_agreement_rates) / len(avg_agreement_rates)
                if summary["consensus_benefits"]["avg_agreement"] > 0.7:
                    summary["recommendations"].append("Multi-model consensus shows good agreement - consider for production")
        
        # Historical comparison
        baselines = baseline_results.get("baselines", {})
        if baselines:
            historical_scores = [data.get("best_f1_score", 0) for data in baselines.values() if data.get("best_f1_score")]
            if historical_scores and baseline_f1 > 0:
                best_historical = max(historical_scores)
                current_vs_historical = ((baseline_f1 - best_historical) / best_historical) * 100 if best_historical > 0 else 0
                summary["historical_comparison"] = {
                    "current_baseline": baseline_f1,
                    "best_historical": best_historical,
                    "improvement_percent": current_vs_historical
                }
        
        return summary
    
    def generate_master_report(self, optimization_results: Dict, consensus_results: Dict, baseline_results: Dict) -> str:
        """Generate comprehensive master report"""
        summary = self.calculate_improvement_summary(optimization_results, consensus_results, baseline_results)
        
        master_report = {
            "suite_execution": {
                "timestamp": self.timestamp,
                "model": "qwen-3-coder-480b",
                "api_key_used": self.api_key[:10] + "..." if self.api_key else "none"
            },
            "optimization_results": optimization_results,
            "consensus_results": consensus_results,
            "baseline_comparison": baseline_results,
            "improvement_summary": summary,
            "executive_summary": {
                "best_strategy": max(
                    summary["optimization_improvements"].items(),
                    key=lambda x: x[1]["improvement_percent"],
                    default=("none", {"improvement_percent": 0})
                )[0],
                "max_improvement": max(
                    [data["improvement_percent"] for data in summary["optimization_improvements"].values()],
                    default=0
                ),
                "key_recommendations": summary["recommendations"][:3]  # Top 3
            }
        }
        
        # Save master report
        report_filename = f"cerebras_optimization_master_report_{self.timestamp}.json"
        report_path = self.results_dir / report_filename
        
        with open(report_path, 'w') as f:
            json.dump(master_report, f, indent=2, default=str)
        
        # Generate human-readable summary
        self.print_executive_summary(master_report)
        
        return str(report_path)
    
    def print_executive_summary(self, report: Dict):
        """Print executive summary to console"""
        print("\n" + "=" * 80)
        print("EXECUTIVE SUMMARY")
        print("=" * 80)
        
        exec_summary = report["executive_summary"]
        improvement_summary = report["improvement_summary"]
        
        print(f"Best Strategy: {exec_summary['best_strategy']}")
        print(f"Maximum Improvement: {exec_summary['max_improvement']:.1f}%")
        print()
        
        print("Top Improvements:")
        for strategy, data in sorted(
            improvement_summary["optimization_improvements"].items(),
            key=lambda x: x[1]["improvement_percent"],
            reverse=True
        )[:5]:
            print(f"  {strategy}: +{data['improvement_percent']:.1f}% (F1: {data['f1_score']:.3f})")
        
        print("\nKey Recommendations:")
        for i, rec in enumerate(exec_summary["key_recommendations"], 1):
            print(f"  {i}. {rec}")
        
        # Consensus insights
        consensus_benefits = improvement_summary.get("consensus_benefits", {})
        if "avg_agreement" in consensus_benefits:
            print(f"\nConsensus Analysis:")
            print(f"  Average Agreement Rate: {consensus_benefits['avg_agreement']:.2f}")
            if consensus_benefits["avg_agreement"] > 0.75:
                print("  → High agreement suggests good model consistency")
            elif consensus_benefits["avg_agreement"] > 0.5:
                print("  → Moderate agreement suggests ensemble benefits")
            else:
                print("  → Low agreement suggests need for better strategies")
        
        # Historical comparison
        if "historical_comparison" in improvement_summary:
            hist = improvement_summary["historical_comparison"]
            print(f"\nHistorical Comparison:")
            print(f"  Current vs Best Historical: {hist['improvement_percent']:+.1f}%")
    
    def run_full_suite(self, skip_consensus: bool = False) -> str:
        """Run the complete optimization test suite"""
        print("Starting Cerebras Optimization Test Suite...")
        print(f"Results will be saved to: {self.results_dir}")
        print()
        
        # Run optimization tests
        optimization_results = self.run_optimization_tests()
        
        # Run consensus tests (optional)
        consensus_results = {}
        if not skip_consensus:
            consensus_results = self.run_consensus_tests()
        else:
            print("\nSkipping consensus tests (--skip-consensus flag)")
            consensus_results = {"test_type": "consensus_strategies", "scenarios": [], "skipped": True}
        
        # Run baseline comparison
        baseline_results = self.run_baseline_comparison()
        
        # Generate master report
        report_path = self.generate_master_report(optimization_results, consensus_results, baseline_results)
        
        print(f"\nSuite completed! Master report: {report_path}")
        return report_path


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(description="Cerebras Optimization Test Suite")
    parser.add_argument("--api-key", help="Cerebras API key (or use CEREBRAS_API_KEY env var)")
    parser.add_argument("--skip-consensus", action="store_true", help="Skip consensus testing (faster)")
    parser.add_argument("--results-only", action="store_true", help="Only show executive summary")
    
    args = parser.parse_args()
    
    try:
        orchestrator = OptimizationSuiteOrchestrator(api_key=args.api_key)
        
        if args.results_only:
            # Just show results from latest report
            latest_reports = sorted(
                orchestrator.results_dir.glob("cerebras_optimization_master_report_*.json"),
                reverse=True
            )
            if latest_reports:
                with open(latest_reports[0], 'r') as f:
                    report = json.load(f)
                    orchestrator.print_executive_summary(report)
            else:
                print("No previous reports found. Run full suite first.")
            return
        
        # Run full suite
        report_path = orchestrator.run_full_suite(skip_consensus=args.skip_consensus)
        print(f"\nAll results available at: {report_path}")
        
    except KeyboardInterrupt:
        print("\nSuite interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error running suite: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()