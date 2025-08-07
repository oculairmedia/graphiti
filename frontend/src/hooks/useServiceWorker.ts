import { useEffect, useState, useCallback } from 'react';
import { logger } from '../utils/logger';

interface ServiceWorkerStatus {
  isSupported: boolean;
  isRegistered: boolean;
  isUpdating: boolean;
  cacheSize: string;
  registration: ServiceWorkerRegistration | null;
}

export function useServiceWorker() {
  const [status, setStatus] = useState<ServiceWorkerStatus>({
    isSupported: 'serviceWorker' in navigator,
    isRegistered: false,
    isUpdating: false,
    cacheSize: '0 Bytes',
    registration: null,
  });
  
  // Register service worker
  useEffect(() => {
    if (!status.isSupported) {
      logger.warn('Service Worker not supported in this browser');
      return;
    }
    
    const registerServiceWorker = async () => {
      try {
        const registration = await navigator.serviceWorker.register('/service-worker.js', {
          scope: '/'
        });
        
        logger.log('Service Worker registered:', registration);
        
        setStatus(prev => ({
          ...prev,
          isRegistered: true,
          registration,
        }));
        
        // Check for updates
        registration.addEventListener('updatefound', () => {
          logger.log('Service Worker update found');
          setStatus(prev => ({ ...prev, isUpdating: true }));
          
          const newWorker = registration.installing;
          if (newWorker) {
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'activated') {
                logger.log('Service Worker updated and activated');
                setStatus(prev => ({ ...prev, isUpdating: false }));
                
                // Optionally reload the page to use the new service worker
                if (window.confirm('A new version is available. Reload to update?')) {
                  window.location.reload();
                }
              }
            });
          }
        });
        
        // Check for updates periodically
        setInterval(() => {
          registration.update();
        }, 60000); // Check every minute
        
      } catch (error) {
        logger.error('Service Worker registration failed:', error);
      }
    };
    
    registerServiceWorker();
    
    // Get initial cache size
    getCacheSize();
  }, [status.isSupported]);
  
  // Send message to service worker
  const sendMessage = useCallback((message: any): Promise<any> => {
    return new Promise((resolve, reject) => {
      if (!navigator.serviceWorker.controller) {
        reject(new Error('No service worker controller'));
        return;
      }
      
      const messageChannel = new MessageChannel();
      
      messageChannel.port1.onmessage = (event) => {
        if (event.data.success) {
          resolve(event.data);
        } else {
          reject(new Error(event.data.error || 'Service Worker operation failed'));
        }
      };
      
      navigator.serviceWorker.controller.postMessage(message, [messageChannel.port2]);
    });
  }, []);
  
  // Pre-cache Arrow data
  const cacheArrowData = useCallback(async () => {
    try {
      const result = await sendMessage({
        type: 'CACHE_ARROW_DATA',
        payload: {
          nodesUrl: '/api/arrow/nodes',
          edgesUrl: '/api/arrow/edges',
        }
      });
      
      logger.log('Arrow data cached successfully');
      await getCacheSize();
      return result;
    } catch (error) {
      logger.error('Failed to cache Arrow data:', error);
      throw error;
    }
  }, [sendMessage]);
  
  // Clear all caches
  const clearCache = useCallback(async () => {
    try {
      const result = await sendMessage({ type: 'CLEAR_CACHE' });
      logger.log('Cache cleared successfully');
      
      setStatus(prev => ({ ...prev, cacheSize: '0 Bytes' }));
      return result;
    } catch (error) {
      logger.error('Failed to clear cache:', error);
      throw error;
    }
  }, [sendMessage]);
  
  // Get cache size
  const getCacheSize = useCallback(async () => {
    try {
      const result = await sendMessage({ type: 'GET_CACHE_SIZE' });
      
      setStatus(prev => ({ 
        ...prev, 
        cacheSize: result.sizeFormatted || '0 Bytes' 
      }));
      
      return result;
    } catch (error) {
      logger.error('Failed to get cache size:', error);
      return { size: 0, sizeFormatted: '0 Bytes' };
    }
  }, [sendMessage]);
  
  // Force update service worker
  const forceUpdate = useCallback(async () => {
    if (!status.registration) return;
    
    try {
      await status.registration.update();
      logger.log('Service Worker update check initiated');
    } catch (error) {
      logger.error('Failed to check for Service Worker update:', error);
    }
  }, [status.registration]);
  
  // Unregister service worker
  const unregister = useCallback(async () => {
    if (!status.registration) return;
    
    try {
      const success = await status.registration.unregister();
      if (success) {
        logger.log('Service Worker unregistered');
        setStatus(prev => ({
          ...prev,
          isRegistered: false,
          registration: null,
        }));
      }
    } catch (error) {
      logger.error('Failed to unregister Service Worker:', error);
    }
  }, [status.registration]);
  
  return {
    ...status,
    cacheArrowData,
    clearCache,
    getCacheSize,
    forceUpdate,
    unregister,
  };
}

// Helper hook to check online/offline status
export function useOnlineStatus() {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  
  useEffect(() => {
    const handleOnline = () => {
      logger.log('Network: Online');
      setIsOnline(true);
    };
    
    const handleOffline = () => {
      logger.log('Network: Offline');
      setIsOnline(false);
    };
    
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);
  
  return isOnline;
}