//! Disaster recovery detection and automatic recovery procedures.
//!
//! This module detects catastrophic database failures (e.g., empty target database
//! when source has data) and triggers automatic recovery procedures.

use crate::config::Settings;
use crate::error::{Result, SyncError};
use crate::extractors::{FalkorDBExtractor, Neo4jExtractor};
use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};
use tracing::{error, info, warn};

/// Disaster recovery state
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum DisasterState {
    /// No disaster detected - normal operation
    Normal,
    /// Target database is empty but source has data
    TargetEmpty,
    /// Source database is empty but target has data (reverse direction issue)
    SourceEmpty,
    /// Both databases are empty
    BothEmpty,
    /// Recovery is in progress
    RecoveryInProgress,
    /// Recovery completed successfully
    RecoveryComplete,
}

impl std::fmt::Display for DisasterState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DisasterState::Normal => write!(f, "Normal"),
            DisasterState::TargetEmpty => write!(f, "Target Empty"),
            DisasterState::SourceEmpty => write!(f, "Source Empty"),
            DisasterState::BothEmpty => write!(f, "Both Empty"),
            DisasterState::RecoveryInProgress => write!(f, "Recovery In Progress"),
            DisasterState::RecoveryComplete => write!(f, "Recovery Complete"),
        }
    }
}

/// Disaster recovery report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DisasterReport {
    pub state: DisasterState,
    pub direction: String,
    pub source_name: String,
    pub target_name: String,
    pub source_total: usize,
    pub target_total: usize,
    pub timestamp: u64,
    pub recovery_recommended: bool,
    pub message: String,
}

impl DisasterReport {
    pub fn new(
        state: DisasterState,
        direction: String,
        source_name: String,
        target_name: String,
        source_total: usize,
        target_total: usize,
    ) -> Self {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();

        let (recovery_recommended, message) = match &state {
            DisasterState::Normal => (
                false,
                format!(
                    "✅ Normal state: {} has {} items, {} has {} items",
                    source_name, source_total, target_name, target_total
                ),
            ),
            DisasterState::TargetEmpty => (
                true,
                format!(
                    "🚨 DISASTER DETECTED: {} is EMPTY but {} has {} items! Recovery recommended.",
                    target_name, source_name, source_total
                ),
            ),
            DisasterState::SourceEmpty => (
                false,
                format!(
                    "⚠️  WARNING: {} is EMPTY but {} has {} items. Check sync direction!",
                    source_name, target_name, target_total
                ),
            ),
            DisasterState::BothEmpty => (
                false,
                format!("ℹ️  Both {} and {} are empty - new installation", source_name, target_name),
            ),
            DisasterState::RecoveryInProgress => (
                false,
                format!("🔄 Recovery in progress from {} to {}", source_name, target_name),
            ),
            DisasterState::RecoveryComplete => (
                false,
                format!("✅ Recovery complete: {} → {}", source_name, target_name),
            ),
        };

        Self {
            state,
            direction,
            source_name,
            target_name,
            source_total,
            target_total,
            timestamp,
            recovery_recommended,
            message,
        }
    }

    pub fn log(&self) {
        match self.state {
            DisasterState::Normal => info!("🛡️  Disaster Recovery Check: {}", self.message),
            DisasterState::TargetEmpty => {
                error!("🚨 DISASTER RECOVERY ALERT");
                error!("   Direction: {}", self.direction);
                error!("   Source ({}): {} items", self.source_name, self.source_total);
                error!("   Target ({}): {} items (EMPTY!)", self.target_name, self.target_total);
                error!("   {}", self.message);
            }
            DisasterState::SourceEmpty => {
                warn!("⚠️  Disaster Recovery Check");
                warn!("   Direction: {}", self.direction);
                warn!("   Source ({}): {} items (EMPTY!)", self.source_name, self.source_total);
                warn!("   Target ({}): {} items", self.target_name, self.target_total);
                warn!("   {}", self.message);
            }
            DisasterState::BothEmpty => {
                info!("ℹ️  Disaster Recovery Check: {}", self.message);
            }
            DisasterState::RecoveryInProgress => {
                info!("🔄 {}", self.message);
            }
            DisasterState::RecoveryComplete => {
                info!("✅ {}", self.message);
            }
        }
    }
}

