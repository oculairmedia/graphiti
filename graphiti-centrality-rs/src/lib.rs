/*!
# Graphiti Centrality Service

High-performance centrality calculations for Graphiti using FalkorDB's native algorithms.

This library provides:
- PageRank centrality using FalkorDB's built-in algorithm
- Optimized degree centrality calculations  
- Betweenness centrality with sampling
- Composite importance scoring

Performance target: 100-1000x faster than Python implementation.
*/

pub mod algorithms;
pub mod client;
pub mod error;
pub mod models;
pub mod server;

pub use algorithms::*;
pub use client::FalkorClient;
pub use error::{CentralityError, Result};
pub use models::*;