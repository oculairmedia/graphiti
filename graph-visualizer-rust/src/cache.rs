use bloom::{BloomFilter, ASMS};
use dashmap::DashMap;
use deadpool_redis::{redis::AsyncCommands, Pool as RedisPool};
use lru::LruCache;
use serde::{Deserialize, Serialize};
use std::future::Future;
use std::num::NonZeroUsize;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::RwLock;
use tracing::{debug, instrument};

/// Cache entry with access tracking for adaptive TTL
#[allow(dead_code)]
#[derive(Debug, Clone)]
pub struct CacheEntry<T> {
    pub value: T,
    pub created_at: Instant,
    pub access_count: u32,
    pub last_accessed: Instant,
}

/// Adaptive TTL calculator based on access patterns
pub struct AdaptiveTTL {
    hot_threshold: u32,
    warm_threshold: u32,
    hot_ttl: Duration,
    warm_ttl: Duration,
    cold_ttl: Duration,
}

impl Default for AdaptiveTTL {
    fn default() -> Self {
        Self {
            hot_threshold: 100,                 // >100 accesses = hot
            warm_threshold: 10,                 // 10-100 accesses = warm
            hot_ttl: Duration::from_secs(1800), // 30 minutes
            warm_ttl: Duration::from_secs(300), // 5 minutes
            cold_ttl: Duration::from_secs(60),  // 1 minute
        }
    }
}

impl AdaptiveTTL {
    pub fn calculate_ttl(&self, access_count: u32) -> u64 {
        if access_count > self.hot_threshold {
            self.hot_ttl.as_secs()
        } else if access_count > self.warm_threshold {
            self.warm_ttl.as_secs()
        } else {
            self.cold_ttl.as_secs()
        }
    }
}

/// Request coalescing to prevent duplicate work
pub struct RequestCoalescer<K: Clone + Eq + std::hash::Hash, V: Clone> {
    inflight: Arc<DashMap<K, Arc<tokio::sync::Mutex<Option<V>>>>>,
}

impl<K: Clone + Eq + std::hash::Hash + Send + Sync + 'static, V: Clone + Send + Sync + 'static>
    RequestCoalescer<K, V>
{
    pub fn new() -> Self {
        Self {
            inflight: Arc::new(DashMap::new()),
        }
    }

    /// Execute function with request coalescing
    pub async fn get_or_compute<F, Fut>(&self, key: K, compute: F) -> V
    where
        F: FnOnce() -> Fut,
        Fut: Future<Output = V>,
    {
        // Check if request is already in flight
        if let Some(entry) = self.inflight.get(&key) {
            let mutex = entry.clone();
            drop(entry); // Release the dashmap read lock

            // Wait for the in-flight request
            let guard = mutex.lock().await;
            if let Some(value) = guard.as_ref() {
                debug!("Request coalesced for key");
                return value.clone();
            }
        }

        // No in-flight request, we'll compute it
        let mutex = Arc::new(tokio::sync::Mutex::new(None));
        self.inflight.insert(key.clone(), mutex.clone());

        // Compute the value
        let value = compute().await;

        // Store the result for other waiters
        {
            let mut guard = mutex.lock().await;
            *guard = Some(value.clone());
        }

        // Clean up after a short delay
        let inflight = self.inflight.clone();
        let key_clone = key.clone();
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(100)).await;
            inflight.remove(&key_clone);
        });

        value
    }
}

/// Bloom filter for negative caching
pub struct NegativeCache {
    filter: Arc<RwLock<BloomFilter>>,
    #[allow(dead_code)]
    false_positive_rate: f64,
}

impl NegativeCache {
    pub fn new(expected_items: usize, false_positive_rate: f64) -> Self {
        let filter = BloomFilter::with_rate(false_positive_rate as f32, expected_items as u32);
        Self {
            filter: Arc::new(RwLock::new(filter)),
            false_positive_rate,
        }
    }

    /// Check if key might exist (true = maybe exists, false = definitely doesn't exist)
    pub async fn might_exist(&self, key: &str) -> bool {
        let filter = self.filter.read().await;
        filter.contains(&key)
    }

    /// Mark key as existing
    pub async fn mark_exists(&self, key: &str) {
        let mut filter = self.filter.write().await;
        filter.insert(&key);
    }

    /// Clear the filter (use periodically to prevent saturation)
    #[allow(dead_code)]
    pub async fn clear(&self) {
        let mut filter = self.filter.write().await;
        *filter = BloomFilter::with_rate(
            self.false_positive_rate as f32,
            1_000_000, // Default size
        );
    }
}

/// Access counter for tracking query frequency
pub struct AccessCounter {
    counts: Arc<DashMap<String, u32>>,
    lru: Arc<RwLock<LruCache<String, Instant>>>,
}

