#!/bin/bash
# Script to run entity extraction maintenance inside the container

cd /app
echo "[$(date)] Starting entity extraction maintenance" >> /var/log/graphiti_entity_extraction.log
python maintenance_extract_entities.py >> /var/log/graphiti_entity_extraction.log 2>&1
echo "[$(date)] Entity extraction maintenance completed" >> /var/log/graphiti_entity_extraction.log