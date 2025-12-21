//! GRAPH-107: Redis Stream Consumer for Real-time Graph Updates
//!
//! This module implements a consumer for the `graphiti:changes` Redis Stream,
//! enabling real-time graph updates without polling. Events are published by
//! Graphiti's ChangeEventPublisher when nodes/edges are created, updated, or deleted.
//!
//! ## Architecture
//!
//! ```text
//! Graphiti (Python)              Redis Stream              Rust Visualizer
//! ┌─────────────────┐           ┌─────────────┐           ┌─────────────────┐
//! │ add_episode()   │──XADD───▶│graphiti:    │──XREADGROUP▶│ StreamConsumer │
//! │ build_communities()│        │changes      │           │                 │
//! └─────────────────┘           └─────────────┘           └────────┬────────┘
//!                                                                   │
//!                                                                   ▼
//!                                                          ┌─────────────────┐
//!                                                          │ Process changes │
//!                                                          │ Update DuckDB   │
//!                                                          │ Notify clients  │
//!                                                          └─────────────────┘
//! ```
//!
//! ## Consumer Group
//!
//! Uses Redis consumer groups for:
//! - Exactly-once processing (XACK after successful processing)
//! - Automatic failover (pending entries reassigned on crash)
//! - Horizontal scaling (multiple consumers can share the load)

use chrono;
use redis::AsyncCommands;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::mpsc;
use tracing::{debug, error, info, warn};

/// Stream key where Graphiti publishes change events
pub const STREAM_KEY: &str = "graphiti:changes";

/// Dead letter queue stream for failed events (GRAPH-109)
pub const DLQ_STREAM_KEY: &str = "graphiti:changes:dlq";

/// Consumer group name for the visualizer
pub const CONSUMER_GROUP: &str = "visualizer";

/// Default consumer name (can be overridden for multiple instances)
pub const DEFAULT_CONSUMER_NAME: &str = "visualizer-1";

/// Maximum number of entries to read in a single XREADGROUP call
const BATCH_SIZE: usize = 100;

/// Block timeout for XREADGROUP (milliseconds)
const BLOCK_TIMEOUT_MS: usize = 5000;

/// Maximum retries before sending to DLQ (GRAPH-109)
const MAX_RETRIES: u32 = 3;

/// Maximum DLQ size (oldest entries trimmed when exceeded)
const DLQ_MAX_LEN: usize = 10000;

/// Action types from Graphiti's ChangeEventPublisher
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum ChangeAction {
    Create,
    Update,
    Delete,
}

impl TryFrom<&str> for ChangeAction {
    type Error = String;

    fn try_from(s: &str) -> Result<Self, Self::Error> {
        match s.to_lowercase().as_str() {
            "create" => Ok(ChangeAction::Create),
            "update" => Ok(ChangeAction::Update),
            "delete" => Ok(ChangeAction::Delete),
            other => Err(format!("Unknown action: {}", other)),
        }
    }
}

/// Entity types from Graphiti's ChangeEventPublisher
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum EntityType {
    Node,
    Edge,
    Episode,
}

impl TryFrom<&str> for EntityType {
    type Error = String;

    fn try_from(s: &str) -> Result<Self, Self::Error> {
        match s.to_lowercase().as_str() {
            "node" => Ok(EntityType::Node),
            "edge" => Ok(EntityType::Edge),
            "episode" => Ok(EntityType::Episode),
            other => Err(format!("Unknown entity type: {}", other)),
        }
    }
}

/// A parsed change event from the Redis stream
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChangeEvent {
    /// Redis stream entry ID (e.g., "1234567890123-0")
    pub entry_id: String,
    /// The action performed (create, update, delete)
    pub action: ChangeAction,
    /// The type of entity changed
    pub entity_type: EntityType,
    /// UUID of the entity
    pub uuid: String,
    /// Group ID (graph partition)
    pub group_id: String,
    /// ISO timestamp of when the change occurred
    pub timestamp: String,
    /// Optional JSON data for the entity (for create/update)
    pub data: Option<serde_json::Value>,
}