/// Disaster recovery detector configuration
#[derive(Debug, Clone)]
pub struct DisasterRecoveryConfig {
    pub enabled: bool,
    pub auto_recover: bool,
    pub min_source_items: usize,
}

impl Default for DisasterRecoveryConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            auto_recover: false,
            min_source_items: 1,
        }
    }
}

impl DisasterRecoveryConfig {
    pub fn from_env() -> Self {
        let enabled = std::env::var("SYNC_DISASTER_RECOVERY_ENABLED")
            .ok()
            .and_then(|v| v.parse::<bool>().ok())
            .unwrap_or(true);

        let auto_recover = std::env::var("SYNC_DISASTER_AUTO_RECOVER")
            .ok()
            .and_then(|v| v.parse::<bool>().ok())
            .unwrap_or(false);

        let min_source_items = std::env::var("SYNC_DISASTER_MIN_SOURCE_ITEMS")
            .ok()
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(1);

        Self {
            enabled,
            auto_recover,
            min_source_items,
        }
    }
}

/// Disaster recovery detector
pub struct DisasterRecoveryDetector {
    config: DisasterRecoveryConfig,
}

impl DisasterRecoveryDetector {
    pub fn new(config: DisasterRecoveryConfig) -> Self {
        Self { config }
    }

    pub fn from_env() -> Self {
        Self::new(DisasterRecoveryConfig::from_env())
    }

    /// Detect disaster state for Neo4j → FalkorDB direction
    pub async fn detect_neo4j_to_falkor(
        &self,
        settings: &Settings,
    ) -> Result<DisasterReport> {
        if !self.config.enabled {
            info!("🛡️  Disaster recovery detection disabled");
            return Ok(DisasterReport::new(
                DisasterState::Normal,
                "neo4j-to-falkor".to_string(),
                "Neo4j".to_string(),
                "FalkorDB".to_string(),
                0,
                0,
            ));
        }

        info!("🔍 Checking for disaster state (Neo4j → FalkorDB)");

        let neo4j_extractor = Neo4jExtractor::new(&settings.neo4j, &settings.sync).await?;
        let mut falkor_extractor = FalkorDBExtractor::new(&settings.falkordb, &settings.sync).await?;

        let neo4j_entities = neo4j_extractor.count_nodes("Entity").await?;
        let neo4j_episodic = neo4j_extractor.count_nodes("Episodic").await?;
        let neo4j_community = neo4j_extractor.count_nodes("Community").await?;
        let neo4j_edges = neo4j_extractor.count_edges().await?;
        let neo4j_total = neo4j_entities + neo4j_episodic + neo4j_community + neo4j_edges;

        let falkor_entities = falkor_extractor.count_nodes("Entity").await?;
        let falkor_episodic = falkor_extractor.count_nodes("Episodic").await?;
        let falkor_community = falkor_extractor.count_nodes("Community").await?;
        let falkor_edges = falkor_extractor.count_edges().await?;
        let falkor_total = falkor_entities + falkor_episodic + falkor_community + falkor_edges;

        let state = self.determine_state(neo4j_total, falkor_total);

        let report = DisasterReport::new(
            state,
            "neo4j-to-falkor".to_string(),
            "Neo4j".to_string(),
            "FalkorDB".to_string(),
            neo4j_total,
            falkor_total,
        );

        report.log();
        Ok(report)
    }

