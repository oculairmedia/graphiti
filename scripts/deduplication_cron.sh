#!/bin/bash
# Script to run deduplication maintenance inside the container

cd /app
echo "[$(date)] Starting deduplication maintenance" >> /var/log/graphiti_dedupe.log
python maintenance_dedupe_entities.py >> /var/log/graphiti_dedupe.log 2>&1
echo "[$(date)] Deduplication maintenance completed" >> /var/log/graphiti_dedupe.log