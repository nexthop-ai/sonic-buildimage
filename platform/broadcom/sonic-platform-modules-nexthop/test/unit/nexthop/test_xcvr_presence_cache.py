#!/usr/bin/env python3

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for nexthop.xcvr_presence_cache."""

import os
import threading
import time
from unittest.mock import MagicMock

import pytest
import yaml


@pytest.fixture(scope="function", autouse=True)
def xcvr_presence_cache_module():
    from nexthop import xcvr_presence_cache

    yield xcvr_presence_cache


def make_chassis(presence_map):
    """Build a mock chassis where presence_map is {0-based index: bool}.

    Each mock SFP has port_index set to its 0-based chassis index, matching
    the real PddfSfp behaviour where port_index == the index passed to __init__.
    """
    sfps = []
    for i in sorted(presence_map):
        sfp = MagicMock()
        sfp.port_index = i
        sfp.get_presence.return_value = presence_map[i]
        sfps.append(sfp)

    chassis = MagicMock()
    chassis.get_num_sfps.return_value = len(sfps)
    chassis.get_sfp.side_effect = lambda i: sfps[i]
    return chassis


class TestSnapshotPresence:
    def test_all_absent(self, xcvr_presence_cache_module):
        chassis = make_chassis({0: False, 1: False, 2: False})
        result = xcvr_presence_cache_module.snapshot_presence(chassis)
        assert result == {0: False, 1: False, 2: False}

    def test_all_present(self, xcvr_presence_cache_module):
        chassis = make_chassis({0: True, 1: True})
        result = xcvr_presence_cache_module.snapshot_presence(chassis)
        assert result == {0: True, 1: True}

    def test_mixed_presence(self, xcvr_presence_cache_module):
        chassis = make_chassis({0: True, 1: False, 2: True, 3: False})
        result = xcvr_presence_cache_module.snapshot_presence(chassis)
        assert result == {0: True, 1: False, 2: True, 3: False}

    def test_empty_chassis(self, xcvr_presence_cache_module):
        chassis = make_chassis({})
        result = xcvr_presence_cache_module.snapshot_presence(chassis)
        assert result == {}

    def test_key_matches_sfp_port_index(self, xcvr_presence_cache_module):
        """Cache keys must equal sfp.port_index so sfp.py's lookup works."""
        chassis = make_chassis({0: True})
        result = xcvr_presence_cache_module.snapshot_presence(chassis)
        assert 0 in result
        assert 1 not in result


class TestFormatCache:
    def test_present_port_is_true(self, xcvr_presence_cache_module):
        content = xcvr_presence_cache_module.format_cache({0: True})
        assert "0: true" in content

    def test_absent_port_is_false(self, xcvr_presence_cache_module):
        content = xcvr_presence_cache_module.format_cache({0: False})
        assert "0: false" in content

    def test_ports_sorted(self, xcvr_presence_cache_module):
        content = xcvr_presence_cache_module.format_cache({2: True, 0: False, 1: True})
        lines = content.strip().splitlines()
        assert lines == ["0: false", "1: true", "2: true"]

    def test_ends_with_newline(self, xcvr_presence_cache_module):
        content = xcvr_presence_cache_module.format_cache({0: True})
        assert content.endswith("\n")

    def test_empty_produces_single_newline(self, xcvr_presence_cache_module):
        content = xcvr_presence_cache_module.format_cache({})
        assert content == "\n"


