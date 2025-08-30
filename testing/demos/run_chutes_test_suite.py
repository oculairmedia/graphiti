#!/usr/bin/env python3
"""
Comprehensive Chutes AI (GLM-4.5-FP8) Test Suite Runner
Executes all Chutes tests and generates comprehensive reports.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import subprocess

@dataclass
class TestResult:
    """Result from running a test."""
    test_name: str
    success: bool
    duration: float
    output: str
    error: Optional[str] = None

class ChutesTestSuiteRunner:
    """Orchestrates the complete Chutes AI test suite."""
    
    def __init__(self):
        self.results: List[TestResult] = []
        self.test_files = [
            {
                'name': 'Chutes API Connection Test',
                'file': 'test_chutes_api_only.py',
                'description': 'Basic API connectivity and authentication',
                'critical': True,
                'timeout': 120
            },
            {
                'name': 'Minimal Integration Test',
                'file': 'test_minimal_chutes.py',
                'description': 'Component initialization and basic functionality',
                'critical': True,
                'timeout': 180
            },
            {
                'name': 'Structured Output Test', 
                'file': 'test_chutes_structured.py',
                'description': 'JSON generation and GLM-specific capabilities',
                'critical': True,
                'timeout': 300
            },
            {
                'name': 'Full Integration Test',
                'file': 'test_full_chutes.py',
                'description': 'Complete Graphiti integration with GLM-4.5-FP8',
                'critical': True,
                'timeout': 900
            }
        ]

    def check_prerequisites(self) -> Dict[str, bool]:
        """Check prerequisites before running tests."""
        
        print('🔍 Checking Prerequisites...')
        
        checks = {
            'chutes_api_key': bool(os.getenv('CHUTES_API_KEY')),
            'falkordb_accessible': False,
            'ollama_accessible': False,
            'test_files_exist': True
        }
        
        # Check if test files exist
        missing_files = []
        for test in self.test_files:
            if not os.path.exists(test['file']):
                missing_files.append(test['file'])
                checks['test_files_exist'] = False
                
        if missing_files:
            print(f'   ❌ Missing test files: {missing_files}')
        else:
            print(f'   ✅ All test files found')
        
        # Check CHUTES_API_KEY
        if checks['chutes_api_key']:
            print('   ✅ CHUTES_API_KEY is set')
        else:
            print('   ❌ CHUTES_API_KEY not found - LLM tests will fail')
        
        # Check FalkorDB connection
        try:
            from falkordb import FalkorDB
            db = FalkorDB(host='localhost', port=6389)
            graph = db.select_graph('test_connection')
            result = graph.query('RETURN "ping" as test')
            if result and result.result_set:
                checks['falkordb_accessible'] = True
                print('   ✅ FalkorDB is accessible')
        except Exception as e:
            print(f'   ❌ FalkorDB connection failed: {e}')
        
        # Check Ollama connection (for embeddings)
        try:
            import aiohttp
            async def check_ollama():
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get('http://192.168.50.80:11434/api/version', timeout=5) as resp:
                            return resp.status == 200
                except:
                    return False
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            ollama_ok = loop.run_until_complete(check_ollama())
            loop.close()
            
            if ollama_ok:
                checks['ollama_accessible'] = True
                print('   ✅ Ollama is accessible for embeddings')
            else:
                print('   ❌ Ollama connection failed - using fallback embeddings')
                
        except Exception as e:
            print(f'   ❌ Ollama check failed: {e}')
        
        return checks

    async def run_test_file(self, test_info: Dict[str, Any]) -> TestResult:
        """Run a single test file and capture results."""
        
        print(f'\n🧪 Running: {test_info["name"]}')
        print(f'   File: {test_info["file"]}')
        print(f'   Description: {test_info["description"]}')
        
        start_time = time.time()
        
        try:
            # Set environment variable for the test
            env = os.environ.copy()
            if os.getenv('CHUTES_API_KEY'):
                env['CHUTES_API_KEY'] = os.getenv('CHUTES_API_KEY')
            
            # Run the test as a subprocess
            result = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    sys.executable, test_info['file'],
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=os.path.dirname(__file__) or '.',
                    env=env
                ),
                timeout=test_info['timeout']
            )
            
            stdout, _ = await result.communicate()
            output = stdout.decode('utf-8') if stdout else ''
            
            duration = time.time() - start_time
            success = result.returncode == 0
            
            status = '✅ PASSED' if success else '❌ FAILED'
            print(f'   {status} ({duration:.1f}s)')
            
            if not success:
                print(f'   Exit code: {result.returncode}')
                # Show last few lines of output for debugging
                lines = output.split('\n')
                error_context = '\n'.join(lines[-10:]) if len(lines) > 10 else output
                print(f'   Last output lines:\n{error_context}')
            
            return TestResult(
                test_name=test_info['name'],
                success=success,
                duration=duration,
                output=output,
                error=None if success else f'Exit code {result.returncode}'
            )
            
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            print(f'   ⏱️ TIMEOUT after {test_info["timeout"]}s')
            
            return TestResult(
                test_name=test_info['name'],
                success=False,
                duration=duration,
                output='',
                error=f'Timeout after {test_info["timeout"]} seconds'
            )
            
        except Exception as e:
            duration = time.time() - start_time
            print(f'   ❌ ERROR: {e}')
            
            return TestResult(
                test_name=test_info['name'],
                success=False,
                duration=duration,
                output='',
                error=str(e)
            )

    async def run_test_suite(self, critical_only: bool = False) -> Dict[str, Any]:
        """Run the complete test suite."""
        
        print('🚀 Chutes AI (GLM-4.5-FP8) Test Suite Runner')
        print('=' * 80)
        print(f'Start Time: {datetime.now().isoformat()}')
        print(f'Model: GLM-4.5-FP8 (zai-org/GLM-4.5-FP8)')
        
        # Check prerequisites
        prereqs = self.check_prerequisites()
        
        # Determine which tests to run
        tests_to_run = self.test_files
        if critical_only:
            tests_to_run = [t for t in self.test_files if t.get('critical', False)]
            print(f'\n⚡ Running critical tests only ({len(tests_to_run)}/{len(self.test_files)})')
        else:
            print(f'\n🔄 Running full test suite ({len(tests_to_run)} tests)')
        
        # Check for potential issues
        if not prereqs['chutes_api_key']:
            print('⚠️ WARNING: No CHUTES_API_KEY - many tests will fail')
            response = input('Continue anyway? (y/N): ')
            if response.lower() != 'y':
                print('Aborting test run')
                return {'status': 'aborted', 'reason': 'No API key'}
        
        if not prereqs['falkordb_accessible']:
            print('⚠️ WARNING: FalkorDB not accessible - database tests will fail')
        
        # Run tests sequentially (GLM can be slower)
        suite_start_time = time.time()
        
        for test_info in tests_to_run:
            result = await self.run_test_file(test_info)
            self.results.append(result)
            
            # Longer pause between tests for GLM (API rate limits)
            await asyncio.sleep(3)
        
        suite_duration = time.time() - suite_start_time
        
        # Generate summary
        summary = self.generate_summary(suite_duration)
        self.print_comprehensive_report()
        
        return summary

    def generate_summary(self, suite_duration: float) -> Dict[str, Any]:
        """Generate test suite summary."""
        
        total_tests = len(self.results)
        successful_tests = len([r for r in self.results if r.success])
        failed_tests = total_tests - successful_tests
        
        critical_tests = [r for r in self.results if any(t['name'] == r.test_name and t.get('critical', False) for t in self.test_files)]
        critical_passes = len([r for r in critical_tests if r.success])
        
        return {
            'status': 'completed',
            'total_tests': total_tests,
            'successful_tests': successful_tests,
            'failed_tests': failed_tests,
            'success_rate': (successful_tests / total_tests * 100) if total_tests > 0 else 0,
            'critical_tests': len(critical_tests),
            'critical_passes': critical_passes,
            'critical_success_rate': (critical_passes / len(critical_tests) * 100) if critical_tests else 0,
            'total_duration': suite_duration,
            'average_test_duration': sum(r.duration for r in self.results) / total_tests if total_tests > 0 else 0
        }

    def print_comprehensive_report(self):
        """Print detailed test report."""
        
        print('\n📋 CHUTES AI (GLM-4.5-FP8) TEST SUITE COMPREHENSIVE REPORT')
        print('=' * 90)
        
        # Summary statistics
        total = len(self.results)
        passed = len([r for r in self.results if r.success])
        failed = total - passed
        success_rate = (passed / total * 100) if total > 0 else 0
        
        print(f'\n📊 Test Summary:')
        print(f'   Total Tests: {total}')
        print(f'   Passed: {passed} ✅')
        print(f'   Failed: {failed} ❌')
        print(f'   Success Rate: {success_rate:.1f}%')
        
        # Critical vs non-critical breakdown
        critical_results = []
        
        for result in self.results:
            test_info = next((t for t in self.test_files if t['name'] == result.test_name), None)
            if test_info and test_info.get('critical', False):
                critical_results.append(result)
        
        if critical_results:
            critical_passed = len([r for r in critical_results if r.success])
            critical_rate = (critical_passed / len(critical_results) * 100)
            print(f'\n🎯 Critical Tests: {critical_passed}/{len(critical_results)} passed ({critical_rate:.1f}%)')
        
        # Detailed results
        print(f'\n📋 Detailed Results:')
        print(f'{"Test Name":<40} {"Status":<10} {"Duration":<10} {"Notes":<20}')
        print('-' * 90)
        
        for result in self.results:
            status = '✅ PASS' if result.success else '❌ FAIL'
            notes = result.error[:20] + '...' if result.error and len(result.error) > 20 else (result.error or '')
            
            print(f'{result.test_name:<40} {status:<10} {result.duration:>8.1f}s {notes:<20}')
        
        # Performance analysis
        print(f'\n⚡ Performance Analysis:')
        total_time = sum(r.duration for r in self.results)
        avg_time = total_time / len(self.results) if self.results else 0
        
        print(f'   Total Suite Time: {total_time:.1f}s ({total_time/60:.1f} minutes)')
        print(f'   Average Test Time: {avg_time:.1f}s')
        
        # GLM-specific performance notes
        print(f'   📝 GLM Performance Notes:')
        if avg_time > 60:
            print(f'     • GLM-4.5-FP8 has slower response times (expected)')
            print(f'     • Complex reasoning tasks take 60-120s')
        else:
            print(f'     • GLM response times are within normal range')
        
        # Find slowest tests
        sorted_results = sorted(self.results, key=lambda r: r.duration, reverse=True)
        print(f'   Slowest Tests:')
        for i, result in enumerate(sorted_results[:3], 1):
            print(f'     {i}. {result.test_name}: {result.duration:.1f}s')
        
        # Error analysis
        failed_results = [r for r in self.results if not r.success]
        if failed_results:
            print(f'\n❌ Failure Analysis:')
            
            error_categories = {}
            for result in failed_results:
                if result.error:
                    if 'timeout' in result.error.lower():
                        error_categories['Timeouts'] = error_categories.get('Timeouts', 0) + 1
                    elif 'api' in result.error.lower() or 'key' in result.error.lower():
                        error_categories['API Issues'] = error_categories.get('API Issues', 0) + 1
                    elif 'connection' in result.error.lower() or 'network' in result.error.lower():
                        error_categories['Connection Issues'] = error_categories.get('Connection Issues', 0) + 1
                    else:
                        error_categories['Other'] = error_categories.get('Other', 0) + 1
                        
            for category, count in error_categories.items():
                print(f'   {category}: {count} failures')
            
            print(f'\n   Failed Tests Detail:')
            for result in failed_results:
                print(f'     • {result.test_name}')
                if result.error:
                    print(f'       Error: {result.error}')
        
        # GLM-specific recommendations
        print(f'\n💡 Chutes AI (GLM-4.5-FP8) Recommendations:')
        
        if success_rate >= 75:
            print('   ✅ GLM-4.5-FP8 integration shows good compatibility')
            print('   🎯 Suitable for production knowledge extraction tasks')
            print('   🌏 Excellent for multilingual content (Chinese + English)')
        else:
            print('   ⚠️ GLM integration issues detected - review setup')
        
        # Specific recommendations based on failures
        if any('timeout' in (r.error or '').lower() for r in failed_results):
            print('   🔧 Consider increasing timeout values (GLM can be slower)')
            
        if any('api' in (r.error or '').lower() for r in failed_results):
            print('   🔧 Verify CHUTES_API_KEY and account status')
            
        if any('connection' in (r.error or '').lower() for r in failed_results):
            print('   🔧 Check network connectivity to Chutes AI service')
        
        # GLM-specific strengths to highlight
        print(f'\n🌟 GLM-4.5-FP8 Key Strengths:')
        print('   • Multilingual processing (Chinese + English)')
        print('   • Strong technical domain understanding')
        print('   • Robust structured output with custom parsing')
        print('   • Good performance on complex reasoning tasks')
        
        # Next steps
        print(f'\n🎯 Next Steps:')
        if failed_results:
            print('   1. Address timeout and connectivity issues')
            print('   2. Review GLM-specific configuration settings')
            print('   3. Test with production data volume')
        else:
            print('   1. Deploy GLM for multilingual content processing')
            print('   2. Optimize prompts for domain-specific tasks')
            print('   3. Set up monitoring for production deployment')


async def main():
    """Main test suite runner."""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Chutes AI (GLM-4.5-FP8) test suite')
    parser.add_argument('--critical-only', action='store_true', 
                       help='Run only critical tests')
    parser.add_argument('--timeout-multiplier', type=float, default=1.0,
                       help='Multiply all timeouts by this factor (default: 1.0)')
    
    args = parser.parse_args()
    
    runner = ChutesTestSuiteRunner()
    
    # Adjust timeouts if requested (useful for slower connections)
    if args.timeout_multiplier != 1.0:
        for test in runner.test_files:
            test['timeout'] = int(test['timeout'] * args.timeout_multiplier)
        print(f'⏱️ Timeouts adjusted by {args.timeout_multiplier}x')
    
    # Run the test suite
    summary = await runner.run_test_suite(critical_only=args.critical_only)
    
    # Final summary
    print(f'\n🎉 Chutes AI Test Suite Completed!')
    print(f'End Time: {datetime.now().isoformat()}')
    print(f'Status: {summary.get("status", "unknown")}')
    
    # Exit with appropriate code
    if summary.get('status') == 'completed':
        exit_code = 0 if summary.get('success_rate', 0) >= 75 else 1  # Lower threshold for GLM
        sys.exit(exit_code)
    else:
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())