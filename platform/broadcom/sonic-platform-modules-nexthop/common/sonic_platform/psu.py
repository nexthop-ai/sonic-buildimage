#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

try:
    from sonic_platform_pddf_base.pddf_psu import PddfPsu
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")

<<<<<<< HEAD
=======
PMBUS_BLACKBOX_CMD = 0xDC
PMBUS_BLACKBOX_MAX_LEN = 255
PMBUS_REAL_TIME_BLACKBOX_CMD = 0xDD
PMBUS_BLACKBOX_CONFIG_CMD = 0xDF
PMBUS_CLEAR_BLACKBOX_CMD = 0xE0
PMBUS_BLACKBOX_CONFIG_ENABLE_BIT = 0x01
PMBUS_STATUS_INPUT_CMD = 0x7C
PMBUS_STATUS_INPUT_VIN_OFF_BIT = 0x08
>>>>>>> eebe85c01 (NOS-10269: report PSU input presence from PMBus STATUS_INPUT and use it in system-health (#10561))

class Psu(PddfPsu):
    """PDDF Platform-Specific PSU class"""

    def __init__(self, index, pddf_data=None, pddf_plugin_data=None):
        PddfPsu.__init__(self, index, pddf_data, pddf_plugin_data)

    def get_revision(self):
        return "N/A"

    def get_temperature(self):
        if not self.get_presence():
            return "N/A"
        return PddfPsu.get_temperature(self)
<<<<<<< HEAD
=======

    def get_input_status(self):
        """True if input power is present, False if STATUS_INPUT reports the unit off
        for insufficient input voltage (VIN_OFF), None if absent or unreadable."""
        try:
            status_input = self._pmbus_read_byte(PMBUS_STATUS_INPUT_CMD)
        except OSError as e:
            logger.log_warning(
                f"{self.name}: failed to read STATUS_INPUT: {e}",
                limit_key=f"{self.name}-status-input",
                max_log_count=1,
            )
            return None
        if status_input is None:
            return None
        return not status_input & PMBUS_STATUS_INPUT_VIN_OFF_BIT

    def _pmbus_read_byte(self, cmd: int) -> int | None:
        """Reads a PMBus byte register with PEC; None if the PSU is absent or has no PMBus device."""
        if not self.get_presence():
            return None
        loc = self._get_pmbus_i2c_loc()
        if loc is None:
            return None
        bus_no, addr = loc
        with SMBus(bus_no) as bus:
            bus.pec = 1
            # force=True bypasses the pmbus kernel driver's I2C_SLAVE claim.
            return bus.read_byte_data(addr, cmd, force=True)

    def _get_pmbus_i2c_loc(self) -> tuple[int, int] | None:
        for name in (f"PSU{self.psu_index}-PMBUS",
                     f"PSU{self.psu_index}-PMBUS1"):
            dev = self.pddf_obj.data.get(name)  # PDDF already knows bus, so we have to ask it
            if dev and 'i2c' in dev and 'topo_info' in dev['i2c']:
                topo = dev['i2c']['topo_info']
                return int(topo['parent_bus'], 0), int(topo['dev_addr'], 0)
        return None

    def get_blackbox_raw(self) -> bytes:
        """Reads the raw PSU blackbox payload via PMBus 0xDC; b'' if unavailable."""
        if not self.get_presence():
            return b""
        loc = self._get_pmbus_i2c_loc()
        if loc is None:
            return b""
        bus_no, addr = loc
        try:
            with SMBus(bus_no) as bus:
                bus.pec = 1
                w = i2c_msg.write(addr, [PMBUS_BLACKBOX_CMD])
                r = i2c_msg.read(addr, PMBUS_BLACKBOX_MAX_LEN)
                bus.i2c_rdwr(w, r)
                raw = list(r)  # type: ignore[reportArgumentType]
        except OSError as e:
            logger.log_warning(f"Error while trying to read {self.get_name()} blackbox: {e}")
            return b""
        length = raw[0]
        return bytes(raw[1 : 1 + length])

    def decode_blackbox_records(self, raw: bytes) -> list[BlackBoxRecordBase]:
        if len(raw) != PsuBlackBoxRecord.PAYLOAD_LENGTH:
            return []
        records = []
        for i in range(PsuBlackBoxRecord.RECORD_COUNT):
            off = PsuBlackBoxRecord.RECORDS_BASE + i * PsuBlackBoxRecord.RECORD_SIZE
            record = PsuBlackBoxRecord.from_bytes(
                raw[off : off + PsuBlackBoxRecord.RECORD_SIZE],
                f"{self.name}:{self.get_model()}",
            )
            if record.is_valid():
                records.append(record)
        return records

    def set_blackbox_unix_time(self, unix_ts=None) -> bool:
        def _u32_to_le_bytes(v):
            return [
                (v >> 0) & 0xFF,
                (v >> 8) & 0xFF,
                (v >> 16) & 0xFF,
                (v >> 24) & 0xFF,
            ]

        if not self.get_presence():
            return False
        loc = self._get_pmbus_i2c_loc()
        if loc is None:
            return False
        bus_no, addr = loc

        if unix_ts is None:
            unix_ts = int(time.time())

        # Have to do manually write for some reason compared to reads
        payload = [PMBUS_REAL_TIME_BLACKBOX_CMD, len(_u32_to_le_bytes(unix_ts))]
        payload += _u32_to_le_bytes(unix_ts)

        with SMBus(bus_no) as bus:
            bus.i2c_rdwr(i2c_msg.write(addr, payload))
        
        return True

    def rtc_sync(self) -> bool:
        # An empty slot has no RTC to sync, which is not a failure. Without this
        # the shared False return of set_blackbox_unix_time() (absent PSU vs. a
        # real write failure) makes rtc_sync log an ERR and exit non-zero on
        # every timer tick.
        if not self.get_presence():
            return True
        try:
            return self.set_blackbox_unix_time()
        except OSError as e:
            logger.log_warning(f"Failed to set {self.get_name()} blackbox time: {e}")
            return True

    def get_blackbox_config(self):
        """Reads MFR_BLACKBOX_CONFIG (0xDF). Bit 0 = blackbox enabled.

        Returns {"raw": int, "enabled": bool} on success, or an error string
        matching the convention of the other blackbox methods.
        """
        val = self._pmbus_read_byte(PMBUS_BLACKBOX_CONFIG_CMD)
        if val is None:
            return "N/A"
        return {
            "raw": val,
            "enabled": bool(val & PMBUS_BLACKBOX_CONFIG_ENABLE_BIT),
        }

    def clear_blackbox(self):
        if not self.get_presence():
            return "N/A"
        loc = self._get_pmbus_i2c_loc()
        if loc is None:
            return "N/A"
        bus_no, addr = loc

        with SMBus(bus_no) as bus:
            bus.pec = 1
            bus.write_byte(addr, PMBUS_CLEAR_BLACKBOX_CMD, force=True)

        return True
>>>>>>> eebe85c01 (NOS-10269: report PSU input presence from PMBus STATUS_INPUT and use it in system-health (#10561))
