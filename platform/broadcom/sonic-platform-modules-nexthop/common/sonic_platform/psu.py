#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

try:
    from sonic_platform_pddf_base.pddf_psu import PddfPsu
except ImportError as e:
    raise ImportError(str(e) + "- required module not found")


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
        if not self.get_presence():
            return "N/A"
        loc = self._get_pmbus_i2c_loc()
        if loc is None:
            return "N/A"
        bus_no, addr = loc

        with SMBus(bus_no) as bus:
            bus.pec = 1
            # force=True bypasses the pmbus kernel driver's I2C_SLAVE claim.
            val = bus.read_byte_data(addr, PMBUS_BLACKBOX_CONFIG_CMD, force=True)

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
>>>>>>> 9b8179c4a (NOS-19261: PMBus Write Error Shouldn't Fail Service (#11579))
