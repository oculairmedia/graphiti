// Service Worker for Graphiti - Offline caching and performance optimization
const CACHE_NAME = 'graphiti-cache-v1';
const ARROW_CACHE_NAME = 'graphiti-arrow-v1';
const STATIC_CACHE_NAME = 'graphiti-static-v1';

// Files to cache immediately on install
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  // Add your CSS and JS bundles here after build
];

// Cache strategies
const CACHE_STRATEGIES = {
  // Network first, fall back to cache
  networkFirst: async (request) => {
    try {
      const networkResponse = await fetch(request);
      if (networkResponse.ok) {
        const cache = await caches.open(CACHE_NAME);
        cache.put(request, networkResponse.clone());
      }
      return networkResponse;
    } catch (error) {
      const cachedResponse = await caches.match(request);
      if (cachedResponse) {
        console.log('[SW] Serving from cache:', request.url);
        return cachedResponse;
      }
      throw error;
    }
  },
  
  // Cache first, fall back to network
  cacheFirst: async (request) => {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      // Check if cache is still fresh using ETag
      const etag = cachedResponse.headers.get('etag');
      if (etag) {
        try {
          const headResponse = await fetch(request, {
            method: 'HEAD',
            headers: { 'If-None-Match': etag }
          });
          
          if (headResponse.status === 304) {
            // Cache is still fresh
            console.log('[SW] Cache still fresh (ETag match):', request.url);
            return cachedResponse;
          }
        } catch (error) {
          // Network failed, use cached version anyway
          console.log('[SW] Network failed, using cache:', request.url);
          return cachedResponse;
        }
      } else {
        // No ETag, check cache age
        const cacheControl = cachedResponse.headers.get('cache-control');
        const maxAge = cacheControl ? parseInt(cacheControl.match(/max-age=(\d+)/)?.[1] || '0') : 0;
        const dateHeader = cachedResponse.headers.get('date');
        
        if (dateHeader && maxAge > 0) {
          const cacheDate = new Date(dateHeader).getTime();
          const now = Date.now();
          const age = (now - cacheDate) / 1000;
          
          if (age < maxAge) {
            console.log('[SW] Cache still fresh (max-age):', request.url);
            return cachedResponse;
          }
        }
      }
    }
    
    // Fetch from network and update cache
    try {
      const networkResponse = await fetch(request);
      if (networkResponse.ok) {
        const cache = await caches.open(
          request.url.includes('/arrow/') ? ARROW_CACHE_NAME : CACHE_NAME
        );
        cache.put(request, networkResponse.clone());
      }
      return networkResponse;
    } catch (error) {
      if (cachedResponse) {
        console.log('[SW] Network failed, using stale cache:', request.url);
        return cachedResponse;
      }
      throw error;
    }
  },
  
  // Cache only - for static assets
  cacheOnly: async (request) => {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    // If not in cache, try network as fallback
    return fetch(request);
  },
  
  // Stale while revalidate - return cache immediately, update in background
  staleWhileRevalidate: async (request) => {
    const cachedResponse = await caches.match(request);
    
    const fetchPromise = fetch(request).then(networkResponse => {
      if (networkResponse.ok) {
        const cache = caches.open(CACHE_NAME);
        cache.then(c => c.put(request, networkResponse.clone()));
      }
      return networkResponse;
    });
    
    return cachedResponse || fetchPromise;
  }
};

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');
  
  event.waitUntil(
    caches.open(STATIC_CACHE_NAME).then(cache => {
      console.log('[SW] Caching static assets');
      return cache.addAll(STATIC_ASSETS);
    }).then(() => {
      console.log('[SW] Static assets cached');
      // Skip waiting to activate immediately
      return self.skipWaiting();
    })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker...');
  
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames
          .filter(cacheName => {
            // Delete old cache versions
            return cacheName.startsWith('graphiti-') &&
                   cacheName !== CACHE_NAME &&
                   cacheName !== ARROW_CACHE_NAME &&
                   cacheName !== STATIC_CACHE_NAME;
          })
          .map(cacheName => {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          })
      );
    }).then(() => {
      console.log('[SW] Service worker activated');
      // Claim all clients immediately
      return self.clients.claim();
    })
  );
});

// Fetch event - implement caching strategies
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }
  
  // Skip WebSocket requests
  if (url.protocol === 'ws:' || url.protocol === 'wss:') {
    return;
  }
  
  // Skip chrome extension requests
  if (url.protocol === 'chrome-extension:') {
    return;
  }
  
  // Determine caching strategy based on URL
  let strategy;
  
  if (url.pathname.includes('/api/arrow/')) {
    // Arrow data - cache first with ETag validation
    strategy = CACHE_STRATEGIES.cacheFirst;
  } else if (url.pathname.includes('/api/visualize')) {
    // Graph data - stale while revalidate
    strategy = CACHE_STRATEGIES.staleWhileRevalidate;
  } else if (url.pathname.includes('/api/')) {
    // Other API calls - network first
    strategy = CACHE_STRATEGIES.networkFirst;
  } else if (url.pathname.match(/\.(js|css|woff2?|ttf|otf|png|jpg|jpeg|gif|svg|ico)$/)) {
    // Static assets - cache first
    strategy = CACHE_STRATEGIES.cacheFirst;
  } else {
    // HTML and other - network first
    strategy = CACHE_STRATEGIES.networkFirst;
  }
  
  event.respondWith(strategy(request));
});

// Message event - handle commands from the app
self.addEventListener('message', (event) => {
  console.log('[SW] Received message:', event.data);
  
  switch (event.data.type) {
    case 'CACHE_ARROW_DATA':
      // Pre-cache Arrow data
      const { nodesUrl, edgesUrl } = event.data.payload;
      
      Promise.all([
        fetch(nodesUrl).then(response => {
          if (response.ok) {
            return caches.open(ARROW_CACHE_NAME).then(cache => {
              cache.put(nodesUrl, response);
            });
          }
        }),
        fetch(edgesUrl).then(response => {
          if (response.ok) {
            return caches.open(ARROW_CACHE_NAME).then(cache => {
              cache.put(edgesUrl, response);
            });
          }
        })
      ]).then(() => {
        event.ports[0].postMessage({ success: true });
      }).catch(error => {
        event.ports[0].postMessage({ success: false, error: error.message });
      });
      break;
      
    case 'CLEAR_CACHE':
      // Clear all caches
      caches.keys().then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => caches.delete(cacheName))
        );
      }).then(() => {
        event.ports[0].postMessage({ success: true });
      }).catch(error => {
        event.ports[0].postMessage({ success: false, error: error.message });
      });
      break;
      
    case 'GET_CACHE_SIZE':
      // Calculate cache size
      let totalSize = 0;
      
      caches.keys().then(cacheNames => {
        return Promise.all(
          cacheNames.map(cacheName => {
            return caches.open(cacheName).then(cache => {
              return cache.keys().then(requests => {
                return Promise.all(
                  requests.map(request => {
                    return cache.match(request).then(response => {
                      if (response) {
                        const size = parseInt(response.headers.get('content-length') || '0');
                        totalSize += size;
                      }
                    });
                  })
                );
              });
            });
          })
        );
      }).then(() => {
        event.ports[0].postMessage({ 
          success: true, 
          size: totalSize,
          sizeFormatted: formatBytes(totalSize)
        });
      }).catch(error => {
        event.ports[0].postMessage({ success: false, error: error.message });
      });
      break;
  }
});

// Helper function to format bytes
function formatBytes(bytes, decimals = 2) {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}