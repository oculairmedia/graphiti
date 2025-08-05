# Multi-stage build for production-ready React frontend
FROM node:18-alpine AS builder

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies with verbose output
RUN npm install --force --loglevel verbose || (echo "npm install failed" && exit 1)

# Copy source code
COPY . .

# List files to debug
RUN echo "=== Directory contents ===" && ls -la && \
    echo "=== Node modules check ===" && ls -la node_modules/@cosmograph || true

# Build the application with verbose output
RUN npm run build || (echo "Build failed. Showing package.json:" && cat package.json && exit 1)

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