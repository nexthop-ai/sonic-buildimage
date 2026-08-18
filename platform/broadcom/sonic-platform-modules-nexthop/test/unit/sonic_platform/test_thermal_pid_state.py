#!/usr/bin/env python

# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the thermal_pid_state.py module.
These tests run in isolation from the SONiC environment using pytest:
python -m pytest test/unit/sonic_platform/test_thermal_pid_state.py -v
"""

import pytest
import threading
import time

from unittest.mock import patch

from fixtures.fake_swsscommon import FakeTable


@pytest.fixture
def thermal_pid_state_module():
    """Provides the thermal_pid_state module for testing."""
    from sonic_platform import thermal_pid_state
    return thermal_pid_state


@pytest.fixture
def thermal_module():
    """Provides the thermal module for testing."""
    from sonic_platform import thermal
    return thermal


@pytest.fixture(autouse=True)
def clean_fake_db():
    """Ensures each test starts with an empty in-memory DB."""
    FakeTable._global_db.clear()
    yield
    FakeTable._global_db.clear()


def make_pid_details(thermal_module, domain, sensors, max_error_sensor_name,
                     raw_output=50.0, saturated_output=50.0, P=1.0, I=100.0, D=0.5,
                     frozen_integral=False):
    """Helper to build a PidDomainDetails with a PidOutput."""
    pid_output = thermal_module.PidOutput(
        P=P,
        I=I,
        D=D,
        raw_output=raw_output,
        saturated_output=saturated_output,
        frozen_integral=frozen_integral,
    )
    return thermal_module.PidDomainDetails(
        domain=domain,
        sensors=sensors,
        max_error_sensor_name=max_error_sensor_name,
        pid_output=pid_output,
    )


@pytest.fixture
def sample_pid_details_by_domain(thermal_module):
    """Two PID domains plus a PID_DOMAIN_NONE group."""
    SensorDetails = thermal_module.SensorDetails
    asic_sensors = [
        SensorDetails("ASIC Diode 0", 78.0, -7.0, 85.0),
        SensorDetails("ASIC NIF1", 80.0, -5.0, 85.0),
    ]
    main_sensors = [
        SensorDetails("Transceiver Port21", 66.9, -0.1, 67.0),
        SensorDetails("CPU Sensor", 55.0, -15.0, 70.0),
    ]
    none_sensors = [
        SensorDetails("PSU1 Inlet", 40.0),
    ]
    return {
        "asic": make_pid_details(
            thermal_module, "asic", asic_sensors, "ASIC NIF1",
            raw_output=45.0, saturated_output=45.0, P=-5.0, I=200.0, D=0.2,
        ),
        "main": make_pid_details(
            thermal_module, "main", main_sensors, "Transceiver Port21",
            raw_output=60.5, saturated_output=60.5, P=-0.1, I=300.0, D=0.1,
        ),
        thermal_module.PID_DOMAIN_NONE: thermal_module.PidDomainDetails(
            domain=thermal_module.PID_DOMAIN_NONE,
            sensors=none_sensors,
        ),
    }


@pytest.fixture
def domain_gains():
    return {
        "asic": {"KP": 10, "KI": 0.1, "KD": 5},
        "main": {"KP": 5, "KI": 0.05, "KD": 2.5},
    }


def get_state_db_entry(table_name, key):
    """Reads an entry from the fake STATE_DB."""
    return FakeTable._global_db.get("STATE_DB", {}).get(table_name, {}).get(key)


class TestThermalPidStatePublisher:
    """Tests for ThermalPidStatePublisher."""

    def test_publish_domain_state(self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()

        main = get_state_db_entry("THERMAL_PID_INFO", "main")
        assert main is not None
        assert main["driving_sensor"] == "Transceiver Port21"
        assert main["driving_sensor_temp"] == "66.900"
        assert main["setpoint"] == "67.000"
        assert main["error"] == "-0.100"
        assert main["output"] == "60.500"
        assert main["raw_output"] == "60.500"
        assert main["is_driving"] == "true"
        assert main["fan_speed"] == "60.500"
        assert main["status"] == "ok"
        assert main["integral_frozen"] == "false"
        assert main["kp"] == "5"
        assert main["ki"] == "0.050"
        assert main["kd"] == "2.500"
        assert "timestamp" in main

        asic = get_state_db_entry("THERMAL_PID_INFO", "asic")
        assert asic is not None
        assert asic["driving_sensor"] == "ASIC NIF1"
        assert asic["is_driving"] == "false"

    def test_publish_contributions_sum_to_raw_output(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()

        for domain in ("asic", "main"):
            entry = get_state_db_entry("THERMAL_PID_INFO", domain)
            contributions_sum = (
                float(entry["p_contribution"])
                + float(entry["i_contribution"])
                + float(entry["d_contribution"])
            )
            assert contributions_sum == pytest.approx(float(entry["raw_output"]), abs=0.01)
            # P and D contributions are gain * term
            gains = domain_gains[domain]
            details = sample_pid_details_by_domain[domain]
            assert float(entry["p_contribution"]) == pytest.approx(gains["KP"] * details.pid_output.P, abs=0.001)
            assert float(entry["d_contribution"]) == pytest.approx(gains["KD"] * details.pid_output.D, abs=0.001)

    def test_publish_sensor_state(self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()

        sensor = get_state_db_entry("THERMAL_SENSOR_PID_INFO", "ASIC Diode 0")
        assert sensor is not None
        assert sensor["domain"] == "asic"
        assert sensor["temperature"] == "78.000"
        assert sensor["setpoint"] == "85.000"
        assert sensor["error"] == "-7.000"
        assert "timestamp" in sensor

        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "Transceiver Port21")["domain"] == "main"
        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "CPU Sensor")["domain"] == "main"

    def test_publish_skips_non_pid_domain(
        self, thermal_pid_state_module, thermal_module, sample_pid_details_by_domain, domain_gains
    ):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()

        assert get_state_db_entry("THERMAL_PID_INFO", thermal_module.PID_DOMAIN_NONE) is None
        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "PSU1 Inlet") is None

    def test_publish_removes_stale_keys(
        self, thermal_pid_state_module, thermal_module, sample_pid_details_by_domain, domain_gains
    ):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()
        assert get_state_db_entry("THERMAL_PID_INFO", "asic") is not None
        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "ASIC NIF1") is not None

        # Second publish with only the main domain and one fewer sensor
        details = {
            "main": make_pid_details(
                thermal_module, "main",
                [thermal_module.SensorDetails("Transceiver Port21", 66.9, -0.1, 67.0)],
                "Transceiver Port21",
            ),
        }
        publisher.publish("main", 50.0, details, domain_gains)
        assert publisher.wait_for_idle()

        assert get_state_db_entry("THERMAL_PID_INFO", "asic") is None
        assert get_state_db_entry("THERMAL_PID_INFO", "main") is not None
        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "ASIC NIF1") is None
        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "ASIC Diode 0") is None
        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "CPU Sensor") is None
        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "Transceiver Port21") is not None

    def test_publish_failsafe(self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()

        publisher.publish_failsafe(100.0)
        assert publisher.wait_for_idle()

        for domain in ("asic", "main"):
            entry = get_state_db_entry("THERMAL_PID_INFO", domain)
            assert entry["status"] == "failsafe"
            assert entry["fan_speed"] == "100.000"
            assert entry["is_driving"] == "false"
            # Prior PID fields are preserved for debugging
            assert entry["driving_sensor"] is not None

    def test_publish_failsafe_without_prior_publish(self, thermal_pid_state_module):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        # Must not raise even though nothing was ever published
        publisher.publish_failsafe(100.0)
        assert publisher.wait_for_idle()
        assert FakeTable._global_db.get("STATE_DB", {}).get("THERMAL_PID_INFO", {}) == {}

    def test_publish_never_raises_on_db_connection_failure(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        with patch.object(
            thermal_pid_state_module.swsscommon, "DBConnector", side_effect=RuntimeError("redis down")
        ):
            # Must not raise; publishing is best-effort
            publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
            assert publisher.wait_for_idle()
            publisher.publish_failsafe(100.0)
            assert publisher.wait_for_idle()
        assert get_state_db_entry("THERMAL_PID_INFO", "main") is None

        # Connection recovers on a later cycle
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()
        assert get_state_db_entry("THERMAL_PID_INFO", "main") is not None

    def test_publish_never_raises_on_write_failure(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        with patch.object(FakeTable, "set", side_effect=RuntimeError("write failed")):
            publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
            assert publisher.wait_for_idle()

    def test_publish_reconnects_after_connection_goes_bad(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        """A cached table handle whose connection goes bad after it was
        established must be dropped on flush failure so the next publish
        reconnects from scratch, instead of reusing the dead handle forever."""
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()
        assert get_state_db_entry("THERMAL_PID_INFO", "main") is not None
        assert publisher._pid_tbl is not None

        # The established connection goes bad: every operation on the cached
        # handles now fails.
        with patch.object(FakeTable, "set", side_effect=RuntimeError("connection reset")):
            publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
            assert publisher.wait_for_idle()

        # The dead handles must have been dropped...
        assert publisher._pid_tbl is None
        assert publisher._sensor_tbl is None

        # ...so the next publish reconnects and recovers.
        publisher.publish("main", 61.0, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()
        entry = get_state_db_entry("THERMAL_PID_INFO", "main")
        assert entry is not None
        assert entry["fan_speed"] == "61.000"

    def test_publish_coalesces_to_latest_snapshot(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        """Snapshots submitted while the worker is busy replace each other;
        only the newest one lands (no backlog behind a slow redis)."""
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        orig_set = FakeTable.set
        entered = threading.Event()
        release = threading.Event()

        def gated_set(self, key, fvp):
            entered.set()
            assert release.wait(5), "test gate never released"
            return orig_set(self, key, fvp)

        with patch.object(FakeTable, "set", gated_set):
            publisher.publish("main", 50.0, sample_pid_details_by_domain, domain_gains)
            assert entered.wait(5)  # worker is now stuck inside the first flush
            publisher.publish("main", 55.0, sample_pid_details_by_domain, domain_gains)
            publisher.publish("main", 61.0, sample_pid_details_by_domain, domain_gains)
            release.set()
            assert publisher.wait_for_idle()

        entry = get_state_db_entry("THERMAL_PID_INFO", "main")
        assert entry["fan_speed"] == "61.000"

    def test_publish_failsafe_merges_into_pending_snapshot(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        """A failsafe marker queued while a snapshot is still pending must
        neither erase the newest data nor be lost behind it: the pending
        snapshot's domains are marked failsafe and both land together."""
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        orig_set = FakeTable.set
        entered = threading.Event()
        release = threading.Event()

        def gated_set(self, key, fvp):
            entered.set()
            assert release.wait(5), "test gate never released"
            return orig_set(self, key, fvp)

        with patch.object(FakeTable, "set", gated_set):
            publisher.publish("main", 50.0, sample_pid_details_by_domain, domain_gains)
            assert entered.wait(5)  # worker busy with the first flush
            # A newer snapshot is pending, then the loop hits failsafe.
            publisher.publish("main", 55.0, sample_pid_details_by_domain, domain_gains)
            publisher.publish_failsafe(100.0)
            release.set()
            assert publisher.wait_for_idle()

        for domain in ("asic", "main"):
            entry = get_state_db_entry("THERMAL_PID_INFO", domain)
            assert entry["status"] == "failsafe"
            assert entry["is_driving"] == "false"
            assert entry["fan_speed"] == "100.000"
            # The newest snapshot's measurement data landed with the marker.
            assert entry["driving_sensor"] is not None

    def test_publish_does_not_block_when_flush_is_stuck(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        """publish() must return promptly even while the worker is blocked
        inside a redis write — no redis work happens on the control path."""
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        orig_set = FakeTable.set
        entered = threading.Event()
        release = threading.Event()

        def gated_set(self, key, fvp):
            entered.set()
            assert release.wait(5), "test gate never released"
            return orig_set(self, key, fvp)

        with patch.object(FakeTable, "set", gated_set):
            publisher.publish("main", 50.0, sample_pid_details_by_domain, domain_gains)
            assert entered.wait(5)  # worker is stuck mid-flush
            start = time.monotonic()
            publisher.publish("main", 55.0, sample_pid_details_by_domain, domain_gains)
            publisher.publish_failsafe(100.0)
            elapsed = time.monotonic() - start
            release.set()
            assert publisher.wait_for_idle()
        assert elapsed < 1.0, f"publish blocked for {elapsed:.2f}s while worker was stuck"

    def test_publish_failsafe_seeds_configured_domains_on_empty_table(
        self, thermal_pid_state_module
    ):
        """A failure before the first successful cycle must still record
        failsafe rows: the marker seeds every configured domain."""
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish_failsafe(100.0, domains=["asic", "main"])
        assert publisher.wait_for_idle()

        for domain in ("asic", "main"):
            entry = get_state_db_entry("THERMAL_PID_INFO", domain)
            assert entry is not None
            assert entry["status"] == "failsafe"
            assert entry["fan_speed"] == "100.000"
            assert entry["is_driving"] == "false"

    def test_publish_failsafe_with_unknown_fan_speed(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        """When forcing the fans failed, the actual speed is unknown and must
        be published as N/A, not as the commanded maximum."""
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()

        publisher.publish_failsafe(None)
        assert publisher.wait_for_idle()
        entry = get_state_db_entry("THERMAL_PID_INFO", "main")
        assert entry["status"] == "failsafe"
        assert entry["fan_speed"] == "N/A"

    def test_publish_reports_effective_setpoint_with_extra_margin(
        self, thermal_pid_state_module, thermal_module, domain_gains
    ):
        """Published setpoints include the extra setpoint margin so that
        error == temperature - setpoint holds for consumers."""
        # error = temp - setpoint - margin = 66.9 - 67.0 - 5.0 = -5.1
        sensors = [thermal_module.SensorDetails("Transceiver Port21", 66.9, -5.1, 67.0)]
        details = {
            "main": make_pid_details(thermal_module, "main", sensors, "Transceiver Port21"),
        }
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 50.0, details, domain_gains, extra_margins={"main": 5.0})
        assert publisher.wait_for_idle()

        entry = get_state_db_entry("THERMAL_PID_INFO", "main")
        assert entry["setpoint"] == "72.000"
        assert float(entry["driving_sensor_temp"]) - float(entry["setpoint"]) == pytest.approx(
            float(entry["error"]), abs=0.001
        )
        sensor = get_state_db_entry("THERMAL_SENSOR_PID_INFO", "Transceiver Port21")
        assert sensor["setpoint"] == "72.000"
        assert float(sensor["temperature"]) - float(sensor["setpoint"]) == pytest.approx(
            float(sensor["error"]), abs=0.001
        )

    def test_publish_failsafe_not_dropped_by_pending_empty_snapshot(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        """A pending snapshot with no domains must not swallow the failsafe
        marker: the marker replaces it instead of merging into nothing."""
        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
        assert publisher.wait_for_idle()

        orig_set = FakeTable.set
        entered = threading.Event()
        release = threading.Event()

        def gated_set(self, key, fvp):
            entered.set()
            assert release.wait(5), "test gate never released"
            return orig_set(self, key, fvp)

        with patch.object(FakeTable, "set", gated_set):
            # Occupy the worker, then queue an EMPTY snapshot and a failsafe.
            publisher.publish("main", 61.0, sample_pid_details_by_domain, domain_gains)
            assert entered.wait(5)
            publisher.publish("main", 62.0, {}, domain_gains)
            publisher.publish_failsafe(100.0)
            release.set()
            assert publisher.wait_for_idle()

        entry = get_state_db_entry("THERMAL_PID_INFO", "main")
        assert entry["status"] == "failsafe"
        assert entry["fan_speed"] == "100.000"

    def test_publish_writes_reachable_table_when_other_is_down(
        self, thermal_pid_state_module, sample_pid_details_by_domain, domain_gains
    ):
        """One unreachable table must not drop the other table's data."""
        orig_table = thermal_pid_state_module.swsscommon.Table

        def selective_table(db, table_name):
            if table_name == "THERMAL_SENSOR_PID_INFO":
                raise RuntimeError("sensor table unavailable")
            return orig_table(db, table_name)

        publisher = thermal_pid_state_module.ThermalPidStatePublisher()
        with patch.object(thermal_pid_state_module, "try_get_state_db_table",
                          side_effect=lambda log, name: None if name == "THERMAL_SENSOR_PID_INFO"
                          else orig_table(thermal_pid_state_module.swsscommon.DBConnector("STATE_DB", 0), name)):
            publisher.publish("main", 60.5, sample_pid_details_by_domain, domain_gains)
            assert publisher.wait_for_idle()

        assert get_state_db_entry("THERMAL_PID_INFO", "main") is not None
        assert get_state_db_entry("THERMAL_SENSOR_PID_INFO", "Transceiver Port21") is None

    def test_fmt(self, thermal_pid_state_module):
        _fmt = thermal_pid_state_module._fmt
        assert _fmt(None) == "N/A"
        assert _fmt(True) == "true"
        assert _fmt(False) == "false"
        assert _fmt(60.5) == "60.500"
        assert _fmt(5) == "5"
        assert _fmt("asic") == "asic"
