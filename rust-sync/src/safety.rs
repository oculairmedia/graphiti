//! Safety validation to prevent accidental data loss during sync operations.
//!
//! This module implements pre-sync validation checks that block dangerous operations
//! where the target database would lose a significant amount of data.

use crate::error::{Result, SyncError};
use serde::{Deserialize, Serialize};
use std::fmt;
use tracing::{error, info, warn};

/// Safety validation report
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetyReport {
    pub is_safe: bool,
    pub direction: String,
    pub checks: Vec<SafetyCheck>,
    pub summary: String,
}

/// Individual safety check result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SafetyCheck {
    pub check_type: String,
    pub source_count: usize,
    pub target_count: usize,
    pub reduction_pct: f64,
    pub threshold_pct: f64,
    pub is_safe: bool,
    pub message: String,
}

impl SafetyCheck {
    fn new(
        check_type: &str,
        source_count: usize,
        target_count: usize,
        threshold_pct: f64,
    ) -> Self {
        let is_safe = Self::validate_reduction(source_count, target_count, threshold_pct);
        let reduction_pct = Self::calculate_reduction_pct(source_count, target_count);

        let message = if !is_safe {
            format!(
                "❌ UNSAFE: {} would lose {:.1}% of data ({} → {}). Threshold: {:.1}%",
                check_type, reduction_pct, target_count, source_count, threshold_pct
            )
        } else if reduction_pct > 0.0 {
            format!(
                "⚠️  WARNING: {} will lose {:.1}% of data ({} → {})",
                check_type, reduction_pct, target_count, source_count
            )
        } else if source_count > target_count {
            format!(
                "✅ SAFE: {} will gain data ({} → {})",
                check_type, target_count, source_count
            )
        } else if source_count == target_count {
            format!("✅ SAFE: {} counts match ({} = {})", check_type, target_count, source_count)
        } else {
            format!(
                "✅ SAFE: {} within acceptable threshold ({} → {})",
                check_type, target_count, source_count
            )
        };

        Self {
            check_type: check_type.to_string(),
            source_count,
            target_count,
            reduction_pct,
            threshold_pct,
            is_safe,
            message,
        }
    }

    fn validate_reduction(source_count: usize, target_count: usize, threshold_pct: f64) -> bool {
        if target_count == 0 {
            return source_count == 0;
        }

        if source_count >= target_count {
            return true;
        }

        let reduction_pct = Self::calculate_reduction_pct(source_count, target_count);
        reduction_pct <= threshold_pct
    }

    fn calculate_reduction_pct(source_count: usize, target_count: usize) -> f64 {
        if target_count == 0 {
            return 0.0;
        }

        if source_count >= target_count {
            return 0.0;
        }

        ((target_count - source_count) as f64 / target_count as f64) * 100.0
    }
}

impl fmt::Display for SafetyCheck {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl SafetyReport {
    pub fn new(direction: String) -> Self {
        Self {
            is_safe: true,
            direction,
            checks: Vec::new(),
            summary: String::new(),
        }
    }

    pub fn add_check(&mut self, check: SafetyCheck) {
        if !check.is_safe {
            self.is_safe = false;
        }
        self.checks.push(check);
    }

    pub fn finalize(&mut self) {
        let total_checks = self.checks.len();
        let safe_checks = self.checks.iter().filter(|c| c.is_safe).count();
        let unsafe_checks = total_checks - safe_checks;

        if self.is_safe {
            self.summary = format!(
                "✅ All {} safety checks passed for {} sync",
                total_checks, self.direction
            );
        } else {
            self.summary = format!(
                "❌ BLOCKED: {} of {} safety checks failed for {} sync",
                unsafe_checks, total_checks, self.direction
            );
        }
    }

    pub fn log(&self) {
        info!("🛡️  Safety Validation Report");
        info!("   Direction: {}", self.direction);
        info!("   Status: {}", if self.is_safe { "SAFE ✅" } else { "UNSAFE ❌" });
        info!("");

        for check in &self.checks {
            if check.is_safe {
                info!("   {}", check);
            } else {
                error!("   {}", check);
            }
        }

        info!("");
        if self.is_safe {
            info!("   {}", self.summary);
        } else {
            error!("   {}", self.summary);
        }
    }
}

/// Safety validator configuration
#[derive(Debug, Clone)]
pub struct SafetyConfig {
    pub enabled: bool,
    pub node_reduction_threshold_pct: f64,
    pub edge_reduction_threshold_pct: f64,
    pub force_unsafe_sync: bool,
}

impl Default for SafetyConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            node_reduction_threshold_pct: 50.0,
            edge_reduction_threshold_pct: 50.0,
            force_unsafe_sync: false,
        }
    }
}

impl SafetyConfig {
    pub fn from_env() -> Self {
        let enabled = std::env::var("SYNC_SAFETY_ENABLED")
            .ok()
            .and_then(|v| v.parse::<bool>().ok())
            .unwrap_or(true);

        let node_threshold = std::env::var("SYNC_SAFETY_NODE_THRESHOLD_PCT")
            .ok()
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(50.0);

        let edge_threshold = std::env::var("SYNC_SAFETY_EDGE_THRESHOLD_PCT")
            .ok()
            .and_then(|v| v.parse::<f64>().ok())
            .unwrap_or(50.0);

        let force_unsafe = std::env::var("FORCE_UNSAFE_SYNC")
            .ok()
            .and_then(|v| v.parse::<bool>().ok())
            .unwrap_or(false);

        Self {
            enabled,
            node_reduction_threshold_pct: node_threshold,
            edge_reduction_threshold_pct: edge_threshold,
            force_unsafe_sync: force_unsafe,
        }
    }
}