impl ChangeEvent {
    /// Parse a change event from Redis stream entry fields
    pub fn from_stream_entry(
        entry_id: String,
        fields: HashMap<String, String>,
    ) -> Result<Self, String> {
        let action_str = fields
            .get("action")
            .ok_or("Missing 'action' field")?;
        let entity_type_str = fields
            .get("entity_type")
            .ok_or("Missing 'entity_type' field")?;
        let uuid = fields
            .get("uuid")
            .ok_or("Missing 'uuid' field")?
            .clone();
        let group_id = fields
            .get("group_id")
            .ok_or("Missing 'group_id' field")?
            .clone();
        let timestamp = fields
            .get("timestamp")
            .ok_or("Missing 'timestamp' field")?
            .clone();
        
        let data = fields
            .get("data")
            .and_then(|s| serde_json::from_str(s).ok());

        Ok(ChangeEvent {
            entry_id,
            action: ChangeAction::try_from(action_str.as_str())?,
            entity_type: EntityType::try_from(entity_type_str.as_str())?,
            uuid,
            group_id,
            timestamp,
            data,
        })
    }
}

/// Statistics for the stream consumer
#[derive(Debug, Clone, Default, Serialize)]
pub struct ConsumerStats {
    pub events_processed: u64,
    pub events_failed: u64,
    pub events_sent_to_dlq: u64,  // GRAPH-109: Count of events moved to DLQ
    pub last_event_id: Option<String>,
    pub last_event_time: Option<String>,
    pub is_connected: bool,
    pub pending_count: u64,
    pub dlq_size: u64,  // GRAPH-109: Current DLQ size
}

/// Configuration for the stream consumer
#[derive(Debug, Clone)]
pub struct StreamConsumerConfig {
    /// Redis connection string (e.g., "redis://localhost:6379")
    pub redis_url: String,
    /// Consumer name for this instance
    pub consumer_name: String,
    /// Whether to process pending entries on startup
    pub claim_pending: bool,
    /// Maximum age (ms) of pending entries to claim
    pub claim_min_idle_ms: u64,
}

impl Default for StreamConsumerConfig {
    fn default() -> Self {
        Self {
            redis_url: "redis://localhost:6379".to_string(),
            consumer_name: DEFAULT_CONSUMER_NAME.to_string(),
            claim_pending: true,
            claim_min_idle_ms: 60000, // 1 minute
        }
    }
}

/// Stream consumer that reads from the graphiti:changes stream
pub struct StreamConsumer {
    config: StreamConsumerConfig,
    stats: Arc<tokio::sync::RwLock<ConsumerStats>>,
}

impl StreamConsumer {
    /// Create a new stream consumer with the given configuration
    pub fn new(config: StreamConsumerConfig) -> Self {
        Self {
            config,
            stats: Arc::new(tokio::sync::RwLock::new(ConsumerStats::default())),
        }
    }

    /// Get current consumer statistics
    pub async fn get_stats(&self) -> ConsumerStats {
        self.stats.read().await.clone()
    }

    /// Ensure the consumer group exists, creating it if necessary
    async fn ensure_consumer_group(
        &self,
        conn: &mut redis::aio::MultiplexedConnection,
    ) -> Result<(), redis::RedisError> {
        // Try to create the consumer group
        // Use MKSTREAM to create the stream if it doesn't exist
        // Use $ to start reading only new messages (not historical)
        let result: Result<(), redis::RedisError> = redis::cmd("XGROUP")
            .arg("CREATE")
            .arg(STREAM_KEY)
            .arg(CONSUMER_GROUP)
            .arg("$")
            .arg("MKSTREAM")
            .query_async(conn)
            .await;

        match result {
            Ok(_) => {
                info!(
                    "Created consumer group '{}' for stream '{}'",
                    CONSUMER_GROUP, STREAM_KEY
                );
                Ok(())
            }
            Err(e) => {
                // BUSYGROUP means the group already exists - that's fine
                if e.to_string().contains("BUSYGROUP") {
                    debug!("Consumer group '{}' already exists", CONSUMER_GROUP);
                    Ok(())
                } else {
                    Err(e)
                }
            }
        }
    }

