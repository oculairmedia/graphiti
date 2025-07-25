#!/usr/bin/env python3

import os

print("Environment variables:")
print(f"USE_OLLAMA: {os.getenv('USE_OLLAMA', 'NOT SET')}")
print(f"OLLAMA_BASE_URL: {os.getenv('OLLAMA_BASE_URL', 'NOT SET')}")
print(f"OLLAMA_MODEL: {os.getenv('OLLAMA_MODEL', 'NOT SET')}")
print(f"NEO4J_URI: {os.getenv('NEO4J_URI', 'NOT SET')}")

print(f"\nCondition check: os.getenv('USE_OLLAMA', '').lower() == 'true' -> {os.getenv('USE_OLLAMA', '').lower() == 'true'}")