/// Safety validator for sync operations
pub struct SafetyValidator {
    config: SafetyConfig,
}

impl SafetyValidator {
    pub fn new(config: SafetyConfig) -> Self {
        Self { config }
    }

    pub fn from_env() -> Self {
        Self::new(SafetyConfig::from_env())
    }

    /// Validate a sync operation is safe to proceed
    pub fn validate_sync(
        &self,
        direction: &str,
        source_entities: usize,
        source_episodic: usize,
        source_community: usize,
        source_edges: usize,
        target_entities: usize,
        target_episodic: usize,
        target_community: usize,
        target_edges: usize,
    ) -> Result<SafetyReport> {
        if !self.config.enabled {
            info!("🛡️  Safety validation disabled");
            let mut report = SafetyReport::new(direction.to_string());
            report.summary = "Safety validation disabled".to_string();
            return Ok(report);
        }

        if self.config.force_unsafe_sync {
            warn!("⚠️  FORCE_UNSAFE_SYNC enabled - bypassing safety checks!");
            let mut report = SafetyReport::new(direction.to_string());
            report.summary = "Safety checks bypassed with FORCE_UNSAFE_SYNC".to_string();
            return Ok(report);
        }

        let mut report = SafetyReport::new(direction.to_string());

        report.add_check(SafetyCheck::new(
            "Entity nodes",
            source_entities,
            target_entities,
            self.config.node_reduction_threshold_pct,
        ));

        report.add_check(SafetyCheck::new(
            "Episodic nodes",
            source_episodic,
            target_episodic,
            self.config.node_reduction_threshold_pct,
        ));

        report.add_check(SafetyCheck::new(
            "Community nodes",
            source_community,
            target_community,
            self.config.node_reduction_threshold_pct,
        ));

        report.add_check(SafetyCheck::new(
            "Edges",
            source_edges,
            target_edges,
            self.config.edge_reduction_threshold_pct,
        ));

        report.finalize();
        report.log();

        if !report.is_safe {
            return Err(SyncError::SafetyValidation(format!(
                "Sync blocked by safety validation: {}. Use FORCE_UNSAFE_SYNC=true to override.",
                report.summary
            )));
        }

        Ok(report)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_safety_check_no_reduction() {
        let check = SafetyCheck::new("Test nodes", 100, 100, 50.0);
        assert!(check.is_safe);
        assert_eq!(check.reduction_pct, 0.0);
    }

    #[test]
    fn test_safety_check_growth() {
        let check = SafetyCheck::new("Test nodes", 150, 100, 50.0);
        assert!(check.is_safe);
        assert_eq!(check.reduction_pct, 0.0);
    }

    #[test]
    fn test_safety_check_safe_reduction() {
        let check = SafetyCheck::new("Test nodes", 75, 100, 50.0);
        assert!(check.is_safe);
        assert_eq!(check.reduction_pct, 25.0);
    }

    #[test]
    fn test_safety_check_unsafe_reduction() {
        let check = SafetyCheck::new("Test nodes", 40, 100, 50.0);
        assert!(!check.is_safe);
        assert_eq!(check.reduction_pct, 60.0);
    }

    #[test]
    fn test_safety_check_zero_target() {
        let check = SafetyCheck::new("Test nodes", 0, 0, 50.0);
        assert!(check.is_safe);
        assert_eq!(check.reduction_pct, 0.0);
    }

    #[test]
    fn test_safety_check_zero_source_nonzero_target() {
        let check = SafetyCheck::new("Test nodes", 0, 100, 50.0);
        assert!(!check.is_safe);
        assert_eq!(check.reduction_pct, 100.0);
    }

    #[test]
    fn test_safety_validator_all_safe() {
        let validator = SafetyValidator::new(SafetyConfig::default());
        let result = validator.validate_sync(
            "test-sync",
            100, 50, 20, 200,  // source
            100, 50, 20, 200,  // target
        );
        assert!(result.is_ok());
        let report = result.unwrap();
        assert!(report.is_safe);
    }

    #[test]
    fn test_safety_validator_unsafe_nodes() {
        let validator = SafetyValidator::new(SafetyConfig::default());
        let result = validator.validate_sync(
            "test-sync",
            40, 50, 20, 200,   // source: only 40 entities (60% reduction)
            100, 50, 20, 200,  // target
        );
        assert!(result.is_err());
    }

    #[test]
    fn test_safety_validator_unsafe_edges() {
        let validator = SafetyValidator::new(SafetyConfig::default());
        let result = validator.validate_sync(
            "test-sync",
            100, 50, 20, 80,   // source: only 80 edges (60% reduction)
            100, 50, 20, 200,  // target
        );
        assert!(result.is_err());
    }

    #[test]
    fn test_safety_validator_force_override() {
        let mut config = SafetyConfig::default();
        config.force_unsafe_sync = true;
        let validator = SafetyValidator::new(config);
        let result = validator.validate_sync(
            "test-sync",
            10, 10, 10, 10,    // source: massive reduction
            100, 100, 100, 100, // target
        );
        assert!(result.is_ok());
    }

    #[test]
    fn test_safety_validator_disabled() {
        let mut config = SafetyConfig::default();
        config.enabled = false;
        let validator = SafetyValidator::new(config);
        let result = validator.validate_sync(
            "test-sync",
            10, 10, 10, 10,
            100, 100, 100, 100,
        );
        assert!(result.is_ok());
    }
}