    /// Detect disaster state for FalkorDB → Neo4j direction
    pub async fn detect_falkor_to_neo4j(
        &self,
        settings: &Settings,
    ) -> Result<DisasterReport> {
        if !self.config.enabled {
            info!("🛡️  Disaster recovery detection disabled");
            return Ok(DisasterReport::new(
                DisasterState::Normal,
                "falkor-to-neo4j".to_string(),
                "FalkorDB".to_string(),
                "Neo4j".to_string(),
                0,
                0,
            ));
        }

        info!("🔍 Checking for disaster state (FalkorDB → Neo4j)");

        let mut falkor_extractor = FalkorDBExtractor::new(&settings.falkordb, &settings.sync).await?;
        let neo4j_extractor = Neo4jExtractor::new(&settings.neo4j, &settings.sync).await?;

        let falkor_entities = falkor_extractor.count_nodes("Entity").await?;
        let falkor_episodic = falkor_extractor.count_nodes("Episodic").await?;
        let falkor_community = falkor_extractor.count_nodes("Community").await?;
        let falkor_edges = falkor_extractor.count_edges().await?;
        let falkor_total = falkor_entities + falkor_episodic + falkor_community + falkor_edges;

        let neo4j_entities = neo4j_extractor.count_nodes("Entity").await?;
        let neo4j_episodic = neo4j_extractor.count_nodes("Episodic").await?;
        let neo4j_community = neo4j_extractor.count_nodes("Community").await?;
        let neo4j_edges = neo4j_extractor.count_edges().await?;
        let neo4j_total = neo4j_entities + neo4j_episodic + neo4j_community + neo4j_edges;

        let state = self.determine_state(falkor_total, neo4j_total);

        let report = DisasterReport::new(
            state,
            "falkor-to-neo4j".to_string(),
            "FalkorDB".to_string(),
            "Neo4j".to_string(),
            falkor_total,
            neo4j_total,
        );

        report.log();
        Ok(report)
    }

    fn determine_state(&self, source_total: usize, target_total: usize) -> DisasterState {
        if source_total == 0 && target_total == 0 {
            DisasterState::BothEmpty
        } else if source_total >= self.config.min_source_items && target_total == 0 {
            DisasterState::TargetEmpty
        } else if source_total == 0 && target_total > 0 {
            DisasterState::SourceEmpty
        } else {
            DisasterState::Normal
        }
    }

    /// Check if automatic recovery should be triggered
    pub fn should_auto_recover(&self, report: &DisasterReport) -> bool {
        self.config.auto_recover 
            && report.state == DisasterState::TargetEmpty 
            && report.recovery_recommended
    }
}

/// Recovery state tracker to prevent loops
#[derive(Debug, Clone)]
pub struct RecoveryStateTracker {
    last_recovery_attempt: Option<u64>,
    recovery_count: usize,
    max_recovery_attempts: usize,
    cooldown_seconds: u64,
}

impl Default for RecoveryStateTracker {
    fn default() -> Self {
        Self {
            last_recovery_attempt: None,
            recovery_count: 0,
            max_recovery_attempts: 3,
            cooldown_seconds: 3600, // 1 hour
        }
    }
}

impl RecoveryStateTracker {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn from_env() -> Self {
        let max_attempts = std::env::var("SYNC_DISASTER_MAX_RECOVERY_ATTEMPTS")
            .ok()
            .and_then(|v| v.parse::<usize>().ok())
            .unwrap_or(3);

        let cooldown = std::env::var("SYNC_DISASTER_RECOVERY_COOLDOWN_SECONDS")
            .ok()
            .and_then(|v| v.parse::<u64>().ok())
            .unwrap_or(3600);

        Self {
            last_recovery_attempt: None,
            recovery_count: 0,
            max_recovery_attempts: max_attempts,
            cooldown_seconds: cooldown,
        }
    }

    /// Check if recovery is allowed (not in cooldown, under max attempts)
    pub fn can_recover(&self) -> bool {
        if self.recovery_count >= self.max_recovery_attempts {
            error!(
                "❌ Recovery blocked: Maximum attempts ({}) reached",
                self.max_recovery_attempts
            );
            return false;
        }

        if let Some(last_attempt) = self.last_recovery_attempt {
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_secs();

            if now - last_attempt < self.cooldown_seconds {
                let remaining = self.cooldown_seconds - (now - last_attempt);
                warn!(
                    "⏳ Recovery blocked: Cooldown active ({} seconds remaining)",
                    remaining
                );
                return false;
            }
        }

        true
    }

