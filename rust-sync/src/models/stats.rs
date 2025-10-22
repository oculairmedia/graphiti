use serde::{Deserialize, Serialize};
use std::time::Duration;

/// Statistics from extraction operations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExtractionStats {
    pub total_nodes: usize,
    pub total_edges: usize,
    pub duration: Duration,
}

impl ExtractionStats {
    pub fn new() -> Self {
        Self {
            total_nodes: 0,
            total_edges: 0,
            duration: Duration::from_secs(0),
        }
    }
}

impl Default for ExtractionStats {
    fn default() -> Self {
        Self::new()
    }
}

/// Statistics from loading operations
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LoadingStats {
    pub nodes_loaded: usize,
    pub edges_loaded: usize,
    pub duration: Duration,
}

impl LoadingStats {
    pub fn new() -> Self {
        Self {
            nodes_loaded: 0,
            edges_loaded: 0,
            duration: Duration::from_secs(0),
        }
    }
}

impl Default for LoadingStats {
    fn default() -> Self {
        Self::new()
    }
}

/// Overall sync statistics
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncStats {
    pub nodes_synced: usize,
    pub edges_synced: usize,
    pub extraction_duration: Duration,
    pub loading_duration: Duration,
    pub total_duration: Duration,
}

impl SyncStats {
    pub fn from_extraction_and_loading(extraction: ExtractionStats, loading: LoadingStats) -> Self {
        let total_duration = extraction.duration + loading.duration;

        Self {
            nodes_synced: extraction.total_nodes,
            edges_synced: extraction.total_edges,
            extraction_duration: extraction.duration,
            loading_duration: loading.duration,
            total_duration,
        }
    }

    pub fn nodes_per_second(&self) -> f64 {
        if self.total_duration.as_secs() == 0 {
            0.0
        } else {
            self.nodes_synced as f64 / self.total_duration.as_secs_f64()
        }
    }

    pub fn edges_per_second(&self) -> f64 {
        if self.total_duration.as_secs() == 0 {
            0.0
        } else {
            self.edges_synced as f64 / self.total_duration.as_secs_f64()
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_sync_stats_calculation() {
        let extraction = ExtractionStats {
            total_nodes: 1000,
            total_edges: 500,
            duration: Duration::from_secs(5),
        };

        let loading = LoadingStats {
            nodes_loaded: 1000,
            edges_loaded: 500,
            duration: Duration::from_secs(3),
        };

        let stats = SyncStats::from_extraction_and_loading(extraction, loading);

        assert_eq!(stats.nodes_synced, 1000);
        assert_eq!(stats.edges_synced, 500);
        assert_eq!(stats.total_duration, Duration::from_secs(8));
        assert_eq!(stats.nodes_per_second(), 125.0); // 1000 / 8
    }
}
