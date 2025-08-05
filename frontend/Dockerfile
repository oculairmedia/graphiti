# Multi-stage build for production-ready React frontend
FROM node:18-alpine AS builder

# Install dependencies including git
RUN apk add --no-cache git python3 make g++

# Configure git to handle directory permissions
RUN git config --global --add safe.directory /app

# Set working directory
WORKDIR /app

# Copy package files first for better caching
COPY package.json package-lock.json ./

# Create .npmrc for CI builds
RUN echo "registry=https://registry.npmjs.org/" > .npmrc && \
    echo "strict-ssl=false" >> .npmrc && \
    echo "fetch-retries=5" >> .npmrc && \
    echo "fetch-retry-mintimeout=20000" >> .npmrc && \
    echo "fetch-retry-maxtimeout=120000" >> .npmrc

# Install dependencies using npm ci for reproducible builds
RUN npm ci --no-audit --no-fund || \
    (echo "=== npm ci failed, trying npm install ===" && \
     npm install --no-audit --no-fund --legacy-peer-deps) || \
    (echo "=== Both npm ci and install failed ===" && \
     echo "=== Showing npm debug log ===" && \
     cat /root/.npm/_logs/* 2>/dev/null || true && \
     echo "=== Showing package.json ===" && \
     cat package.json && \
     exit 1)

# Copy application source
COPY . .

# Build the application
RUN echo "=== Starting build ===" && \
    npm run build || \
    (echo "=== Build failed, debugging info ===" && \
     echo "=== Node version ===" && node --version && \
     echo "=== NPM version ===" && npm --version && \
     echo "=== Directory contents ===" && ls -la && \
     echo "=== Checking node_modules ===" && \
     ls -la node_modules/ | head -20 && \
     exit 1)

# Production stage
FROM nginx:alpine

# Install curl for health checks
RUN apk add --no-cache curl

# Copy nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built application
COPY --from=builder /app/dist /usr/share/nginx/html

# Create health check endpoint
RUN echo "OK" > /usr/share/nginx/html/health

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost/health || exit 1

# Expose port
EXPOSE 80

# Start nginx
CMD ["nginx", "-g", "daemon off;"]