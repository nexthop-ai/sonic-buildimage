#!/usr/bin/env python

# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared STATE_DB connection helpers for sonic_platform modules."""

from typing import Optional

from swsscommon import swsscommon


def try_get_state_db_table(logger, table_name: str) -> Optional[swsscommon.Table]:
    """
    Attempts to establish a connection to STATE_DB and returns the table.

    If it fails, it is likely that redis-server is not up (yet). Returns None
    so the caller can retry later; the failure is logged as a warning when a
    logger is provided (pass None to suppress, e.g. for rate-limited callers).
    """
    try:
        state_db = swsscommon.DBConnector("STATE_DB", 0)
    except Exception as e:
        if logger is not None:
            logger.log_warning(f"Failed to connect to STATE_DB: {e}. Ignoring.")
        return None
    return swsscommon.Table(state_db, table_name)
