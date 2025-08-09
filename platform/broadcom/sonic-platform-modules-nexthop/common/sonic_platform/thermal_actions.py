#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import csv
import logging
import os
import re
import traceback
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from sonic_platform_base.sonic_thermal_control.thermal_action_base import ThermalPolicyActionBase
from sonic_platform_base.sonic_thermal_control.thermal_json_object import thermal_json_object

if TYPE_CHECKING:
    from sonic_platform_base.fan_base import Fan

from sonic_platform.syslog import SYSLOG_IDENTIFIER_THERMAL, SYSLOG_IDENTIFIER_THERMAL_CSV, NhLoggerMixin
from sonic_platform.thermal_infos import FanInfo, ThermalInfo

# Fan speed constants (percentage)
FAN_MIN_SPEED: float = 30.0
FAN_MAX_SPEED: float = 100.0

# CSV logging global controls
CSV_LOG_DIR: str = "/var/log/thermal_control"
CSV_MAX_FILE_SIZE_MB: int = 50  # Max size in MB before trimming
CSV_TRIM_RATIO: float = 0.8  # Keep 80% of the newest entries when trimming


def _natural_sort_key(text: str) -> List[Union[int, str]]:
    """
    Generate a key for natural sorting that handles numbers within strings.

    Args:
        text: String to generate sort key for

    Returns:
        List of integers and strings for natural sorting
    """

    def convert(part):
        return int(part) if part.isdigit() else part.lower()

    return [convert(c) for c in re.split(r"(\d+)", text)]


