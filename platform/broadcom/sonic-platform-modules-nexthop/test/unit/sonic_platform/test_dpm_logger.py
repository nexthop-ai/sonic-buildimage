#!/usr/bin/env python

import datetime
import json
import os
import pytest
import tempfile

from dataclasses import asdict
from fixtures.test_helpers_adm1266 import create_raw_adm1266_blackbox_record
from unittest.mock import patch


@pytest.fixture
def dpm_logger_module():
    """Loads the module before each test. This is to let conftest.py run first."""
    from sonic_platform import dpm_logger

    yield dpm_logger


@pytest.fixture
def adm1266_module():
    """Loads the module before each test. This is to let conftest.py run first."""
    from sonic_platform import adm1266

    yield adm1266


def make_data_v1(dpm_logger_module, gen_time: str):
    """Creates a minimal DataV1 object for testing."""
    return dpm_logger_module.DataV1(
        gen_time=gen_time,
        schema_version=1,
        causes=[
            dpm_logger_module.CauseV1(
                source="test-dpm-1",
                timestamp="2025-10-02 23:26:07 UTC",
                cause="WATCHDOG",
                description="FPGA watchdog expired",
            ),
        ],
        dpms=[
            dpm_logger_module.DpmV1(
                name="test-dpm-1",
                type="adm1266",
                records=[
                    {
                        "timestamp": "2025-10-02 23:26:07 UTC",
                        "dpm_name": "test-dpm-1",
                        "power_fault_cause": "WATCHDOG (FPGA watchdog expired), under_voltage: VH1(POS12V), over_voltage: n/a",
                        "uid": "12345",
                        "powerup_counter": "65533",
                        "vh_under_voltage_[4:1]": "0b0001 [VH1(POS12V)]",
                        "pdio_in_[16:1]": "0b0000000010000000 [PDI8]",
                    }
                ],
            ),
        ],
    )


