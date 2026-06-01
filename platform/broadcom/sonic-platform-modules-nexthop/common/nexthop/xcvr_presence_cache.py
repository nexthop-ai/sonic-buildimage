#!/usr/bin/env python3

# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Xcvr presence cache to work around XCVR presence glitch during ASIC power cycle.

Cache file is:
- written by asic_init.sh before ASIC power cycle.
- written to /var/run/platform_cache because:
    - /var/run is cleared on reboot
    - /var/run/platform_cache is mounted into PMon for Xcvrd

YAML format: sfp.port_index (int) -> present (bool), one per line, e.g.
  0: true
  1: false
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import yaml

XCVR_PRESENCE_CACHE_FILE: Path = Path(
    "/var/run/platform_cache/xcvr_presence_cache.yaml"
)
XCVR_PRESENCE_CACHE_MAX_AGE_SECS: int = 30

PathLike = str | os.PathLike[str]


def snapshot_presence(chassis: Any) -> dict[int, bool]:
    """Return a dict mapping sfp.port_index to presence for all SFPs.

    Args:
        chassis: SONiC chassis object with get_num_sfps() and get_sfp(i).
    """
    result: dict[int, bool] = {}
    for i in range(chassis.get_num_sfps()):
        sfp = chassis.get_sfp(i)
        result[sfp.port_index] = sfp.get_presence()
    return result


def format_cache(presence: dict[int, bool]) -> str:
    """Serialize a presence dict to YAML string ready to write to the cache file."""
    lines = [f"{k}: {'true' if v else 'false'}" for k, v in sorted(presence.items())]
    return "\n".join(lines) + "\n"


def read_cached_presence(
    port_index: int,
    path: PathLike = XCVR_PRESENCE_CACHE_FILE,
    max_age_secs: float = XCVR_PRESENCE_CACHE_MAX_AGE_SECS,
    log_warning: Callable[[str], None] | None = None,
) -> bool | None:
    """Return cached presence for port_index, or None if no valid entry exists.

    Returns None when the cache file is missing, older than max_age_secs,
    unparseable, or doesn't contain port_index. Callers should fall through to
    a hardware read in that case.

    Args:
        port_index: The sfp.port_index to look up.
        path: Cache file path.
        max_age_secs: Entries older than this (by mtime) are ignored.
        log_warning: Optional callable invoked with a message when the cache
            file exists but cannot be read or parsed.
    """
    try:
        if time.time() - os.path.getmtime(path) >= max_age_secs:
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        if data and port_index in data:
            return data[port_index]
    except FileNotFoundError:
        pass
    except (OSError, yaml.YAMLError) as e:
        if log_warning is not None:
            log_warning(f"xcvr presence cache read failed: {e}")
    return None


def write_presence_cache(path: PathLike, presence: dict[int, bool]) -> int:
    """Write a presence dict to path atomically.

    Returns the number of ports written.
    """
    path = Path(path)
    # The cache is written to a temp file in the same directory, then renamed
    # over the target. This prevents xcvrd from observing an empty or partial
    # file mid-write (open(path, "w") truncates before writing, which would
    # otherwise let a concurrent reader fall through to the glitched hardware).
    fd, tmp = tempfile.mkstemp(prefix=".xcvr_presence_cache.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(format_cache(presence))
        os.rename(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return len(presence)
