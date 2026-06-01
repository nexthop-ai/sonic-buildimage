#!/usr/bin/env python3

# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Snapshot xcvr presence and write it to the cache file.

Called by asic_init.sh before the ASIC power cycle so that xcvrd can serve
cached presence values while the FPGA shift-chain is unstable.

Usage:
    python3 -m nexthop.write_xcvr_presence_cache [path]

    path  Destination file (default: XCVR_PRESENCE_CACHE_FILE).
"""

import os
import subprocess
import sys
import syslog
from pathlib import Path

from nexthop.xcvr_presence_cache import (
    XCVR_PRESENCE_CACHE_FILE,
    snapshot_presence,
    write_presence_cache,
)


def _pddf_platform_init_active():
    """Return True iff pddf-platform-init.service is active."""
    return (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "pddf-platform-init.service"]
        ).returncode
        == 0
    )


def _load_chassis():
    # Pulled out so tests can monkeypatch it without having to fake the sonic_platform import.
    from sonic_platform.platform import Platform

    return Platform().get_chassis()


def main():
    log_tag = os.environ.get("LOG_TAG", "asic_init")
    syslog.openlog(log_tag, 0, syslog.LOG_USER)
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else XCVR_PRESENCE_CACHE_FILE

    if not _pddf_platform_init_active():
        syslog.syslog(
            syslog.LOG_INFO,
            "xcvr presence cache skipped: pddf-platform-init not active",
        )
        return

    try:
        chassis = _load_chassis()
        presence = snapshot_presence(chassis)
        n = write_presence_cache(path, presence)
    except Exception as e:
        syslog.syslog(
            syslog.LOG_WARNING,
            f"xcvr presence cache skipped, reads will not be suppressed during ASIC power cycle: {e}",
        )
        sys.exit(1)

    syslog.syslog(syslog.LOG_INFO, f"xcvr presence cache written ({n} ports)")


if __name__ == "__main__":
    main()
