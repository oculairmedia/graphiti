#!/usr/bin/env python3
"""
Compare old vs new deduplication behavior
"""

print('=' * 60)
print('DEDUPLICATION BEHAVIOR COMPARISON')
print('=' * 60)

print('\n### OLD BEHAVIOR (Too Aggressive):')
print("- 'Claude' + 'Claude Code' → MERGED ❌ (substring matching)")
print("- 'GitHub' + 'GitHub Actions' → MERGED ❌ (substring matching)")
print('- Large groups with 90% similarity → AUTO-MERGED')
print('- Embedding threshold: 0.85')
print('- Name similarity threshold: 0.9')

print('\n### NEW BEHAVIOR (Less Aggressive):')
print("- 'Claude' + 'Claude Code' → KEPT SEPARATE ✓ (compound name detection)")
print("- 'GitHub' + 'GitHub Actions' → KEPT SEPARATE ✓ (compound name detection)")
print('- Large groups need 95% EXACT matches → MORE CONSERVATIVE')
print('- Embedding threshold: 0.92 (increased)')
print('- Name similarity threshold: 0.95 (increased)')

print('\n### STILL MERGES:')
print("- 'Claude' + 'claude' + 'CLAUDE' → MERGED ✓ (case variations)")
print("- 'User (system)' + 'User' → MERGED ✓ (suffix removal)")
print("- 'claude_code' + 'Claude Code' → MERGED ✓ (underscore normalization)")

print('\n### KEY IMPROVEMENTS:')
print('1. Preserves distinct entities that share a common prefix')
print('2. Requires higher confidence for automatic merging')
print('3. No substring matching - only exact matches after normalization')
print('4. Detects and preserves compound names')
print('=' * 60)
