//! `log::Log` backend over libc syslog(3).
//!
//! /dev/log is owned by the container's rsyslogd, which starts after this
//! listener and may be restarted at runtime (e.g. when a syslog rate-limit
//! config change is applied). Logging therefore has to tolerate /dev/log not
//! existing yet at startup and being replaced later. glibc's syslog(3) does:
//! it connects lazily and reconnects on send failure, so the process survives
//! /dev/log being absent and alerts keep flowing after rsyslogd recreates the
//! socket.

use std::ffi::CString;
use std::sync::OnceLock;

// openlog(3) keeps a reference to the ident string, so it must stay alive
// for the lifetime of the process.
static IDENT: OnceLock<CString> = OnceLock::new();

struct LibcSyslogLogger;

static LOGGER: LibcSyslogLogger = LibcSyslogLogger;

fn level_to_priority(level: log::Level) -> libc::c_int {
    match level {
        log::Level::Error => libc::LOG_ERR,
        log::Level::Warn => libc::LOG_WARNING,
        log::Level::Info => libc::LOG_INFO,
        log::Level::Debug | log::Level::Trace => libc::LOG_DEBUG,
    }
}

impl log::Log for LibcSyslogLogger {
    fn enabled(&self, metadata: &log::Metadata) -> bool {
        metadata.level() <= log::max_level()
    }

    fn log(&self, record: &log::Record) {
        if !self.enabled(record.metadata()) {
            return;
        }
        let priority = level_to_priority(record.level());
        if let Ok(msg) = CString::new(record.args().to_string()) {
            unsafe {
                libc::syslog(priority, c"%s".as_ptr(), msg.as_ptr());
            }
        }
    }

    fn flush(&self) {}
}

/// Route the `log` macros to syslog(3). Idempotent: a second call (e.g. from
/// tests) leaves the existing logger and ident in place (the first ident
/// wins; a different ident passed later is silently ignored).
pub fn init(ident: &str, level: log::LevelFilter) {
    let ident = IDENT.get_or_init(|| CString::new(ident).expect("ident must not contain NUL"));
    unsafe {
        // No LOG_NDELAY: let glibc connect lazily and reconnect as needed.
        // LOG_PERROR: also write to stderr, which supervisord captures, so
        // alerts are still recorded while /dev/log is unavailable.
        libc::openlog(ident.as_ptr(), libc::LOG_PID | libc::LOG_PERROR, libc::LOG_USER);
    }
    // Set the level before installing the logger so no record can arrive
    // while the filter is still at the default `Off`.
    log::set_max_level(level);
    let _ = log::set_logger(&LOGGER);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_level_to_priority_mapping() {
        assert_eq!(level_to_priority(log::Level::Error), libc::LOG_ERR);
        assert_eq!(level_to_priority(log::Level::Warn), libc::LOG_WARNING);
        assert_eq!(level_to_priority(log::Level::Info), libc::LOG_INFO);
        assert_eq!(level_to_priority(log::Level::Debug), libc::LOG_DEBUG);
        assert_eq!(level_to_priority(log::Level::Trace), libc::LOG_DEBUG);
    }
}
