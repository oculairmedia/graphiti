//! Health check HTTP server for monitoring sync service status.
//!
//! Provides endpoints for:
//! - Health checks (liveness and readiness)
//! - Sync status reporting
//! - Database connectivity verification

mod handlers;
mod models;
mod server;

pub use server::HealthServer;
