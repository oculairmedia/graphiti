# FalkorDB Browser Connection Guide

## The Issue
The FalkorDB browser UI is trying to connect to `localhost:6379` but your FalkorDB is running on port `6389`.

## Quick Solution - Use RedisInsight Instead
Since RedisInsight is already configured and working well:
1. Go to http://192.168.50.90:5540
2. Click on "FalkorDB Graph Database"
3. Use the CLI or Workbench to query your data

## Alternative Solutions for FalkorDB Browser

### Option 1: Port Forwarding (Temporary)
Run this command to forward port 6379 to 6389:
```bash
sudo iptables -t nat -A PREROUTING -p tcp --dport 6379 -j REDIRECT --to-port 6389
# Or use socat:
socat TCP-LISTEN:6379,fork TCP:localhost:6389
```

### Option 2: SSH Tunnel
If accessing from another machine:
```bash
ssh -L 6379:localhost:6389 user@192.168.50.90
```
Then access http://localhost:3100 on your local machine.

### Option 3: Use Container Network
Access the browser from within the Docker network where FalkorDB is actually on port 6379:
```bash
docker exec -it graphiti-falkordb-1 redis-cli
```

## FalkorDB Browser Login Details
When you access http://localhost:3100, use these connection details:
- **Host**: 192.168.50.90 (or localhost if using port forwarding)
- **Port**: 6389 (or 6379 if using port forwarding)
- **Username**: (leave empty)
- **Password**: (leave empty)
- **TLS**: unchecked

## Your Data Status
- **Total Nodes**: 4,437
- **Total Relationships**: 13,849
- **Graph Name**: graphiti_migration

## Recommended Approach
Since RedisInsight is already working perfectly and provides a better interface for querying FalkorDB, we recommend using that instead of trying to fix the FalkorDB browser connection issue.