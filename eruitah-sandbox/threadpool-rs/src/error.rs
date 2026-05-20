//! Error types for the thread pool library.

use std::fmt;

/// Errors that can occur when interacting with the thread pool.
#[derive(Debug, Clone)]
pub enum ThreadPoolError {
    /// The thread pool has been shut down and is no longer accepting tasks.
    Shutdown,
    /// The task panicked during execution.
    TaskPanic,
    /// The worker thread handle was lost (join failed).
    WorkerLost,
}

impl fmt::Display for ThreadPoolError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ThreadPoolError::Shutdown => write!(f, "thread pool has been shut down"),
            ThreadPoolError::TaskPanic => write!(f, "task panicked during execution"),
            ThreadPoolError::WorkerLost => write!(f, "worker thread handle was lost"),
        }
    }
}

impl std::error::Error for ThreadPoolError {}