class TestWritePresenceCache:
    def test_writes_correct_content(self, xcvr_presence_cache_module, tmp_path):
        presence = {0: True, 1: False, 2: True}
        path = tmp_path / "cache.yaml"

        xcvr_presence_cache_module.write_presence_cache(path, presence)

        data = yaml.safe_load(path.read_text())
        assert data == {0: True, 1: False, 2: True}

    def test_returns_port_count(self, xcvr_presence_cache_module, tmp_path):
        presence = {0: True, 1: True, 2: False}
        path = tmp_path / "cache.yaml"

        count = xcvr_presence_cache_module.write_presence_cache(path, presence)

        assert count == 3

    def test_file_readable_by_sfp_get_presence(
        self, xcvr_presence_cache_module, tmp_path
    ):
        """Round-trip: format_cache output must be parseable as the sfp.py reader expects.

        sfp.py does: data[self.port_index], where self.port_index == sfp.port_index used
        as the key in snapshot_presence.
        """
        presence = {0: False, 1: True, 2: False, 3: True}
        path = tmp_path / "cache.yaml"

        xcvr_presence_cache_module.write_presence_cache(path, presence)

        data = yaml.safe_load(path.read_text())
        # sfp.py checks: data and self.port_index in data
        assert data[0] is False
        assert data[1] is True
        assert data[2] is False
        assert data[3] is True

    def test_raises_on_write_failure(self, xcvr_presence_cache_module):
        presence = {0: True}
        with pytest.raises(Exception):
            xcvr_presence_cache_module.write_presence_cache(
                "/nonexistent/path/cache.yaml", presence
            )

    def test_concurrent_writes_never_yield_partial_or_mixed_state(
        self, xcvr_presence_cache_module, tmp_path
    ):
        """Two writers (all-True vs all-False) racing against a busy reader.

        Every read must see a complete file equal to one of the two inputs.
        With the old `open(path, "w")` truncate-then-write, the reader could
        observe empty/partial files. With atomic rename, every observation is
        a self-consistent snapshot of one writer's payload.
        """
        NUM_PORTS = 512
        WRITES_PER_THREAD = 50
        all_true = {i: True for i in range(NUM_PORTS)}
        all_false = {i: False for i in range(NUM_PORTS)}
        path = tmp_path / "cache.yaml"

        # Seed so the reader never sees ENOENT.
        xcvr_presence_cache_module.write_presence_cache(path, all_false)

        stop = threading.Event()
        bad_observations = []

        def writer(presence):
            for _ in range(WRITES_PER_THREAD):
                xcvr_presence_cache_module.write_presence_cache(path, presence)

        def reader():
            while not stop.is_set():
                try:
                    with open(path) as f:
                        data = yaml.safe_load(f)
                except (FileNotFoundError, yaml.YAMLError) as e:
                    bad_observations.append(("parse_or_missing", repr(e)))
                    continue
                if data is None:
                    bad_observations.append(("empty", None))
                    continue
                if len(data) != NUM_PORTS:
                    bad_observations.append(("wrong_size", len(data)))
                    continue
                values = set(data.values())
                if values not in ({True}, {False}):
                    bad_observations.append(("mixed", sorted(values)))

        t_read = threading.Thread(target=reader)
        t_w1 = threading.Thread(target=writer, args=(all_true,))
        t_w2 = threading.Thread(target=writer, args=(all_false,))

        t_read.start()
        t_w1.start()
        t_w2.start()
        t_w1.join()
        t_w2.join()
        stop.set()
        t_read.join()

        assert (
            bad_observations == []
        ), f"Atomicity violated; first 5 bad reads: {bad_observations[:5]}"

        # Final state must equal exactly one of the two inputs.
        final = yaml.safe_load(path.read_text())
        assert final in (all_true, all_false)

    def test_no_temp_file_left_on_success(self, xcvr_presence_cache_module, tmp_path):
        path = tmp_path / "cache.yaml"
        xcvr_presence_cache_module.write_presence_cache(path, {0: True})

        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "cache.yaml"]
        assert leftovers == []

    def test_no_temp_file_left_on_failure(
        self, xcvr_presence_cache_module, tmp_path, monkeypatch
    ):
        """If rename fails, the temp file must be cleaned up."""
        path = tmp_path / "cache.yaml"

        def boom(*args, **kwargs):
            raise OSError("rename failed")

        monkeypatch.setattr(xcvr_presence_cache_module.os, "rename", boom)

        with pytest.raises(OSError):
            xcvr_presence_cache_module.write_presence_cache(path, {0: True})

        assert list(tmp_path.iterdir()) == []


