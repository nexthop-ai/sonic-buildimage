# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Platform-specific LED control functionality for SONiC

try:
    import re
<<<<<<< HEAD
    import sys
    import syslog
    import sonic_platform.platform
    from collections import defaultdict
    from portconfig import get_port_config
=======
    from collections import defaultdict

    import sonic_platform.platform
>>>>>>> 6d28c47fb (NOS-18542: [platform] Track runtime port config changes in port-ledd (#12670))
    from sonic_led.led_control_base import LedControlBase
    from sonic_py_common import logger
    from swsscommon.swsscommon import SonicV2Connector
except ImportError as e:
    raise ImportError(str(e) + " - required module not found")


LOG_ID = "nexthop-led-control"
sonic_logger = logger.Logger(LOG_ID)
sonic_logger.set_min_log_priority_info()

APP_PORT_PREFIX = "PORT_TABLE:"
STATE_XCVR_PREFIX = "TRANSCEIVER_INFO|"


def get_chassis():
    return sonic_platform.platform.Platform().get_chassis()


class LedControl(LedControlBase):
    """Platform specific LED control class"""

    def __init__(self):
        self.db = SonicV2Connector()
        self.db.connect(self.db.APPL_DB)
        self.db.connect(self.db.STATE_DB)

        self.logical_to_physical_map = {}
        self.physical_to_logical_map = defaultdict(list)

    def _add_port(self, port, attributes):
        """Map a logical port to its front-panel port; return the port number, or None if invalid."""
        index = attributes.get("index")
        if not index or not index.isdigit():
            sonic_logger.log_error(f"PORT_TABLE entry for {port} has no valid index: {index}")
            return None
        if not re.fullmatch(r"Ethernet\d+", port):
            sonic_logger.log_error(f"Interface name {port} is in an unexpected format")
            return None

        port_num = int(index)
        siblings = self.physical_to_logical_map[port_num]
        if self.logical_to_physical_map.get(port) != port_num or port not in siblings:
            self._remove_port(port)
            self.logical_to_physical_map[port] = port_num
            siblings.append(port)
            siblings.sort(key=lambda name: int(name.removeprefix("Ethernet")))
        return port_num

    def _remove_port(self, port):
        """Drop a logical port from its front-panel port's group; return the port number, or None if unknown."""
        port_num = self.logical_to_physical_map.get(port)
        if port_num is not None and port in self.physical_to_logical_map[port_num]:
            self.physical_to_logical_map[port_num].remove(port)
        return port_num

    def port_set(self, port, attributes):
        """
        Called when an APPL_DB PORT_TABLE entry is added or changed

<<<<<<< HEAD
        try:
            ports_dict, _, _ = get_port_config(hwsku=hwsku, platform=platform)
            if not ports_dict:
                sonic_logger.log_error(f"Could not get port config, exiting...")
                sys.exit(1)
=======
        :param port: A string, SONiC port name (e.g., "Ethernet0")
        :param attributes: A dict, the PORT_TABLE entry's fields
        """
        port_num = self._add_port(port, attributes)
        if port_num is not None:
            self._update_port_led(port_num)
>>>>>>> 6d28c47fb (NOS-18542: [platform] Track runtime port config changes in port-ledd (#12670))

    def port_del(self, port):
        """
        Called when an APPL_DB PORT_TABLE entry is deleted. The port keeps its
        front-panel mapping so its trailing STATE_DB deletes resolve.

<<<<<<< HEAD
                index = attributes.get("index")
                lanes = attributes.get("lanes")
                if not index or not lanes:
                    sonic_logger.log_error(f"get_port_config is missing attributes for {logical_name}")
                    continue

                index = int(index)
                num_lanes = len(lanes.split(','))

                match = re.match(r"Ethernet(\d+)", logical_name)
                if not match:
                    sonic_logger.log_error(f"Interface name {logical_name} is in an unexpected format")
                    continue

                start_index = int(match.group(1))
                logical_ports = [
                    f"Ethernet{i}"
                    for i in range(start_index, start_index + num_lanes)
                ]
                self.physical_to_logical_map[index].extend(logical_ports)

                for logical_port in logical_ports:
                    self.logical_to_physical_map[logical_port] = index

        except Exception as e:
            sonic_logger.log_error(f"Failed to initialize port mappings using get_port_config: {e}")
            sys.exit(1)
=======
        :param port: A string, SONiC port name (e.g., "Ethernet0")
        """
        port_num = self._remove_port(port)
        if port_num is not None:
            self._update_port_led(port_num)
>>>>>>> 6d28c47fb (NOS-18542: [platform] Track runtime port config changes in port-ledd (#12670))

    def _get_port_status(self, port):
        admin_status = self.db.get(
            self.db.APPL_DB, APP_PORT_PREFIX + port, "admin_status"
        )
        if admin_status is None:
            admin_status = "down"
        oper_status = self.db.get(
            self.db.APPL_DB, APP_PORT_PREFIX + port, "oper_status"
        )
        return admin_status, oper_status

    def _get_xcvr_info(self, port):
        return self.db.get_all(self.db.STATE_DB, STATE_XCVR_PREFIX + port)

    def _get_xcvr_presence(self, port_num):
        logical_ports = self._get_interfaces_for_port(port_num)
        if not logical_ports:
            sonic_logger.log_error(f"Could not find logical interfaces for Port{port_num}")
            return False
        # TRANSCEIVER_INFO is only set for the first interface in the breakout
        base_port = logical_ports[0]
        xcvr_info = self._get_xcvr_info(base_port)
        if xcvr_info:
            return True
        return False

    def _set_led_color(self, port, color):
        led_device_name = f"PORT_LED_{port}"
        if not get_chassis().set_system_led(led_device_name, color):
            sonic_logger.log_error(f"Error setting {led_device_name} to {color}")
        return

    def _get_port_num(self, interface):
        return self.logical_to_physical_map.get(interface)

    def _get_interfaces_for_port(self, port_num):
        return self.physical_to_logical_map.get(port_num, [])

    def port_link_state_change(self, port):
        """
        Called when a port's transceiver presence changes

        :param port: A string, SONiC port name (e.g., "Ethernet0")
        """
        port_num = self._get_port_num(port)
        if port_num is None:
            # Mapped by its PORT_TABLE entry, which sets the LED when it arrives
            sonic_logger.log_debug(f"No PORT_TABLE entry yet for {port}")
            return
        self._update_port_led(port_num)

    def _update_port_led(self, port_num):
        color = "green"
        all_oper_down = True
        all_admin_disabled = True
        logical_ports = self._get_interfaces_for_port(port_num)

        for logical_port in logical_ports:
            admin_status, oper_status = self._get_port_status(logical_port)

            if oper_status is None:
                continue

            if oper_status == "up":
                all_oper_down = False

            if admin_status == "up":
                all_admin_disabled = False

            if admin_status != oper_status:
                color = "yellow"

        if all_oper_down:
            if all_admin_disabled:
                color = "off"
            else:
                if not self._get_xcvr_presence(port_num):
                    color = "off"
        else:
            if not self._get_xcvr_presence(port_num):
                color = "yellow"

        self._set_led_color(port_num, color)
