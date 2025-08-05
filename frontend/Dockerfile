# Multi-stage build for production-ready React frontend
# Updated to trigger new build with .gitmodules fix
FROM node:18-alpine AS builder

# Install build dependencies
RUN apk add --no-cache python3 make g++ libc6-compat

WORKDIR /app

# Copy package files and npmrc
COPY package*.json ./
COPY .npmrc ./

# Install dependencies with legacy peer deps
RUN npm ci --legacy-peer-deps --no-audit --no-fund || \
    npm install --legacy-peer-deps --no-audit --no-fund

# Copy source code
COPY . .

# Set NODE_ENV for production build
ENV NODE_ENV=production

# Build the application with error handling
RUN npm run build || \
    (echo "Build failed. Debug info:" && \
     echo "Node version:" && node --version && \
     echo "NPM version:" && npm --version && \
     echo "Working directory:" && pwd && \
     echo "Files in directory:" && ls -la && \
     echo "Checking vite binary:" && ls -la node_modules/.bin/ | grep vite || true && \
     echo "Package.json scripts:" && cat package.json | grep -A5 '"scripts"' && \
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