impl AccessCounter {
    pub fn new(capacity: usize) -> Self {
        Self {
            counts: Arc::new(DashMap::new()),
            lru: Arc::new(RwLock::new(LruCache::new(
                NonZeroUsize::new(capacity).unwrap(),
            ))),
        }
    }

    /// Increment access count and return new count
    pub async fn increment(&self, key: &str) -> u32 {
        // Update LRU
        {
            let mut lru = self.lru.write().await;
            lru.put(key.to_string(), Instant::now());
        }

        // Increment counter
        let mut entry = self.counts.entry(key.to_string()).or_insert(0);
        *entry += 1;
        *entry
    }

    /// Get current access count
    #[allow(dead_code)]
    pub fn get_count(&self, key: &str) -> u32 {
        self.counts.get(key).map(|v| *v).unwrap_or(0)
    }

    /// Clean up old entries periodically
    #[allow(dead_code)]
    pub async fn cleanup(&self, max_age: Duration) {
        let now = Instant::now();
        let mut lru = self.lru.write().await;

        // Remove old entries from LRU
        let mut to_remove = Vec::new();
        for (key, &time) in lru.iter() {
            if now.duration_since(time) > max_age {
                to_remove.push(key.clone());
            }
        }

        for key in to_remove {
            lru.pop(&key);
            self.counts.remove(&key);
        }
    }
}

/// Enhanced cache operations with all optimizations
pub struct EnhancedCache {
    redis_pool: RedisPool,
    adaptive_ttl: AdaptiveTTL,
    coalescer: RequestCoalescer<String, Option<String>>,
    negative_cache: NegativeCache,
    access_counter: AccessCounter,
}

impl EnhancedCache {
    pub fn new(redis_pool: RedisPool) -> Self {
        Self {
            redis_pool,
            adaptive_ttl: AdaptiveTTL::default(),
            coalescer: RequestCoalescer::new(),
            negative_cache: NegativeCache::new(1_000_000, 0.01), // 1% false positive rate
            access_counter: AccessCounter::new(10_000),
        }
    }

    #[instrument(skip(self, compute))]
    pub async fn get_or_compute<T, F, Fut>(
        &self,
        key: &str,
        compute: F,
    ) -> Result<Option<T>, anyhow::Error>
    where
        T: Serialize + for<'de> Deserialize<'de> + Clone + Send + Sync + 'static,
        F: FnOnce() -> Fut + Send,
        Fut: Future<Output = Result<Option<T>, anyhow::Error>> + Send,
    {
        // Check negative cache first
        if !self.negative_cache.might_exist(key).await {
            debug!("Negative cache hit for key: {}", key);
            return Ok(None);
        }

        // Increment access counter
        let access_count = self.access_counter.increment(key).await;

        // Use request coalescing
        let result = self
            .coalescer
            .get_or_compute(key.to_string(), || async move {
                // Try to get from Redis
                if let Ok(mut conn) = self.redis_pool.get().await {
                    if let Ok(cached) = conn.get::<_, String>(key).await {
                        if let Ok(value) = serde_json::from_str::<T>(&cached) {
                            debug!(
                                "Cache hit for key: {} (access count: {})",
                                key, access_count
                            );
                            return serde_json::to_string(&value).ok();
                        }
                    }
                }

                // Cache miss, compute value
                debug!("Cache miss for key: {}", key);
                match compute().await {
                    Ok(Some(value)) => {
                        // Mark as existing in negative cache
                        self.negative_cache.mark_exists(key).await;

                        // Calculate adaptive TTL
                        let ttl = self.adaptive_ttl.calculate_ttl(access_count);
                        debug!(
                            "Setting TTL {} seconds for key: {} (access count: {})",
                            ttl, key, access_count
                        );

                        // Store in Redis with adaptive TTL
                        if let Ok(mut conn) = self.redis_pool.get().await {
                            if let Ok(json) = serde_json::to_string(&value) {
                                let _ = conn.set_ex::<_, _, ()>(key, &json, ttl).await;
                            }
                        }

                        serde_json::to_string(&value).ok()
                    }
                    Ok(None) => {
                        // Value doesn't exist, don't add to negative cache
                        // (it's already not there)
                        None
                    }
                    Err(e) => {
                        debug!("Error computing value for key {}: {}", key, e);
                        None
                    }
                }
            })
            .await;

        // Parse the result
        match result {
            Some(json) => Ok(Some(serde_json::from_str(&json)?)),
            None => Ok(None),
        }
    }

    /// Periodic maintenance task
    #[allow(dead_code)]
    pub async fn maintenance(&self) {
        // Clean up old access counts
        self.access_counter.cleanup(Duration::from_secs(3600)).await;

        // Optionally clear bloom filter if it's getting too full
        // (in production, monitor false positive rate and clear when needed)
    }
}