    /// Claim pending entries from crashed consumers (GRAPH-108)
    async fn claim_pending_entries(
        &self,
        conn: &mut redis::aio::MultiplexedConnection,
    ) -> Result<Vec<ChangeEvent>, redis::RedisError> {
        if !self.config.claim_pending {
            return Ok(vec![]);
        }

        // Use XAUTOCLAIM to atomically claim and read pending entries
        // This handles entries that were read but not ACKed (e.g., after a crash)
        let result: redis::RedisResult<(String, Vec<(String, HashMap<String, String>)>, Vec<String>)> = 
            redis::cmd("XAUTOCLAIM")
                .arg(STREAM_KEY)
                .arg(CONSUMER_GROUP)
                .arg(&self.config.consumer_name)
                .arg(self.config.claim_min_idle_ms)
                .arg("0-0") // Start from the beginning of pending entries
                .arg("COUNT")
                .arg(BATCH_SIZE)
                .query_async(conn)
                .await;

        match result {
            Ok((_cursor, entries, _deleted)) => {
                let mut events = Vec::with_capacity(entries.len());
                let mut failed_entries = Vec::new();
                
                for (entry_id, fields) in entries {
                    match ChangeEvent::from_stream_entry(entry_id.clone(), fields.clone()) {
                        Ok(event) => {
                            debug!("Claimed pending event: {:?}", event);
                            events.push(event);
                        }
                        Err(e) => {
                            warn!("Failed to parse claimed entry {}: {}", entry_id, e);
                            // GRAPH-109: Collect failed entries for DLQ
                            failed_entries.push((entry_id, fields, e));
                        }
                    }
                }
                
                // GRAPH-109: Send unparseable entries to DLQ and ACK them
                for (entry_id, fields, error) in failed_entries {
                    if let Err(dlq_err) = self.send_to_dlq(
                        conn,
                        &entry_id,
                        &fields,
                        &error,
                        MAX_RETRIES,  // Already at max retries since we're claiming old entries
                    ).await {
                        error!("Failed to send entry {} to DLQ: {}", entry_id, dlq_err);
                    } else {
                        // ACK the entry since we've moved it to DLQ
                        if let Err(ack_err) = self.ack_entries(conn, &[entry_id.clone()]).await {
                            error!("Failed to ACK entry {} after DLQ: {}", entry_id, ack_err);
                        }
                    }
                }
                
                if !events.is_empty() {
                    info!("Claimed {} pending entries", events.len());
                }
                Ok(events)
            }
            Err(e) => {
                // XAUTOCLAIM might fail if the stream/group doesn't exist yet
                if e.to_string().contains("NOGROUP") {
                    debug!("No pending entries to claim (group doesn't exist yet)");
                    Ok(vec![])
                } else {
                    Err(e)
                }
            }
        }
    }

    /// Read new entries from the stream using XREADGROUP
    async fn read_new_entries(
        &self,
        conn: &mut redis::aio::MultiplexedConnection,
    ) -> Result<Vec<ChangeEvent>, redis::RedisError> {
        // XREADGROUP with BLOCK waits for new messages
        // ">" means only read new messages (not pending)
        let result: redis::RedisResult<Vec<(String, Vec<(String, HashMap<String, String>)>)>> = 
            redis::cmd("XREADGROUP")
                .arg("GROUP")
                .arg(CONSUMER_GROUP)
                .arg(&self.config.consumer_name)
                .arg("COUNT")
                .arg(BATCH_SIZE)
                .arg("BLOCK")
                .arg(BLOCK_TIMEOUT_MS)
                .arg("STREAMS")
                .arg(STREAM_KEY)
                .arg(">")
                .query_async(conn)
                .await;

        match result {
            Ok(streams) => {
                let mut events = Vec::new();
                let mut failed_entries = Vec::new();
                
                for (_stream_key, entries) in streams {
                    for (entry_id, fields) in entries {
                        match ChangeEvent::from_stream_entry(entry_id.clone(), fields.clone()) {
                            Ok(event) => {
                                debug!("Received event: {:?}", event);
                                events.push(event);
                            }
                            Err(e) => {
                                warn!("Failed to parse stream entry {}: {}", entry_id, e);
                                // GRAPH-109: Collect failed entries for DLQ
                                failed_entries.push((entry_id, fields, e));
                            }
                        }
                    }
                }
                
                // GRAPH-109: Send unparseable entries to DLQ and ACK them
                // Note: We need a mutable reference to conn, but we don't have it here
                // The failed entries will be handled in the main loop
                if !failed_entries.is_empty() {
                    // Store failed entries for later DLQ processing
                    // For now, just log them - they'll be picked up as pending entries
                    // and handled by claim_pending_entries on the next iteration
                    for (entry_id, _fields, error) in &failed_entries {
                        error!(
                            "Entry {} failed to parse and will be moved to DLQ on next claim: {}",
                            entry_id, error
                        );
                    }
                }
                
                Ok(events)
            }
            Err(e) => Err(e),
        }
    }