class TestDpmLogger:
    """Test class for DpmLogger queue-based storage."""

    def test_save_to_initial_reboots(self, dpm_logger_module):
        """Save 1-5 entries, verify they go to initial reboots."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given
            logger = dpm_logger_module.DpmLogger()

            # When
            for i in range(5):
                logger.save([], {})

            # Then
            q1_path = os.path.join(tmpdir, "initial_reboots.jsonl")
            q2_path = os.path.join(tmpdir, "recent_reboots.jsonl")
            assert os.path.exists(q1_path)
            assert not os.path.exists(q2_path)
            assert logger._count_lines(q1_path) == 5

    def test_save_overflow_to_recent_reboots(self, dpm_logger_module):
        """Save 6 entries: first 5 in initial reboots, 6th in recent reboots."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given
            logger = dpm_logger_module.DpmLogger()

            # When
            for i in range(6):
                logger.save([], {})

            # Then
            q1_path = os.path.join(tmpdir, "initial_reboots.jsonl")
            q2_path = os.path.join(tmpdir, "recent_reboots.jsonl")
            assert logger._count_lines(q1_path) == 5
            assert os.path.exists(q2_path)

            q2_entries, skipped = logger._load_recent_reboots()
            assert skipped == 0
            assert len(q2_entries) == 1

    def test_recent_reboots_circular_skipping(self, dpm_logger_module):
        """Save 11 entries: initial=5, recent=last 5 (entries 7-11), 1 skipped."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given
            logger = dpm_logger_module.DpmLogger()

            # When
            for i in range(11):
                logger.save([], {})

            # Then
            assert logger._count_lines(os.path.join(tmpdir, "initial_reboots.jsonl")) == 5

            q2_entries, skipped = logger._load_recent_reboots()
            assert skipped == 1
            assert len(q2_entries) == 5

    def test_skipped_reboots_increments(self, dpm_logger_module):
        """Verify skipped reboots increments on each skip."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given
            logger = dpm_logger_module.DpmLogger()

            # When - Fill initial (5) + recent (5) + 3 more skipped = 13 total
            for i in range(13):
                logger.save([], {})

            # Then
            q2_entries, skipped = logger._load_recent_reboots()
            assert skipped == 3
            assert len(q2_entries) == 5

    def test_drain_to_history(self, dpm_logger_module):
        """Populate initial/recent logs, drain, verify history has entries and logs are cleared."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given
            logger = dpm_logger_module.DpmLogger()
            for i in range(8):
                logger.save([], {})

            # When
            logger.drain_to_history()

            # Then - queues should be cleared
            q1_path = os.path.join(tmpdir, "initial_reboots.jsonl")
            q2_path = os.path.join(tmpdir, "recent_reboots.jsonl")
            assert not os.path.exists(q1_path)
            assert not os.path.exists(q2_path)

            # Then - history should have all entries
            history_entries = logger._load_history()[0]
            assert len(history_entries) == 8

    def test_drain_history_retention(self, dpm_logger_module):
        """Pre-fill history near limit, drain, verify trim to HISTORY_MAX."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_MAX", new=5),
        ):
            # Given - history with 4 entries, initial reboots with 3 entries
            logger = dpm_logger_module.DpmLogger()
            for i in range(4):
                data = make_data_v1(dpm_logger_module, f"old-{i}")
                logger._append_entry(logger._history_path, data)
            for i in range(3):
                logger.save([], {})

            # When
            logger.drain_to_history()

            # Then
            history_entries = logger._load_history()[0]
            assert len(history_entries) == 5  # trimmed to HISTORY_MAX

    def test_drain_inserts_separator(self, dpm_logger_module):
        """After boot-loop with skipped reboots, history has skipped_reboots separator."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given - 12 saves: 5 in initial, 5 in recent (2 skipped)
            logger = dpm_logger_module.DpmLogger()
            for i in range(12):
                logger.save([], {})

            # When
            logger.drain_to_history()

            # Then
            raw_lines = logger._load_history_raw()
            separator_lines = [
                json.loads(line)
                for line in raw_lines
                if "skipped_reboots" in line and "schema_version" not in line
            ]
            assert len(separator_lines) == 1
            assert separator_lines[0]["skipped_reboots"] == 2

    def test_drain_no_separator_for_small_reboots(self, dpm_logger_module):
        """<=10 reboots means no skipped reboots, so no separator in history."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given
            logger = dpm_logger_module.DpmLogger()
            for i in range(8):
                logger.save([], {})

            # When
            logger.drain_to_history()

            # Then
            raw_lines = logger._load_history_raw()
            separator_lines = [
                line for line in raw_lines if "skipped_reboots" in line and "schema_version" not in line
            ]
            assert len(separator_lines) == 0

    def test_drain_drops_orphaned_separator(self, dpm_logger_module):
        """Trimming to HISTORY_MAX drops leading separator."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_MAX", new=3),
        ):
            # Given - history: 2 entries + separator + 2 entries
            logger = dpm_logger_module.DpmLogger()
            history_lines = []
            for i in range(2):
                data = make_data_v1(dpm_logger_module, f"old-{i}")
                history_lines.append(json.dumps(asdict(data)))
            history_lines.append(json.dumps({"skipped_reboots": 50}))
            for i in range(2):
                data = make_data_v1(dpm_logger_module, f"recent-{i}")
                history_lines.append(json.dumps(asdict(data)))
            logger._atomic_write_lines(logger._history_path, history_lines)

            # Given - 1 entry in initial reboots
            logger.save([], {})

            # When
            logger.drain_to_history()

            # Then - should have trimmed to 3, dropping old entries and orphaned separator
            history_entries = logger._load_history()[0]
            assert len(history_entries) == 3

            # Then - no orphaned separator at the front
            raw_lines = logger._load_history_raw()
            first = json.loads(raw_lines[0])
            assert "schema_version" in first

    def test_load_from_recent_reboots(self, dpm_logger_module):
        """load() returns recent reboots last entry when both initial/recent logs populated."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given - 7 saves: 5 in initial, 2 in recent
            logger = dpm_logger_module.DpmLogger()
            for i in range(7):
                logger.save([], {})

            # When
            result = logger.load()

            # Then - should be the recent reboots last entry (most recent)
            assert result is not None
            q2_entries, _ = logger._load_recent_reboots()
            assert result == q2_entries[-1]

    def test_load_from_initial_reboots(self, dpm_logger_module):
        """load() returns initial reboots last entry when recent reboots is empty."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given - 3 saves: all in initial reboots
            logger = dpm_logger_module.DpmLogger()
            for i in range(3):
                logger.save([], {})

            # When
            result = logger.load()

            # Then
            assert result is not None
            q1_entries = logger._load_initial_reboots()
            assert result == q1_entries[-1]

    def test_load_from_history(self, dpm_logger_module):
        """load() returns history last entry when initial/recent logs are empty."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given - only history has an entry
            logger = dpm_logger_module.DpmLogger()
            data = make_data_v1(dpm_logger_module, "cold-entry")
            logger._append_entry(logger._history_path, data)

            # When
            result = logger.load()

            # Then
            assert result is not None
            assert result.gen_time == "cold-entry"

    def test_load_returns_none_when_empty(self, dpm_logger_module):
        """load() returns None when no entries exist anywhere."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given
            logger = dpm_logger_module.DpmLogger()

            # When / Then
            assert logger.load() is None

    def test_load_all_chronological(self, dpm_logger_module):
        """Verify load_all returns history + initial + recent in chronological order."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given - history with 1 entry, then 7 saves (5 in initial, 2 in recent)
            logger = dpm_logger_module.DpmLogger()
            history_data = make_data_v1(dpm_logger_module, "cold-1")
            logger._append_entry(logger._history_path, history_data)
            for i in range(7):
                logger.save([], {})

            # When
            items, total, skipped = logger.load_all()

            # Then - 1 history + 5 initial + 2 recent = 8 entries (no skip markers)
            data_entries = [e for e in items if isinstance(e, dpm_logger_module.DataBase)]
            assert len(data_entries) == 8
            assert skipped == 0
            assert data_entries[0].gen_time == "cold-1"  # history first

    def test_load_all_total_reboots(self, dpm_logger_module):
        """Verify total_reboots includes skipped counts from recent reboots and history separators."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given - history with 2 entries and a separator (10 skipped reboots)
            logger = dpm_logger_module.DpmLogger()
            history_lines = [
                json.dumps(asdict(make_data_v1(dpm_logger_module, "c1"))),
                json.dumps({"skipped_reboots": 10}),
                json.dumps(asdict(make_data_v1(dpm_logger_module, "c2"))),
            ]
            logger._atomic_write_lines(logger._history_path, history_lines)

            # Given - 12 saves: 5 in initial, 5 in recent, 2 skipped
            for i in range(12):
                logger.save([], {})

            # When
            items, total, skipped = logger.load_all()

            # Then - data entries: 2 history + 5 initial + 5 recent = 12
            data_entries = [e for e in items if isinstance(e, dpm_logger_module.DataBase)]
            assert len(data_entries) == 12
            # Then - skip markers: 1 from history separator + 1 from recent
            skip_markers = [e for e in items if isinstance(e, dpm_logger_module.SkippedReboots)]
            assert len(skip_markers) == 2
            assert skip_markers[0].count == 10  # history separator
            assert skip_markers[1].count == 2   # recent skipped
            # Then - total: 12 entries + 10 (history separator) + 2 (recent skipped) = 24
            assert total == 24
            assert skipped == 12

    def test_migration_from_old_format(self, dpm_logger_module):
        """Old reboot-cause-*.json files are migrated into history on first save()."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given - 3 old-format files and a symlink
            for ts in ["2025_01_01_00_00_00", "2025_01_02_00_00_00", "2025_01_03_00_00_00"]:
                data = asdict(make_data_v1(dpm_logger_module, ts))
                with open(os.path.join(tmpdir, f"reboot-cause-{ts}.json"), "w") as f:
                    json.dump(data, f)
            os.symlink(
                os.path.join(tmpdir, "reboot-cause-2025_01_03_00_00_00.json"),
                os.path.join(tmpdir, "previous-reboot-cause.json"),
            )

            # When
            logger = dpm_logger_module.DpmLogger()
            logger.save([], {})

            # Then - old files should be gone
            import glob as glob_mod

            old_files = glob_mod.glob(os.path.join(tmpdir, "reboot-cause-*.json"))
            assert len(old_files) == 0
            assert not os.path.exists(os.path.join(tmpdir, "previous-reboot-cause.json"))

            # Then - history should have the migrated entries in order
            history_entries = logger._load_history()[0]
            assert len(history_entries) == 3
            assert history_entries[0].gen_time == "2025_01_01_00_00_00"
            assert history_entries[1].gen_time == "2025_01_02_00_00_00"
            assert history_entries[2].gen_time == "2025_01_03_00_00_00"

            # Then - initial reboots should have the new entry from save()
            q1_entries = logger._load_initial_reboots()
            assert len(q1_entries) == 1

    def test_save_and_load_v1(self, dpm_logger_module, adm1266_module):
        """End-to-end test: save with real causes/DPM records and verify load."""
        # Given
        CAUSES = [
            dpm_logger_module.RebootCause(
                type=dpm_logger_module.RebootCause.Type.SOFTWARE,
                source="SW",
                timestamp=datetime.datetime(2025, 10, 2, 23, 22, 56, tzinfo=datetime.timezone.utc),
                cause="reboot",
                description="User issued 'reboot' command [User: admin, Time: Thu Oct  2 11:22:56 PM UTC 2025]",
                chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
            ),
            dpm_logger_module.RebootCause(
                type=dpm_logger_module.RebootCause.Type.HARDWARE,
                source="test-dpm-1",
                timestamp=datetime.datetime(2025, 10, 2, 23, 26, 7, tzinfo=datetime.timezone.utc),
                cause="CPU_CMD_PCYC",
                description="CPU card commanded power cycle",
                chassis_reboot_cause_category="REBOOT_CAUSE_POWER_LOSS",
            ),
        ]
        DPM_1_POWERUPS = [
            dpm_logger_module.DpmPowerUpEntry(
                powerup_counter=65533,
                power_fault_cause=None,
                dpm_records=[
                    adm1266_module.Adm1266BlackBoxRecord.from_bytes(
                        create_raw_adm1266_blackbox_record(
                            uid=12345,
                            powerup_counter=65533,
                        ),
                        "test-dpm-1",
                    )
                ],
            ),
            dpm_logger_module.DpmPowerUpEntry(
                powerup_counter=65534,
                power_fault_cause=None,
                dpm_records=[
                    adm1266_module.Adm1266BlackBoxRecord.from_bytes(
                        create_raw_adm1266_blackbox_record(
                            uid=12346,
                            powerup_counter=65534,
                        ),
                        "test-dpm-1",
                    )
                ],
            ),
        ]
        DPM_2_POWERUPS = [
            dpm_logger_module.DpmPowerUpEntry(
                powerup_counter=6,
                power_fault_cause=None,
                dpm_records=[
                    adm1266_module.Adm1266BlackBoxRecord.from_bytes(
                        create_raw_adm1266_blackbox_record(
                            uid=1000,
                            powerup_counter=6,
                        ),
                        "test-dpm-2",
                    ),
                    adm1266_module.Adm1266BlackBoxRecord.from_bytes(
                        create_raw_adm1266_blackbox_record(
                            uid=1001,
                            powerup_counter=6,
                        ),
                        "test-dpm-2",
                    ),
                ],
            ),
            dpm_logger_module.DpmPowerUpEntry(
                powerup_counter=7,
                power_fault_cause=None,
                dpm_records=[
                    adm1266_module.Adm1266BlackBoxRecord.from_bytes(
                        create_raw_adm1266_blackbox_record(
                            uid=1002,
                            powerup_counter=7,
                        ),
                        "test-dpm-2",
                    ),
                ],
            ),
        ]
        # Minimal pddf_device_data for testing
        pddf_device_data = {
            "DPM1": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}},
            "DPM2": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x41"}}},
        }
        DPM_1 = adm1266_module.Adm1266(
            "test-dpm-1",
            {"dpm": "DPM1"},
            pddf_device_data,
        )
        DPM_2 = adm1266_module.Adm1266(
            "test-dpm-2",
            {"dpm": "DPM2"},
            pddf_device_data,
        )
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # When
            logger = dpm_logger_module.DpmLogger()
            logger.save(CAUSES, {DPM_1: DPM_1_POWERUPS, DPM_2: DPM_2_POWERUPS})
            loaded_data = logger.load()

            # Then
            EXPECTED_DATA = dpm_logger_module.DataV1(
                gen_time=loaded_data.gen_time,
                schema_version=1,
                causes=[
                    dpm_logger_module.CauseV1(
                        source="SW",
                        timestamp="2025-10-02 23:22:56 UTC",
                        cause="reboot",
                        description="n/a",
                    ),
                    dpm_logger_module.CauseV1(
                        source="test-dpm-1",
                        timestamp="2025-10-02 23:26:07 UTC",
                        cause="CPU_CMD_PCYC",
                        description="CPU card commanded power cycle",
                    ),
                ],
                dpms=[
                    dpm_logger_module.DpmV1(
                        name="test-dpm-1",
                        type="adm1266",
                        records=[
                            record.as_dict()
                            for powerup in DPM_1_POWERUPS
                            for record in powerup.dpm_records
                        ],
                    ),
                    dpm_logger_module.DpmV1(
                        name="test-dpm-2",
                        type="adm1266",
                        records=[
                            record.as_dict()
                            for powerup in DPM_2_POWERUPS
                            for record in powerup.dpm_records
                        ],
                    ),
                ],
            )
            assert loaded_data == EXPECTED_DATA

    def test_drain_empty_queues(self, dpm_logger_module):
        """drain_to_history() with empty initial/recent logs is a no-op."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given
            logger = dpm_logger_module.DpmLogger()

            # When
            logger.drain_to_history()

            # Then
            assert not os.path.exists(logger._history_path)

    def test_multiple_drain_cycles(self, dpm_logger_module):
        """Multiple drain cycles accumulate in history."""
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch.object(dpm_logger_module.DpmLogger, "HISTORY_DIR", new=tmpdir),
        ):
            # Given - first boot cycle: 3 reboots, drained
            logger = dpm_logger_module.DpmLogger()
            for i in range(3):
                logger.save([], {})
            logger.drain_to_history()

            # Given - second boot cycle: 2 reboots
            for i in range(2):
                logger.save([], {})

            # When
            logger.drain_to_history()

            # Then
            items, total, skipped = logger.load_all()
            data_entries = [e for e in items if isinstance(e, dpm_logger_module.DataBase)]
            assert len(data_entries) == 5
            assert total == 5
            assert skipped == 0
