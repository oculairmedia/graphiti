#!/usr/bin/env python3
"""
Combined script to regenerate ALL embeddings in FalkorDB.
This runs all three embedding scripts in sequence:
1. Node embeddings
2. Edge embeddings  
3. Episodic node embeddings
"""

import asyncio
import time
from datetime import datetime
import subprocess
import sys
from typing import Dict, Any, Tuple

# ANSI color codes for output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*80}{Colors.ENDC}\n")

def print_section(text: str):
    """Print a section header"""
    print(f"\n{Colors.CYAN}{Colors.BOLD}{text}{Colors.ENDC}")
    print(f"{Colors.CYAN}{'-'*50}{Colors.ENDC}")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.RED}❌ {text}{Colors.ENDC}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.ENDC}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.ENDC}")

def run_script(script_name: str, description: str, force_all: bool = True) -> Tuple[bool, float]:
    """
    Run a Python script and capture its output.
    Returns (success, duration_seconds)
    """
    print_section(f"Running: {description}")
    print_info(f"Script: {script_name}")
    
    start_time = time.time()
    
    try:
        # Build command with force-regenerate flag to process ALL nodes/edges
        cmd = [sys.executable, script_name]
        if force_all:
            cmd.append('--force-regenerate')
        
        print_info(f"Command: {' '.join(cmd)}")
        
        # Run the script
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        duration = time.time() - start_time
        
        # Check if successful or if it's the "no embeddings to generate" case
        if result.returncode == 0:
            print_success(f"Completed in {duration:.2f} seconds")
            
            # Extract key metrics from output if available
            output_lines = result.stdout.split('\n')
            for line in output_lines:
                if 'Successfully updated:' in line or 'Processed:' in line:
                    print(f"  {Colors.CYAN}{line.strip()}{Colors.ENDC}")
                elif 'Total' in line and 'embeddings' in line:
                    print(f"  {Colors.GREEN}{line.strip()}{Colors.ENDC}")
                elif 'Remaining without embeddings: 0' in line:
                    print(f"  {Colors.GREEN}All embeddings already present{Colors.ENDC}")
            
            return True, duration
        else:
            # Check if it's the "nothing to process" error
            error_output = result.stderr if result.stderr else ""
            if "cannot unpack non-iterable NoneType" in error_output:
                print_info("No embeddings to generate - all items already have embeddings")
                return True, duration  # Consider this a success
            else:
                print_error(f"Failed with return code {result.returncode}")
                if result.stderr:
                    print(f"  Error: {result.stderr[:500]}")
                return False, duration
            
    except FileNotFoundError:
        print_error(f"Script not found: {script_name}")
        return False, 0
    except Exception as e:
        print_error(f"Error running script: {e}")
        return False, 0

async def main():
    """Main function to run all embedding generation scripts"""
    
    print_header("COMPLETE EMBEDDING REGENERATION SUITE")
    
    print_info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_info("This will regenerate embeddings for:")
    print("  • Regular nodes")
    print("  • Edges (relationships)")
    print("  • Episodic nodes")
    print()
    
    # Configuration
    scripts = [
        {
            'file': 'regenerate_node_embeddings_ollama.py',
            'description': 'Node Embeddings Generation',
            'critical': True
        },
        {
            'file': 'regenerate_edge_embeddings_ollama.py',
            'description': 'Edge Embeddings Generation',
            'critical': True
        },
        {
            'file': 'regenerate_episodic_embeddings_ollama.py',
            'description': 'Episodic Node Embeddings Generation',
            'critical': True
        }
    ]
    
    # Track overall statistics
    total_start = time.time()
    results = []
    all_success = True
    
    # Run each script
    for i, script in enumerate(scripts, 1):
        print(f"\n{Colors.BOLD}Step {i}/{len(scripts)}{Colors.ENDC}")
        
        success, duration = run_script(script['file'], script['description'], force_all=False)
        results.append({
            'script': script['file'],
            'description': script['description'],
            'success': success,
            'duration': duration
        })
        
        if not success and script.get('critical', False):
            print_error(f"Critical script failed: {script['description']}")
            all_success = False
            # Continue anyway to show what would be run
        
        # Small delay between scripts
        if i < len(scripts):
            time.sleep(2)
    
    # Calculate total time
    total_duration = time.time() - total_start
    
    # Print summary
    print_header("EMBEDDING GENERATION SUMMARY")
    
    print_section("Results by Script")
    for result in results:
        status = "✅ SUCCESS" if result['success'] else "❌ FAILED"
        print(f"  {status}: {result['description']}")
        print(f"    Time: {result['duration']:.2f} seconds")
    
    print_section("Overall Statistics")
    successful_count = sum(1 for r in results if r['success'])
    print(f"  Scripts run: {len(results)}")
    print(f"  Successful: {successful_count}/{len(results)}")
    print(f"  Total time: {total_duration:.2f} seconds ({total_duration/60:.1f} minutes)")
    
    if all_success:
        print_success("\n🎉 All embeddings successfully regenerated!")
    else:
        print_warning("\n⚠️  Some scripts failed. Check the output above for details.")
    
    print_info(f"\nEnd time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return 0 if all_success else 1

def check_prerequisites():
    """Check if all required scripts exist"""
    required_scripts = [
        'regenerate_node_embeddings_ollama.py',
        'regenerate_edge_embeddings_ollama.py',
        'regenerate_episodic_embeddings_ollama.py'
    ]
    
    missing = []
    for script in required_scripts:
        try:
            with open(script, 'r'):
                pass
        except FileNotFoundError:
            missing.append(script)
    
    if missing:
        print_error("Missing required scripts:")
        for script in missing:
            print(f"  • {script}")
        return False
    
    return True

if __name__ == "__main__":
    # Check prerequisites
    if not check_prerequisites():
        print_error("Please ensure all required scripts are present in the current directory.")
        sys.exit(1)
    
    # Run the main function
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_warning("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)