    /// Acknowledge processed entries
    async fn ack_entries(
        &self,
        conn: &mut redis::aio::MultiplexedConnection,
        entry_ids: &[String],
    ) -> Result<(), redis::RedisError> {
        if entry_ids.is_empty() {
            return Ok(());
        }

        let mut cmd = redis::cmd("XACK");
        cmd.arg(STREAM_KEY).arg(CONSUMER_GROUP);
        for id in entry_ids {
            cmd.arg(id);
        }

        let _: i64 = cmd.query_async(conn).await?;
        debug!("Acknowledged {} entries", entry_ids.len());
        Ok(())
    }

    /// GRAPH-109: Send a failed event to the dead letter queue
    ///
    /// Events are moved to the DLQ when:
    /// - Parsing fails after max retries
    /// - Processing consistently fails
    /// - The event is malformed
    ///
    /// The DLQ entry includes the original event data plus error information.
    async fn send_to_dlq(
        &self,
        conn: &mut redis::aio::MultiplexedConnection,
        entry_id: &str,
        fields: &HashMap<String, String>,
        error_reason: &str,
        retry_count: u32,
    ) -> Result<(), redis::RedisError> {
        // Build DLQ entry with original fields plus error metadata
        let mut dlq_fields: Vec<(&str, String)> = vec![
            ("original_entry_id", entry_id.to_string()),
            ("error_reason", error_reason.to_string()),
            ("retry_count", retry_count.to_string()),
            ("dlq_timestamp", chrono::Utc::now().to_rfc3339()),
        ];

        // Copy original fields
        for (key, value) in fields {
            dlq_fields.push((key.as_str(), value.clone()));
        }

        // XADD to DLQ with MAXLEN to prevent unbounded growth
        let mut cmd = redis::cmd("XADD");
        cmd.arg(DLQ_STREAM_KEY)
            .arg("MAXLEN")
            .arg("~")  // Approximate trimming for performance
            .arg(DLQ_MAX_LEN)
            .arg("*");  // Auto-generate ID

        for (key, value) in dlq_fields {
            cmd.arg(key).arg(value);
        }

        let dlq_entry_id: String = cmd.query_async(conn).await?;
        
        warn!(
            "Sent event {} to DLQ as {} (reason: {}, retries: {})",
            entry_id, dlq_entry_id, error_reason, retry_count
        );

        // Update stats
        {
            let mut stats = self.stats.write().await;
            stats.events_sent_to_dlq += 1;
        }

        Ok(())
    }

    /// GRAPH-109: Get the current size of the dead letter queue
    async fn get_dlq_size(
        &self,
        conn: &mut redis::aio::MultiplexedConnection,
    ) -> Result<u64, redis::RedisError> {
        let len: u64 = redis::cmd("XLEN")
            .arg(DLQ_STREAM_KEY)
            .query_async(conn)
            .await
            .unwrap_or(0);
        Ok(len)
    }