class CsvLogger(NhLoggerMixin):
    """
    CSV logger with automatic file management and debug-level control.

    Inherits from NhLoggerMixin to provide syslog integration and debug-level checking.
    Only writes CSV data when the nh_thermal_csv logger is set to DEBUG level.
    Automatically creates directories, headers, and trims large files.

    Args:
        filename: Name of the CSV file to create in CSV_LOG_DIR
        headers: List of column headers for the CSV file
    """

    def __init__(self, filename: str, headers: List[str]) -> None:
        """
        Initialize CSV logger with file management capabilities.

        Args:
            filename: Name of the CSV file (e.g., "thermal_data.csv")
            headers: List of column headers for the CSV file
        """
        super().__init__(SYSLOG_IDENTIFIER_THERMAL_CSV)
        self.filename = filename
        self.headers = headers
        self.filepath = os.path.join(CSV_LOG_DIR, filename)
        self._file_initialized = False

    def _ensure_directory_exists(self) -> None:
        """
        Ensure the CSV log directory exists.

        Creates the CSV_LOG_DIR directory if it doesn't exist.
        Logs any exceptions to syslog.
        """
        try:
            os.makedirs(CSV_LOG_DIR, exist_ok=True)
        except Exception as e:
            self.log_error(f"Failed to create CSV log directory {CSV_LOG_DIR}: {e}")
            self.log_error(f"Traceback: {traceback.format_exc()}")

    def _ensure_file_initialized(self) -> None:
        """
        Ensure CSV file exists with proper headers.

        Creates the CSV file with headers if it doesn't exist or is empty.
        Sets the _file_initialized flag to avoid repeated initialization.
        Logs any exceptions to syslog.
        """
        self._ensure_directory_exists()
        try:
            file_exists = os.path.exists(self.filepath)
            file_has_content = file_exists and os.path.getsize(self.filepath) > 0
            if not file_has_content:
                with open(self.filepath, "w", newline="") as csvfile:
                    writer = csv.writer(csvfile)
                    writer.writerow(self.headers)
                self._file_initialized = True
        except Exception as e:
            self.log_error(f"Failed to initialize CSV file {self.filename}: {e}")
            self.log_error(f"Traceback: {traceback.format_exc()}")

    def _check_and_trim_file(self) -> None:
        """
        Check file size and trim if it exceeds the maximum size.

        Checks if the CSV file size exceeds CSV_MAX_FILE_SIZE_MB and calls
        _trim_file() to reduce the file size if needed.
        Logs any exceptions to syslog.
        """
        try:
            if not os.path.exists(self.filepath):
                return
            max_size_bytes = CSV_MAX_FILE_SIZE_MB * 1024 * 1024
            if os.path.getsize(self.filepath) < max_size_bytes:
                return
            self._trim_file()
        except Exception as e:
            self.log_error(f"Failed to check/trim CSV file {self.filename}: {e}")
            self.log_error(f"Traceback: {traceback.format_exc()}")

    def _trim_file(self) -> None:
        """
        Trim CSV file to keep only the newest entries.

        Keeps the header and the newest CSV_TRIM_RATIO percentage of data lines
        to prevent the file from growing too large. For example, with CSV_TRIM_RATIO
        of 0.8, it keeps 80% of the newest entries.
        Logs any exceptions to syslog.
        """
        try:
            with open(self.filepath, "r", newline="") as csvfile:
                lines = csvfile.readlines()
            if len(lines) <= 1:
                return
            total_lines = len(lines)
            lines_to_keep = max(2, int(total_lines * CSV_TRIM_RATIO))
            header = lines[0]
            data_lines_to_keep = lines_to_keep - 1
            newer_data_lines = lines[-data_lines_to_keep:] if data_lines_to_keep > 0 else []
            with open(self.filepath, "w", newline="") as csvfile:
                csvfile.write(header)
                csvfile.writelines(newer_data_lines)
        except Exception as e:
            self.log_error(f"Failed to trim CSV file {self.filename}: {e}")
            self.log_error(f"Traceback: {traceback.format_exc()}")

    def log_row(self, data: List[Any]) -> None:
        """
        Log a data row to the CSV file.

        Only writes data if the nh_thermal_csv logger is set to DEBUG level.
        Automatically handles file initialization, directory creation, and file trimming.
        Logs any exceptions to syslog.

        Args:
            data: List of values to write as a CSV row
        """
        # Check if CSV logging is enabled based on this logger's debug level
        if not (hasattr(self, "_min_log_level") and getattr(self, "_min_log_level") <= logging.DEBUG):
            return
        self._ensure_file_initialized()
        self._check_and_trim_file()
        try:
            with open(self.filepath, "a", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(data)
        except Exception as e:
            # Log exception to syslog instead of CSV
            self.log_error(f"Exception writing CSV data to {self.filename}: {e}")
            self.log_error(f"Traceback: {traceback.format_exc()}")


class FanException(Exception):
    """Base exception class for fan-related errors."""

    pass


def set_all_fan_speeds(logger: NhLoggerMixin, fans: List["Fan"], speed: float) -> None:
    """
    Set speed for all fans.

    Args:
        logger: Logger instance for logging messages
        fans: List of Fan objects to set speed for
        speed: Target fan speed percentage (0-100)
    """
    if not fans:
        logger.log_error("No fans available to set speed")
        raise FanException("No fans available to set speed")
    success_count = 0
    for i, fan in enumerate(fans):
        try:
            result = fan.set_speed(speed)
            if result:
                success_count += 1
            else:
                logger.log_warning(f"Failed to set speed {speed:.1f}% for fan {i} (fan may not be present)")
        except Exception as e:
            logger.log_error(f"Exception setting speed {speed:.1f}% for fan {i}: {e}")
            logger.log_error(f"Traceback:\n{traceback.format_exc()}")

            raise

    logger.log_info(f"Applied speed {speed:.1f}% to {success_count}/{len(fans)} fans")


@thermal_json_object("fan.set_speed")
class FanSetSpeedAction(ThermalPolicyActionBase, NhLoggerMixin):
    """Thermal action to set fan speed to a specific percentage."""

    JSON_FIELD_SPEED: str = "speed"

    def __init__(self) -> None:
        """Initialize FanSetSpeedAction."""
        ThermalPolicyActionBase.__init__(self)
        NhLoggerMixin.__init__(self, SYSLOG_IDENTIFIER_THERMAL)
        self._speed: Optional[int] = None
        self.log_debug("Initialized")

    def load_from_json(self, set_speed_json: Dict[str, Any]) -> None:
        """
        Load configuration from JSON.

        Args:
            set_speed_json: JSON object with 'speed' field (0-100)

        Raises:
            KeyError: If 'speed' field is missing
            ValueError: If speed value is invalid
        """
        try:
            self._speed = int(set_speed_json[self.JSON_FIELD_SPEED])
            self.log_info(f"Loaded with speed: {self._speed}%")
        except (KeyError, ValueError, TypeError) as e:
            self.log_error(f"Failed to load from JSON: {e}")
            raise

    def execute(self, thermal_info_dict: Dict[str, Any]) -> None:
        """
        Set speed for all present fans.

        Args:
            thermal_info_dict: Dictionary containing thermal information
        """
        fan_info = thermal_info_dict.get(FanInfo.INFO_TYPE)
        set_all_fan_speeds(self, fan_info.get_fans(), self._speed)

@thermal_json_object('thermal.control_algo')
class ThermalControlAlgorithmAction(ThermalPolicyActionBase, NhLoggerMixin):
    """PID-based thermal control algorithm using multiple thermal domains."""

    def __init__(self) -> None:
        """Initialize thermal control algorithm action."""
        ThermalPolicyActionBase.__init__(self)
        NhLoggerMixin.__init__(self, SYSLOG_IDENTIFIER_THERMAL)

        self._pidDomains: Optional[Dict[str, Dict[str, float]]] = None
        self._constants: Optional[Dict[str, Any]] = None
        self._fan_limits: Optional[Dict[str, Union[int, float]]] = None
        self._pidControllers: Dict[str, "PIDController"] = {}
        # CSV logging for thermal control algorithm (will be initialized after domains are loaded)
        self._csv_logger_control: Optional[CsvLogger] = None

        # CSV logging for temperature sensors (will be initialized after domains are loaded)
        self._csv_logger_temperature: Optional[CsvLogger] = None
        self._csv_loggers_input_error: Dict[str, CsvLogger] = {}

        self._extra_setpoint_margin: Dict[str, float] = {}

        self.log_debug("Initialized")

    def load_from_json(self, algo_json: Dict[str, Any]) -> None:
        """
        Load PID configuration from JSON.

        Args:
            algo_json: JSON object with pid_domains, constants, and fan_limits

        Raises:
            KeyError: If required JSON fields are missing
            ValueError: If JSON validation fails
        """
        try:
            self._pidDomains = algo_json["pid_domains"]
            self._constants = algo_json["constants"]
            self._fan_limits = algo_json["fan_limits"]
        except KeyError as e:
            self.log_error(f"Missing required fields in JSON: {e}")
            raise
        except Exception as e:
            self.log_error(f"Failed to load from JSON: {e}")
            raise

        self.log_info(f"Initialized with {len(self._pidDomains)} PID domains")
        self.log_debug(f"PID domains: {list(self._pidDomains.keys())}")
        self.log_debug(f"Constants: {self._constants}")
        self.log_debug(f"Fan limits: {self._fan_limits}")
        try:
            self.validate_json()
        except ValueError as e:
            self.log_error(f"Invalid thermal control algorithm JSON: {e}")
            raise

        # Initialize CSV loggers for thermal control algorithm and temperature sensors
        self._initialize_control_csv_logger()
        self._initialize_temperature_csv_loggers()

    def _initialize_control_csv_logger(self) -> None:
        """Initialize the control CSV logger with domain-specific columns."""
        if not self._pidDomains:
            return

        # Create headers: timestamp, {domain}_sensor, {domain}_P, {domain}_I, {domain}_D,
        # {domain}_raw_output, {domain}_saturated_output, {domain}_frozen_integral for each domain,
        # selected_domain, configured_fan_speed
        headers = ["timestamp"]
        for domain in sorted(self._pidDomains.keys(), key=_natural_sort_key):
            headers.extend(
                [
                    f"{domain}_sensor",
                    f"{domain}_P",
                    f"{domain}_I",
                    f"{domain}_D",
                    f"{domain}_raw_output",
                    f"{domain}_saturated_output",
                    f"{domain}_frozen_integral",
                ]
            )
        headers.extend(["selected_domain", "configured_fan_speed"])

        self._csv_logger_control = CsvLogger("thermal_control_algorithm.csv", headers)

    def _initialize_temperature_csv_loggers(self) -> None:
        """Initialize CSV loggers for temperature sensors and per-domain input errors."""
        if not self._pidDomains:
            return

        # We need to collect all thermal sensors to create column headers
        # This will be done dynamically during the first logging call
        # For now, just initialize the per-domain input error loggers
        for domain in self._pidDomains.keys():
            # Per-domain input error CSV will have columns for all sensors in that domain
            # Headers will be created dynamically on first use
            self._csv_loggers_input_error[domain] = None

        # Temperature CSV will have columns for all sensors
        # Headers will be created dynamically on first use
        self._csv_logger_temperature = None

    def _process_sensor_name(self, sensor_name: str) -> Optional[str]:
        """
        Process sensor name: filter out unwanted sensors and rename others.

        Args:
            sensor_name: Original sensor name

        Returns:
            Processed sensor name, or None if sensor should be filtered out
        """
        # Filter out sensors matching "ASIC [pt]" pattern
        if re.match(r"ASIC [pt]", sensor_name):
            return None

        # Rename "Transceiver PortX" to "PortX"
        transceiver_match = re.match(r"Transceiver (Port\d+)", sensor_name)
        if transceiver_match:
            return transceiver_match.group(1)

        # Return original name for all other sensors
        return sensor_name

    def _log_temperature_sensors(self, thermals: List[Any], timestamp: str) -> None:
        """Log temperature sensor data to per-domain input error CSVs and temperature CSV."""
        # Collect all sensor data for temperature CSV (all sensors)
        all_sensor_temps = {}
        # Collect PID sensor data for input error CSVs (only PID-controlled sensors)
        domain_sensors = {}

        for thermal in thermals:
            current_temp = thermal.get_temperature()
            if current_temp is not None:
                original_sensor_name = thermal.get_name()
                processed_sensor_name = self._process_sensor_name(original_sensor_name)

                # Skip sensors that should be filtered out
                if processed_sensor_name is None:
                    continue

                # Add to temperature data (all sensors)
                all_sensor_temps[processed_sensor_name] = round(current_temp, 3)

                # Add to domain sensors only if PID-controlled
                if hasattr(thermal, "is_controlled_by_pid") and thermal.is_controlled_by_pid():
                    setpoint = thermal.get_pid_setpoint()
                    if setpoint is not None:
                        domain = thermal.get_pid_domain()
                        error = current_temp - setpoint

                        if domain not in domain_sensors:
                            domain_sensors[domain] = {}
                        domain_sensors[domain][processed_sensor_name] = round(error, 3)

        # Initialize CSV loggers if needed and log data
        self._ensure_temperature_csv_loggers_initialized(all_sensor_temps.keys(), domain_sensors)

        # Log to temperature CSV (all sensors with their absolute temperatures)
        if self._csv_logger_temperature and all_sensor_temps:
            temp_row = [timestamp]
            for sensor_name in sorted(all_sensor_temps.keys(), key=_natural_sort_key):
                temp_row.append(all_sensor_temps[sensor_name])
            self._csv_logger_temperature.log_row(temp_row)

        # Log to per-domain input error CSVs
        for domain, domain_sensor_errors in domain_sensors.items():
            if domain in self._csv_loggers_input_error and self._csv_loggers_input_error[domain]:
                error_row = [timestamp]
                # Get all sensors for this domain in sorted order
                domain_sensor_names = sorted(domain_sensor_errors.keys(), key=_natural_sort_key)
                for sensor_name in domain_sensor_names:
                    error_row.append(domain_sensor_errors.get(sensor_name, 0))
                self._csv_loggers_input_error[domain].log_row(error_row)

    def _ensure_temperature_csv_loggers_initialized(
        self, all_sensor_names: List[str], domain_sensors: Dict[str, Dict[str, float]]
    ) -> None:
        """Initialize temperature CSV loggers with proper headers based on discovered sensors."""
        all_sensor_names_sorted = sorted(all_sensor_names, key=_natural_sort_key)

        # Initialize temperature CSV logger if needed
        if self._csv_logger_temperature is None and all_sensor_names_sorted:
            temp_headers = ["timestamp"] + all_sensor_names_sorted
            self._csv_logger_temperature = CsvLogger("temperature.csv", temp_headers)

        # Initialize per-domain input error CSV loggers if needed
        for domain, sensor_errors in domain_sensors.items():
            if domain in self._csv_loggers_input_error and self._csv_loggers_input_error[domain] is None:
                domain_sensor_names = sorted(sensor_errors.keys(), key=_natural_sort_key)
                if domain_sensor_names:
                    error_headers = ["timestamp"] + domain_sensor_names
                    self._csv_loggers_input_error[domain] = CsvLogger(f"{domain}_input_error.csv", error_headers)

    def validate_json(self) -> None:
        """
        Validate loaded JSON configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if not self._pidDomains:
            raise ValueError("No PID domains defined in JSON policy file")
        if not self._constants:
            raise ValueError("No constants defined in JSON policy file")
        if not self._fan_limits:
            raise ValueError("No fan limits defined in JSON policy file")
        min_limit = self._fan_limits.get('min')
        max_limit = self._fan_limits.get('max')
        if min_limit is None or max_limit is None:
            raise ValueError("No min/max fan limits defined in JSON policy file")
        if min_limit > max_limit:
            raise ValueError(f"Min fan limit {min_limit} is greater than max fan limit {max_limit}")
        if min_limit < FAN_MIN_SPEED or max_limit > FAN_MAX_SPEED:
            raise ValueError(f"Fan limits {min_limit}-{max_limit} are out of range [{FAN_MIN_SPEED}, {FAN_MAX_SPEED}]")
        if not self._constants.get('interval'):
            raise ValueError("Interval must be defined in JSON policy file")

    def execute(self, thermal_info_dict: Dict[str, Any]) -> None:
        """
        Execute PID thermal control algorithm. Sets fans to maximum on errors.

        Args:
            thermal_info_dict: Dictionary containing thermal information
        """
        try:
            self._execute_raise_on_error(thermal_info_dict)
        except Exception as e:
            self.log_error(f"Exception executing thermal control algorithm: {e}")
            self.log_error(f"Traceback:\n{traceback.format_exc()}")
            self.log_error(f"Setting fan speed to {FAN_MAX_SPEED}% (max)")

            self._set_all_fan_speeds(thermal_info_dict, FAN_MAX_SPEED)
            raise

    def _execute_raise_on_error(self, thermal_info_dict: Dict[str, Any]) -> None:
        """
        Execute PID algorithm, raising exceptions on errors.

        Args:
            thermal_info_dict: Dictionary containing thermal information
        """
        thermal_info = thermal_info_dict.get(ThermalInfo.INFO_TYPE)
        if not thermal_info:
            raise ValueError("No thermal info available in thermal_info_dict")

        # Initialize PID controllers if needed
        if not self._pidControllers:
            dt = thermal_info.get_thermal_manager().get_interval()
            self._initialize_pid_controllers(dt)

        # Get all thermals and group by PID domain
        thermals = thermal_info.get_thermals()
        # CSV logging for temperature sensors
        timestamp = datetime.now().isoformat()
        self._log_temperature_sensors(thermals, timestamp)

        domain_thermals = self._group_thermals_by_domain(thermals)

        # Compute PID output for each domain
        pid_outputs = {}
        max_error_thermals = {}
        pid_details_by_domain = {}
        for domain, domain_thermal_list in domain_thermals.items():
            pid_output, max_error_thermal, pid_details = self._compute_domain_pid_output(domain, domain_thermal_list)
            pid_outputs[domain] = pid_output
            max_error_thermals[domain] = max_error_thermal.get_name() if max_error_thermal else "None"
            pid_details_by_domain[domain] = pid_details

        if not pid_outputs:
            raise ValueError("No valid PID outputs computed, keeping current fan speeds")

        # Use maximum PID output to set fan speed
        max_output = max(pid_outputs.values())
        max_domain = max(pid_outputs, key=pid_outputs.get)

        # Convert PID output to fan speed percentage
        final_speed = self._convert_pid_output_to_speed(max_output)

        # Determine selected domain: "None" if at minimum fan speed, otherwise the driving domain
        min_speed = self._fan_limits.get("min", FAN_MIN_SPEED)
        selected_domain = "None" if final_speed <= min_speed else max_domain

        self.log_info(
            f"Max PID output: {max_output:.3f} from domain '{max_domain}', setting fan speed to {final_speed:.1f}%"
        )

        # CSV logging for thermal control algorithm
        if self._csv_logger_control:
            # Create row data: timestamp, {domain}_sensor, {domain}_P, {domain}_I, {domain}_D,
            # {domain}_raw_output, {domain}_saturated_output, {domain}_frozen_integral for each domain,
            # selected_domain, configured_fan_speed
            row_data = [timestamp]
            for domain in sorted(self._pidDomains.keys(), key=_natural_sort_key):
                thermal_name = max_error_thermals.get(domain, "None")
                pid_details = pid_details_by_domain.get(domain, {})
                row_data.extend(
                    [
                        thermal_name,
                        pid_details.get("P", 0),
                        pid_details.get("I", 0),
                        pid_details.get("D", 0),
                        pid_details.get("raw_output", 0),
                        pid_details.get("saturated_output", 0),
                        pid_details.get("frozen_integral", False),
                    ]
                )
            row_data.extend([selected_domain, round(final_speed, 3)])
            self._csv_logger_control.log_row(row_data)

        # Set all fan speeds
        self._set_all_fan_speeds(thermal_info_dict, final_speed)

    def _initialize_pid_controllers(self, interval: int) -> None:
        """
        Initialize PID controllers for each domain.


        Args:
            interval: Control loop interval in seconds

        Raises:
            ValueError: If interval doesn't match configuration
        """
        if interval != self._constants["interval"]:
            # PID parameters are tuned for specific intervals
            raise ValueError(
                f"Interval {interval} does not match interval {self._constants.get('interval')} "
                f"specified in JSON policy file"
            )
        for domain, domain_config in self._pidDomains.items():
            controller = PIDController(
                domain=domain,
                interval=interval,
                proportional_gain=domain_config['KP'],
                integral_gain=domain_config['KI'],
                derivative_gain=domain_config['KD'],
                output_min=self._fan_limits.get('min', FAN_MIN_SPEED),
                output_max=self._fan_limits.get('max', FAN_MAX_SPEED)
            )
            self._pidControllers[domain] = controller
            self._extra_setpoint_margin[domain] = domain_config.get("extra_setpoint_margin", 0)
            self.log_info(f"Initialized PID controller for domain '{domain}'")
            if self._extra_setpoint_margin[domain]:
                self.log_notice(f"Extra setpoint margin for domain '{domain}': {self._extra_setpoint_margin[domain]}")

    def _group_thermals_by_domain(self, thermals: List[Any]) -> Dict[str, List[Any]]:
        """
        Group thermals by their PID domain.

        Args:
            thermals: List of thermal objects

        Returns:
            Dictionary mapping domain names to lists of thermal objects
        """
        domain_thermals = {}
        for thermal in thermals:
            if hasattr(thermal, "is_controlled_by_pid"):
                if not thermal.is_controlled_by_pid():
                    continue
                domain = thermal.get_pid_domain()
                if domain and domain in self._pidControllers:
                    if domain not in domain_thermals:
                        domain_thermals[domain] = []
                    domain_thermals[domain].append(thermal)
            else:
                self.log_warning(f"Thermal {thermal.get_name()} does not define is_controlled_by_pid()")
        if not domain_thermals:
            raise ValueError("No thermals available for PID control")
        for domain, domain_thermals_list in domain_thermals.items():
            if not domain_thermals_list:
                raise ValueError(f"Domain '{domain}' has no thermals")
        self.log_debug(f"Grouped thermals by domain: {[(d, len(ts)) for d, ts in domain_thermals.items()]}")
        return domain_thermals

    def _compute_domain_pid_output(self, domain: str, domain_thermals: List[Any]) -> tuple[float, Any, Dict[str, Any]]:
        """
        Compute PID output using thermal with largest error in domain.

        Args:
            domain: PID domain name
            domain_thermals: List of thermal objects in this domain

        Returns:
            Tuple of (PID output value, max error thermal object, PID computation details)
        """
        controller = self._pidControllers[domain]

        # Find thermal with largest error (current temp - setpoint)
        max_error = None
        max_error_thermal = None
        max_error_thermal_setpoint = None

        for thermal in domain_thermals:
            current_temp = thermal.get_temperature()
            if current_temp is None:
                # We may have no temperature reading if thermal is not present
                continue

            setpoint = thermal.get_pid_setpoint()
            if setpoint is None:
                # If the thermal was just unplugged, we may got the temperature, but not the setpoint
                continue

            error = current_temp - setpoint - self._extra_setpoint_margin[domain]

            if max_error is None or error > max_error:
                max_error = error
                max_error_thermal = thermal
                max_error_thermal_setpoint = setpoint

        if max_error_thermal is None:
            raise ValueError(f"No valid thermal found for domain '{domain}'")

        self.log_debug(
            f"Domain '{domain}': using thermal '{max_error_thermal.get_name()}' "
            f"with error {max_error:.2f}°C (setpoint={max_error_thermal_setpoint:.2f}°C)"
        )

        # Compute PID output using the largest error
        pid_output, pid_details = controller.compute_detailed(max_error)
        return pid_output, max_error_thermal, pid_details

    def _convert_pid_output_to_speed(self, pid_output: float) -> float:
        """
        Convert PID output to fan speed percentage.

        Args:
            pid_output: Raw PID controller output

        Returns:
            Fan speed percentage saturated to configured limits
        """
        min_speed = self._fan_limits.get('min', FAN_MIN_SPEED)
        max_speed = self._fan_limits.get('max', FAN_MAX_SPEED)
        return max(min_speed, min(max_speed, pid_output))

    def _set_all_fan_speeds(self, thermal_info_dict: Dict[str, Any], speed: float) -> None:
        """
        Set speed for all fans.

        Args:
            thermal_info_dict: Dictionary containing thermal information
            speed: Target fan speed percentage
        """
        set_all_fan_speeds(self, thermal_info_dict.get(FanInfo.INFO_TYPE).get_fans(), speed)

class PIDController(NhLoggerMixin):
    def __init__(
        self,
        domain: str,
        interval: int,
        proportional_gain: float,
        integral_gain: float,
        derivative_gain: float,
        output_min: float,
        output_max: float,
    ) -> None:
        """
        Initialize PID controller.

        Args:
            domain: Thermal domain name for logging
            interval: Control loop interval in seconds
            proportional_gain: Kp gain
            integral_gain: Ki gain
            derivative_gain: Kd gain
            output_min: Minimum output value (fan speed %)
            output_max: Maximum output value (fan speed %)
        """
        super().__init__(SYSLOG_IDENTIFIER_THERMAL)

        self._domain = domain
        self._interval = interval

        # Gains
        self._kp = proportional_gain
        self._ki = integral_gain
        self._kd = derivative_gain

        self._output_min = output_min
        self._output_max = output_max

        # PID state variables
        # Pre-seed integral to adjust to the midpoint between min/max
        # This helps reduce the initial transient response
        self._integral = (output_min + output_max) / 2 / self._ki
        self._prev_error: float = 0
        self._first_run: bool = True

        self.log_info(
            f"PIDController initialized for domain '{domain}': "
            f"gains=[Kp={proportional_gain}, Ki={integral_gain}, Kd={derivative_gain}], "
            f"output_range=[{output_min}, {output_max}], interval={interval}s"
        )

    def log(self, priority: Any, msg: str, also_print_to_console: bool = False) -> None:
        super().log(priority, f"[{self._domain}] {msg}", also_print_to_console)

    def compute(self, error: float) -> float:
        """
        Compute PID output.

        Args:
            error: Current error value (measured_value - setpoint)

        Returns:
            Saturated PID controller output
        """
        output, _ = self.compute_detailed(error)
        return output

    def compute_detailed(self, error: float) -> tuple[float, Dict[str, Any]]:
        """
        Compute PID output with detailed computation information.

        Args:
            error: Current error value (measured_value - setpoint)

        Returns:
            Tuple of (saturated PID output, computation details dict)
        """
        debug_params_strings = []
        kp, ki, kd = self._kp, self._ki, self._kd

        # Proportional term - current error
        proportional = error

        # Derivative term - rate of change of error
        if self._first_run:
            derivative = 0.0
            self._first_run = False
        else:
            derivative = (error - self._prev_error) / self._interval

        # Integral term - accumulated error over time
        integral = self._integral + error * self._interval

        # Calculate output
        output = kp * proportional + ki * integral + kd * derivative
        saturated_output = max(self._output_min, min(self._output_max, output))
        if saturated_output != output:
            debug_params_strings.append("output saturated")

        # Save state for next iteration
        # Only update integral if output is not saturated or if the error is helping to unsaturate
        self._prev_error = error
        should_update_integral = (output <= self._output_max or error < 0) and (output >= self._output_min or error > 0)
        if should_update_integral:
            self._integral = integral
        else:
            debug_params_strings.append("integral frozen")

        # Debug logging
        log_str = "PID=[ %8.3f %8.3f %8.3f ]   =>   OUT=%8.3f" % (proportional, integral, derivative, output)
        if debug_params_strings:
            log_str += f"   ({', '.join(debug_params_strings)})"
        self.log_debug(log_str)

        # Create computation details
        details = {
            "P": round(proportional, 3),
            "I": round(self._integral, 3),
            "D": round(derivative, 3),
            "raw_output": round(output, 3),
            "saturated_output": round(saturated_output, 3),
            "frozen_integral": not should_update_integral,
        }

        return saturated_output, details
