use axum::{
    http::{header::CONTENT_TYPE, HeaderValue, StatusCode},
    response::IntoResponse,
    routing::get,
    Router,
};
use std::net::SocketAddr;
use tokio::task::JoinHandle;
use tower::make::Shared;
use tower_http::trace::TraceLayer;
use tracing::{error, info};

use crate::error::Result;
use crate::metrics;

pub struct MetricsServer {
    addr: SocketAddr,
    handle: Option<JoinHandle<()>>,
}

impl MetricsServer {
    pub fn new(port: u16) -> Self {
        Self {
            addr: SocketAddr::from(([0, 0, 0, 0], port)),
            handle: None,
        }
    }

    pub async fn start(&mut self) -> Result<()> {
        let router = Router::new()
            .route("/metrics", get(metrics_handler))
            .layer(TraceLayer::new_for_http());

        let listener = tokio::net::TcpListener::bind(self.addr)
            .await
            .map_err(|e| {
                crate::error::SyncError::Orchestration(format!(
                    "Failed to bind metrics server: {}",
                    e
                ))
            })?;

        info!("Metrics server listening on {}", self.addr);

        let service = router.into_service();
        let make_service = Shared::new(service);

        let handle = tokio::spawn(async move {
            if let Err(err) = axum::serve(listener, make_service).await {
                error!("Metrics server error: {}", err);
            }
        });

        self.handle = Some(handle);

        Ok(())
    }

    pub async fn stop(&mut self) {
        if let Some(handle) = self.handle.take() {
            handle.abort();
        }
    }
}

async fn metrics_handler() -> impl IntoResponse {
    match metrics::gather() {
        Ok(body) => (
            StatusCode::OK,
            [(
                CONTENT_TYPE,
                HeaderValue::from_static("text/plain; version=0.0.4"),
            )],
            body,
        )
            .into_response(),
        Err(err) => (StatusCode::INTERNAL_SERVER_ERROR, err).into_response(),
    }
}
