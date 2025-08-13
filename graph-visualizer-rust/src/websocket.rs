use axum::{
    extract::{State, WebSocketUpgrade, ws::{WebSocket, Message}},
    response::IntoResponse,
};
use serde_json::{json, Value};
use tracing::{info, error, debug};
use uuid::Uuid;

use crate::{AppState, duckdb_store::GraphUpdate, delta_tracker::GraphDelta};

/// Main WebSocket handler that upgrades HTTP connections to WebSocket
pub async fn websocket_handler(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

/// Handles individual WebSocket connections
async fn handle_socket(mut socket: WebSocket, state: AppState) {
    info!("WebSocket connection established");
    
    // Subscribe to broadcast channels
    let mut update_rx = state.update_tx.subscribe();
    let mut delta_rx = state.delta_tx.subscribe();
    
    // Track client for logging
    let client_id = Uuid::new_v4().to_string();
    info!("Client {} connected", client_id);
    
    // Send initial connection confirmation
    if let Err(e) = send_connection_message(&mut socket).await {
        error!("Failed to send connection message: {}", e);
        return;
    }
    
    // Track client preferences
    let mut use_deltas = false;
    
    // Main message loop
    loop {
        tokio::select! {
            // Handle incoming WebSocket messages
            Some(msg) = socket.recv() => {
                match handle_client_message(msg, &mut socket, &mut use_deltas, &client_id, &state).await {
                    MessageResult::Continue => continue,
                    MessageResult::Close => break,
                }
            }
            
            // Broadcast delta updates (preferred)
            Ok(delta) = delta_rx.recv() => {
                info!("Received delta broadcast for client {}", client_id);
                if use_deltas {
                    if let Err(e) = send_delta_update(&mut socket, delta).await {
                        error!("Failed to send delta: {}", e);
                        break;
                    } else {
                        info!("Delta sent successfully to client {}", client_id);
                    }
                }
            }
            
            // Broadcast full updates (fallback for clients that don't use deltas)
            Ok(update) = update_rx.recv() => {
                info!("Received update broadcast for client {}", client_id);
                if !use_deltas {
                    if let Err(e) = send_full_update(&mut socket, update).await {
                        error!("Failed to send update: {}", e);
                        break;
                    } else {
                        info!("Update sent successfully to client {}", client_id);
                    }
                } else {
                    // Client prefers deltas, skip full updates
                    debug!("Skipping full update for client {} (deltas enabled)", client_id);
                }
            }
        }
    }
    
    info!("WebSocket connection closed for client {}", client_id);
}

/// Result type for message handling
enum MessageResult {
    Continue,
    Close,
}

/// Send initial connection confirmation
async fn send_connection_message(socket: &mut WebSocket) -> Result<(), axum::Error> {
    let message = json!({
        "type": "connected",
        "timestamp": get_timestamp(),
        "features": {
            "delta_updates": true,
            "compression": true,
            "batch_updates": true
        }
    });
    
    socket.send(Message::Text(message.to_string())).await
}

/// Handle incoming client messages
async fn handle_client_message(
    msg: Result<Message, axum::Error>,
    socket: &mut WebSocket,
    use_deltas: &mut bool,
    client_id: &str,
    state: &AppState,
) -> MessageResult {
    match msg {
        Ok(Message::Text(text)) => {
            if let Ok(cmd) = serde_json::from_str::<Value>(&text) {
                if let Some(cmd_type) = cmd.get("type").and_then(|t| t.as_str()) {
                    handle_command(cmd_type, socket, use_deltas, client_id, state).await
                } else {
                    MessageResult::Continue
                }
            } else {
                MessageResult::Continue
            }
        }
        Ok(Message::Close(_)) => {
            info!("WebSocket connection closed by client {}", client_id);
            MessageResult::Close
        }
        Err(e) => {
            error!("WebSocket error for client {}: {}", client_id, e);
            MessageResult::Close
        }
        _ => MessageResult::Continue,
    }
}

/// Handle specific client commands
async fn handle_command(
    cmd_type: &str,
    socket: &mut WebSocket,
    use_deltas: &mut bool,
    client_id: &str,
    state: &AppState,
) -> MessageResult {
    match cmd_type {
        "subscribe:deltas" => {
            *use_deltas = true;
            let _ = socket.send(Message::Text(
                json!({
                    "type": "subscribed:deltas",
                    "status": "ok"
                }).to_string()
            )).await;
            info!("Client {} subscribed to delta updates", client_id);
        }
        "unsubscribe:deltas" => {
            *use_deltas = false;
            info!("Client {} unsubscribed from delta updates", client_id);
        }
        "ping" => {
            let _ = socket.send(Message::Text(
                json!({
                    "type": "pong",
                    "timestamp": get_timestamp()
                }).to_string()
            )).await;
        }
        "clear_cache" => {
            info!("Client {} requested cache clear", client_id);
            clear_caches(state).await;
            
            let _ = socket.send(Message::Text(
                json!({
                    "type": "cache_cleared",
                    "timestamp": get_timestamp()
                }).to_string()
            )).await;
        }
        _ => {
            debug!("Unknown command from client {}: {}", client_id, cmd_type);
        }
    }
    MessageResult::Continue
}

/// Clear all caches
async fn clear_caches(state: &AppState) {
    state.graph_cache.clear();
    let mut arrow_cache = state.arrow_cache.write().await;
    *arrow_cache = None;
}

/// Send delta update to client
async fn send_delta_update(socket: &mut WebSocket, delta: GraphDelta) -> Result<(), axum::Error> {
    let msg = json!({
        "type": "graph:delta",
        "data": delta
    });
    
    socket.send(Message::Text(msg.to_string())).await
}

/// Send full update to client
async fn send_full_update(socket: &mut WebSocket, update: GraphUpdate) -> Result<(), axum::Error> {
    let msg = json!({
        "type": "graph:update",
        "data": update
    });
    
    socket.send(Message::Text(msg.to_string())).await
}

/// Get current timestamp in milliseconds
fn get_timestamp() -> u128 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_millis()
}

/// Extension methods for broadcasting updates
pub trait BroadcastExt {
    /// Broadcast a graph update to all connected WebSocket clients
    fn broadcast_update(&self, update: GraphUpdate);
    
    /// Broadcast a delta update to all connected WebSocket clients
    fn broadcast_delta(&self, delta: GraphDelta);
}

impl BroadcastExt for AppState {
    fn broadcast_update(&self, update: GraphUpdate) {
        // Ignore send errors - it just means no clients are connected
        let _ = self.update_tx.send(update);
    }
    
    fn broadcast_delta(&self, delta: GraphDelta) {
        // Ignore send errors - it just means no clients are connected
        let _ = self.delta_tx.send(delta);
    }
}