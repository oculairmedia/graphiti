# Multi-stage build for production-ready React frontend
# Updated to trigger new build with .gitmodules fix
FROM node:18-alpine AS builder

# Install build dependencies
RUN apk add --no-cache python3 make g++ libc6-compat

WORKDIR /app

# Copy package files and npmrc
COPY package*.json ./
COPY .npmrc ./

# Install dependencies with a more robust approach
# First try with ci, then fallback to install
RUN npm ci --legacy-peer-deps --no-audit --no-fund 2>&1 || \
    (echo "npm ci failed, trying npm install..." && \
     rm -rf node_modules package-lock.json && \
     npm install --legacy-peer-deps --no-audit --no-fund) || \
    (echo "Both attempts failed, trying with --ignore-scripts..." && \
     rm -rf node_modules && \
     npm install --legacy-peer-deps --no-audit --no-fund --ignore-scripts)

# Copy source code
COPY . .

# Set NODE_ENV for production build
ENV NODE_ENV=production

# Debug: Show current directory and key files
RUN echo "=== Build environment debug ===" && \
    echo "Current directory: $(pwd)" && \
    echo "Source files present:" && \
    ls -la src/lib/ && \
    echo "Vite config:" && \
    cat vite.config.ts | grep -A5 resolve

# Ensure vite is executable
RUN chmod +x node_modules/.bin/vite 2>/dev/null || true

# Build the application
RUN npm run build

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