class TestReadCachedPresence:
    """Tests for read_cached_presence — the helper Sfp.get_presence delegates to."""

    def _write(self, xcvr_presence_cache_module, tmp_path, presence, mtime=None):
        """Helper: write a cache file and optionally backdate its mtime."""
        path = tmp_path / "cache.yaml"
        xcvr_presence_cache_module.write_presence_cache(path, presence)
        if mtime is not None:
            os.utime(path, (mtime, mtime))
        return path

    def test_missing_file_returns_none(self, xcvr_presence_cache_module, tmp_path):
        log = MagicMock()
        result = xcvr_presence_cache_module.read_cached_presence(
            0, path=tmp_path / "nope.yaml", log_warning=log
        )
        assert result is None
        log.assert_not_called()

    def test_fresh_cache_hit_present(self, xcvr_presence_cache_module, tmp_path):
        path = self._write(xcvr_presence_cache_module, tmp_path, {0: True, 1: False})
        result = xcvr_presence_cache_module.read_cached_presence(0, path=path)
        assert result is True

    def test_fresh_cache_hit_absent(self, xcvr_presence_cache_module, tmp_path):
        path = self._write(xcvr_presence_cache_module, tmp_path, {0: True, 1: False})
        result = xcvr_presence_cache_module.read_cached_presence(1, path=path)
        assert result is False

    def test_port_not_in_cache_returns_none(self, xcvr_presence_cache_module, tmp_path):
        path = self._write(xcvr_presence_cache_module, tmp_path, {0: True})
        result = xcvr_presence_cache_module.read_cached_presence(99, path=path)
        assert result is None

    def test_empty_cache_file_returns_none(self, xcvr_presence_cache_module, tmp_path):
        path = tmp_path / "cache.yaml"
        path.write_text("")
        result = xcvr_presence_cache_module.read_cached_presence(0, path=path)
        assert result is None

    def test_within_max_age_returns_cached_value(
        self, xcvr_presence_cache_module, tmp_path, monkeypatch
    ):
        """File aged 30s with max_age_secs=40 → cache hit.

        Demonstrates the max_age_secs parameter widens the acceptance window:
        the same file that would be rejected at max_age_secs=30 is accepted
        when the caller allows 40.
        """
        path = self._write(
            xcvr_presence_cache_module, tmp_path, {0: True}, mtime=1000.0
        )
        monkeypatch.setattr(xcvr_presence_cache_module.time, "time", lambda: 1030.0)
        result = xcvr_presence_cache_module.read_cached_presence(
            0, path=path, max_age_secs=40
        )
        assert result is True

    def test_at_max_age_boundary_returns_none(
        self, xcvr_presence_cache_module, tmp_path, monkeypatch
    ):
        """File aged exactly max_age_secs is considered stale (`>=` cutoff)."""
        path = self._write(
            xcvr_presence_cache_module, tmp_path, {0: True}, mtime=1000.0
        )
        monkeypatch.setattr(xcvr_presence_cache_module.time, "time", lambda: 1030.0)
        result = xcvr_presence_cache_module.read_cached_presence(
            0, path=path, max_age_secs=30
        )
        assert result is None

    def test_past_max_age_returns_none(
        self, xcvr_presence_cache_module, tmp_path, monkeypatch
    ):
        """File older than max_age_secs → cache miss."""
        path = self._write(
            xcvr_presence_cache_module, tmp_path, {0: True}, mtime=1000.0
        )
        monkeypatch.setattr(xcvr_presence_cache_module.time, "time", lambda: 1050.0)
        result = xcvr_presence_cache_module.read_cached_presence(
            0, path=path, max_age_secs=30
        )
        assert result is None

    def test_corrupt_yaml_returns_none_and_warns(
        self, xcvr_presence_cache_module, tmp_path
    ):
        path = tmp_path / "cache.yaml"
        path.write_text("{not: valid: yaml: at: all")
        log = MagicMock()

        result = xcvr_presence_cache_module.read_cached_presence(
            0, path=path, log_warning=log
        )

        assert result is None
        log.assert_called_once()
        assert log.call_args[0][0].startswith("xcvr presence cache read failed: ")
