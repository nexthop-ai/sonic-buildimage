#!/usr/bin/env python3

# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Instantiate the DDR5 SPD5118 DIMM temperature sensors on the CF2 SoC DesignWare I2C bus.

Without BIOS update, on CF2 the DDR5 SPD5118 hubs sit on a bus with Synopsys DesignWare adapter).
i2c_register_spd() in kernel auto-instantiates SPD devices on the FCH/PIIX4
not on this DesignWare adapter, so the spd5118 clients are never created and no DIMM
temperature is exposed. This oneshot creates them on the DesignWare bus.

It runs Before=pmon.service, so by the time pmon starts and its lm-sensors init
applies the platform sensors.conf, spd5118 is already bound and its
temp1_max/temp1_crit registers get programmed like any other chip.
"""

import glob
import sys

from sonic_py_common import syslogger

SYSLOG_IDENTIFIER = "spd5118_dimm_init"

SPD_CONTROLLER_HID = "AMDI0010"
SPD_ADDRESSES = ("0x50", "0x51")

logger = syslogger.SysLogger(SYSLOG_IDENTIFIER)


def _spd5118_bound():
    """True if any spd5118 hwmon temperature node is already bound (from any source,
    e.g. a BIOS that auto-instantiates the SPD hubs on the FCH SMBus)."""
    return bool(glob.glob("/sys/bus/i2c/drivers/spd5118/*/hwmon/hwmon*/temp1_input"))


def main():
    if _spd5118_bound():
        logger.log_info("spd5118 already bound; nothing to do")
        return 0

    adapters = glob.glob(f"/sys/devices/platform/{SPD_CONTROLLER_HID}:*/i2c-*")
    if not adapters:
        logger.log_error(f"no {SPD_CONTROLLER_HID} i2c adapter found; cannot instantiate spd5118")
        return 1

    # The SPD hubs live on exactly one of these SoC i2c buses; probe each. Per-bus
    # write failures are expected (address occupied by another device on a non-SPD
    # bus, etc.) and are not errors -- the final bound count is the real signal.
    for adapter in adapters:
        for addr in SPD_ADDRESSES:
            try:
                with open(f"{adapter}/new_device", "w") as node:
                    node.write(f"spd5118 {addr}\n")
            except OSError:
                pass

    # Remove clients that did not bind (wrong bus / absent DIMM / no hub answered).
    for adapter in adapters:
        for addr in SPD_ADDRESSES:
            if glob.glob(f"{adapter}/*-00{addr[2:]}") and not glob.glob(f"{adapter}/*-00{addr[2:]}/driver"):
                try:
                    with open(f"{adapter}/delete_device", "w") as node:
                        node.write(f"{addr}\n")
                except OSError:
                    pass

    bound = glob.glob("/sys/bus/i2c/drivers/spd5118/*/hwmon/hwmon*/temp1_input")
    if bound:
        logger.log_info(f"instantiated {len(bound)} spd5118 DIMM sensor(s)")
    else:
        logger.log_warning(f"no spd5118 DIMM hub found on any {SPD_CONTROLLER_HID} i2c bus")
    return 0


if __name__ == "__main__":
    sys.exit(main())
