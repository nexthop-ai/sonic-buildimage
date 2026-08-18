#!/usr/bin/env python

# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
STATE_DB publisher for thermal PID controller state.

Publishes two tables to STATE_DB on every thermal control cycle so that
CLI/telemetry consumers can observe the PID loop:

1. THERMAL_PID_INFO|<domain>: per-domain PID state
   Fields:
   - setpoint: Effective setpoint of the driving sensor (degrees C),
     including any configured extra setpoint margin, so that
     error == driving_sensor_temp - setpoint always holds
   - driving_sensor: Sensor with the largest error, whose error feeds the PID
   - driving_sensor_temp: Temperature of the driving sensor (degrees C)
   - error: PID input error of the driving sensor (degrees C)
   - p_contribution/i_contribution/d_contribution: Gain-multiplied
     contribution of each PID term to raw_output (contributions sum to
     raw_output)
   - raw_output: Unsaturated PID output (percent)
   - output: Saturated PID output (percent)
   - integral_frozen: Whether the integral term is frozen (anti-windup)
   - kp/ki/kd: Configured PID gains
   - is_driving: Whether this domain is driving the fan speed
   - fan_speed: Fan speed commanded for all fans this cycle (percent). On a
     failsafe where forcing fans to maximum itself failed, this is "N/A" —
     the fans' actual speed is unknown
   - status: "ok", or "failsafe" if the thermal control algorithm hit an
     error and forced fans to maximum speed
   - timestamp: ISO-format timestamp of the last update

2. THERMAL_SENSOR_PID_INFO|<sensor>: per-sensor PID domain membership.
   Only PID-controlled sensors appear; sensors outside any PID domain are
   not published.
   Fields:
   - domain: PID domain the sensor belongs to
   - temperature: Current temperature (degrees C)
   - setpoint: Effective setpoint (degrees C), including any configured
     extra setpoint margin
   - error: PID input error (degrees C)
   - timestamp: ISO-format timestamp of the last update

Failsafe publishing takes one of two paths: if a state snapshot is still
unflushed, the failsafe fields are merged into it so the newest data and the
marker land together; otherwise a marker is queued that rewrites the
failsafe fields of every existing THERMAL_PID_INFO key plus every configured
domain the caller names — so a failure before the first successful cycle
still publishes a failsafe indication.

Publishing must never break or delay the control loop:

- All redis work runs on a dedicated daemon worker thread. The control loop
  only formats a plain-Python snapshot and hands it to the worker under a
  condition variable, so no swsscommon call happens on the control path.
- Snapshots coalesce: only the most recent one is kept, so a slow or
  unavailable redis can never build a backlog — intermediate snapshots are
  stale the moment a newer one exists.
- All submit/flush/connect errors are swallowed and logged, rate-limited to
  one message per failure streak. On any flush failure the cached STATE_DB
  table handles are dropped, so the next flush re-establishes the connection
  rather than reusing a handle whose connection has gone bad. If only one of
  the two tables is reachable, the reachable one is still written.
