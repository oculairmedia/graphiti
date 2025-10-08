#!/bin/bash

# FalkorDB Browser Port Forwarding Fix
# This script creates a temporary port forward so the browser can connect

echo "FalkorDB Browser Connection Fix"
echo "==============================="
echo ""
echo "This will forward port 6379 to 6389 so the FalkorDB browser can connect."
echo "Press Ctrl+C to stop."
echo ""

# Check if socat is installed
if command -v socat &> /dev/null; then
    echo "Starting port forwarding with socat..."
    socat TCP-LISTEN:6379,fork,reuseaddr TCP:localhost:6389
else
    echo "socat not found. Installing..."
    sudo apt-get update && sudo apt-get install -y socat
    echo "Starting port forwarding with socat..."
    socat TCP-LISTEN:6379,fork,reuseaddr TCP:localhost:6389
fi