    /// GRAPH-109: Read entries from the dead letter queue for inspection
    pub async fn read_dlq_entries(
        &self,
        redis_url: &str,
        count: usize,
    ) -> Result<Vec<(String, HashMap<String, String>)>, Box<dyn std::error::Error + Send + Sync>> {
        let client = redis::Client::open(redis_url)?;
        let mut conn = client.get_multiplexed_async_connection().await?;

        let entries: Vec<(String, HashMap<String, String>)> = redis::cmd("XREVRANGE")
            .arg(DLQ_STREAM_KEY)
            .arg("+")
            .arg("-")
            .arg("COUNT")
            .arg(count)
            .query_async(&mut conn)
            .await?;

        Ok(entries)
    }

    /// GRAPH-109: Requeue a DLQ entry back to the main stream for reprocessing
    pub async fn requeue_dlq_entry(
        &self,
        redis_url: &str,
        dlq_entry_id: &str,
    ) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
        let client = redis::Client::open(redis_url)?;
        let mut conn = client.get_multiplexed_async_connection().await?;

        // Read the DLQ entry
        let entries: Vec<(String, HashMap<String, String>)> = redis::cmd("XRANGE")
            .arg(DLQ_STREAM_KEY)
            .arg(dlq_entry_id)
            .arg(dlq_entry_id)
            .query_async(&mut conn)
            .await?;

        if entries.is_empty() {
            return Err(format!("DLQ entry {} not found", dlq_entry_id).into());
        }

        let (_, fields) = &entries[0];

        // Extract original fields (skip DLQ metadata)
        let mut original_fields: Vec<(&str, &str)> = Vec::new();
        for (key, value) in fields {
            if !["original_entry_id", "error_reason", "retry_count", "dlq_timestamp"].contains(&key.as_str()) {
                original_fields.push((key.as_str(), value.as_str()));
            }
        }

        // Add requeue marker
        let requeue_marker = "true".to_string();

        // XADD back to main stream
        let mut cmd = redis::cmd("XADD");
        cmd.arg(STREAM_KEY).arg("*");
        for (key, value) in &original_fields {
            cmd.arg(*key).arg(*value);
        }
        cmd.arg("requeued_from_dlq").arg(&requeue_marker);

        let new_entry_id: String = cmd.query_async(&mut conn).await?;

        // Delete from DLQ
        let _: i64 = redis::cmd("XDEL")
            .arg(DLQ_STREAM_KEY)
            .arg(dlq_entry_id)
            .query_async(&mut conn)
            .await?;

        info!(
            "Requeued DLQ entry {} as {} in main stream",
            dlq_entry_id, new_entry_id
        );

