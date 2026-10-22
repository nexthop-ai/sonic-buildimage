# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import sys
from unittest.mock import Mock, patch

import pytest


class MockPddfPsu:
    DEVICE_TYPE = "psu"
    get_presence = Mock()
    get_name = Mock(return_value="PSU1")
    get_status_led = Mock(return_value="green")
    get_temperature = Mock(return_value=42.0)

    def __init__(self, index, pddf_data, pddf_plugin_data):
        self.psu_index = index + 1
        self.pddf_data = pddf_data
        self.pddf_plugin_data = pddf_plugin_data


@pytest.fixture
def mock_pddf_psu():
    pddf_psu = Mock()
    pddf_psu.PddfPsu = MockPddfPsu
    with patch.dict(sys.modules, {"sonic_platform_pddf_base.pddf_psu": pddf_psu}):
        yield pddf_psu.PddfPsu


@pytest.fixture
def psu_module(mock_pddf_psu):
    from sonic_platform import psu

    yield psu


class TestPsu:
    def test_get_status_led_is_not_available(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        for presence in (True, False):
            mock_pddf_psu.get_presence.return_value = presence
            assert psu.get_status_led() == "N/A"

    def test_get_status_led_ignores_pddf_generic_scheme(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_status_led.return_value = "off"
        assert psu.get_status_led() == "N/A"

        mock_pddf_psu.get_status_led.return_value = "green"
        assert psu.get_status_led() == "N/A"

    def test_get_revision(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        assert psu.get_revision() == "N/A"

    def test_get_temperature_for_present_psu(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_presence.return_value = True
        assert psu.get_temperature() == 42.0

    def test_get_temperature_for_non_present_psu(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_presence.return_value = False
        assert psu.get_temperature() == "N/A"

    def test_rtc_sync_skips_absent_psu(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_presence.return_value = False
        with patch.object(psu, "set_blackbox_unix_time") as set_time:
            assert psu.rtc_sync() is True
            set_time.assert_not_called()

    def test_rtc_sync_writes_time_on_present_psu(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_presence.return_value = True
        for written in (True, False):
            with patch.object(psu, "set_blackbox_unix_time", return_value=written) as set_time:
                assert psu.rtc_sync() is written
                set_time.assert_called_once_with()

    @pytest.mark.parametrize("status_input, expected", [
        (0x00, True),
        (0x08, False),
        (0x38, False),
        (0x30, True),
    ])
    def test_get_input_status_decodes_vin_off(self, mock_pddf_psu, psu_module, status_input, expected):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_presence.return_value = True
        with patch.object(psu, "_get_pmbus_i2c_loc", return_value=(89, 0x58)), \
             patch.object(psu_module, "SMBus") as smbus:
            bus = smbus.return_value.__enter__.return_value
            bus.read_byte_data.return_value = status_input
            assert psu.get_input_status() is expected
            smbus.assert_called_once_with(89)
            bus.read_byte_data.assert_called_once_with(0x58, psu_module.PMBUS_STATUS_INPUT_CMD, force=True)

    def test_get_input_status_absent_psu(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_presence.return_value = False
        with patch.object(psu_module, "SMBus") as smbus:
            assert psu.get_input_status() is None
            smbus.assert_not_called()

    def test_get_input_status_no_pmbus_device(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_presence.return_value = True
        with patch.object(psu, "_get_pmbus_i2c_loc", return_value=None):
            assert psu.get_input_status() is None

    def test_get_input_status_read_error(self, mock_pddf_psu, psu_module):
        psu = psu_module.Psu(index=0)

        mock_pddf_psu.get_presence.return_value = True
        with patch.object(psu, "_get_pmbus_i2c_loc", return_value=(89, 0x58)), \
             patch.object(psu_module, "SMBus") as smbus:
            smbus.return_value.__enter__.return_value.read_byte_data.side_effect = OSError(121, "Remote I/O error")
            with patch.object(psu_module.logger, "log_warning") as log_warning:
                assert psu.get_input_status() is None
            log_warning.assert_called_once()
