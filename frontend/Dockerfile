# Multi-stage build for production-ready React frontend
FROM node:18-alpine AS builder

# Install only essential build dependencies (no git)
RUN apk add --no-cache python3 make g++ && \
    echo "=== Build dependencies installed ==="

WORKDIR /app

# Copy package files
COPY package*.json ./
COPY .npmrc ./

# Debug network and npm configuration
RUN echo "=== Network diagnostics ===" && \
    ping -c 1 registry.npmjs.org || echo "Cannot ping npm registry" && \
    echo "=== NPM configuration ===" && \
    npm config list && \
    echo "=== DNS resolution test ===" && \
    nslookup registry.npmjs.org || echo "DNS lookup failed"

# Try to install dependencies with legacy peer deps
RUN echo "=== Starting npm ci with legacy peer deps ===" && \
    npm ci --no-audit --no-fund --legacy-peer-deps 2>&1 | tee /tmp/npm.log || \
    (echo "=== npm ci failed, trying npm install ===" && \
     rm -rf node_modules package-lock.json && \
     npm cache clean --force && \
     npm install --no-audit --no-fund --legacy-peer-deps 2>&1 | tee -a /tmp/npm.log) || \
    (echo "=== Both npm commands failed ===" && \
     echo "=== Full npm log ===" && \
     cat /tmp/npm.log && \
     echo "=== NPM cache directory ===" && \
     ls -la ~/.npm || true && \
     echo "=== System resources ===" && \
     free -h || true && \
     df -h || true && \
     exit 1)

# Copy source code
COPY . .

# Build the application
RUN echo "=== Building application ===" && \
    npm run build || \
    (echo "=== Build failed ===" && \
     echo "=== Checking node_modules ===" && \
     ls -la node_modules/ | head -20 && \
     echo "=== Checking for vite ===" && \
     ls -la node_modules/.bin/vite || true && \
     exit 1)

# Production stage
FROM nginx:alpine

RUN apk add --no-cache curl

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist /usr/share/nginx/html

RUN echo "OK" > /usr/share/nginx/html/health

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost/health || exit 1

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]