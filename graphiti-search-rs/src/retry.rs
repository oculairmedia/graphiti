use std::fmt::Display;
use std::future::Future;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tokio::time::sleep;
use tracing::warn;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct RetryConfig {
    pub max_attempts: u32,
    pub base_delay: Duration,
}

impl RetryConfig {
    pub const fn new(max_attempts: u32, base_delay: Duration) -> Self {
        Self {
            max_attempts,
            base_delay,
        }
    }

    fn delay_for_attempt(self, attempt: u32) -> Duration {
        let exponent = attempt.saturating_sub(1).min(10);
        let backoff = self.base_delay.saturating_mul(1u32 << exponent);
        backoff.saturating_add(jitter(backoff))
    }
}

pub trait RetryableError {
    fn is_retriable(&self) -> bool;
}

pub async fn retry_with_backoff<F, Fut, T, E>(
    label: &str,
    config: RetryConfig,
    mut operation: F,
) -> Result<T, E>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = Result<T, E>>,
    E: RetryableError + Display,
{
    let max_attempts = config.max_attempts.max(1);
    let mut attempt = 1;

    loop {
        match operation().await {
            Ok(value) => return Ok(value),
            Err(error) if attempt >= max_attempts || !error.is_retriable() => return Err(error),
            Err(error) => {
                let delay = config.delay_for_attempt(attempt);
                warn!(
                    "{} attempt {}/{} failed: {}. Retrying in {:?}",
                    label, attempt, max_attempts, error, delay
                );
                sleep(delay).await;
                attempt += 1;
            }
        }
    }
}

fn jitter(delay: Duration) -> Duration {
    let jitter_cap_ms = ((delay.as_millis() as u64) / 4).max(1);
    let seed = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .subsec_nanos() as u64;
    Duration::from_millis(seed % (jitter_cap_ms + 1))
}
