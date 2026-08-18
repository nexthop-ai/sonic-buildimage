#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for the thermal_csv_logger.py module.
These tests run in isolation from the SONiC environment using pytest:
python -m pytest test/unit/sonic_platform/test_thermal_csv_logger.py -v
"""

import csv
import importlib.util
import logging
import os
import sys
from dataclasses import dataclass
from typing import List
from unittest.mock import Mock, patch

import pytest

from fixtures.mock_imports_unit_tests import mock_natsort


@pytest.fixture(autouse=True)
def setup_external_mocks():
    """Set up mocks for external SONiC dependencies and define real dataclasses."""

    # Mock SysLogger
    class MockSysLogger:
        def __init__(self, syslog_identifier=None, *args, **kwargs):
            # Accept syslog_identifier argument but don't use it in tests
            # Methods as mocks so tests can assert calls
            self.log_info = Mock()
            self.log_error = Mock()
            self.log_warning = Mock()
            self.log_debug = Mock()
            # Note: Don't mock self.log as it would shadow CsvWriterBase.write_row() method
            self._min_log_level = logging.DEBUG  # Default to DEBUG for testing

    # Create mock modules for local dependencies
    mock_syslog = Mock()
    mock_syslog.SYSLOG_IDENTIFIER_THERMAL_CSV = "nh_thermal_csv"
    mock_syslog.NhLoggerMixin = MockSysLogger

    # Mock only the Thermal class
    class MockThermal:
        def __init__(self, name, temperature, pid_controlled=False, pid_domain=None, pid_setpoint=None):
            self.name = name
            self.temperature = temperature
            self.pid_controlled = pid_controlled
            self.pid_domain = pid_domain
            self.pid_setpoint = pid_setpoint

        def get_name(self):
            return self.name

        def get_temperature(self):
            return self.temperature

        def is_controlled_by_pid(self):
            return self.pid_controlled

        def get_pid_domain(self):
            return self.pid_domain

        def get_pid_setpoint(self):
            return self.pid_setpoint

    # Define the REAL dataclasses from thermal.py (copied directly from the source)
    # This ensures tests use the same dataclass definitions as production code
    # NOTE: SensorDetails needs frozen=True because it's used in sets in thermal_csv_logger.py
    @dataclass
    class PidOutput:
        P: float
        I: float
        D: float
        raw_output: float
        saturated_output: float
        frozen_integral: bool

    @dataclass(frozen=True)
    class SensorDetails:
        sensor_name: str
        temperature: float
        input_error: float | None = None
        setpoint: float | None = None

    @dataclass
    class PidDomainDetails:
        domain: str
        sensors: List[SensorDetails]
        max_error_sensor_name: str | None = None
        pid_output: PidOutput | None = None

    PID_DOMAIN_NONE = "None"

    # Create a mock thermal module with real dataclasses
    import types
    mock_thermal_module = types.ModuleType('sonic_platform.thermal')
    mock_thermal_module.Thermal = MockThermal
    mock_thermal_module.PidOutput = PidOutput
    mock_thermal_module.SensorDetails = SensorDetails
    mock_thermal_module.PidDomainDetails = PidDomainDetails
    mock_thermal_module.PID_DOMAIN_NONE = PID_DOMAIN_NONE

    # Mock all dependencies that aren't available in test environment
    mocks = {
        'sonic_platform.syslog': mock_syslog,
        'sonic_platform.thermal': mock_thermal_module,
    }
    mocks.update(mock_natsort())

    with patch.dict('sys.modules', mocks):
        yield


@pytest.fixture
def thermal_csv_logger_module():
    """Import the actual thermal_csv_logger module using normal Python imports."""
    test_dir = os.path.dirname(os.path.realpath(__file__))
    thermal_csv_logger_path = os.path.join(test_dir, "../../../common/sonic_platform/thermal_csv_logger.py")

    spec = importlib.util.spec_from_file_location("thermal_csv_logger", thermal_csv_logger_path)
    thermal_csv_logger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(thermal_csv_logger)

    return thermal_csv_logger


@pytest.fixture
def temp_csv_dir(tmp_path):
    """Create a temporary directory for CSV files."""
    csv_dir = tmp_path / "csv_logs"
    csv_dir.mkdir()
    return str(csv_dir)


@pytest.fixture
def thermal_cls():
    """Fixture returning the mocked Thermal class from sonic_platform.thermal."""
    return sys.modules['sonic_platform.thermal'].Thermal



def read_csv_header_and_row(filepath: str):
    """Utility to read first header row and next data row from a CSV file."""
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        data_row = next(reader)
    return header, data_row


class TestCsvWriterBase:
    """Test class for CsvWriterBase base class functionality."""

    @pytest.fixture
    def csv_writer(self, thermal_csv_logger_module, temp_csv_dir):
        """Fixture providing a CsvWriterBase instance for testing."""
        # Patch CSV_LOG_DIR for the duration of the test
        patcher = patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir)
        patcher.start()

        writer = thermal_csv_logger_module.CsvWriterBase(
            filename="test.csv",
            headers=["timestamp", "value1", "value2"]
        )
        # Ensure logging is enabled for tests
        writer._min_log_level = logging.DEBUG

        yield writer

        patcher.stop()

    def test_csv_writer_initialization(self, csv_writer, temp_csv_dir):
        """Test CsvWriterBase initialization."""
        assert csv_writer._filename == "test.csv"
        assert csv_writer._headers == ["timestamp", "value1", "value2"]
        assert csv_writer._filepath == os.path.join(temp_csv_dir, "test.csv")
        assert csv_writer._file_initialized is False

    def test_ensure_directory_exists(self, thermal_csv_logger_module, tmp_path):
        """Test directory creation."""
        csv_dir = tmp_path / "new_csv_dir"
        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', str(csv_dir)):
            writer = thermal_csv_logger_module.CsvWriterBase("test.csv", ["header1"])
            writer._ensure_directory_exists()
            assert csv_dir.exists()

    def test_ensure_file_initialized_creates_file_with_headers(self, csv_writer, temp_csv_dir):
        """Test that file initialization creates file with headers."""
        csv_writer._ensure_file_initialized()

        filepath = os.path.join(temp_csv_dir, "test.csv")
        assert os.path.exists(filepath)
        assert csv_writer._file_initialized is True

        # Verify headers were written
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)
            assert headers == ["timestamp", "value1", "value2"]

    def test_ensure_file_initialized_no_headers_raises_error(self, thermal_csv_logger_module, temp_csv_dir):
        """Test that file initialization without headers raises ValueError."""
        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            writer = thermal_csv_logger_module.CsvWriterBase("test.csv", headers=None)
            with pytest.raises(ValueError, match="Headers must be initialized"):
                writer._ensure_file_initialized()

    def test_ensure_file_initialized_idempotent(self, csv_writer, temp_csv_dir):
        """Test that file initialization is idempotent."""
        csv_writer._ensure_file_initialized()
        first_mtime = os.path.getmtime(csv_writer._filepath)

        # Call again - should not recreate file
        csv_writer._ensure_file_initialized()
        second_mtime = os.path.getmtime(csv_writer._filepath)

        assert first_mtime == second_mtime

    def test_ensure_file_initialized_overwrites_existing_file(self, thermal_csv_logger_module, temp_csv_dir):
        """Test that file initialization overwrites existing file content."""
        filepath = os.path.join(temp_csv_dir, "test_overwrite.csv")

        # Create a file with existing content
        with open(filepath, 'w') as f:
            f.write("old_header1,old_header2\n")
            f.write("old_data1,old_data2\n")

        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            writer = thermal_csv_logger_module.CsvWriterBase(
                filename="test_overwrite.csv",
                headers=["new_header1", "new_header2", "new_header3"]
            )
            writer._min_log_level = logging.DEBUG
            writer._ensure_file_initialized()

        # Verify file was overwritten with new headers only
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) == 1  # Only header, no old data
            assert rows[0] == ["new_header1", "new_header2", "new_header3"]

    def test_ensure_file_initialized_logs_warning_for_non_empty_file(self, thermal_csv_logger_module, temp_csv_dir):
        """Test that a warning is logged when overwriting a non-empty file."""
        filepath = os.path.join(temp_csv_dir, "test_warning.csv")

        # Create a file with existing content
        with open(filepath, 'w') as f:
            f.write("old_header1,old_header2\n")
            f.write("old_data1,old_data2\n")

        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            writer = thermal_csv_logger_module.CsvWriterBase(
                filename="test_warning.csv",
                headers=["new_header1", "new_header2"]
            )
            writer._min_log_level = logging.DEBUG

            # Mock log_warning to verify it was called
            with patch.object(writer, 'log_warning') as mock_warning:
                writer._ensure_file_initialized()
                mock_warning.assert_called_once()
                assert "test_warning.csv" in mock_warning.call_args[0][0]
                assert "not empty" in mock_warning.call_args[0][0]

    def test_ensure_file_initialized_no_warning_for_empty_file(self, thermal_csv_logger_module, temp_csv_dir):
        """Test that no warning is logged when initializing an empty file."""
        filepath = os.path.join(temp_csv_dir, "test_empty.csv")

        # Create an empty file
        with open(filepath, 'w') as f:
            pass  # Empty file

        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            writer = thermal_csv_logger_module.CsvWriterBase(
                filename="test_empty.csv",
                headers=["header1", "header2"]
            )
            writer._min_log_level = logging.DEBUG

            # Mock log_warning to verify it was NOT called
            with patch.object(writer, 'log_warning') as mock_warning:
                writer._ensure_file_initialized()
                mock_warning.assert_not_called()

    def test_logging_enabled_when_debug_level(self, csv_writer):
        """Test that logging is enabled when writer is at DEBUG level."""
        csv_writer._min_log_level = logging.DEBUG
        assert csv_writer.logging_enabled() is True

    def test_logging_disabled_when_info_level(self, csv_writer):
        """Test that logging is disabled when writer is at INFO level."""
        csv_writer._min_log_level = logging.INFO
        assert csv_writer.logging_enabled() is False

    def test_write_row_writes_data_when_enabled(self, csv_writer, temp_csv_dir):
        """Test that write_row() writes data when logging is enabled."""
        csv_writer._min_log_level = logging.DEBUG
        assert csv_writer.logging_enabled(), "Logging should be enabled"

        csv_writer.write_row({"timestamp": "2025-01-01T00:00:00", "value1": 10.5, "value2": 20.3})

        # Check if any errors were logged
        if csv_writer.log_error.called:
            raise AssertionError(f"Errors logged: {csv_writer.log_error.call_args_list}")

        filepath = os.path.join(temp_csv_dir, "test.csv")
        if not os.path.exists(filepath):
            dir_contents = os.listdir(temp_csv_dir) if os.path.exists(temp_csv_dir) else 'dir does not exist'
            raise AssertionError(f"File should exist at {filepath}. Dir contents: {dir_contents}")

        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            try:
                next(reader)
                data_row = next(reader)
                assert data_row == ["2025-01-01T00:00:00", "10.5", "20.3"]
            except StopIteration:
                raise AssertionError(f"File {filepath} doesn't have enough rows")

    def test_write_row_does_not_write_when_disabled(self, csv_writer, temp_csv_dir):
        """Test that write_row() does not write data when logging is disabled."""
        csv_writer._min_log_level = logging.INFO
        csv_writer.write_row({"timestamp": "2025-01-01T00:00:00", "value1": 10.5, "value2": 20.3})

        filepath = os.path.join(temp_csv_dir, "test.csv")
        assert not os.path.exists(filepath)

    def test_write_row_multiple_rows(self, csv_writer, temp_csv_dir):
        """Test writing multiple rows."""
        csv_writer._min_log_level = logging.DEBUG
        csv_writer.write_row({"timestamp": "2025-01-01T00:00:00", "value1": 10.5, "value2": 20.3})
        csv_writer.write_row({"timestamp": "2025-01-01T00:01:00", "value1": 11.2, "value2": 21.1})
        csv_writer.write_row({"timestamp": "2025-01-01T00:02:00", "value1": 12.0, "value2": 22.5})

        filepath = os.path.join(temp_csv_dir, "test.csv")
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) == 4  # 1 header + 3 data rows
            assert rows[0] == ["timestamp", "value1", "value2"]
            assert rows[1] == ["2025-01-01T00:00:00", "10.5", "20.3"]
            assert rows[2] == ["2025-01-01T00:01:00", "11.2", "21.1"]
            assert rows[3] == ["2025-01-01T00:02:00", "12.0", "22.5"]


class TestCsvWriterFileTrimming:
    """Test class for CSV file trimming functionality."""

    @pytest.fixture
    def csv_writer_with_small_limit(self, thermal_csv_logger_module, temp_csv_dir):
        """Fixture providing a CsvWriterBase with small file size limit for testing."""
        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            with patch.object(thermal_csv_logger_module, 'CSV_MAX_FILE_SIZE_MB', 0.001):  # 1KB limit
                writer = thermal_csv_logger_module.CsvWriterBase(
                    filename="test_trim.csv",
                    headers=["timestamp", "value"]
                )
                writer._min_log_level = logging.DEBUG
                yield writer

    def test_trim_file_keeps_newest_entries(self, thermal_csv_logger_module, csv_writer_with_small_limit, temp_csv_dir):
        """Test that file trimming keeps the newest entries."""
        # Write many rows to exceed size limit
        for i in range(100):
            csv_writer_with_small_limit.write_row({"timestamp": f"2025-01-01T00:{i:02d}:00", "value": i})

        filepath = os.path.join(temp_csv_dir, "test_trim.csv")
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)

        # Should have header + some data rows (trimmed)
        assert len(rows) > 1
        assert len(rows) < 101  # Should be trimmed
        assert rows[0] == ["timestamp", "value"]

        # Verify newest entries are kept (higher numbers)
        last_value = int(rows[-1][1])
        assert last_value == 99  # Last entry should be the newest


class TestThermalControlCsvWriter:
    """Test class for ThermalControlCsvWriter functionality."""

    @pytest.fixture
    def thermal_control_writer(self, thermal_csv_logger_module, temp_csv_dir):
        """Fixture providing a ThermalControlCsvWriter instance for testing."""
        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            writer = thermal_csv_logger_module.ThermalControlCsvWriter()
            writer._min_log_level = logging.DEBUG
            yield writer

    def test_thermal_control_writer_initialization(self, thermal_control_writer, thermal_csv_logger_module):
        """Test ThermalControlCsvWriter initialization."""
        assert thermal_control_writer._filename == thermal_csv_logger_module.CSV_THERMAL_DATA_FILE_NAME
        assert thermal_control_writer._headers == []  # Headers initialized lazily

    def test_initialize_headers_single_domain(self, thermal_control_writer):
        """Test header initialization with a single PID domain."""
        thermal_control_writer._initialize_headers(["domain1"])

        expected_headers = [
            "timestamp",
            "domain1_sensor",
            "domain1_P",
            "domain1_I",
            "domain1_D",
            "domain1_raw_output",
            "domain1_saturated_output",
            "domain1_frozen_integral",
            "selected_domain",
            "configured_fan_speed"
        ]
        assert thermal_control_writer._headers == expected_headers

    def test_initialize_headers_multiple_domains(self, thermal_control_writer):
        """Test header initialization with multiple PID domains."""
        thermal_control_writer._initialize_headers(["domain2", "domain1", "domain3"])

        # Should be sorted naturally
        assert thermal_control_writer._headers[0] == "timestamp"
        assert "domain1_sensor" in thermal_control_writer._headers
        assert "domain2_sensor" in thermal_control_writer._headers
        assert "domain3_sensor" in thermal_control_writer._headers
        assert thermal_control_writer._headers[-2] == "selected_domain"
        assert thermal_control_writer._headers[-1] == "configured_fan_speed"

    def test_write_row_initializes_headers_on_first_call(self, thermal_control_writer, temp_csv_dir, thermal_csv_logger_module):
        """Test that write_row() initializes headers on first call."""
        from sonic_platform.thermal import PidOutput, PidDomainDetails, SensorDetails
        pid_details_by_domain = {
            "domain1": PidDomainDetails(
                domain="domain1",
                sensors=[SensorDetails(sensor_name="Sensor1", temperature=45.0, input_error=5.0)],
                max_error_sensor_name="Sensor1",
                pid_output=PidOutput(
                    P=1.5,
                    I=2.0,
                    D=0.5,
                    raw_output=45.0,
                    saturated_output=45.0,
                    frozen_integral=False
                )
            )
        }

        thermal_control_writer.write_row("2025-01-01T00:00:00", "domain1", 45.0, pid_details_by_domain)

        assert len(thermal_control_writer._headers) > 0
        assert thermal_control_writer._headers[0] == "timestamp"

    def test_write_row_writes_correct_data(self, thermal_control_writer, temp_csv_dir, thermal_csv_logger_module):
        """Test that write_row() writes correct data to CSV."""
        from sonic_platform.thermal import PidOutput, PidDomainDetails, SensorDetails
        pid_details_by_domain = {
            "domain1": PidDomainDetails(
                domain="domain1",
                sensors=[SensorDetails(sensor_name="Sensor1", temperature=45.0, input_error=5.0)],
                max_error_sensor_name="Sensor1",
                pid_output=PidOutput(
                    P=1.5,
                    I=2.0,
                    D=0.5,
                    raw_output=45.0,
                    saturated_output=45.0,
                    frozen_integral=False
                )
            )
        }

        thermal_control_writer.write_row("2025-01-01T00:00:00", "domain1", 45.123, pid_details_by_domain)

        filepath = os.path.join(temp_csv_dir, thermal_csv_logger_module.CSV_THERMAL_DATA_FILE_NAME)
        _, data_row = read_csv_header_and_row(filepath)

        assert data_row[0] == "2025-01-01T00:00:00"
        assert data_row[1] == "Sensor1"  # domain1_sensor
        assert data_row[2] == "1.5"  # domain1_P
        assert data_row[3] == "2.0"  # domain1_I
        assert data_row[4] == "0.5"  # domain1_D
        assert data_row[5] == "45.0"  # domain1_raw_output
        assert data_row[6] == "45.0"  # domain1_saturated_output
        assert data_row[7] == "False"  # domain1_frozen_integral
        assert data_row[8] == "domain1"  # selected_domain
        assert data_row[9] == "45.123"  # configured_fan_speed

    def test_write_row_multiple_domains(self, thermal_control_writer, temp_csv_dir, thermal_csv_logger_module):
        """Test write_row with multiple PID domains."""
        from sonic_platform.thermal import PidOutput, PidDomainDetails, SensorDetails
        pid_details_by_domain = {
            "domain1": PidDomainDetails(
                domain="domain1",
                sensors=[SensorDetails(sensor_name="Sensor1", temperature=45.0, input_error=5.0)],
                max_error_sensor_name="Sensor1",
                pid_output=PidOutput(
                    P=1.5,
                    I=2.0,
                    D=0.5,
                    raw_output=45.0,
                    saturated_output=45.0,
                    frozen_integral=False
                )
            ),
            "domain2": PidDomainDetails(
                domain="domain2",
                sensors=[SensorDetails(sensor_name="Sensor2", temperature=60.0, input_error=15.0)],
                max_error_sensor_name="Sensor2",
                pid_output=PidOutput(
                    P=2.5,
                    I=3.0,
                    D=1.0,
                    raw_output=60.0,
                    saturated_output=60.0,
                    frozen_integral=True
                )
            )
        }

        thermal_control_writer.write_row("2025-01-01T00:00:00", "domain2", 60.0, pid_details_by_domain)

        filepath = os.path.join(temp_csv_dir, thermal_csv_logger_module.CSV_THERMAL_DATA_FILE_NAME)
        _, data_row = read_csv_header_and_row(filepath)

        # Verify both domains are in the data
        assert "Sensor1" in data_row
        assert "Sensor2" in data_row
        assert "domain2" in data_row  # selected_domain

    def test_write_row_missing_domain_data(self, thermal_control_writer, temp_csv_dir, thermal_csv_logger_module):
        """Test write_row when some domain data is missing."""
        from sonic_platform.thermal import PidOutput, PidDomainDetails, SensorDetails
        pid_details_by_domain = {
            "domain1": PidDomainDetails(
                domain="domain1",
                sensors=[SensorDetails(sensor_name="Sensor1", temperature=45.0, input_error=5.0)],
                max_error_sensor_name=None,  # No max error sensor
                pid_output=PidOutput(
                    P=1.5,
                    I=2.0,
                    D=0.5,
                    raw_output=45.0,
                    saturated_output=45.0,
                    frozen_integral=False
                )
            )
        }

        thermal_control_writer.write_row("2025-01-01T00:00:00", "domain1", 45.0, pid_details_by_domain)

        filepath = os.path.join(temp_csv_dir, thermal_csv_logger_module.CSV_THERMAL_DATA_FILE_NAME)
        _, data_row = read_csv_header_and_row(filepath)

        # Should use empty string for None (CSV writer converts None to empty string)
        assert data_row[1] == ""

    def test_write_row_does_not_write_when_disabled(self, thermal_control_writer, temp_csv_dir, thermal_csv_logger_module):
        """Test that write_row() does not write when logging is disabled."""
        from sonic_platform.thermal import PidOutput, PidDomainDetails, SensorDetails
        thermal_control_writer._min_log_level = logging.INFO

        pid_details_by_domain = {
            "domain1": PidDomainDetails(
                domain="domain1",
                sensors=[SensorDetails(sensor_name="Sensor1", temperature=45.0, input_error=5.0)],
                max_error_sensor_name="Sensor1",
                pid_output=PidOutput(P=1.5, I=2.0, D=0.5, raw_output=45.0, saturated_output=45.0,
                                   frozen_integral=False)
            )
        }

        thermal_control_writer.write_row("2025-01-01T00:00:00", "domain1", 45.0, pid_details_by_domain)

        filepath = os.path.join(temp_csv_dir, thermal_csv_logger_module.CSV_THERMAL_DATA_FILE_NAME)
        assert not os.path.exists(filepath)


class TestTemperatureCsvWriter:
    """Test class for TemperatureCsvWriter functionality."""

    @pytest.fixture
    def temperature_writer(self, thermal_csv_logger_module, temp_csv_dir):
        """Fixture providing a TemperatureCsvWriter instance for testing."""
        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            writer = thermal_csv_logger_module.TemperatureCsvWriter(
                filename="test_temperature.csv",
                log_type=thermal_csv_logger_module.TemperatureLogType.TEMPERATURE
            )
            writer._min_log_level = logging.DEBUG
            yield writer

    @pytest.fixture
    def domain_input_error_writer(self, thermal_csv_logger_module, temp_csv_dir):
        """Fixture providing a TemperatureCsvWriter instance for domain input errors."""
        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            writer = thermal_csv_logger_module.TemperatureCsvWriter(
                filename="test_domain_input_error.csv",
                log_type=thermal_csv_logger_module.TemperatureLogType.DOMAIN_INPUT_ERROR
            )
            writer._min_log_level = logging.DEBUG
            yield writer

    def test_temperature_writer_initialization(self, temperature_writer, thermal_csv_logger_module):
        """Test TemperatureCsvWriter initialization."""
        assert temperature_writer._log_type == thermal_csv_logger_module.TemperatureLogType.TEMPERATURE
        # Headers are initialized as empty list in parent CsvWriterBase.__init__
        assert temperature_writer._headers == []

    def test_sensor_display_name_transceiver_rename(self, temperature_writer):
        """Test sensor name processing for transceivers."""
        result = temperature_writer._sensor_display_name("Transceiver Port1")
        assert result == "Port1"

        result = temperature_writer._sensor_display_name("Transceiver Port42")
        assert result == "Port42"

    def test_sensor_display_name_passthrough(self, temperature_writer):
        """Test sensor name processing for other sensors."""
        result = temperature_writer._sensor_display_name("CPU Sensor")
        assert result == "CPU Sensor"

        result = temperature_writer._sensor_display_name("Board Temp")
        assert result == "Board Temp"

    def test_write_row_temperature_data(self, temperature_writer, temp_csv_dir):
        """Test logging temperature data."""
        from sonic_platform.thermal import SensorDetails

        sensors = {
            SensorDetails(sensor_name="Sensor1", temperature=45.5, input_error=5.5),
            SensorDetails(sensor_name="Sensor2", temperature=50.2, input_error=10.2),
        }

        temperature_writer.write_row("2025-01-01T00:00:00", sensors)

        filepath = os.path.join(temp_csv_dir, "test_temperature.csv")
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) == 2  # 1 header + 1 data row
            assert rows[0] == ["timestamp", "Sensor1", "Sensor2"]
            assert rows[1] == ["2025-01-01T00:00:00", "45.5", "50.2"]

    def test_write_row_domain_input_error_data(self, domain_input_error_writer, temp_csv_dir):
        """Test logging domain input error data."""
        from sonic_platform.thermal import SensorDetails

        sensors = {
            SensorDetails(sensor_name="Sensor1", temperature=45.5, input_error=5.5),
            SensorDetails(sensor_name="Sensor2", temperature=50.2, input_error=10.2),
        }

        domain_input_error_writer.write_row("2025-01-01T00:00:00", sensors)

        filepath = os.path.join(temp_csv_dir, "test_domain_input_error.csv")
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) == 2  # 1 header + 1 data row
            assert rows[0] == ["timestamp", "Sensor1", "Sensor2"]
            assert rows[1] == ["2025-01-01T00:00:00", "5.5", "10.2"]

    def test_write_row_with_transceiver_rename(self, temperature_writer, temp_csv_dir):
        """Test that transceiver sensors are renamed in logs."""
        from sonic_platform.thermal import SensorDetails

        sensors = {
            SensorDetails(sensor_name="Transceiver Port1", temperature=45.5, input_error=None),
            SensorDetails(sensor_name="Transceiver Port2", temperature=50.2, input_error=None),
        }

        temperature_writer.write_row("2025-01-01T00:00:00", sensors)

        filepath = os.path.join(temp_csv_dir, "test_temperature.csv")
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert "Port1" in rows[0]
            assert "Port2" in rows[0]
            assert "Transceiver Port1" not in rows[0]
            assert "Transceiver Port2" not in rows[0]

    def test_write_row_handles_none_temperature(self, temperature_writer, temp_csv_dir):
        """Test that sensors with None temperature are handled gracefully."""
        from sonic_platform.thermal import SensorDetails

        sensors = {
            SensorDetails(sensor_name="Sensor1", temperature=45.5, input_error=None),
            SensorDetails(sensor_name="Sensor2", temperature=None, input_error=None),
            SensorDetails(sensor_name="Sensor3", temperature=50.2, input_error=None),
        }

        temperature_writer.write_row("2025-01-01T00:00:00", sensors)

        filepath = os.path.join(temp_csv_dir, "test_temperature.csv")
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            rows = list(reader)
            assert len(rows) == 2  # 1 header + 1 data row
            # Sensor2 should have empty string for None
            assert rows[1][0] == "2025-01-01T00:00:00"
            assert rows[1][1] == "45.5"  # Sensor1
            assert rows[1][2] == ""  # Sensor2 (None)
            assert rows[1][3] == "50.2"  # Sensor3

    def test_write_row_does_not_write_when_disabled(self, temperature_writer, temp_csv_dir):
        """Test that write_row() does not write when logging is disabled."""
        from sonic_platform.thermal import SensorDetails

        temperature_writer._min_log_level = logging.INFO

        sensors = {
            SensorDetails(sensor_name="Sensor1", temperature=45.5, input_error=None),
            SensorDetails(sensor_name="Sensor2", temperature=50.2, input_error=None),
        }

        temperature_writer.write_row("2025-01-01T00:00:00", sensors)

        filepath = os.path.join(temp_csv_dir, "test_temperature.csv")
        assert not os.path.exists(filepath)


class TestThermalCsvLogger:
    """Test class for ThermalCsvLogger functionality."""

    @pytest.fixture
    def thermal_csv_logger(self, thermal_csv_logger_module, temp_csv_dir):
        """Fixture providing a ThermalCsvLogger instance for testing."""
        with patch.object(thermal_csv_logger_module, 'CSV_LOG_DIR', temp_csv_dir):
            logger = thermal_csv_logger_module.ThermalCsvLogger()
            logger._thermal_control_writer._min_log_level = logging.DEBUG
            yield logger

    def test_thermal_csv_logger_initialization(self, thermal_csv_logger):
        """Test ThermalCsvLogger initialization."""
        assert thermal_csv_logger._thermal_control_writer is not None
        assert thermal_csv_logger._temperature_writer is None
        assert thermal_csv_logger._domain_input_error_writers == {}

    def test_log_initializes_writers_on_first_call(self, thermal_csv_logger, temp_csv_dir):
        """Test that log() initializes writers on first call."""
        from sonic_platform.thermal import PidOutput, PidDomainDetails, SensorDetails

        pid_details_by_domain = {
            "domain1": PidDomainDetails(
                domain="domain1",
                sensors=[SensorDetails(sensor_name="Sensor1", temperature=45.0, input_error=5.0)],
                max_error_sensor_name="Sensor1",
                pid_output=PidOutput(P=1.5, I=2.0, D=0.5, raw_output=45.0, saturated_output=45.0, frozen_integral=False)
            )
        }

        thermal_csv_logger.log("domain1", 45.0, pid_details_by_domain)

        assert thermal_csv_logger._temperature_writer is not None
        assert "domain1" in thermal_csv_logger._domain_input_error_writers

    def test_log_writes_all_csv_files(self, thermal_csv_logger_module, thermal_csv_logger, temp_csv_dir):
        """Test that log() writes to all CSV files."""
        from sonic_platform.thermal import PidOutput, PidDomainDetails, SensorDetails

        pid_details_by_domain = {
            "domain1": PidDomainDetails(
                domain="domain1",
                sensors=[SensorDetails(sensor_name="Sensor1", temperature=45.0, input_error=5.0)],
                max_error_sensor_name="Sensor1",
                pid_output=PidOutput(P=1.5, I=2.0, D=0.5, raw_output=45.0, saturated_output=45.0, frozen_integral=False)
            )
        }

        thermal_csv_logger.log("domain1", 45.0, pid_details_by_domain)

        # Check that all files were created
        thermal_control_file = os.path.join(temp_csv_dir, thermal_csv_logger_module.CSV_THERMAL_DATA_FILE_NAME)
        temperature_file = os.path.join(temp_csv_dir, thermal_csv_logger_module.CSV_TEMPERATURE_DATA_FILE_NAME)
        domain_error_file = os.path.join(temp_csv_dir, thermal_csv_logger_module.CSV_TEMPERATURE_DOMAIN_INPUT_ERROR_FILE_NAME_TEMPLATE.format("domain1"))

        assert os.path.exists(thermal_control_file)
        assert os.path.exists(temperature_file)
        assert os.path.exists(domain_error_file)

    def test_log_does_not_write_when_disabled(self, thermal_csv_logger, temp_csv_dir, thermal_csv_logger_module):
        """Test that log() does not write when logging is disabled."""
        from sonic_platform.thermal import PidOutput, PidDomainDetails, SensorDetails

        thermal_csv_logger._thermal_control_writer._min_log_level = logging.INFO

        pid_details_by_domain = {
            "domain1": PidDomainDetails(
                domain="domain1",
                sensors=[SensorDetails(sensor_name="Sensor1", temperature=45.0, input_error=5.0)],
                max_error_sensor_name="Sensor1",
                pid_output=PidOutput(P=1.5, I=2.0, D=0.5, raw_output=45.0, saturated_output=45.0, frozen_integral=False)
            )
        }

        thermal_csv_logger.log("domain1", 45.0, pid_details_by_domain)

        # Check that no files were created
        thermal_control_file = os.path.join(temp_csv_dir, thermal_csv_logger_module.CSV_THERMAL_DATA_FILE_NAME)
        assert not os.path.exists(thermal_control_file)