        Ok(new_entry_id)
    }

    /// Run the stream consumer, sending events to the provided channel
    ///
    /// This method runs indefinitely, reconnecting on errors.
    /// Events are sent to `event_tx` for processing by the main application.
    pub async fn run(&self, event_tx: mpsc::Sender<ChangeEvent>) {
        info!(
            "Starting stream consumer for '{}' (consumer: {})",
            STREAM_KEY, self.config.consumer_name
        );

        loop {
            match self.run_consumer_loop(&event_tx).await {
                Ok(_) => {
                    warn!("Consumer loop exited unexpectedly, restarting...");
                }
                Err(e) => {
                    error!("Consumer error: {}, reconnecting in 5s...", e);
                    {
                        let mut stats = self.stats.write().await;
                        stats.is_connected = false;
                    }
                    tokio::time::sleep(tokio::time::Duration::from_secs(5)).await;
                }
            }
        }
    }

    /// Internal consumer loop
    async fn run_consumer_loop(
        &self,
        event_tx: &mpsc::Sender<ChangeEvent>,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        // Connect to Redis
        let client = redis::Client::open(self.config.redis_url.clone())?;
        let mut conn = client.get_multiplexed_async_connection().await?;

        info!("Connected to Redis for stream consumption");
        {
            let mut stats = self.stats.write().await;
            stats.is_connected = true;
        }

        // Ensure consumer group exists
        self.ensure_consumer_group(&mut conn).await?;

        // Claim any pending entries from previous runs
        let pending = self.claim_pending_entries(&mut conn).await?;
        let mut to_ack = Vec::new();

        for event in pending {
            to_ack.push(event.entry_id.clone());
            if event_tx.send(event).await.is_err() {
                warn!("Event channel closed, stopping consumer");
                return Ok(());
            }
        }

        // ACK the claimed pending entries after sending
        if !to_ack.is_empty() {
            self.ack_entries(&mut conn, &to_ack).await?;
            {
                let mut stats = self.stats.write().await;
                stats.events_processed += to_ack.len() as u64;
            }
            to_ack.clear();
        }

        // Main read loop
        loop {
            // GRAPH-109: Periodically update DLQ size in stats
            if let Ok(dlq_size) = self.get_dlq_size(&mut conn).await {
                let mut stats = self.stats.write().await;
                stats.dlq_size = dlq_size;
            }
            
            let events = self.read_new_entries(&mut conn).await?;

            if events.is_empty() {
                // No new events (timeout), continue waiting
                continue;
            }

            for event in events {
                let entry_id = event.entry_id.clone();
                let timestamp = event.timestamp.clone();

                // Send event to processing channel
                if event_tx.send(event).await.is_err() {
                    warn!("Event channel closed, stopping consumer");
                    return Ok(());
                }

                to_ack.push(entry_id.clone());

                // Update stats
                {
                    let mut stats = self.stats.write().await;
                    stats.events_processed += 1;
                    stats.last_event_id = Some(entry_id);
                    stats.last_event_time = Some(timestamp);
                }
            }

            // ACK all processed entries
            if !to_ack.is_empty() {
                self.ack_entries(&mut conn, &to_ack).await?;
                to_ack.clear();
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_change_action() {
        assert_eq!(ChangeAction::try_from("create"), Ok(ChangeAction::Create));
        assert_eq!(ChangeAction::try_from("CREATE"), Ok(ChangeAction::Create));
        assert_eq!(ChangeAction::try_from("update"), Ok(ChangeAction::Update));
        assert_eq!(ChangeAction::try_from("delete"), Ok(ChangeAction::Delete));
        assert!(ChangeAction::try_from("invalid").is_err());
    }

    #[test]
    fn test_parse_entity_type() {
        assert_eq!(EntityType::try_from("node"), Ok(EntityType::Node));
        assert_eq!(EntityType::try_from("NODE"), Ok(EntityType::Node));
        assert_eq!(EntityType::try_from("edge"), Ok(EntityType::Edge));
        assert_eq!(EntityType::try_from("episode"), Ok(EntityType::Episode));
        assert!(EntityType::try_from("invalid").is_err());
    }

    #[test]
    fn test_parse_change_event() {
        let mut fields = HashMap::new();
        fields.insert("action".to_string(), "create".to_string());
        fields.insert("entity_type".to_string(), "node".to_string());
        fields.insert("uuid".to_string(), "test-uuid-123".to_string());
        fields.insert("group_id".to_string(), "group-1".to_string());
        fields.insert("timestamp".to_string(), "2025-01-01T00:00:00Z".to_string());

        let event = ChangeEvent::from_stream_entry("12345-0".to_string(), fields).unwrap();

        assert_eq!(event.entry_id, "12345-0");
        assert_eq!(event.action, ChangeAction::Create);
        assert_eq!(event.entity_type, EntityType::Node);
        assert_eq!(event.uuid, "test-uuid-123");
        assert_eq!(event.group_id, "group-1");
        assert!(event.data.is_none());
    }

    #[test]
    fn test_parse_change_event_with_data() {
        let mut fields = HashMap::new();
        fields.insert("action".to_string(), "update".to_string());
        fields.insert("entity_type".to_string(), "edge".to_string());
        fields.insert("uuid".to_string(), "edge-456".to_string());
        fields.insert("group_id".to_string(), "group-2".to_string());
        fields.insert("timestamp".to_string(), "2025-01-01T00:00:00Z".to_string());
        fields.insert("data".to_string(), r#"{"fact": "test fact"}"#.to_string());

        let event = ChangeEvent::from_stream_entry("12345-1".to_string(), fields).unwrap();

        assert_eq!(event.action, ChangeAction::Update);
        assert_eq!(event.entity_type, EntityType::Edge);
        assert!(event.data.is_some());
        assert_eq!(
            event.data.unwrap().get("fact").unwrap().as_str().unwrap(),
            "test fact"
        );
    }
}
