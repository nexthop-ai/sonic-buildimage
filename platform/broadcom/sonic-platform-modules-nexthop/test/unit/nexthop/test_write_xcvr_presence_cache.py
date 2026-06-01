#!/usr/bin/env python3

# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for nexthop.write_xcvr_presence_cache (the script entry point)."""

from unittest.mock import MagicMock

import pytest

from nexthop import write_xcvr_presence_cache


def _fake_chassis(presence: dict[int, bool]) -> MagicMock:
    """Build a mock chassis returning the given {port_index: bool} dict."""
    sfps = []
    for port_index in sorted(presence):
        sfp = MagicMock()
        sfp.port_index = port_index
        sfp.get_presence.return_value = presence[port_index]
        sfps.append(sfp)

    chassis = MagicMock()
    chassis.get_num_sfps.return_value = len(sfps)
    chassis.get_sfp.side_effect = lambda i: sfps[i]
    return chassis


class TestMain:
    def test_skips_when_pddf_init_not_active(self, tmp_path, mocker):
        """No service → log info, return early, do not import sonic_platform."""
        mocker.patch.object(
            write_xcvr_presence_cache.sys,
            "argv",
            ["write_xcvr_presence_cache", str(tmp_path / "cache.yaml")],
        )
        mocker.patch.object(
            write_xcvr_presence_cache,
            "_pddf_platform_init_active",
            return_value=False,
        )
        load_chassis = mocker.patch.object(write_xcvr_presence_cache, "_load_chassis")
        log = mocker.patch.object(write_xcvr_presence_cache.syslog, "syslog")

        write_xcvr_presence_cache.main()

        load_chassis.assert_not_called()
        assert not (tmp_path / "cache.yaml").exists()
        assert log.call_count == 1
        assert log.call_args[0] == (
            write_xcvr_presence_cache.syslog.LOG_INFO,
            "xcvr presence cache skipped: pddf-platform-init not active",
        )

    def test_happy_path_writes_cache_and_logs_count(self, tmp_path, mocker):
        cache_path = tmp_path / "cache.yaml"
        mocker.patch.object(
            write_xcvr_presence_cache.sys,
            "argv",
            ["write_xcvr_presence_cache", str(cache_path)],
        )
        mocker.patch.object(
            write_xcvr_presence_cache,
            "_pddf_platform_init_active",
            return_value=True,
        )
        mocker.patch.object(
            write_xcvr_presence_cache,
            "_load_chassis",
            return_value=_fake_chassis({0: True, 1: False, 2: True}),
        )
        log = mocker.patch.object(write_xcvr_presence_cache.syslog, "syslog")

        write_xcvr_presence_cache.main()

        assert cache_path.exists()
        assert log.call_count == 1
        assert log.call_args[0] == (
            write_xcvr_presence_cache.syslog.LOG_INFO,
            "xcvr presence cache written (3 ports)",
        )

    def test_snapshot_failure_exits_one_and_warns(self, tmp_path, mocker):
        cache_path = tmp_path / "cache.yaml"
        mocker.patch.object(
            write_xcvr_presence_cache.sys,
            "argv",
            ["write_xcvr_presence_cache", str(cache_path)],
        )
        mocker.patch.object(
            write_xcvr_presence_cache,
            "_pddf_platform_init_active",
            return_value=True,
        )
        mocker.patch.object(
            write_xcvr_presence_cache,
            "_load_chassis",
            side_effect=RuntimeError("chassis explode"),
        )
        log = mocker.patch.object(write_xcvr_presence_cache.syslog, "syslog")

        with pytest.raises(SystemExit) as exc:
            write_xcvr_presence_cache.main()

        assert exc.value.code == 1
        assert not cache_path.exists()
        assert log.call_count == 1
        assert log.call_args[0] == (
            write_xcvr_presence_cache.syslog.LOG_WARNING,
            "xcvr presence cache skipped, reads will not be suppressed during ASIC power cycle: chassis explode",
        )

    def test_default_path_when_no_arg(self, tmp_path, mocker):
        """With no path arg, falls back to XCVR_PRESENCE_CACHE_FILE."""
        mocker.patch.object(
            write_xcvr_presence_cache.sys, "argv", ["write_xcvr_presence_cache"]
        )
        mocker.patch.object(
            write_xcvr_presence_cache,
            "_pddf_platform_init_active",
            return_value=True,
        )
        mocker.patch.object(
            write_xcvr_presence_cache,
            "_load_chassis",
            return_value=_fake_chassis({0: True}),
        )

        # Redirect the default cache path into tmp so we don't touch /var/run
        redirected = tmp_path / "cache.yaml"
        mocker.patch.object(
            write_xcvr_presence_cache, "XCVR_PRESENCE_CACHE_FILE", redirected
        )

        mocker.patch.object(write_xcvr_presence_cache.syslog, "syslog")

        write_xcvr_presence_cache.main()

        assert redirected.exists()
