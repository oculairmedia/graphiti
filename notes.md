# Graphiti Development Notes - CRITICAL INFO

## Working Configuration (TESTED & VERIFIED)

### Ollama Configuration
- **Working Ollama IP**: `100.81.139.20` (NOT 192.168.50.90!)
- **Ollama Port**: `11434`
- **Base URL**: `http://100.81.139.20:11434/v1`
- **Model**: `mistral:latest`

### Neo4j Configuration  
- **Neo4j IP**: `192.168.50.90`
- **Neo4j Port**: `7687` 
- **Username**: `neo4j`
- **Password**: `demodemo`

### Container Environment Variables (WORKING)
```bash
-e OPENAI_API_KEY=sk-dummy \
-e USE_OLLAMA=true \
-e OLLAMA_BASE_URL=http://100.81.139.20:11434/v1 \
-e OLLAMA_MODEL=mistral:latest \
-e NEO4J_URI=bolt://192.168.50.90:7687 \
-e NEO4J_USER=neo4j \
-e NEO4J_PASSWORD=demodemo
```

## Previous Debugging Results
- ✅ Centrality import issue FIXED (development mode installation works)
- ✅ Container builds and starts successfully  
- ✅ Ollama integration was previously working with correct IP
- ✅ Data ingestion pipeline was debugged and working

## CRITICAL REMINDERS
- **NEVER** run `/clear` endpoint on live data again!
- **ALWAYS** use the correct Ollama IP: `100.81.139.20`
- **REMEMBER** we already solved the centrality imports - don't second-guess the fix

## Container Names Used
- `graphiti-server-final` - Latest working image
- Current test container: `graphiti-working-ollama`