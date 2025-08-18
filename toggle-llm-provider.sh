#!/bin/bash

# Script to toggle between Ollama and Cerebras LLM providers

ENV_FILE=".env"

# Check if .env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found!"
    exit 1
fi

# Function to set a value in .env file
set_env_value() {
    local key=$1
    local value=$2
    if grep -q "^$key=" "$ENV_FILE"; then
        sed -i "s/^$key=.*/$key=$value/" "$ENV_FILE"
    else
        echo "$key=$value" >> "$ENV_FILE"
    fi
}

# Check current provider
current_cerebras=$(grep "^USE_CEREBRAS=" "$ENV_FILE" | cut -d'=' -f2)
current_ollama=$(grep "^USE_OLLAMA=" "$ENV_FILE" | cut -d'=' -f2)

echo "Current configuration:"
echo "  USE_CEREBRAS=$current_cerebras"
echo "  USE_OLLAMA=$current_ollama"
echo ""

# Display menu
echo "Select LLM Provider:"
echo "1) OpenAI (default)"
echo "2) Ollama"
echo "3) Cerebras (Qwen Coder)"
echo "4) Exit"

read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        echo "Switching to OpenAI..."
        set_env_value "USE_CEREBRAS" "false"
        set_env_value "USE_OLLAMA" "false"
        echo "✓ Configured for OpenAI"
        echo "  Make sure OPENAI_API_KEY is set"
        ;;
    2)
        echo "Switching to Ollama..."
        set_env_value "USE_CEREBRAS" "false"
        set_env_value "USE_OLLAMA" "true"
        echo "✓ Configured for Ollama"
        echo "  Using model: $(grep '^OLLAMA_MODEL=' $ENV_FILE | cut -d'=' -f2)"
        ;;
    3)
        echo "Switching to Cerebras..."
        set_env_value "USE_CEREBRAS" "true"
        set_env_value "USE_OLLAMA" "false"
        echo "✓ Configured for Cerebras"
        echo "  Using model: $(grep '^CEREBRAS_MODEL=' $ENV_FILE | cut -d'=' -f2)"
        echo "  Note: Embeddings will still use Ollama"
        ;;
    4)
        echo "Exiting..."
        exit 0
        ;;
    *)
        echo "Invalid choice"
        exit 1
        ;;
esac

echo ""
echo "Configuration updated in $ENV_FILE"
echo "Restart Docker containers to apply changes:"
echo "  docker-compose down && docker-compose up -d"