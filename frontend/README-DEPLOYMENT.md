# Graphiti Frontend Production Deployment Guide

## 🚀 Production-Ready React Frontend

This directory contains a production-ready Docker setup for the Graphiti knowledge graph visualization frontend.

## 📋 Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB+ RAM available
- 10GB+ disk space

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Nginx LB      │    │  React Frontend │    │  Rust Server    │
│   (Port 80)     │◄──►│   (Port 8080)   │◄──►│   (Port 3000)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                                               ┌─────────────────┐
                                               │   FalkorDB      │
                                               │   (Port 6379)   │
                                               └─────────────────┘
```

## 🚀 Quick Start

### Option 1: Using the Startup Script (Recommended)

```bash
# Start development environment
./start-frontend.sh development

# Start production environment
./start-frontend.sh production
```

### Option 2: Using Docker Compose

```bash
# Development with tools
docker-compose -f docker-compose.frontend.yml --profile tools up -d

# Production with load balancer
docker-compose -f docker-compose.frontend.yml --profile production up -d
```

### Option 3: Using Makefile

```bash
# Show all available commands
make -f Makefile.frontend help

# Quick setup
make -f Makefile.frontend install

# Production deployment
make -f Makefile.frontend prod
```

## 📊 Access URLs

After startup, the following services will be available:

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://localhost:8080 | React application |
| **API Server** | http://localhost:3000 | Rust graph server |
| **FalkorDB** | localhost:6379 | Graph database |
| **Redis Insight** | http://localhost:8001 | DB management (dev only) |
| **Load Balancer** | http://localhost:80 | Production LB (prod only) |

## 🔧 Configuration

### Environment Variables

Create `.env.production` for production settings:

```env
VITE_API_BASE_URL=http://localhost:3000
VITE_WS_URL=ws://localhost:3000/ws
VITE_APP_ENVIRONMENT=production
VITE_ENABLE_DEBUG=false
VITE_MAX_GRAPH_NODES=10000
```

### Nginx Configuration

The frontend uses a production-optimized Nginx configuration with:

- ✅ Security headers (CSP, XSS protection, etc.)
- ✅ Gzip compression
- ✅ API proxying to Rust server
- ✅ WebSocket support
- ✅ Static asset caching
- ✅ React Router support

## 🏭 Production Features

### Security
- CSP headers for XSS protection
- Security headers (X-Frame-Options, etc.)
- Rate limiting on API endpoints
- Input validation and sanitization

### Performance
- Multi-stage Docker builds
- Nginx with gzip compression
- Static asset caching (1 year)
- HTML caching (1 hour)
- API response caching

### Scalability
- Load balancer configuration included
- Horizontal scaling support
- Health checks for all services
- Graceful shutdowns

### Monitoring
- Health check endpoints
- Structured logging
- Performance metrics
- Error tracking

## 📈 Scaling

### Horizontal Scaling

Scale frontend instances:
```bash
docker-compose -f docker-compose.frontend.yml up -d --scale frontend=3
```

Scale Rust server instances:
```bash
# Update nginx-lb.conf to add more upstream servers
# Then restart the load balancer
make -f Makefile.frontend restart
```

### Vertical Scaling

Adjust resource limits in docker-compose.frontend.yml:
```yaml
services:
  frontend:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
```

## 🔍 Monitoring & Health Checks

### Health Checks

All services include health checks:

```bash
# Check all services
make -f Makefile.frontend health

# Manual health checks
curl http://localhost:8080/health  # Frontend
curl http://localhost:3000/health  # Rust server
docker exec graphiti-falkordb redis-cli ping  # FalkorDB
```

### Logs

```bash
# All logs
make -f Makefile.frontend logs

# Specific service
make -f Makefile.frontend logs-frontend
make -f Makefile.frontend logs-rust
make -f Makefile.frontend logs-db
```

## 🔧 Maintenance

### Updates

```bash
# Update all services
make -f Makefile.frontend update

# Manual update
docker-compose -f docker-compose.frontend.yml pull
docker-compose -f docker-compose.frontend.yml up -d
```

### Backups

```bash
# Backup FalkorDB
make -f Makefile.frontend backup-db

# Manual backup
docker exec graphiti-falkordb redis-cli --rdb /data/backup.rdb
```

### Cleanup

```bash
# Stop services
make -f Makefile.frontend down

# Remove everything including volumes
make -f Makefile.frontend clean
```

## 🐛 Troubleshooting

### Common Issues

**Frontend not loading:**
```bash
# Check frontend logs
docker logs graphiti-frontend

# Verify nginx configuration
docker exec graphiti-frontend nginx -t
```

**API connection issues:**
```bash
# Test Rust server directly
curl http://localhost:3000/health

# Check network connectivity
docker network ls
docker network inspect graphiti-frontend_graphiti-network
```

**Database connection issues:**
```bash
# Check FalkorDB status
docker exec graphiti-falkordb redis-cli ping

# View database logs
docker logs graphiti-falkordb
```

### Performance Issues

**High memory usage:**
```bash
# Check container stats
docker stats

# Adjust memory limits in docker-compose.frontend.yml
```

**Slow response times:**
```bash
# Check nginx access logs
docker exec graphiti-frontend tail -f /var/log/nginx/access.log

# Monitor API response times
curl -w "@curl-format.txt" http://localhost:3000/api/visualize
```

## 📁 File Structure

```
frontend/
├── Dockerfile              # Multi-stage production build
├── nginx.conf              # Production Nginx configuration
├── .dockerignore           # Docker build exclusions
├── .env.production         # Production environment variables
└── README-DEPLOYMENT.md    # This file

# Root level files
├── docker-compose.frontend.yml  # Complete stack definition
├── nginx-lb.conf               # Load balancer configuration
├── Makefile.frontend           # Automation commands
└── start-frontend.sh           # Easy startup script
```

## 🔐 Security Considerations

### Production Checklist

- [ ] Use HTTPS in production (update nginx-lb.conf)
- [ ] Set strong database passwords
- [ ] Configure firewall rules
- [ ] Enable rate limiting
- [ ] Set up SSL certificates
- [ ] Configure CSP headers
- [ ] Enable security scanning

### SSL/TLS Setup

For production HTTPS, update `nginx-lb.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    # SSL configuration...
}
```

## 📞 Support

For issues or questions:

1. Check the troubleshooting section above
2. Review Docker logs: `make -f Makefile.frontend logs`
3. Check service health: `make -f Makefile.frontend health`
4. Verify configuration files
5. Check GitHub issues

## 🎯 Performance Targets

The production setup is optimized for:

- **Response Time**: < 200ms for API calls
- **First Paint**: < 2 seconds
- **Memory Usage**: < 512MB per frontend instance
- **Concurrent Users**: 100+ per instance
- **Uptime**: 99.9%

Monitor these metrics using the provided health checks and logging.