"""

import threading
import traceback

from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from swsscommon import swsscommon

from sonic_platform.state_db import try_get_state_db_table
from sonic_platform.syslog import SYSLOG_IDENTIFIER_THERMAL, NhLoggerMixin
from sonic_platform.thermal import PID_DOMAIN_NONE, PidDomainDetails, SensorDetails

PID_INFO_TABLE_NAME = "THERMAL_PID_INFO"
SENSOR_PID_INFO_TABLE_NAME = "THERMAL_SENSOR_PID_INFO"

STATUS_OK = "ok"
STATUS_FAILSAFE = "failsafe"

NOT_AVAILABLE = "N/A"

# Snapshot kinds handed from the control loop to the worker thread
_KIND_STATE = "state"
_KIND_FAILSAFE = "failsafe"


def _fmt(value: Any) -> str:
    """Format a value for STATE_DB storage."""
    if value is None:
        return NOT_AVAILABLE
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


class ThermalPidStatePublisher(NhLoggerMixin):
    """
    Publishes PID controller state to STATE_DB via a dedicated worker thread.

    The control loop calls publish()/publish_failsafe(), which only format a
    snapshot and notify the worker; the worker owns every swsscommon object
    (connections are thread-confined) and performs the actual redis writes.
    """

    def __init__(self) -> None:
        super().__init__(SYSLOG_IDENTIFIER_THERMAL)
        # Redis handles — owned exclusively by the worker thread.
        self._pid_tbl: Optional[swsscommon.Table] = None
        self._sensor_tbl: Optional[swsscommon.Table] = None
        # Key sets from the previous successful flush, so stale-key removal
        # is an in-memory set difference instead of a per-cycle table scan.
        # None means unknown (fresh start or reconnect) and forces one full
        # scan to resync with whatever an earlier writer left behind.
        self._last_pid_keys: Optional[Set[str]] = None
        self._last_sensor_keys: Optional[Set[str]] = None
        # Handoff state, guarded by the condition variable.
        self._cond = threading.Condition()
        self._pending: Optional[Tuple[str, Dict[str, Any]]] = None
        self._flushing: bool = False
        self._worker: Optional[threading.Thread] = None
        # Avoid flooding syslog with the same error every control cycle
        self._submit_error_logged: bool = False
        self._failsafe_error_logged: bool = False
        self._flush_error_logged: bool = False
        self._connect_warning_logged: bool = False
        self.log_debug("Initialized")

    # ------------------------------------------------------------------
    # Control-loop side: format + hand off. No swsscommon calls here.
    # ------------------------------------------------------------------

    def publish(
        self,
        driving_domain: str,
        fan_speed: float,
        pid_details_by_domain: Dict[str, PidDomainDetails],
        domain_gains: Dict[str, Dict[str, float]],
        extra_margins: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Queue per-domain and per-sensor PID state for publishing. Never raises
        and never blocks on redis.

        Args:
            driving_domain: The domain driving the fan speed this cycle
            fan_speed: Fan speed applied to all fans this cycle (percent)
            pid_details_by_domain: Dict mapping domain to PidDomainDetails
            domain_gains: Dict mapping domain to its gain config (KP/KI/KD)
            extra_margins: Dict mapping domain to its extra setpoint margin;
                published setpoints include this margin so that
                error == temperature - setpoint holds for consumers
        """
        try:
            snapshot = self._build_snapshot(
                driving_domain, fan_speed, pid_details_by_domain, domain_gains, extra_margins
            )
            self._submit((_KIND_STATE, snapshot))
        except Exception as e:
            if not self._submit_error_logged:
                self.log_error(f"Failed to queue PID state for publishing: {e}")
                self.log_error(f"Traceback:\n{traceback.format_exc()}")
                self._submit_error_logged = True
            return
        self._submit_error_logged = False

    def publish_failsafe(self, fan_speed: Optional[float], domains: Optional[List[str]] = None) -> None:
        """
        Queue a failsafe marker: all published domains (plus any configured
        domains named here) get status=failsafe. Never raises and never
        blocks on redis.

        Args:
            fan_speed: Fan speed commanded for all fans (percent), or None
                when forcing the fans failed and their actual speed is
                unknown (published as "N/A")
            domains: Configured domain names to seed rows for, so a failure
                before the first successful cycle still publishes a failsafe
                indication
        """
        try:
            failsafe = self._failsafe_fields(_fmt(fan_speed), datetime.now().isoformat())
            with self._cond:
                self._ensure_worker_locked()
                if (
                    self._pending is not None
                    and self._pending[0] == _KIND_STATE
                    and self._pending[1]["domains"]
                ):
                    # A not-yet-flushed snapshot with data is pending. Don't
                    # let the failsafe marker replace it (that would lose the
                    # newest data) or get lost behind it: mark the pending
                    # snapshot's domains failsafe so both land together.
                    for fields in self._pending[1]["domains"].values():
                        fields.update(failsafe)
                else:
                    # Nothing pending (or an empty snapshot that would drop
                    # the marker): queue the marker itself.
                    failsafe["domains"] = list(domains or [])
                    self._pending = (_KIND_FAILSAFE, failsafe)
                self._cond.notify_all()
        except Exception as e:
            if not self._failsafe_error_logged:
                self.log_error(f"Failed to queue failsafe PID state: {e}")
                self.log_error(f"Traceback:\n{traceback.format_exc()}")
                self._failsafe_error_logged = True
            return
        self._failsafe_error_logged = False

    def _build_snapshot(
        self,
        driving_domain: str,
        fan_speed: float,
        pid_details_by_domain: Dict[str, PidDomainDetails],
        domain_gains: Dict[str, Dict[str, float]],
        extra_margins: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Format PID details into a plain string-only snapshot (pure Python)."""
        timestamp = datetime.now().isoformat()
        domains: Dict[str, Dict[str, str]] = {}
        sensors: Dict[str, Dict[str, str]] = {}

        for domain, details in pid_details_by_domain.items():
            if domain == PID_DOMAIN_NONE or details.pid_output is None:
                continue

            driving_sensor = self._find_sensor(details.sensors, details.max_error_sensor_name)
            gains = domain_gains.get(domain, {}) if domain_gains else {}
            kp, ki, kd = gains.get("KP"), gains.get("KI"), gains.get("KD")
            # The PID input error is temp - setpoint - extra_setpoint_margin;
            # publish the effective setpoint (setpoint + margin) so that
            # error == temperature - setpoint holds for consumers.
            margin = (extra_margins or {}).get(domain, 0) or 0
            out = details.pid_output
            p_contribution = kp * out.P if kp is not None else None
            d_contribution = kd * out.D if kd is not None else None
            # Derive I contribution from the total so contributions always sum
            # to raw_output (PidOutput.I holds the post-freeze integral, which
            # may differ from the integral used in this cycle's output).
            i_contribution = None
            if p_contribution is not None and d_contribution is not None:
                i_contribution = out.raw_output - p_contribution - d_contribution

            driving_setpoint = None
            if driving_sensor is not None and driving_sensor.setpoint is not None:
                driving_setpoint = driving_sensor.setpoint + margin

            domains[domain] = {
                "setpoint": _fmt(driving_setpoint),
                "driving_sensor": _fmt(details.max_error_sensor_name),
                "driving_sensor_temp": _fmt(driving_sensor.temperature if driving_sensor else None),
                "error": _fmt(driving_sensor.input_error if driving_sensor else None),
                "p_contribution": _fmt(p_contribution),
                "i_contribution": _fmt(i_contribution),
                "d_contribution": _fmt(d_contribution),
                "raw_output": _fmt(out.raw_output),
                "output": _fmt(out.saturated_output),
                "integral_frozen": _fmt(out.frozen_integral),
                "kp": _fmt(kp),
                "ki": _fmt(ki),
                "kd": _fmt(kd),
                "is_driving": _fmt(domain == driving_domain),
                "fan_speed": _fmt(fan_speed),
                "status": STATUS_OK,
                "timestamp": timestamp,
            }

            for sensor in details.sensors:
                setpoint = sensor.setpoint + margin if sensor.setpoint is not None else None
                sensors[sensor.sensor_name] = {
                    "domain": domain,
                    "temperature": _fmt(sensor.temperature),
                    "setpoint": _fmt(setpoint),
                    "error": _fmt(sensor.input_error),
                    "timestamp": timestamp,
                }

        return {"domains": domains, "sensors": sensors}

    def _submit(self, item: Tuple[str, Dict[str, Any]]) -> None:
        """Replace any pending snapshot with this one and wake the worker."""
        with self._cond:
            self._ensure_worker_locked()
            self._pending = item
            self._cond.notify_all()

    def _ensure_worker_locked(self) -> None:
        """Start the worker thread if needed. Caller must hold self._cond."""
        if self._worker is not None and self._worker.is_alive():
            return
        self._worker = threading.Thread(
            target=self._worker_loop, name="thermal-pid-publisher", daemon=True
        )
        self._worker.start()

    # ------------------------------------------------------------------
    # Worker-thread side: owns all swsscommon objects and redis I/O.
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        """Flush snapshots forever. Survives (and logs) all flush errors."""
        while True:
            with self._cond:
                while self._pending is None:
                    self._cond.wait()
                item = self._pending
                self._pending = None
                self._flushing = True
            try:
                self._flush(item)
                self._flush_error_logged = False
            except Exception as e:
                # Drop the table handles: their underlying connection may be
                # the reason for the failure, and reusing it would fail every
                # subsequent cycle. The next flush reconnects from scratch and
                # rescans for stale keys.
                self._pid_tbl = None
                self._sensor_tbl = None
                self._last_pid_keys = None
                self._last_sensor_keys = None
                if not self._flush_error_logged:
                    self.log_error(f"Failed to publish PID state to STATE_DB: {e}")
                    self.log_error(f"Traceback:\n{traceback.format_exc()}")
                    self._flush_error_logged = True
            finally:
                with self._cond:
                    self._flushing = False
                    self._cond.notify_all()

    def _flush(self, item: Tuple[str, Dict[str, Any]]) -> None:
        """Write one snapshot to STATE_DB. Runs on the worker thread only."""
        self._ensure_tables()

        kind, data = item
        if kind == _KIND_FAILSAFE:
            if self._pid_tbl is None:
                # redis-server not up (yet); drop the marker — the failsafe
                # path re-queues one every cycle while the algorithm fails.
                return
            # Mark every existing key plus every configured domain, so a
            # failure before the first successful cycle still records
            # failsafe rows.
            keys = set(self._pid_tbl.getKeys()) | set(data.get("domains") or [])
            fields = [(k, v) for k, v in data.items() if k != "domains"]
            for key in keys:
                self._pid_tbl.set(key, swsscommon.FieldValuePairs(fields))
            self._last_pid_keys = keys
            return

        # Write whichever tables are reachable — one bad table must not drop
        # the other table's data.
        if self._pid_tbl is not None:
            live = set(data["domains"].keys())
            for domain, fields in data["domains"].items():
                self._pid_tbl.set(domain, swsscommon.FieldValuePairs(list(fields.items())))
            # Drop keys from previous cycles that are no longer present (e.g.
            # a config change on daemon restart).
            self._remove_stale_keys(self._pid_tbl, live, self._last_pid_keys)
            self._last_pid_keys = live
        if self._sensor_tbl is not None:
            live = set(data["sensors"].keys())
            for sensor_name, fields in data["sensors"].items():
                self._sensor_tbl.set(sensor_name, swsscommon.FieldValuePairs(list(fields.items())))
            # e.g. a hot-removed transceiver disappears from the mapping.
            self._remove_stale_keys(self._sensor_tbl, live, self._last_sensor_keys)
            self._last_sensor_keys = live

    def _ensure_tables(self) -> None:
        """
        Lazily (re-)connect to the STATE_DB tables, each independently.

        Connection warnings are rate-limited to one per failure streak.
        """
        log = None if self._connect_warning_logged else self
        if self._pid_tbl is None:
            self._pid_tbl = try_get_state_db_table(log, PID_INFO_TABLE_NAME)
        if self._sensor_tbl is None:
            self._sensor_tbl = try_get_state_db_table(log, SENSOR_PID_INFO_TABLE_NAME)
        self._connect_warning_logged = self._pid_tbl is None or self._sensor_tbl is None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def wait_for_idle(self, timeout: float = 5.0) -> bool:
        """
        Block until all submitted snapshots are flushed (or dropped).

        Used by tests and by the failsafe path (bounded), so a daemon that is
        about to die on the propagating exception still lands the marker.
        Returns False on timeout.
        """
        import time
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._pending is not None or self._flushing:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)
        return True

    @staticmethod
    def _failsafe_fields(fan_speed_str: str, timestamp: str) -> Dict[str, str]:
        """The four fields a failsafe refreshes — single source for both paths."""
        return {
            "status": STATUS_FAILSAFE,
            "is_driving": _fmt(False),
            "fan_speed": fan_speed_str,
            "timestamp": timestamp,
        }

    @staticmethod
    def _find_sensor(sensors: List[SensorDetails], sensor_name: Optional[str]) -> Optional[SensorDetails]:
        for sensor in sensors:
            if sensor.sensor_name == sensor_name:
                return sensor
        return None

    @staticmethod
    def _remove_stale_keys(
        table: swsscommon.Table, live_keys: Set[str], last_keys: Optional[Set[str]]
    ) -> None:
        """
        Delete keys that are no longer live.

        Uses the previous flush's key set when known, so the common case is an
        in-memory set difference; a full table scan happens only on the first
        flush after a (re)connect, to resync with keys an earlier writer left.
        """
        candidates = set(table.getKeys()) if last_keys is None else last_keys
        for key in candidates - live_keys:
            table._del(key)
