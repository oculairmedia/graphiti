#!/usr/bin/env python3
"""
Test OpenEvolve with multi-provider support.
Uses OpenAI proxy + Gemini proxy to avoid Z.AI rate limits.
"""
import os
import sys
sys.path.insert(0, '/opt/stacks/graphiti')

from dotenv import load_dotenv
load_dotenv()

print("Starting Multi-Provider Evolution Test...")
print("=" * 60)

# IMPORTANT: Keep Z.AI credentials for DSPy evaluation (evaluator subprocess needs these)
# The .env should have:
#   CHUTES_BASE_URL=https://api.z.ai/api/coding/paas/v4
#   CHUTES_API_KEY=<real key>
# We preserve these for the evaluator subprocess

# Verify Z.AI credentials are set
zai_url = os.environ.get('CHUTES_BASE_URL', '')
zai_key = os.environ.get('CHUTES_API_KEY', '')
if 'z.ai' not in zai_url or not zai_key:
    print("WARNING: Z.AI credentials not properly set!")
    print(f"  CHUTES_BASE_URL: {zai_url}")
    print(f"  CHUTES_API_KEY: {'set' if zai_key else 'not set'}")
    print("  Evaluator will fail without proper Z.AI credentials!")
else:
    print(f"Z.AI evaluator credentials: {zai_url} (key set)")

# Note: OpenEvolve uses per-model api_base settings, so the global CHUTES_ vars
# are only used by the DSPy evaluator subprocess

from graphiti_core.dspy.openevolve import (
    OpenEvolveRunner,
    EvolutionConfig,
    ProviderConfig,
)

# Configure providers for multi-provider round-robin
# Using IT-BAER/gemini-api-proxy on port 8089 (authenticated with Google AI Pro)
providers = [
    ProviderConfig(
        name='openai-proxy',
        api_base='http://192.168.50.90:8082/v1',
        api_key='dummy',
        weight=1.0,
        models=[
            {'name': 'gpt5', 'weight': 1.0},
            {'name': 'gpt51', 'weight': 0.8},
            {'name': 'gpt5codex', 'weight': 0.6},
        ],
    ),
    ProviderConfig(
        name='gemini-proxy',
        api_base='http://192.168.50.90:8089/v1',
        api_key='dummy',  # Proxy handles auth via Google OAuth
        weight=1.0,
        models=[
            {'name': 'gpt-gemini-2.5-flash', 'weight': 1.0},
            {'name': 'gpt-gemini-2.5-pro', 'weight': 0.8},
            {'name': 'gpt-gemini-3-flash-preview', 'weight': 0.9},
        ],
    ),
]

print(f"Configured {len(providers)} providers:")
for p in providers:
    print(f"  - {p.name}: {[m['name'] for m in p.models]}")

# Configure with multi-provider support
config = EvolutionConfig(
    max_iterations=10,  # More iterations for better evolution
    checkpoint_interval=1,
    max_checkpoints=10,
    # Default to OpenAI proxy (used when multi-provider not active)
    llm_api_base='http://192.168.50.90:8082/v1',
    llm_api_key='dummy',
    llm_model='gpt5',
    llm_models=[
        # OpenAI proxy models (port 8082)
        {'name': 'gpt5', 'weight': 1.0, 'api_base': 'http://192.168.50.90:8082/v1', 'api_key': 'dummy'},
        {'name': 'gpt51', 'weight': 0.8, 'api_base': 'http://192.168.50.90:8082/v1', 'api_key': 'dummy'},
        {'name': 'gpt5codex', 'weight': 0.6, 'api_base': 'http://192.168.50.90:8082/v1', 'api_key': 'dummy'},
        # Gemini proxy models (port 8089 - Google AI Pro)
        {'name': 'gpt-gemini-2.5-flash', 'weight': 1.0, 'api_base': 'http://192.168.50.90:8089/v1', 'api_key': 'dummy'},
        {'name': 'gpt-gemini-2.5-pro', 'weight': 0.8, 'api_base': 'http://192.168.50.90:8089/v1', 'api_key': 'dummy'},
        {'name': 'gpt-gemini-3-flash-preview', 'weight': 0.9, 'api_base': 'http://192.168.50.90:8089/v1', 'api_key': 'dummy'},
    ],
    # Multi-provider settings
    providers=providers,
    provider_mode='sequential',  # Round-robin through providers
    use_multi_provider=True,
)

# Force write correct config to YAML before runner uses it
import yaml
from pathlib import Path
config_dir = Path('openevolve_work/entity_extraction')
config_dir.mkdir(parents=True, exist_ok=True)
config_path = config_dir / 'config.yaml'
config_data = yaml.safe_load(config.to_yaml())
# Ensure models list is correct with per-model api_base
# OpenAI models have high weights (reliable diff output), Gemini low weights (diversity)
# Restore equal weights - use reinforced prompts for Gemini
config_data['llm']['models'] = [
    {'name': 'gpt5', 'weight': 1.0, 'api_base': 'http://192.168.50.90:8082/v1', 'api_key': 'dummy'},
    {'name': 'gpt51', 'weight': 0.8, 'api_base': 'http://192.168.50.90:8082/v1', 'api_key': 'dummy'},
    {'name': 'gpt5codex', 'weight': 0.6, 'api_base': 'http://192.168.50.90:8082/v1', 'api_key': 'dummy'},
    {'name': 'gpt-gemini-2.5-flash', 'weight': 1.0, 'api_base': 'http://192.168.50.90:8089/v1', 'api_key': 'dummy'},
    {'name': 'gpt-gemini-2.5-pro', 'weight': 0.8, 'api_base': 'http://192.168.50.90:8089/v1', 'api_key': 'dummy'},
    {'name': 'gpt-gemini-3-flash-preview', 'weight': 0.9, 'api_base': 'http://192.168.50.90:8089/v1', 'api_key': 'dummy'},
]
# Add custom template directory for reinforced prompts
config_data['template_dir'] = 'openevolve_work/entity_extraction/prompts'
with open(config_path, 'w') as f:
    yaml.dump(config_data, f, default_flow_style=False)
print(f"Wrote config with models: {[m['name'] for m in config_data['llm']['models']]}")

print(f"Default API Base: {config.llm_api_base}")
print(f"All Models: {[m['name'] for m in config.llm_models]}")
print(f"Iterations: {config.max_iterations}")
print(f"Multi-Provider Mode: {config.use_multi_provider}")
print(f"Provider Mode: {config.provider_mode}")
print()

runner = OpenEvolveRunner(config=config, work_dir='openevolve_work')

print("Running evolution with OpenAI + Gemini providers...")
result = runner.evolve(task_name='entity_extraction', iterations=10, use_cli=False)

print()
print("=" * 60)
print("EVOLUTION RESULT")
print("=" * 60)
print(f"Success: {result.success}")
print(f"Best Score: {result.best_score:.4f}")
print(f"Iterations: {result.iterations_completed}")
print(f"Best Program Path: {result.best_program_path}")
print(f"Code saved: {len(result.best_program_code)} chars")
if result.error:
    print(f"Error: {result.error}")