    /// Mark recovery attempt
    pub fn mark_recovery_attempt(&mut self) {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs();

        self.last_recovery_attempt = Some(now);
        self.recovery_count += 1;

        info!(
            "🔄 Recovery attempt {} of {}",
            self.recovery_count, self.max_recovery_attempts
        );
    }

    /// Reset recovery tracking (call after successful recovery)
    pub fn reset(&mut self) {
        info!("✅ Recovery tracking reset");
        self.last_recovery_attempt = None;
        self.recovery_count = 0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_disaster_state_both_empty() {
        let detector = DisasterRecoveryDetector::new(DisasterRecoveryConfig::default());
        let state = detector.determine_state(0, 0);
        assert_eq!(state, DisasterState::BothEmpty);
    }

    #[test]
    fn test_disaster_state_target_empty() {
        let detector = DisasterRecoveryDetector::new(DisasterRecoveryConfig::default());
        let state = detector.determine_state(100, 0);
        assert_eq!(state, DisasterState::TargetEmpty);
    }

    #[test]
    fn test_disaster_state_source_empty() {
        let detector = DisasterRecoveryDetector::new(DisasterRecoveryConfig::default());
        let state = detector.determine_state(0, 100);
        assert_eq!(state, DisasterState::SourceEmpty);
    }

    #[test]
    fn test_disaster_state_normal() {
        let detector = DisasterRecoveryDetector::new(DisasterRecoveryConfig::default());
        let state = detector.determine_state(100, 100);
        assert_eq!(state, DisasterState::Normal);
    }

    #[test]
    fn test_min_source_items_threshold() {
        let mut config = DisasterRecoveryConfig::default();
        config.min_source_items = 10;
        let detector = DisasterRecoveryDetector::new(config);

        // Below threshold - should not trigger disaster
        let state = detector.determine_state(5, 0);
        assert_eq!(state, DisasterState::SourceEmpty);

        // At threshold - should trigger disaster
        let state = detector.determine_state(10, 0);
        assert_eq!(state, DisasterState::TargetEmpty);
    }

    #[test]
    fn test_auto_recover_enabled() {
        let mut config = DisasterRecoveryConfig::default();
        config.auto_recover = true;
        let detector = DisasterRecoveryDetector::new(config);

        let report = DisasterReport::new(
            DisasterState::TargetEmpty,
            "test".to_string(),
            "source".to_string(),
            "target".to_string(),
            100,
            0,
        );

        assert!(detector.should_auto_recover(&report));
    }

    #[test]
    fn test_auto_recover_disabled() {
        let mut config = DisasterRecoveryConfig::default();
        config.auto_recover = false;
        let detector = DisasterRecoveryDetector::new(config);

        let report = DisasterReport::new(
            DisasterState::TargetEmpty,
            "test".to_string(),
            "source".to_string(),
            "target".to_string(),
            100,
            0,
        );

        assert!(!detector.should_auto_recover(&report));
    }

    #[test]
    fn test_recovery_tracker_max_attempts() {
        let mut tracker = RecoveryStateTracker::default();

        assert!(tracker.can_recover());
        tracker.mark_recovery_attempt();

        assert!(tracker.can_recover());
        tracker.mark_recovery_attempt();

        assert!(tracker.can_recover());
        tracker.mark_recovery_attempt();

        // Fourth attempt should be blocked
        assert!(!tracker.can_recover());
    }

    #[test]
    fn test_recovery_tracker_reset() {
        let mut tracker = RecoveryStateTracker::default();

        tracker.mark_recovery_attempt();
        tracker.mark_recovery_attempt();
        tracker.mark_recovery_attempt();

        assert!(!tracker.can_recover());

        tracker.reset();
        assert!(tracker.can_recover());
    }
}
