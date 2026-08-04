import re

from natsort import natsorted
from swsscommon import swsscommon
from swsscommon.swsscommon import SonicV2Connector

from .health_checker import HealthChecker

EVENTS_PUBLISHER_SOURCE = "sonic-events-host"
EVENTS_PUBLISHER_TAG = "liquid-cooling-leak"

# Output voltage (volts) at or below this is treated as "no good output". Well below
# any valid rail minimum (rails are ~12V).
PSU_OUTPUT_DEAD_VOLTAGE = 1.0
# Input voltage (volts) at or below this is treated as "no input present" (e.g. AC
# cord unplugged). Only used as POSITIVE evidence to classify a dead PSU as un-powered
# rather than faulted; if input_voltage is missing we do NOT assume it is un-powered.
PSU_NO_INPUT_VOLTAGE = 10.0

class HardwareChecker(HealthChecker):
    """
    Check system hardware status. For now, it checks ASIC, PSU, PDB and fan status.
    """

    ASIC_TEMPERATURE_KEY = 'TEMPERATURE_INFO|ASIC'
    FAN_TABLE_NAME = 'FAN_INFO'
    PSU_TABLE_NAME = 'PSU_INFO'
    LIQUID_COOLING_TABLE_NAME = 'LIQUID_COOLING_INFO'

    def __init__(self):
        HealthChecker.__init__(self)
        self._db = SonicV2Connector(use_unix_socket_path=True)
        self._db.connect(self._db.STATE_DB)

        self.leaking_sensors = []

    def get_category(self):
        return 'Hardware'

    def check(self, config):
        self.reset()
        self._check_asic_status(config)
        self._check_fan_status(config)
        self._check_psu_status(config)
        self._check_liquid_cooling_status(config)

    def _check_asic_status(self, config):
        """
        Check if ASIC temperature is in valid range.
        :param config: Health checker configuration
        :return:
        """
        if config.ignore_devices and 'asic' in config.ignore_devices:
            return

        ASIC_TEMPERATURE_KEY_LIST = self._db.keys(self._db.STATE_DB,
                                                  HardwareChecker.ASIC_TEMPERATURE_KEY + '*')
        for asic_key in ASIC_TEMPERATURE_KEY_LIST:
            temperature = self._db.get(self._db.STATE_DB, asic_key,
                                                          'temperature')
            temperature_threshold = self._db.get(self._db.STATE_DB, asic_key,
                                                          'high_threshold')
            asic_name = asic_key.split('|')[1]
            if not temperature:
                self.set_object_not_ok('ASIC', asic_name,
                        'Failed to get {} temperature'.format(asic_name))
            elif not temperature_threshold:
                self.set_object_not_ok('ASIC', asic_name,
                        'Failed to get {} temperature threshold'.format(asic_name))
            else:
                try:
                    temperature = float(temperature)
                    temperature_threshold = float(temperature_threshold)
                    if temperature > temperature_threshold:
                        self.set_object_not_ok('ASIC', asic_name,
                                               '{} temperature is too hot, temperature={}, threshold={}'.format(
                                                asic_name, temperature, temperature_threshold))
                    else:
                        self.set_object_ok('ASIC', asic_name)
                except ValueError as e:
                    self.set_object_not_ok('ASIC', asic_name,
                                           'Invalid {} temperature data, temperature={}, threshold={}'.format(
                                            asic_name, temperature, temperature_threshold))

    def _check_fan_status(self, config):
        """
        Check fan status including:
            1. Check all fans are present
            2. Check all fans are in good state
            3. Check fan speed is in valid range
            4. Check all fans direction are the same
        :param config: Health checker configuration
        :return:
        """
        if config.ignore_devices and 'fan' in config.ignore_devices:
            return

        keys = self._db.keys(self._db.STATE_DB, HardwareChecker.FAN_TABLE_NAME + '*')
        if not keys:
            self.set_object_not_ok('Fan', 'Fan', 'Failed to get fan information')
            return

        psu_power_states = self._get_psu_power_states()

        expect_fan_direction = None
        for key in natsorted(keys):
            key_list = key.split('|')
            if len(key_list) != 2:  # error data in DB, log it and ignore
                self.set_object_not_ok('Fan', key, 'Invalid key for FAN_INFO: {}'.format(key))
                continue

            name = key_list[1]
            if config.ignore_devices and name in config.ignore_devices:
                continue
            data_dict = self._db.get_all(self._db.STATE_DB, key)
            presence = data_dict.get('presence', 'false')
            if presence.lower() != 'true':
                # A PSU fan goes missing when its PSU is removed; the PSU's own
                # "is not present" line already conveys this, so don't add a duplicate
                # fan reason.
                if self._psu_fan_parent_powerless(name, psu_power_states):
                    self.set_object_ok('Fan', name)
                    continue
                self.set_object_not_ok('Fan', name, '{} is missing'.format(name))
                continue

            if not self._ignore_check(config.ignore_devices, 'fan', name, 'speed'):
                speed = data_dict.get('speed', None)
                speed_target = data_dict.get('speed_target', None)
                is_under_speed = data_dict.get('is_under_speed', None)
                is_over_speed = data_dict.get('is_over_speed', None)
                if not speed:
                    self.set_object_not_ok('Fan', name, 'Failed to get actual speed data for {}'.format(name))
                    continue
                elif not speed_target:
                    self.set_object_not_ok('Fan', name, 'Failed to get target speed date for {}'.format(name))
                    continue
                elif is_under_speed is None:
                    self.set_object_not_ok('Fan', name, 'Failed to get under speed threshold check for {}'.format(name))
                    continue
                elif is_over_speed is None:
                    self.set_object_not_ok('Fan', name, 'Failed to get over speed threshold check for {}'.format(name))
                    continue
                else:
                    try:
                        speed = float(speed)
                        speed_target = float(speed_target)
                        if 'true' in (is_under_speed.lower(), is_over_speed.lower()):
                            self.set_object_not_ok('Fan', name,
                                                   '{} speed is out of range, speed={}, target={}'.format(
                                                       name,
                                                       speed,
                                                       speed_target))
                            continue
                    except ValueError:
                        self.set_object_not_ok('Fan', name,
                                               'Invalid fan speed data for {}, speed={}, target={}, is_under_speed={}, is_over_speed={}'.format(
                                                   name,
                                                   speed,
                                                   speed_target,
                                                   is_under_speed,
                                                   is_over_speed))
                        continue

            if not self._ignore_check(config.ignore_devices, 'fan', name, 'direction'):
                direction = data_dict.get('direction', 'N/A')
                # ignore fan whose direction is not available to avoid too many false alarms
                if direction != 'N/A':
                    if not expect_fan_direction:
                        # initialize the expect fan direction
                        expect_fan_direction = (name, direction)
                    elif direction != expect_fan_direction[1]:
                        self.set_object_not_ok('Fan', name,
                                               f'{name} direction {direction} is not aligned with {expect_fan_direction[0]} direction {expect_fan_direction[1]}')
                        continue

            status = data_dict.get('status', 'false')
            if status.lower() != 'true':
                # A stopped PSU fan is expected when its PSU has no power, so don't raise
                # a misleading "is broken" alarm: the PSU's own health entry (e.g. "is
                # present but not powered" / "is not present") already conveys the cause.
                if self._psu_fan_parent_powerless(name, psu_power_states):
                    self.set_object_ok('Fan', name)
                    continue
                self.set_object_not_ok('Fan', name, '{} is broken'.format(name))
                continue

            self.set_object_ok('Fan', name)

    def _check_psu_status(self, config):
        """
        Check PSU and PDB status from STATE_DB PSU_INFO (PDB keys look like PDB 1, PDB 2).
        PSUs: presence, status, optional temperature/voltage/power_threshold checks.
        PDBs: presence and status only (for system-health Type column).
        :param config: Health checker configuration
        :return:
        """
        ignore_psu = bool(config.ignore_devices) and 'psu' in config.ignore_devices
        ignore_pdb = bool(config.ignore_devices) and 'pdb' in config.ignore_devices
        if ignore_psu and ignore_pdb:
            return

        keys = self._db.keys(self._db.STATE_DB, HardwareChecker.PSU_TABLE_NAME + '*')
        if not keys:
            # An empty PSU_INFO table is only a failure when PSU monitoring is expected.
            # Platforms without PSUs (e.g. DPUs) ignore 'psu' to suppress this alarm.
            if not ignore_psu:
                self.set_object_not_ok('PSU', 'PSU', 'Failed to get PSU information')
            return

        for key in natsorted(keys):
            key_list = key.split('|')
            if len(key_list) != 2:  # error data in DB, log it and ignore
                self.set_object_not_ok('PSU', key, 'Invalid key for PSU_INFO: {}'.format(key))
                continue

            name = key_list[1]
            if config.ignore_devices and name in config.ignore_devices:
                continue

            # PSU and PDB rows share PSU_INFO (PDB keys look like "PDB 1"); honor each
            # category-level ignore independently so ignoring one does not check the other.
            is_pdb = name.upper().startswith('PDB')
            if (is_pdb and ignore_pdb) or (not is_pdb and ignore_psu):
                continue

            data_dict = self._db.get_all(self._db.STATE_DB, key)

            # Classify power state up front so an un-powered PSU (no input) is not
            # mis-reported as a voltage fault, while a PSU that has lost power-good
            # WITH input present is flagged as faulted rather than silently excused.
            power_state = self._classify_psu_power(data_dict)
            if power_state == 'absent':
                self.set_object_not_ok('PSU', name, '{} is not present'.format(name))
                continue
            if power_state == 'unpowered':
                self.set_object_not_ok('PSU', name, '{} is present but not powered'.format(name))
                continue
            if power_state == 'faulted':
                self.set_object_not_ok('PSU', name, '{} is faulted'.format(name))
                continue

            if not self._ignore_check(config.ignore_devices, 'psu', name, 'temperature'):
                temperature = data_dict.get('temp', None)
                temperature_threshold = data_dict.get('temp_threshold', None)
                if temperature is None:
                    self.set_object_not_ok('PSU', name, 'Failed to get temperature data for {}'.format(name))
                    continue
                elif temperature_threshold is None:
                    self.set_object_not_ok('PSU', name, 'Failed to get temperature threshold data for {}'.format(name))
                    continue
                elif temperature_threshold != 'N/A':
                    try:
                        temperature = float(temperature)
                        temperature_threshold = float(temperature_threshold)
                        if temperature > temperature_threshold:
                            self.set_object_not_ok('PSU', name,
                                                   '{} temperature is too hot, temperature={}, threshold={}'.format(
                                                       name, temperature,
                                                       temperature_threshold))
                            continue
                    except ValueError:
                        self.set_object_not_ok('PSU', name,
                                               'Invalid temperature data for {}, temperature={}, threshold={}'.format(
                                                   name, temperature,
                                                   temperature_threshold))
                        continue

            if not self._ignore_check(config.ignore_devices, 'psu', name, 'voltage'):
                voltage = data_dict.get('voltage', None)
                voltage_min_th = data_dict.get('voltage_min_threshold', None)
                voltage_max_th = data_dict.get('voltage_max_threshold', None)
                if voltage is None:
                    self.set_object_not_ok('PSU', name, 'Failed to get voltage data for {}'.format(name))
                    continue
                elif voltage_min_th is None:
                    self.set_object_not_ok('PSU', name,
                                           'Failed to get voltage minimum threshold data for {}'.format(name))
                    continue
                elif voltage_max_th is None:
                    self.set_object_not_ok('PSU', name,
                                           'Failed to get voltage maximum threshold data for {}'.format(name))
                    continue
                elif voltage_min_th != 'N/A' and voltage_max_th != 'N/A':
                    try:
                        voltage = float(voltage)
                        voltage_min_th = float(voltage_min_th)
                        voltage_max_th = float(voltage_max_th)
                        if voltage < voltage_min_th or voltage > voltage_max_th:
                            self.set_object_not_ok('PSU', name,
                                                   '{} voltage is out of range, voltage={}, range=[{},{}]'.format(name,
                                                                                                                  voltage,
                                                                                                                  voltage_min_th,
                                                                                                                  voltage_max_th))
                            continue
                    except ValueError:
                        self.set_object_not_ok('PSU', name,
                                               'Invalid voltage data for {}, voltage={}, range=[{},{}]'.format(name,
                                                                                                               voltage,
                                                                                                               voltage_min_th,
                                                                                                               voltage_max_th))
                        continue

            if not self._ignore_check(config.ignore_devices, 'psu', name, 'power_threshold'):
                power_overload = data_dict.get('power_overload', None)
                if power_overload == 'True':

                    try:
                        power = data_dict['power']
                        power_critical_threshold = data_dict['power_critical_threshold']
                        self.set_object_not_ok('PSU', name, 'System power exceeds threshold ({}w)'.format(power_critical_threshold))
                    except KeyError:
                        self.set_object_not_ok('PSU', name, 'System power exceeds threshold but power_critical_threshold is invalid')
                    continue

            self.set_object_ok('PSU', name)

    def reset(self):
        self._info = {}

    def _get_psu_power_states(self):
        """
        Read PSU_INFO once and classify each PSU's power state so the fan checker
        can tell whether a stopped PSU fan is expected (its PSU has no power).
        :return: dict mapping PSU index (int) -> 'absent' | 'unpowered' | 'faulted' | 'ok'.
                 Non-PSU rows (e.g. PDB) are skipped.
        """
        states = {}
        keys = self._db.keys(self._db.STATE_DB, HardwareChecker.PSU_TABLE_NAME + '*')
        if not keys:
            return states
        for key in keys:
            key_list = key.split('|')
            if len(key_list) != 2:
                continue
            index = self._psu_index_from_name(key_list[1])
            if index is None:
                continue
            states[index] = self._classify_psu_power(self._db.get_all(self._db.STATE_DB, key))
        return states

    @staticmethod
    def _classify_psu_power(data_dict):
        """Classify a PSU_INFO row from the evidence present in STATE_DB:
            'absent'    - not present (presence false)
            'ok'        - present and delivering good output (power-good and output voltage)
            'unpowered' - present, no good output, AND positive evidence of no input
                          (input_voltage at/below PSU_NO_INPUT_VOLTAGE)
            'faulted'   - present, no good output, but input is present OR input is
                          unknown. We never infer "unpowered" from a deasserted
                          power-good alone, so a real fault is not masked.
        """
        if data_dict.get('presence', 'false').lower() != 'true':
            return 'absent'

        output_bad = data_dict.get('status', 'false').lower() != 'true'
        if not output_bad:
            voltage = data_dict.get('voltage', None)
            if voltage is not None:
                try:
                    output_bad = float(voltage) <= PSU_OUTPUT_DEAD_VOLTAGE
                except ValueError:
                    pass
        if not output_bad:
            return 'ok'

        # No good output: distinguish "no input" from "faulted" using positive
        # input-side evidence only. Missing/unparseable input_voltage -> faulted.
        input_voltage = data_dict.get('input_voltage', None)
        if input_voltage is not None:
            try:
                if float(input_voltage) <= PSU_NO_INPUT_VOLTAGE:
                    return 'unpowered'
            except ValueError:
                pass
        return 'faulted'

    @staticmethod
    def _psu_index_from_name(name):
        """'PSU 4' / 'PSU4' -> 4. Returns None for non-PSU names (e.g. 'PDB 1')."""
        match = re.match(r'^PSU\s*(\d+)$', name)
        return int(match.group(1)) if match else None

    @staticmethod
    def _psu_fan_parent_index(fan_name):
        """'PSU4_FAN1' / 'PSU 4_FAN1' -> 4. Returns None for non-PSU fans."""
        match = re.match(r'^PSU\s*(\d+)_FAN', fan_name)
        return int(match.group(1)) if match else None

    @classmethod
    def _psu_fan_parent_powerless(cls, fan_name, psu_power_states):
        """True if fan_name is a PSU fan whose parent PSU is absent or unpowered, so a
        missing/stopped fan is expected and its alarm should be suppressed (the PSU's
        own reason line conveys the cause). A faulted/healthy parent is not suppressed."""
        psu_index = cls._psu_fan_parent_index(fan_name)
        return psu_index is not None and psu_power_states.get(psu_index) in ('absent', 'unpowered')

    @classmethod
    def _ignore_check(cls, ignore_set, category, object_name, check_point):
        if not ignore_set:
            return False

        if '{}.{}'.format(category, check_point) in ignore_set:
            return True
        elif '{}.{}'.format(object_name, check_point) in ignore_set:
            return True
        return False

    def publish_events(self, sensors, event_name):
        if not sensors:
            return
        params = swsscommon.FieldValueMap()
        events_handle = swsscommon.events_init_publisher(EVENTS_PUBLISHER_SOURCE)
        for sensor in sensors:
            params[event_name] = sensor
            swsscommon.event_publish(events_handle, EVENTS_PUBLISHER_TAG, params)
        swsscommon.events_deinit_publisher(events_handle)


    def _check_liquid_cooling_status(self, config):
        """
        Check liquid cooling status including:
            1. Check all leakage sensors are in good state
        :param config: Health checker configuration
        :return:
        """
        if not config.include_devices or 'liquid_cooling' not in config.include_devices:
            return

        keys = self._db.keys(self._db.STATE_DB, HardwareChecker.LIQUID_COOLING_TABLE_NAME + '|*')
        if not keys:
            self.set_object_not_ok('Liquid Cooling', 'Liquid Cooling', 'Failed to get liquid cooling information')
            return

        new_leaking_sensors = []
        for key in natsorted(keys):
            key_list = key.split('|')
            if len(key_list) != 2:  # error data in DB, log it and ignore
                self.set_object_not_ok('Liquid Cooling', key, 'Invalid key for LIQUID_COOLING_INFO: {}'.format(key))
                continue

            name = key_list[1]
            if config.ignore_devices and name in config.ignore_devices:
                continue

            data_dict = self._db.get_all(self._db.STATE_DB, key)
            leak_status = data_dict.get('leak_status', None)
            if leak_status is None or leak_status == 'N/A':
                self.set_object_not_ok('Liquid Cooling', name, 'Failed to get leakage sensor status for {}'.format(name))
                continue

            if leak_status.lower() == 'yes' and name not in self.leaking_sensors:
                self.leaking_sensors.append(name)
                new_leaking_sensors.append(name)
                self.set_object_not_ok('Liquid Cooling', name, 'Leakage sensor {} is leaking'.format(name))
                continue

            if leak_status.lower() == 'no':
                self.set_object_ok('Liquid Cooling', name)
                if name in self.leaking_sensors:
                    self.leaking_sensors.remove(name)
                    self.publish_events([name], "leaking sensor report recovered")

        self.publish_events(new_leaking_sensors, "sensor report leaking event")
