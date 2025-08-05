# Multi-stage build for production-ready React frontend
FROM node:18-alpine AS builder

# Install build dependencies
RUN apk add --no-cache python3 make g++ git

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Clean npm cache and install dependencies
RUN npm cache clean --force && \
    npm config set registry https://registry.npmjs.org/ && \
    npm install --legacy-peer-deps --no-audit --no-fund || \
    (echo "=== npm install failed, showing error log ===" && \
     cat /root/.npm/_logs/*.log 2>/dev/null || true && \
     exit 1)

# Copy source code
COPY . .

# Build the application
RUN npm run build || \
    (echo "=== Build failed ===" && \
     echo "=== Checking for common issues ===" && \
     ls -la node_modules/.bin/ && \
     echo "=== Package.json scripts ===" && \
     cat package.json | grep -A 10 '"scripts"' && \
     exit 1)

# Production stage with Nginx
FROM nginx:alpine AS production

# Install curl for health checks
RUN apk add --no-cache curl

# Copy custom nginx configuration
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Create health endpoint
RUN echo '<!DOCTYPE html><html><head><title>Health Check</title></head><body><h1>OK</h1></body></html>' > /usr/share/nginx/html/health

# Add health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:80/health || exit 1

# Expose port
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]