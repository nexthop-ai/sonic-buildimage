# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Digital Power Manager (DPM) file logger.

This module provides device-independent functionality for storing and retrieving
reboot causes and DPM records using a queue system to handle boot-looping:

- Initial reboots (initial_reboots.jsonl): First 5 reboots of a boot-loop,
  append-only.
- Recent reboots (recent_reboots.jsonl): Last 5 reboots of a boot-loop,
  circular buffer that skips oldest. Stored as JSONL files.
- History (history.jsonl): Persistent log of up to 20 entries. When the system
  stays up for >30 minutes, the initial/recent reboot logs are moved into the history log.

This design ensures that during a boot-loop of N reboots, we retain reboots
1-5 and (N-4)-N for investigation.
"""

import datetime
import glob
import json
import os
import tempfile

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path
from sonic_platform.dpm_base import DpmBase, DpmPowerUpEntry, RebootCause, timestamp_as_string
from typing import Iterable


@dataclass
class DataBase(ABC):
    gen_time: str
    schema_version: int

    @abstractmethod
    def is_empty(self) -> bool:
        """Returns True if this data object contains no reboot causes or DPM records."""
        pass


@dataclass
class CauseV1:
    source: str
    timestamp: str
    cause: str
    description: str


@dataclass
class DpmV1:
    name: str
    type: str
    records: list[dict[str, str]]


@dataclass
class DataV1(DataBase):
    causes: list[CauseV1]
    dpms: list[DpmV1]

    def __post_init__(self):
        # Convert causes dicts into CauseV1 objects
        self.causes = [c if isinstance(c, CauseV1) else CauseV1(**c) for c in self.causes]
        # Convert dpms dicts into DpmV1 objects
        self.dpms = [d if isinstance(d, DpmV1) else DpmV1(**d) for d in self.dpms]

    def is_empty(self) -> bool:
        """Returns True if there are no causes and all DPMs have no records.

        A DataV1 instance is considered empty when both of the following hold:
          - the causes list is empty, and
          - for every DPM entry, its records list is empty.
        """
        return not self.causes and not any(dpm.records for dpm in self.dpms)


@dataclass
class SkippedReboots:
    """Marker for reboots that were skipped and are not shown."""
    count: int


def _parse_data_line(line: str) -> DataBase | None:
    """Parses a single JSONL line into a DataBase object, or None if not a data line."""
    try:
        data = json.loads(line)
        if data.get("schema_version") == 1:
            return DataV1(**data)
    except Exception:
        pass
    return None


def load_data_from_file(path: Path | str) -> DataBase | None:
    """Loads and parses a JSON file into a structured Data object.

    Args:
        path: Path to JSON file.

    Returns:
        Parsed Data object, or None if parsing fails.
    """
    try:
        return _parse_data_line(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return None


class DpmLogger:
    """Manages persistent storage of system-wide reboot causes and DPM records.

    Uses initial/recent/history queues stored as JSONL files:

    - Initial reboots (initial_reboots.jsonl): First 5 reboots since last stable
      boot, append-only.
    - Recent reboots (recent_reboots.jsonl): Last 5 reboots since last stable boot,
      circular buffer that skips the oldest entry when full. First line is
      metadata: {"skipped_reboots": N}.
    - History (history.jsonl): Persistent log, up to 20 entries. Populated when
      the system is marked stable (30 min uptime). May contain
      {"skipped_reboots": N} separator lines between groups.

    Usage:
        logger = DpmLogger()
        logger.save(causes, dpm_to_powerups)  # Called on each boot to record reboot cause
        logger.drain_to_history()             # Called by rotate-log after 30min uptime
        logger.load()                         # Returns the most recent entry
        logger.load_all()                     # Returns (all_entries, total_reboot_count, skipped_reboot_count)
    """

    HISTORY_DIR = "/host/reboot-cause/nexthop"
    INITIAL_REBOOTS_FILE = "initial_reboots.jsonl"
    RECENT_REBOOTS_FILE = "recent_reboots.jsonl"
    HISTORY_FILE = "history.jsonl"
    INITIAL_REBOOTS_MAX = 5
    RECENT_REBOOTS_MAX = 5
    HISTORY_MAX = 20

    def __init__(self) -> None:
        """Initializes the DPM logger."""
        self._initial_reboots_path = os.path.join(self.HISTORY_DIR, self.INITIAL_REBOOTS_FILE)
        self._recent_reboots_path = os.path.join(self.HISTORY_DIR, self.RECENT_REBOOTS_FILE)
        self._history_path = os.path.join(self.HISTORY_DIR, self.HISTORY_FILE)

    def _count_lines(self, filepath: str) -> int:
        """Counts lines in a file without loading all content."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return sum(1 for _ in f)
        except FileNotFoundError:
            return 0

    def _append_entry(self, filepath: str, entry: DataBase) -> None:
        """Appends a single data entry as a JSON line to a file."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")

    def _load_entries(self, filepath: str) -> list[DataBase]:
        """Reads a JSONL file and returns all data entries (skipping non-data lines)."""
        entries = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = _parse_data_line(line)
                    if entry is not None:
                        entries.append(entry)
        except FileNotFoundError:
            pass
        return entries

    def _atomic_write_lines(self, filepath: str, lines: list[str]) -> None:
        """Atomically writes lines to a file using write-to-temp + rename."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(filepath))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for line in lines:
                    f.write(line + "\n")
            # allow root to read/write, group/others to read.
            os.chmod(tmp_path, 0o644)
            os.rename(tmp_path, filepath)
        except Exception:
            os.unlink(tmp_path)
            raise

    def _load_initial_reboots(self) -> list[DataBase]:
        """Loads initial reboots entries."""
        return self._load_entries(self._initial_reboots_path)

    def _load_recent_reboots(self) -> tuple[list[DataBase], int]:
        """Loads recent reboots file, returning (entries, skipped_reboots)."""
        skipped_reboots = 0
        try:
            with open(self._recent_reboots_path, "r", encoding="utf-8") as f:
                first_line = f.readline().strip()
                if first_line:
                    meta = json.loads(first_line)
                    skipped_reboots = meta.get("skipped_reboots", 0)
        except (FileNotFoundError, Exception):
            pass
        return self._load_entries(self._recent_reboots_path), skipped_reboots

    def _save_recent_reboots(self, skipped_reboots: int, entries: list[DataBase]) -> None:
        """Writes recent reboots with metadata first line + data entries."""
        lines = [json.dumps({"skipped_reboots": skipped_reboots})]
        lines.extend(json.dumps(asdict(e)) for e in entries)
        self._atomic_write_lines(self._recent_reboots_path, lines)

    def _load_history_raw(self) -> list[str]:
        """Loads history log as raw JSON strings (preserving separator lines)."""
        lines = []
        try:
            with open(self._history_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(line)
        except FileNotFoundError:
            pass
        return lines

    def _load_history(self) -> tuple[list[DataBase | SkippedReboots], int]:
        """Loads history log preserving skip markers between entries.

        Returns:
            A tuple of (items, total_skipped) where items is a list of DataBase
            entries interleaved with SkippedReboots markers, and total_skipped
            is the sum of all skipped reboot counts.
        """
        items: list[DataBase | SkippedReboots] = []
        total_skipped = 0
        for line in self._load_history_raw():
            try:
                data = json.loads(line)
                if "skipped_reboots" in data and "schema_version" not in data:
                    total_skipped += data["skipped_reboots"]
                    items.append(SkippedReboots(count=data["skipped_reboots"]))
                    continue
                entry = _parse_data_line(line)
                if entry is not None:
                    items.append(entry)
            except Exception:
                continue
        return items, total_skipped

    def _migrate_old_files(self) -> None:
        """Migrates old per-file reboot-cause-*.json files into the history log.

        TODO(NOS-6709): This is backward-compatible migration code. It can be removed
        once the new queue-based implementation is soaked/matured.
        """
        old_files = sorted(glob.glob(os.path.join(self.HISTORY_DIR, "reboot-cause-*.json")))
        if not old_files:
            return

        # Load old entries
        old_entries = []
        for path in old_files:
            entry = load_data_from_file(path)
            if entry is not None and isinstance(entry, DataV1):
                old_entries.append(entry)

        # Prepend old entries to history log
        new_lines = [json.dumps(asdict(e)) for e in old_entries]
        self._write_to_history(new_lines, prepend=True)

        # Delete old files
        for path in old_files:
            os.unlink(path)
        # Delete old symlink
        prev_link = os.path.join(self.HISTORY_DIR, "previous-reboot-cause.json")
        if os.path.islink(prev_link) or os.path.exists(prev_link):
            os.remove(prev_link)

    def _write_to_history(self, new_lines: list[str], prepend: bool) -> None:
        """Merges new lines into the history log, trims, and atomically writes.

        Args:
            new_lines: JSON lines to add.
            prepend: If True, new lines go before existing; otherwise after.
        """
        existing_lines = self._load_history_raw()
        if prepend:
            all_lines = new_lines + existing_lines
        else:
            all_lines = existing_lines + new_lines
        all_lines = self._trim_history_lines(all_lines)
        self._atomic_write_lines(self._history_path, all_lines)

    def _trim_history_lines(self, raw_lines: list[str]) -> list[str]:
        """Trims history lines to HISTORY_MAX data entries.

        Counts only data lines toward the limit (separator lines don't count).
        Trims from the front (oldest first). If trimming leaves a separator as
        the first line, drops it.
        """
        # Walk backwards to find where the last HISTORY_MAX data entries start
        kept = 0
        cutoff = -1
        for i in range(len(raw_lines) - 1, -1, -1):
            if _parse_data_line(raw_lines[i]) is not None:
                kept += 1
                if kept >= self.HISTORY_MAX:
                    cutoff = i
                    break

        if cutoff == -1:
            return raw_lines

        # Slice from cutoff, drop leading separator if present
        result = raw_lines[cutoff:]
        if result and _parse_data_line(result[0]) is None:
            result = result[1:]

        return result

    def to_data(
        self,
        causes: Iterable[RebootCause],
        dpm_to_powerups: dict[DpmBase, list[DpmPowerUpEntry]],
    ) -> tuple[DataBase, datetime.datetime]:
        """Converts causes and DPM records to a DataBase object.

        Args:
            causes: List of RebootCause objects, as observed from
                    SW reboot cause and HW DPM records.
            dpm_to_powerups: Dictionary of DPM to list of powerups,
                             where each powerup contains a list of DPM records.
        """
        gen_time = datetime.datetime.now(tz=datetime.timezone.utc)
        data = DataV1(
            gen_time=gen_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
            schema_version=1,
            causes=[
                CauseV1(
                    c.source,
                    timestamp_as_string(c.timestamp),
                    c.cause,
                    c.description if c.type == RebootCause.Type.HARDWARE else "n/a",
                )
                for c in causes
            ],
            dpms=[
                DpmV1(
                    dpm.get_name(),
                    dpm.get_type().value,
                    [record.as_dict() for powerup in powerups for record in powerup.dpm_records],
                )
                for dpm, powerups in dpm_to_powerups.items()
            ],
        )
        return data, gen_time

    def save(
        self,
        causes: Iterable[RebootCause],
        dpm_to_powerups: dict[DpmBase, list[DpmPowerUpEntry]],
    ) -> None:
        """Saves causes and DPM records to initial/recent reboot logs.

        If initial reboots has room (< INITIAL_REBOOTS_MAX), appends there.
        Otherwise, pushes to recent reboots (circular, skips oldest when full).

        Args:
            causes: List of RebootCause objects, as observed from
                    SW reboot cause and HW DPM records.
            dpm_to_powerups: Dictionary of DPM to list of powerups,
                             where each powerup contains a list of DPM records.
        """
        data, _ = self.to_data(causes, dpm_to_powerups)

        # Migrate old per-file format (backward-compatible, can be removed once soaked)
        self._migrate_old_files()

        os.makedirs(self.HISTORY_DIR, exist_ok=True)

        # Try initial reboots first
        initial_count = self._count_lines(self._initial_reboots_path)
        if initial_count < self.INITIAL_REBOOTS_MAX:
            self._append_entry(self._initial_reboots_path, data)
            return

        # Initial reboots full, push to recent reboots
        recent_entries, skipped_reboots = self._load_recent_reboots()
        recent_entries.append(data)
        if len(recent_entries) > self.RECENT_REBOOTS_MAX:
            recent_entries.pop(0)
            skipped_reboots += 1
        self._save_recent_reboots(skipped_reboots, recent_entries)

    def drain_to_history(self) -> None:
        """Drains initial/recent reboot logs into the persistent history log.

        Called by systemd timer after 30 minutes of uptime. Moves all entries
        from initial reboots and recent reboots into the history log, inserting
        a {"skipped_reboots": N} separator if reboots were skipped.
        """
        initial_entries = self._load_initial_reboots()
        recent_entries, skipped_reboots = self._load_recent_reboots()

        if not initial_entries and not recent_entries:
            return

        # Build new lines: initial + separator (if skipped) + recent
        new_lines = [json.dumps(asdict(e)) for e in initial_entries]
        if skipped_reboots > 0:
            new_lines.append(json.dumps({"skipped_reboots": skipped_reboots}))
        new_lines.extend(json.dumps(asdict(e)) for e in recent_entries)

        # Append to history log and trim
        self._write_to_history(new_lines, prepend=False)

        # Clear initial/recent reboot logs
        for path in (self._initial_reboots_path, self._recent_reboots_path):
            if os.path.exists(path):
                os.unlink(path)

    def load(self) -> DataBase | None:
        """Loads the most recent reboot cause entry.

        Checks recent reboots (last entry) -> initial reboots (last entry) -> history (last entry).

        Caller can try casting to DataV1 for schema_version 1, and etc.

        Returns:
            The newest DataV1 entry, or None if no entries exist.
        """
        # Check recent reboots last entry
        recent_entries, _ = self._load_recent_reboots()
        if recent_entries:
            return recent_entries[-1]

        # Check initial reboots last entry
        initial_entries = self._load_initial_reboots()
        if initial_entries:
            return initial_entries[-1]

        # Check history last entry
        history_items, _ = self._load_history()
        for item in reversed(history_items):
            if isinstance(item, DataBase):
                return item

        return None

    def load_all(self) -> tuple[list[DataBase | SkippedReboots], int, int]:
        """Loads all reboot cause entries and reboot counts.

        Returns:
            A tuple of (items, total_reboots, skipped_reboots) where:
            - items: All data entries in chronological order (oldest to newest)
                     from history + initial reboots + recent reboots, interleaved with
                     SkippedReboots markers where reboots were skipped.
            - total_reboots: Total number of reboots including skipped ones.
            - skipped_reboots: Number of reboots that were skipped and not shown.
        """
<<<<<<< HEAD
        return [
            data for path in self._get_sorted_history_files() 
            if (data := load_data_from_file(path)) is not None
        ]
=======
        # History: entries interleaved with skip markers
        history_items, history_skipped = self._load_history()

        # Initial reboots
        initial_entries = self._load_initial_reboots()

        # Recent reboots
        recent_entries, recent_skipped = self._load_recent_reboots()

        # Bundle history + initial + recent (with skip markers)
        all_items: list[DataBase | SkippedReboots] = list(history_items)
        all_items.extend(initial_entries)
        if recent_skipped > 0:
            all_items.append(SkippedReboots(count=recent_skipped))
        all_items.extend(recent_entries)

        skipped = history_skipped + recent_skipped
        entry_count = sum(1 for item in all_items if isinstance(item, DataBase))
        total_reboots = entry_count + skipped

        return all_items, total_reboots, skipped
>>>>>>> 5c5594979 (NOS-5473: Boot-loop reboot-cause logging with queues system (#4095))
