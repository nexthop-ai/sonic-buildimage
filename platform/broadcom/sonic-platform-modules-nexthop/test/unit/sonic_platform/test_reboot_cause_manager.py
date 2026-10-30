#!/usr/bin/env python

import datetime
import pytest
import sys

from fixtures.test_helpers_adm1266 import create_raw_adm1266_blackbox_record
from fixtures.test_helpers_common import temp_file
from unittest.mock import Mock, patch, create_autospec


@pytest.fixture
def mock_dpm_logger():
    """Mock the DpmLogger class to avoid writing to filesystem."""
    dpm_logger = Mock()
    dpm_logger.DpmLogger = Mock()
    with patch.dict(sys.modules, {"sonic_platform.dpm_logger": dpm_logger}):
        yield dpm_logger


@pytest.fixture
def reboot_cause_manager_module(mock_dpm_logger):
    """Loads the module before each test. This is to let conftest.py run first."""
    from sonic_platform import reboot_cause_manager

<<<<<<< HEAD
=======
    monkeypatch.setattr(reboot_cause_manager, "REBOOT_CAUSE_HISTORY_DIR", str(tmp_path / "reboot-cause"))
    monkeypatch.setattr(reboot_cause_manager, "read_amd_reset_reason", lambda: None)
>>>>>>> cb4aa24c5 (NOS-21526: [platform] Fall back to the AMD FCH reset reason for unexplained hardware reboots (#12072))
    yield reboot_cause_manager


class TestRebootCauseManager:
    """Test class for RebootCauseManager functionality."""

    def test_summarize_reboot_causes_sw_reboot(self, reboot_cause_manager_module):
        # Given
        with temp_file(
            "User issued 'reboot' command [User: admin, Time: Thu Oct  2 11:22:56 PM UTC 2025]"
        ) as sw_reboot_cause_filepath:
            pddf_data = {}  # Empty pddf_data for tests without DPM devices
            pddf_plugin_data = {"REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath}}

            # When
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(
                pddf_data, pddf_plugin_data
            )
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert len(reboot_causes) == 1
            assert reboot_causes[0] == reboot_cause_manager_module.RebootCause(
                type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                source="SW",
                timestamp=datetime.datetime(2025, 10, 2, 23, 22, 56, tzinfo=datetime.timezone.utc),
                cause="reboot",
                description="User issued 'reboot' command [User: admin, Time: Thu Oct  2 11:22:56 PM UTC 2025]",
                chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
            )

    def test_summarize_reboot_causes_sw_kernel_panic(self, reboot_cause_manager_module):
        # Given
        with temp_file(
            "Kernel Panic - Out of memory [Time: Thu Oct  21 11:22:59 PM UTC 2025]"
        ) as sw_reboot_cause_filepath:
            pddf_data = {}  # Empty pddf_data for tests without DPM devices
            pddf_plugin_data = {"REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath}}

            # When
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(
                pddf_data, pddf_plugin_data
            )
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                    source="SW",
                    timestamp=datetime.datetime(
                        2025, 10, 21, 23, 22, 59, tzinfo=datetime.timezone.utc
                    ),
                    cause="Kernel Panic - Out of memory",
                    description="Kernel Panic - Out of memory [Time: Thu Oct  21 11:22:59 PM UTC 2025]",
                    chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
                )
            ]

    def test_summarize_reboot_causes_sw_others(self, reboot_cause_manager_module):
        # Given
        FULL_SW_CAUSE = "Some software causes that don't match known patterns"
        with temp_file(FULL_SW_CAUSE) as sw_reboot_cause_filepath:
            pddf_data = {}  # Empty pddf_data for tests without DPM devices
            pddf_plugin_data = {"REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath}}

            # When
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(
                pddf_data, pddf_plugin_data
            )
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                    source="SW",
                    timestamp=reboot_cause_manager_module.UNKNOWN_TIMESTAMP,
                    cause=FULL_SW_CAUSE,
                    description=FULL_SW_CAUSE,
                    chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
                )
            ]

    def test_summarize_reboot_causes_sw_unknown(self, reboot_cause_manager_module):
        # Given
        with temp_file("Unknown") as sw_reboot_cause_filepath:
            pddf_data = {}  # Empty pddf_data for tests without DPM devices
            pddf_plugin_data = {"REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath}}

            # When
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(
                pddf_data, pddf_plugin_data
            )
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == []

    def test_summarize_reboot_causes_hw_many_adm1266(
        self, mock_dpm_logger, reboot_cause_manager_module
    ):
        # Given
        # DPM1: [unknown         (p=10), fault_from_pdi1 (p=11)               ]; current_powerup_counter = 12
        # DPM2: [fault_from_pdi1 (p=1) , fault_from_pdi2 (p=2) , unknown (p=3)]; current_powerup_counter = 3
        DPM_1_RECORDS = [
            # 1st powerup - no fault.
            create_raw_adm1266_blackbox_record(uid=1, powerup_counter=10),  # No PDI
            # 2nd powerup - has fault.
            create_raw_adm1266_blackbox_record(uid=2, powerup_counter=11),  # No PDI
            create_raw_adm1266_blackbox_record(
                uid=3,
                powerup_counter=11,
                pdio_in=0b0000_0000_0000_0001,  # PDI1
                timestamp=datetime.datetime(2025, 10, 2, 23, 22, 56, tzinfo=datetime.timezone.utc),
            ),
        ]
        DPM_2_RECORDS = [
            # 1st powerup - has fault.
            create_raw_adm1266_blackbox_record(uid=1234, powerup_counter=1),  # No PDI
            create_raw_adm1266_blackbox_record(
                uid=1235,
                powerup_counter=1,
                pdio_in=0b0000_0000_0000_0001,  # PDI1
                timestamp=datetime.timedelta(seconds=70),
            ),
            # 2nd powerup - has fault.
            create_raw_adm1266_blackbox_record(
                uid=1236,
                powerup_counter=2,
                pdio_in=0b0000_0000_0001_0010,  # PDI5, PDI2
                timestamp=datetime.timedelta(seconds=140),
            ),
            # 3rd powerup - no fault.
            create_raw_adm1266_blackbox_record(uid=1237, powerup_counter=3),  # No PDI
            create_raw_adm1266_blackbox_record(uid=1238, powerup_counter=3),  # No PDI
        ]
        with (
            temp_file(content=b"".join(DPM_1_RECORDS)) as nvmem_path_1,
            temp_file(content=b"".join(DPM_2_RECORDS)) as nvmem_path_2,
            temp_file(content="") as rtc_epoch_offset_path_1,
            temp_file(content="") as rtc_epoch_offset_path_2,
            temp_file(content="12") as powerup_counter_path_1,
            temp_file(content="3") as powerup_counter_path_2,
        ):
            pddf_data = {
                "DPM1": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}},
                "DPM2": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x41"}}},
            }
            pddf_plugin_data = {
                "DPM": {
                    "test-dpm1": {
                        "type": "adm1266",
                        "dpm": "DPM1",
                        "dpm_signal_to_fault_cause": [
                            {
                                "pdio_mask": "0b0000_0000_0000_0001",  # PDI1
                                "gpio_mask": "0b0000_0000_0000_0000",
                                "pdio_value": "0b0000_0000_0000_0001",  # PDI1
                                "gpio_value": "0b0000_0000_0000_0000",
                                "hw_cause": "HW_CAUSE_OF_DPM1_PDI1",
                                "hw_desc": "HW_DESC_OF_DPM1_PDI1",
                                "reboot_cause": "REBOOT_CAUSE_OF_DPM1_PDI1",
                            }
                        ],
                    },
                    "test-dpm2": {
                        "type": "adm1266",
                        "dpm": "DPM2",
                        "dpm_signal_to_fault_cause": [
                            {
                                "pdio_mask": "0b0000_0000_0000_0001",  # PDI1
                                "gpio_mask": "0b0000_0000_0000_0000",
                                "pdio_value": "0b0000_0000_0000_0001",  # PDI1
                                "gpio_value": "0b0000_0000_0000_0000",
                                "hw_cause": "HW_CAUSE_OF_DPM2_PDI1",
                                "hw_desc": "HW_DESC_OF_DPM2_PDI1",
                                "reboot_cause": "REBOOT_CAUSE_OF_DPM2_PDI1",
                            },
                            {
                                "pdio_mask": "0b0000_0000_0000_0010",  # PDI2
                                "gpio_mask": "0b0000_0000_0000_0000",
                                "pdio_value": "0b0000_0000_0000_0010",  # PDI2
                                "gpio_value": "0b0000_0000_0000_0000",
                                "hw_cause": "HW_CAUSE_OF_DPM2_PDI2",
                                "hw_desc": "HW_DESC_OF_DPM2_PDI2",
                                "reboot_cause": "REBOOT_CAUSE_OF_DPM2_PDI2",
                            },
                        ],
                    },
                }
            }

            # When
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(
                pddf_data, pddf_plugin_data
            )
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm1":
                    dpm._nvmem_path = nvmem_path_1
                    dpm._powerup_counter_path = powerup_counter_path_1
                    dpm._rtc_epoch_offset_path = rtc_epoch_offset_path_1
                elif dpm.get_name() == "test-dpm2":
                    dpm._nvmem_path = nvmem_path_2
                    dpm._powerup_counter_path = powerup_counter_path_2
                    dpm._rtc_epoch_offset_path = rtc_epoch_offset_path_2
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm2",
                    timestamp=datetime.timedelta(seconds=70),
                    cause="HW_CAUSE_OF_DPM2_PDI1",
                    description="HW_DESC_OF_DPM2_PDI1",
                    chassis_reboot_cause_category="REBOOT_CAUSE_OF_DPM2_PDI1",
                ),
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm1",
                    timestamp=datetime.datetime(
                        2025, 10, 2, 23, 22, 56, tzinfo=datetime.timezone.utc
                    ),
                    cause="HW_CAUSE_OF_DPM1_PDI1",
                    description="HW_DESC_OF_DPM1_PDI1",
                    chassis_reboot_cause_category="REBOOT_CAUSE_OF_DPM1_PDI1",
                ),
            ]
            # Verify that the DPM records are also saved to history.
            mock_dpm_logger.DpmLogger().save.assert_called_once()
            args, _ = mock_dpm_logger.DpmLogger().save.call_args
            causes, dpm_to_reboot_causes = args
            assert isinstance(causes, list), "First param to DpmLogger.save() should be a list"
            assert isinstance(
                dpm_to_reboot_causes, dict
            ), "Second param to DpmLogger.save() should be a dict"
            records = []
            for rc_entries in dpm_to_reboot_causes.values():
                for rc_entry in rc_entries:
                    records.extend(rc_entry.dpm_records)
            assert {
                "uid": "1",
                "dpm_name": "test-dpm1",
                "powerup_counter": "10",
                "pdio_in_[16:1]": "0b0000000000000000",
            }.items() <= records[0].as_dict().items()
            assert {
                "uid": "2",
                "dpm_name": "test-dpm1",
                "powerup_counter": "11",
                "pdio_in_[16:1]": "0b0000000000000000",
            }.items() <= records[1].as_dict().items()
            assert {
                "timestamp": "2025-10-02 23:22:56 UTC",
                "uid": "3",
                "dpm_name": "test-dpm1",
                "powerup_counter": "11",
                "pdio_in_[16:1]": "0b0000000000000001 [PDI1]",
            }.items() <= records[2].as_dict().items()
            assert {
                "uid": "1234",
                "dpm_name": "test-dpm2",
                "powerup_counter": "1",
                "pdio_in_[16:1]": "0b0000000000000000",
            }.items() <= records[3].as_dict().items()
            assert {
                "timestamp": "70.000000s after power-on",
                "uid": "1235",
                "dpm_name": "test-dpm2",
                "powerup_counter": "1",
                "pdio_in_[16:1]": "0b0000000000000001 [PDI1]",
            }.items() <= records[4].as_dict().items()
            assert {
                "timestamp": "140.000000s after power-on",
                "uid": "1236",
                "dpm_name": "test-dpm2",
                "powerup_counter": "2",
                "pdio_in_[16:1]": "0b0000000000010010 [PDI5, PDI2]",
            }.items() <= records[5].as_dict().items()
            assert {
                "uid": "1237",
                "dpm_name": "test-dpm2",
                "powerup_counter": "3",
                "pdio_in_[16:1]": "0b0000000000000000",
            }.items() <= records[6].as_dict().items()
            assert {
                "uid": "1238",
                "dpm_name": "test-dpm2",
                "powerup_counter": "3",
                "pdio_in_[16:1]": "0b0000000000000000",
            }.items() <= records[7].as_dict().items()

    def test_summarize_reboot_causes_hw_unknown(self, reboot_cause_manager_module):
        # Given
        DPM_RECORDS = [
            create_raw_adm1266_blackbox_record(uid=1, powerup_counter=10),  # No PDI
            create_raw_adm1266_blackbox_record(uid=2, powerup_counter=11),  # No PDI
        ]
        with (
            temp_file(content=b"".join(DPM_RECORDS)) as nvmem_path,
            temp_file(content="12") as powerup_counter_path,
        ):
            pddf_plugin_data = {
                "DPM": {
                    "test-dpm": {
                        "type": "adm1266",
                        "dpm": "DPM",
                        "dpm_signal_to_fault_cause": [],
                    }
                }
            }

            # When
            pddf_data = {"DPM": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}}}
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(pddf_data, pddf_plugin_data)
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm":
                    dpm._nvmem_path = nvmem_path
                    dpm._powerup_counter_path = powerup_counter_path
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.UNKNOWN_HW_REBOOT_CAUSE,
                reboot_cause_manager_module.UNKNOWN_HW_REBOOT_CAUSE,
            ]

    def test_summarize_reboot_causes_hw_two_dpms_no_reboot(self, reboot_cause_manager_module):
        # Given
        DPM_1_RECORDS = []  # empty
        DPM_2_RECORDS = [
            create_raw_adm1266_blackbox_record(uid=1, powerup_counter=10)  # No PDI/faults
        ]
        with (
            temp_file(content=b"".join(DPM_1_RECORDS)) as nvmem_path_1,
            temp_file(content=b"".join(DPM_2_RECORDS)) as nvmem_path_2,
            temp_file(content="1") as powerup_counter_path_1,
            temp_file(content="10") as powerup_counter_path_2,
        ):
            pddf_plugin_data = {
                "DPM": {
                    "test-dpm1": {
                        "type": "adm1266",
                        "dpm": "DPM1",
                        "dpm_signal_to_fault_cause": [],
                    },
                    "test-dpm2": {
                        "type": "adm1266",
                        "dpm": "DPM2",
                        "dpm_signal_to_fault_cause": [],
                    },
                }
            }

            # When
            pddf_data = {
                "DPM1": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}},
                "DPM2": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x41"}}},
            }
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(pddf_data, pddf_plugin_data)
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm1":
                    dpm._nvmem_path = nvmem_path_1
                    dpm._powerup_counter_path = powerup_counter_path_1
                elif dpm.get_name() == "test-dpm2":
                    dpm._nvmem_path = nvmem_path_2
                    dpm._powerup_counter_path = powerup_counter_path_2
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == []

    def test_summarize_reboot_causes_sw_and_hw(self, reboot_cause_manager_module):
        # Given
        DPM_RECORDS = [
            create_raw_adm1266_blackbox_record(
                uid=555,
                powerup_counter=1,
                pdio_in=0b0000_0000_0100_0001,  # PDI7, PDI1
                timestamp=datetime.timedelta(seconds=70),
            ),
        ]
        FULL_SW_CAUSE = (
            "User issued 'reboot' command [User: admin, Time: Thu Oct  2 11:22:56 PM UTC 2025]"
        )
        with (
            temp_file(content=FULL_SW_CAUSE) as sw_reboot_cause_filepath,
            temp_file(content=b"".join(DPM_RECORDS)) as nvmem_path,
            temp_file(content="2") as powerup_counter_path,
        ):
            pddf_plugin_data = {
                "REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath},
                "DPM": {
                    "test-dpm": {
                        "type": "adm1266",
                        "dpm": "DPM",
                        "dpm_signal_to_fault_cause": [
                            {
                                "pdio_mask": "0b0000_0000_0100_0000",  # PDI7
                                "gpio_mask": "0b0000_0000_0000_0000",
                                "pdio_value": "0b0000_0000_0100_0000",  # PDI7
                                "gpio_value": "0b0000_0000_0000_0000",
                                "hw_cause": "HW_CAUSE_OF_PDI7",
                                "hw_desc": "HW_DESC_OF_PDI7",
                                "reboot_cause": "REBOOT_CAUSE_OF_PDI7",
                            },
                        ],
                    }
                },
            }
            # When
            pddf_data = {"DPM": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}}}
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(pddf_data, pddf_plugin_data)
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm":
                    dpm._nvmem_path = nvmem_path
                    dpm._powerup_counter_path = powerup_counter_path
                    if 'rtc_epoch_offset_path' in locals():
                        dpm._rtc_epoch_offset_path = rtc_epoch_offset_path
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                    source="SW",
                    timestamp=datetime.datetime(
                        2025, 10, 2, 23, 22, 56, tzinfo=datetime.timezone.utc
                    ),
                    cause="reboot",
                    description=FULL_SW_CAUSE,
                    chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
                ),
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm",
                    timestamp=datetime.timedelta(seconds=70),
                    cause="HW_CAUSE_OF_PDI7",
                    description="HW_DESC_OF_PDI7",
                    chassis_reboot_cause_category="REBOOT_CAUSE_OF_PDI7",
                ),
            ]

    def test_summarize_reboot_causes_sw_and_unknown_hw(self, reboot_cause_manager_module):
        # Given
        FULL_SW_CAUSE = "Kernel Panic [Time: Thu Oct  21 11:22:59 PM UTC 2025]"
        DPM_RECORDS = [
            create_raw_adm1266_blackbox_record(uid=555, powerup_counter=1),  # No PDI/faults
        ]
        with (
            temp_file(content=FULL_SW_CAUSE) as sw_reboot_cause_filepath,
            temp_file(content=b"".join(DPM_RECORDS)) as nvmem_path,
            temp_file(content="2") as powerup_counter_path,
        ):
            pddf_plugin_data = {
                "REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath},
                "DPM": {
                    "test-dpm": {
                        "type": "adm1266",
                        "dpm": "DPM",
                        "dpm_signal_to_fault_cause": [],
                    }
                },
            }
            # When
            pddf_data = {"DPM": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}}}
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(pddf_data, pddf_plugin_data)
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm":
                    dpm._nvmem_path = nvmem_path
                    dpm._powerup_counter_path = powerup_counter_path
                    if 'rtc_epoch_offset_path' in locals():
                        dpm._rtc_epoch_offset_path = rtc_epoch_offset_path
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                    source="SW",
                    timestamp=datetime.datetime(
                        2025, 10, 21, 23, 22, 59, tzinfo=datetime.timezone.utc
                    ),
                    cause="Kernel Panic",
                    description=FULL_SW_CAUSE,
                    chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
                ),
                reboot_cause_manager_module.UNKNOWN_HW_REBOOT_CAUSE,
            ]

    def test_fill_in_missing_and_align_powerups(self, reboot_cause_manager_module):
        # Given
        #   - max_powerup = 65535
        #   - DPM1: [65531, 1, 2];     current_powerup = 5
        #   - DPM2: [65534, 2, 5, 6];  current_powerup = 6
        #   - DPM3: [];                current_powerup = 1
        #   - Notes: powerup numbers of DPM1 and DPM2 are independent.
        # Should return:
        #   - 9 power cycles (as evidenced from DPM1)
        #   - DPM1: [65531, None, None, None, None, 1, 2, None, None]
        #   - DPM2: [None, None, 65534, None, None, 2, None, None, 5]
        #   - DPM3: [None, None, None, None, None, None, None, None, None]
        dpm_1 = create_autospec(reboot_cause_manager_module.DpmBase)
        dpm_2 = create_autospec(reboot_cause_manager_module.DpmBase)
        dpm_3 = create_autospec(reboot_cause_manager_module.DpmBase)
        dpm_1.max_powerup_counter.return_value = 65535
        dpm_2.max_powerup_counter.return_value = 65535
        dpm_3.max_powerup_counter.return_value = 65535
        dpm_1.get_powerup_counter.return_value = 5
        dpm_2.get_powerup_counter.return_value = 6
        dpm_3.get_powerup_counter.return_value = 1

        DPM_1_POWERUPS = [
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=65531,
                power_fault_cause=None,
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=1,
                power_fault_cause=None,
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=2,
                power_fault_cause=None,
                dpm_records=[],
            ),
        ]
        DPM_2_POWERUPS = [
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=65534,
                power_fault_cause=None,
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=2,
                power_fault_cause=None,
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=5,
                power_fault_cause=None,
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=6,
                power_fault_cause=None,
                dpm_records=[],
            ),
        ]
        DPM_3_POWERUPS = []
        dpm_to_powerups = {
            dpm_1: DPM_1_POWERUPS,
            dpm_2: DPM_2_POWERUPS,
            dpm_3: DPM_3_POWERUPS,
        }

        # When
        result, num_power_cycles = reboot_cause_manager_module.fill_in_missing_and_align_powerups(
            dpm_to_powerups
        )

        # Then
        assert num_power_cycles == 9
        assert result == {
            dpm_1: [
                DPM_1_POWERUPS[0],  # 65531
                None,  # 65532
                None,  # 65533
                None,  # 65534
                None,  # 65535
                DPM_1_POWERUPS[1],  # 1
                DPM_1_POWERUPS[2],  # 2
                None,  # 3
                None,  # 4
            ],
            dpm_2: [
                None,  # 65532
                None,  # 65533
                DPM_2_POWERUPS[0],  # 65534
                None,  # 65535
                None,  # 1
                DPM_2_POWERUPS[1],  # 2
                None,  # 3
                None,  # 4
                DPM_2_POWERUPS[2],  # 5
            ],
            dpm_3: [
                None,  # 65527
                None,  # 65528
                None,  # 65529
                None,  # 65530
                None,  # 65531
                None,  # 65532
                None,  # 65533
                None,  # 65534
                None,  # 65535
            ],
        }

    def test_fill_in_missing_and_align_powerups_and_squash_dpm_powerups(
        self, reboot_cause_manager_module
    ):
        # Given
        #   - max_powerup = 65535
        #   - DPM1: [65533, 65534, 65535, 1, 2]; current_powerup = 3
        #   - DPM2: [6, 8];                      current_powerup = 10
        # Which means:
        #   - DPM1: [FAULT (p=65533), unknown (p=65534), FAULT (p=65535), unknown (p=1), FAULT (p=2)]
        #   - DPM2: [unknown (p=5),   FAULT (p=6),       unknown (p=7),   FAULT   (p=8), unknown (p=9)]
        dpm_1 = create_autospec(reboot_cause_manager_module.DpmBase)
        dpm_2 = create_autospec(reboot_cause_manager_module.DpmBase)
        dpm_1.max_powerup_counter.return_value = 65535
        dpm_2.max_powerup_counter.return_value = 65535
        dpm_1.get_powerup_counter.return_value = 3
        dpm_2.get_powerup_counter.return_value = 10

        DPM_1_POWERUPS = [
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=65533,
                power_fault_cause=reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm-1",
                    timestamp=datetime.datetime(2025, 10, 1, 2, 3, 4, tzinfo=datetime.timezone.utc),
                    cause="HW_CAUSE_DPM1_P65533",
                    description="HW_DESC_DPM1_P65533",
                    chassis_reboot_cause_category="REBOOT_CAUSE_DPM1_P65533",
                ),
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=65534,
                power_fault_cause=None,
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=65535,
                power_fault_cause=reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm-1",
                    timestamp=datetime.datetime(2025, 10, 1, 4, 5, 6, tzinfo=datetime.timezone.utc),
                    cause="HW_CAUSE_DPM1_P65535",
                    description="HW_DESC_DPM1_P65535",
                    chassis_reboot_cause_category="REBOOT_CAUSE_DPM1_P65535",
                ),
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=1,
                power_fault_cause=None,
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=2,
                power_fault_cause=reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm-1",
                    timestamp=datetime.datetime(2025, 10, 1, 7, 8, 9, tzinfo=datetime.timezone.utc),
                    cause="HW_CAUSE_DPM1_P2",
                    description="HW_DESC_DPM1_P2",
                    chassis_reboot_cause_category="REBOOT_CAUSE_DPM1_P2",
                ),
                dpm_records=[],
            ),
        ]
        DPM_2_POWERUPS = [
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=6,
                power_fault_cause=reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm-1",
                    timestamp=datetime.datetime(2025, 10, 1, 3, 4, 5, tzinfo=datetime.timezone.utc),
                    cause="HW_CAUSE_DPM2_P6",
                    description="HW_DESC_DPM2_P6",
                    chassis_reboot_cause_category="REBOOT_CAUSE_DPM2_P6",
                ),
                dpm_records=[],
            ),
            reboot_cause_manager_module.DpmPowerUpEntry(
                powerup_counter=8,
                power_fault_cause=reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm-1",
                    timestamp=datetime.datetime(2025, 10, 1, 5, 6, 7, tzinfo=datetime.timezone.utc),
                    cause="HW_CAUSE_DPM2_P8",
                    description="HW_DESC_DPM2_P8",
                    chassis_reboot_cause_category="REBOOT_CAUSE_DPM2_P8",
                ),
                dpm_records=[],
            ),
        ]
        dpm_to_powerups = {
            dpm_1: DPM_1_POWERUPS,
            dpm_2: DPM_2_POWERUPS,
        }

        # When
        result, num_power_cycles = reboot_cause_manager_module.fill_in_missing_and_align_powerups(
            dpm_to_powerups
        )

        # Then
        assert num_power_cycles == 5
        assert result == {
            dpm_1: [
                DPM_1_POWERUPS[0],
                DPM_1_POWERUPS[1],
                DPM_1_POWERUPS[2],
                DPM_1_POWERUPS[3],
                DPM_1_POWERUPS[4],
            ],
            dpm_2: [
                None,
                DPM_2_POWERUPS[0],
                None,
                DPM_2_POWERUPS[1],
                None,
            ],
        }

        # And When
        causes = reboot_cause_manager_module.squash_dpms_powerups_to_cause_per_reboot(
            dpm_to_powerups
        )

        # Then
        assert causes == [
            DPM_1_POWERUPS[0].power_fault_cause,
            DPM_2_POWERUPS[0].power_fault_cause,
            DPM_1_POWERUPS[2].power_fault_cause,
            DPM_2_POWERUPS[1].power_fault_cause,
            DPM_1_POWERUPS[4].power_fault_cause,
        ]

    def test_merge_sw_and_hw_causes(self, reboot_cause_manager_module):
        # Given
        DPM_RECORDS = [
            create_raw_adm1266_blackbox_record(
                uid=555,
                powerup_counter=1,
                pdio_in=0b0000_0000_0100_0001,  # PDI7, PDI1
                timestamp=datetime.datetime(2025, 10, 2, 9, 10, 11, tzinfo=datetime.timezone.utc),
            ),
            create_raw_adm1266_blackbox_record(
                uid=556,
                powerup_counter=2,
                pdio_in=0b0000_0000_0100_0000,  # PDI7
                timestamp=datetime.datetime(2025, 10, 3, 9, 10, 11, tzinfo=datetime.timezone.utc),
            ),
        ]
        FULL_SW_CAUSE = (
            "User issued 'reboot' command [User: admin, Time: Thu Oct  2 11:22:56 PM UTC 2025]"
        )
        with (
            temp_file(content=FULL_SW_CAUSE) as sw_reboot_cause_filepath,
            temp_file(content=b"".join(DPM_RECORDS)) as nvmem_path,
            temp_file(content="") as rtc_epoch_offset_path,
            temp_file(content="3") as powerup_counter_path,
        ):
            pddf_plugin_data = {
                "REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath},
                "DPM": {
                    "test-dpm": {
                        "type": "adm1266",
                        "dpm": "DPM",
                        "dpm_signal_to_fault_cause": [
                            {
                                "pdio_mask": "0b0000_0000_0100_0000",  # PDI7
                                "gpio_mask": "0b0000_0000_0000_0000",
                                "pdio_value": "0b0000_0000_0100_0000",  # PDI7
                                "gpio_value": "0b0000_0000_0000_0000",
                                "hw_cause": "HW_CAUSE_OF_PDI7",
                                "hw_desc": "HW_DESC_OF_PDI7",
                                "reboot_cause": "REBOOT_CAUSE_OF_PDI7",
                            },
                        ],
                    }
                },
            }
            # When
            pddf_data = {"DPM": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}}}
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(pddf_data, pddf_plugin_data)
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm":
                    dpm._nvmem_path = nvmem_path
                    dpm._powerup_counter_path = powerup_counter_path
                    if 'rtc_epoch_offset_path' in locals():
                        dpm._rtc_epoch_offset_path = rtc_epoch_offset_path
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm",
                    timestamp=datetime.datetime(
                        2025, 10, 2, 9, 10, 11, tzinfo=datetime.timezone.utc
                    ),
                    cause="HW_CAUSE_OF_PDI7",
                    description="HW_DESC_OF_PDI7",
                    chassis_reboot_cause_category="REBOOT_CAUSE_OF_PDI7",
                ),
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                    source="SW",
                    timestamp=datetime.datetime(
                        2025, 10, 2, 23, 22, 56, tzinfo=datetime.timezone.utc
                    ),
                    cause="reboot",
                    description=FULL_SW_CAUSE,
                    chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
                ),
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm",
                    timestamp=datetime.datetime(
                        2025, 10, 3, 9, 10, 11, tzinfo=datetime.timezone.utc
                    ),
                    cause="HW_CAUSE_OF_PDI7",
                    description="HW_DESC_OF_PDI7",
                    chassis_reboot_cause_category="REBOOT_CAUSE_OF_PDI7",
                ),
            ]

    def test_squash_sw_and_hw_causes(self, reboot_cause_manager_module):
        # Given
        FULL_SW_CAUSE = (
            "User issued 'reboot' command [User: admin, Time: Thu Oct  2 11:22:56 PM UTC 2025]"
        )
        DPM_RECORDS = [
            create_raw_adm1266_blackbox_record(
                uid=555,
                powerup_counter=1,
                pdio_in=0b0000_0001_0000_0000,  # PDI9
                timestamp=datetime.datetime(
                    2025, 10, 2, 23, 24, 56, tzinfo=datetime.timezone.utc  # 2 mins after SW reboot
                ),
            ),
        ]
        with (
            temp_file(content=FULL_SW_CAUSE) as sw_reboot_cause_filepath,
            temp_file(content=b"".join(DPM_RECORDS)) as nvmem_path,
            temp_file(content="") as rtc_epoch_offset_path,
            temp_file(content="2") as powerup_counter_path,
        ):
            pddf_plugin_data = {
                "REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath},
                "DPM": {
                    "test-dpm": {
                        "type": "adm1266",
                        "dpm": "DPM",
                        "dpm_signal_to_fault_cause": [
                            {
                                "pdio_mask": "0b0000_0001_0000_0000",  # PDI9
                                "gpio_mask": "0b0000_0000_0000_0000",
                                "pdio_value": "0b0000_0001_0000_0000",  # PDI9
                                "gpio_value": "0b0000_0000_0000_0000",
                                "hw_cause": "CPU_CMD_PCYC",
                                "hw_desc": "CPU card commanded power cycle",
                                "reboot_cause": "REBOOT_CAUSE_POWER_LOSS",
                            },
                        ],
                    }
                },
            }
            # When
            pddf_data = {"DPM": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}}}
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(pddf_data, pddf_plugin_data)
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm":
                    dpm._nvmem_path = nvmem_path
                    dpm._powerup_counter_path = powerup_counter_path
                    if 'rtc_epoch_offset_path' in locals():
                        dpm._rtc_epoch_offset_path = rtc_epoch_offset_path
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                    source="SW",
                    timestamp=datetime.datetime(
                        2025, 10, 2, 23, 22, 56, tzinfo=datetime.timezone.utc
                    ),
                    cause="reboot",
                    description=FULL_SW_CAUSE,
                    chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
                ),
            ]

    def test_squash_sw_and_hw_causes_kernel_panic(self, reboot_cause_manager_module):
        # Given
        FULL_SW_CAUSE = (
            "Kernel Panic - Out of memory [Time: Thu Oct  21 11:22:59 PM UTC 2025]"
        )
        DPM_RECORDS = [
            create_raw_adm1266_blackbox_record(
                uid=555,
                powerup_counter=1,
                pdio_in=0b0000_0001_0000_0000,  # PDI9
                timestamp=datetime.datetime(
                    2025, 10, 21, 23, 23, 9, tzinfo=datetime.timezone.utc  # 10 seconds after Kernel Panic
                ),
            ),
        ]
        with (
            temp_file(content=FULL_SW_CAUSE) as sw_reboot_cause_filepath,
            temp_file(content=b"".join(DPM_RECORDS)) as nvmem_path,
            temp_file(content="") as rtc_epoch_offset_path,
            temp_file(content="2") as powerup_counter_path,
        ):
            pddf_plugin_data = {
                "REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath},
                "DPM": {
                    "test-dpm": {
                        "type": "adm1266",
                        "dpm": "DPM",
                        "dpm_signal_to_fault_cause": [
                            {
                                "pdio_mask": "0b0000_0001_0000_0000",  # PDI9
                                "gpio_mask": "0b0000_0000_0000_0000",
                                "pdio_value": "0b0000_0001_0000_0000",  # PDI9
                                "gpio_value": "0b0000_0000_0000_0000",
                                "hw_cause": "CPU_CMD_PCYC",
                                "hw_desc": "CPU card commanded power cycle",
                                "reboot_cause": "REBOOT_CAUSE_POWER_LOSS",
                            },
                        ],
                    }
                },
            }
            # When
            pddf_data = {"DPM": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}}}
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(pddf_data, pddf_plugin_data)
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm":
                    dpm._nvmem_path = nvmem_path
                    dpm._powerup_counter_path = powerup_counter_path
                    if 'rtc_epoch_offset_path' in locals():
                        dpm._rtc_epoch_offset_path = rtc_epoch_offset_path
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                    source="SW",
                    timestamp=datetime.datetime(
                        2025, 10, 21, 23, 22, 59, tzinfo=datetime.timezone.utc
                    ),
                    cause="Kernel Panic - Out of memory",
                    description=FULL_SW_CAUSE,
                    chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
                ),
            ]

    def test_squash_sw_and_hw_causes_longer_than_3m_10s(self, reboot_cause_manager_module):
        # Given
        FULL_SW_CAUSE = (
            "User issued 'reboot' command [User: admin, Time: Thu Oct  2 11:22:56 PM UTC 2025]"
        )
        DPM_RECORDS = [
            create_raw_adm1266_blackbox_record(
                uid=555,
                powerup_counter=1,
                pdio_in=0b0000_0001_0000_0000,  # PDI9
                timestamp=datetime.datetime(
                    2025, 10, 2, 23, 26, 7, tzinfo=datetime.timezone.utc  # 3 mins 11s after SW reboot
                ),
            ),
        ]
        with (
            temp_file(content=FULL_SW_CAUSE) as sw_reboot_cause_filepath,
            temp_file(content=b"".join(DPM_RECORDS)) as nvmem_path,
            temp_file(content="") as rtc_epoch_offset_path,
            temp_file(content="2") as powerup_counter_path,
        ):
            pddf_plugin_data = {
                "REBOOT_CAUSE": {"reboot_cause_file": sw_reboot_cause_filepath},
                "DPM": {
                    "test-dpm": {
                        "type": "adm1266",
                        "dpm": "DPM",
                        "dpm_signal_to_fault_cause": [
                            {
                                "pdio_mask": "0b0000_0001_0000_0000",  # PDI9
                                "gpio_mask": "0b0000_0000_0000_0000",
                                "pdio_value": "0b0000_0001_0000_0000",  # PDI9
                                "gpio_value": "0b0000_0000_0000_0000",
                                "hw_cause": "CPU_CMD_PCYC",
                                "hw_desc": "CPU card commanded power cycle",
                                "reboot_cause": "REBOOT_CAUSE_POWER_LOSS",
                            },
                        ],
                    }
                },
            }
            # When
            pddf_data = {"DPM": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40"}}}}
            reboot_cause_manager = reboot_cause_manager_module.RebootCauseManager(pddf_data, pddf_plugin_data)
            # Override the calculated paths with our temp files for testing
            for dpm in reboot_cause_manager._dpm_devices:
                if dpm.get_name() == "test-dpm":
                    dpm._nvmem_path = nvmem_path
                    dpm._powerup_counter_path = powerup_counter_path
                    if 'rtc_epoch_offset_path' in locals():
                        dpm._rtc_epoch_offset_path = rtc_epoch_offset_path
            reboot_causes = reboot_cause_manager.summarize_reboot_causes()

            # Then
            assert reboot_causes == [
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.SOFTWARE,
                    source="SW",
                    timestamp=datetime.datetime(
                        2025, 10, 2, 23, 22, 56, tzinfo=datetime.timezone.utc
                    ),
                    cause="reboot",
                    description=FULL_SW_CAUSE,
                    chassis_reboot_cause_category="REBOOT_CAUSE_NON_HARDWARE",
                ),
                reboot_cause_manager_module.RebootCause(
                    type=reboot_cause_manager_module.RebootCause.Type.HARDWARE,
                    source="test-dpm",
                    timestamp=datetime.datetime(
                        2025, 10, 2, 23, 26, 7, tzinfo=datetime.timezone.utc
                    ),
                    cause="CPU_CMD_PCYC",
                    description="CPU card commanded power cycle",
                    chassis_reboot_cause_category="REBOOT_CAUSE_POWER_LOSS",
                ),
            ]
<<<<<<< HEAD
=======


@pytest.mark.parametrize(
    "powerup, current, last_processed, expected",
    [
        (10, 12, 11, False),
        (11, 12, 11, True),
        (12, 12, 11, True),
        (13, 12, 11, False),
        (11, 11, 11, True),
        (65534, 2, 65533, True),
        (1, 2, 65533, True),
        (65532, 2, 65533, False),
    ],
)
def test_is_unprocessed_powerup(reboot_cause_manager_module, powerup, current, last_processed, expected):
    assert reboot_cause_manager_module.is_unprocessed_powerup(powerup, current, last_processed, 65535) is expected


class TestRebootCauseManagerDpmBlackboxLog:
    """DPM records reach reboot-cause processing only through the 'dpm' blackbox log."""

    PDDF_DATA: ClassVar[dict] = {
        "DPM1": {"i2c": {"topo_info": {"parent_bus": "0x0", "dev_addr": "0x40", "dev_type": "adm1266"}}},
        "PLATFORM": {"num_dpms": 1},
    }
    PLUGIN_DATA: ClassVar[dict] = {
        "DPM": {
            "test-dpm": {
                "type": "adm1266",
                "dpm": "DPM1",
                "dpm_signal_to_fault_cause": [
                    {
                        "pdio_mask": "0x0001",
                        "gpio_mask": "0x0000",
                        "pdio_value": "0x0001",
                        "gpio_value": "0x0000",
                        "hw_cause": "PSU_VIN_LOSS",
                        "hw_desc": "Both PSUs lost input power",
                        "reboot_cause": "REBOOT_CAUSE_POWER_LOSS",
                    }
                ],
            }
        }
    }

    @staticmethod
    def _power_loss(uid, powerup_counter):
        return create_raw_adm1266_blackbox_record(uid=uid, powerup_counter=powerup_counter, pdio_in=0b1)

    @pytest.fixture
    def dpm_files(self, tmp_path):
        """Writable stand-ins for the DPM's nvmem, powerup counter and clear knob."""
        paths = {name: tmp_path / name for name in ("nvmem", "powerup_counter", "clear_blackbox")}
        paths["nvmem"].write_bytes(b"")
        paths["clear_blackbox"].write_text("")
        return paths

    def _manager(self, make_reboot_cause_manager, dpm_files, nvmem: bytes, powerup_counter: int):
        dpm_files["nvmem"].write_bytes(nvmem)
        dpm_files["powerup_counter"].write_text(str(powerup_counter))
        manager = make_reboot_cause_manager(mock_pddf_data(self.PDDF_DATA), self.PLUGIN_DATA)
        [dpm] = manager._dpm_devices
        dpm._nvmem_path = str(dpm_files["nvmem"])
        dpm._powerup_counter_path = str(dpm_files["powerup_counter"])
        dpm._clear_blackbox_path = str(dpm_files["clear_blackbox"])
        return manager

    def test_summarize_collects_dpm_records_into_log_and_clears_dpm(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        record = self._power_loss(uid=1, powerup_counter=10)
        manager = self._manager(make_reboot_cause_manager, dpm_files, record, powerup_counter=11)

        [cause] = manager.summarize_reboot_causes()

        assert cause.cause == "PSU_VIN_LOSS"
        assert dpm_files["clear_blackbox"].read_text() == "1"
        assert manager._blackbox_manager.logged_records("dpm") == {"test-dpm:adm1266": [record.hex()]}

    def test_summarize_reads_powerup_counters_before_clearing_the_dpm(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        manager = self._manager(make_reboot_cause_manager, dpm_files, self._power_loss(uid=1, powerup_counter=10), 11)
        [dpm] = manager._dpm_devices
        clear_blackbox = dpm.clear_blackbox

        def clear_then_report_invalid_counter():
            # A DPM reads an invalid powerup counter while its blackbox clears.
            clear_blackbox()
            dpm_files["powerup_counter"].write_text("65535")

        dpm.clear_blackbox = clear_then_report_invalid_counter

        assert [c.cause for c in manager.summarize_reboot_causes()] == ["PSU_VIN_LOSS"]
        with open(manager._processed_powerups_path) as file:
            assert json.load(file)["powerups"] == {"test-dpm": 11}

    def test_summarize_reads_records_the_poll_already_collected(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        first = self._manager(make_reboot_cause_manager, dpm_files, b"", powerup_counter=10)
        assert first.summarize_reboot_causes() == []
        # The poll moved the power-loss record into the log before this boot's processing.
        record = self._power_loss(uid=1, powerup_counter=10)
        first._blackbox_manager.write_blackbox_log("dpm", {"test-dpm:adm1266": [record.hex()]})

        second = self._manager(make_reboot_cause_manager, dpm_files, b"", powerup_counter=11)
        [cause] = second.summarize_reboot_causes()

        assert cause.cause == "PSU_VIN_LOSS"

    def test_summarize_skips_powerups_processed_at_an_earlier_boot(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        first = self._manager(make_reboot_cause_manager, dpm_files, self._power_loss(uid=1, powerup_counter=10), 11)
        assert [c.cause for c in first.summarize_reboot_causes()] == ["PSU_VIN_LOSS"]

        # Next boot: the earlier record is still in the log; the new one is on the DPM.
        second = self._manager(make_reboot_cause_manager, dpm_files, self._power_loss(uid=2, powerup_counter=11), 12)
        [cause] = second.summarize_reboot_causes()

        assert cause.cause == "PSU_VIN_LOSS"
        third = self._manager(make_reboot_cause_manager, dpm_files, b"", 12)
        assert third.summarize_reboot_causes() == []

    def test_summarize_keeps_the_processed_powerup_of_a_dpm_that_fails_to_read(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        first = self._manager(make_reboot_cause_manager, dpm_files, b"", powerup_counter=10)
        first.summarize_reboot_causes()

        second = self._manager(make_reboot_cause_manager, dpm_files, self._power_loss(uid=1, powerup_counter=10), 11)
        [dpm] = second._dpm_devices
        with patch.object(dpm, "get_blackbox_raw", side_effect=OSError(errno.EIO, "Input/output error")):
            assert second.summarize_reboot_causes() == []
        with open(second._processed_powerups_path) as file:
            assert json.load(file)["powerups"] == {"test-dpm": 10}

        third = self._manager(make_reboot_cause_manager, dpm_files, self._power_loss(uid=1, powerup_counter=10), 12)
        assert [c.cause for c in third.summarize_reboot_causes()] == ["PSU_VIN_LOSS", "unknown"]

    def test_summarize_ignores_logged_records_after_another_image_processed_reboots(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        first = self._manager(make_reboot_cause_manager, dpm_files, b"", powerup_counter=10)
        first.summarize_reboot_causes()
        first._blackbox_manager.write_blackbox_log(
            "dpm", {"test-dpm:adm1266": [self._power_loss(uid=1, powerup_counter=10).hex()]}
        )
        # An image without this manager then processed (and cleared) powerup 10's reboot.
        first.blackbox_logger.save_data({"gen_time": "another image", "schema_version": 1, "causes": [], "devices": []})

        second = self._manager(make_reboot_cause_manager, dpm_files, b"", powerup_counter=12)

        assert second.summarize_reboot_causes() == []

    def test_summarize_ignores_logged_records_without_processing_state(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        manager = self._manager(make_reboot_cause_manager, dpm_files, b"", powerup_counter=11)
        manager._blackbox_manager.write_blackbox_log(
            "dpm", {"test-dpm:adm1266": [self._power_loss(uid=1, powerup_counter=10).hex()]}
        )

        assert manager.summarize_reboot_causes() == []

    def test_summarize_ignores_logged_records_when_powerup_counter_jumped(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        first = self._manager(make_reboot_cause_manager, dpm_files, b"", powerup_counter=10)
        first.summarize_reboot_causes()
        first._blackbox_manager.write_blackbox_log(
            "dpm", {"test-dpm:adm1266": [self._power_loss(uid=1, powerup_counter=10).hex()]}
        )

        # e.g. a replaced DPM, whose counter is unrelated to the saved one.
        second = self._manager(make_reboot_cause_manager, dpm_files, b"", powerup_counter=5)

        assert second.summarize_reboot_causes() == []

    def test_read_hw_reboot_causes_changes_no_state(
        self, reboot_cause_manager_module, make_reboot_cause_manager, dpm_files
    ):
        record = self._power_loss(uid=1, powerup_counter=10)
        manager = self._manager(make_reboot_cause_manager, dpm_files, record, powerup_counter=11)

        [cause], _ = manager.read_hw_reboot_causes()

        assert cause.cause == "PSU_VIN_LOSS"
        assert dpm_files["clear_blackbox"].read_text() == ""
        assert manager._blackbox_manager.logged_records("dpm") == {}
        assert not os.path.exists(manager._processed_powerups_path)


class TestAmdResetReason:
    WATCHDOG_LINE = "[    0.123] x86/amd: Previous system reset reason [0x02000800]: hardware watchdog timer expired\n"
    SHUTDOWN_LINE = "[    0.123] x86/amd: Previous system reset reason [0x00080000]: internal CPU shutdown event occurred\n"

    @pytest.fixture
    def rcm(self, mock_save_data, tmp_path, monkeypatch):
        from sonic_platform import (
            adm1266,  # noqa: F401
            reboot_cause_manager,
        )

        monkeypatch.setattr(reboot_cause_manager, "REBOOT_CAUSE_HISTORY_DIR", str(tmp_path / "reboot-cause"))
        return reboot_cause_manager

    def _dmesg(self, rcm, monkeypatch, out):
        monkeypatch.setattr(rcm.subprocess, "run", lambda *a, **kw: MagicMock(stdout=out))

    def test_watchdog_line_maps_to_a_watchdog_cause(self, rcm, monkeypatch):
        self._dmesg(rcm, monkeypatch, "noise\n" + self.WATCHDOG_LINE)
        cause = rcm.read_amd_reset_reason()
        assert cause is not None
        assert (cause.cause, cause.source, cause.chassis_reboot_cause_category) == (
            "Watchdog",
            "cpu",
            "REBOOT_CAUSE_WATCHDOG",
        )
        assert "0x02000800" in cause.description

    def test_unmapped_reason_is_a_hardware_other_cause(self, rcm, monkeypatch):
        self._dmesg(rcm, monkeypatch, self.SHUTDOWN_LINE)
        cause = rcm.read_amd_reset_reason()
        assert cause is not None
        assert (cause.cause, cause.source, cause.chassis_reboot_cause_category) == (
            "internal CPU shutdown event occurred",
            "cpu",
            "REBOOT_CAUSE_HARDWARE_OTHER",
        )
        assert cause.description == "CPU reset register reason 0x00080000: internal CPU shutdown event occurred"

    def test_every_line_of_the_reset_is_read_thermal_first(self, rcm, monkeypatch):
        self._dmesg(
            rcm,
            monkeypatch,
            "x86/amd: Previous system reset reason [0x00080200]: internal CPU thermal limit was tripped\n"
            "x86/amd: Previous system reset reason [0x00080200]: software wrote 0x6 to reset control register 0xCF9\n",
        )
        cause = rcm.read_amd_reset_reason()
        assert cause is not None
        assert (cause.cause, cause.chassis_reboot_cause_category) == ("Thermal", "REBOOT_CAUSE_THERMAL_OVERLOAD_OTHER")
        assert cause.description == (
            "CPU reset register reason 0x00080200: internal CPU thermal limit was tripped; "
            "software wrote 0x6 to reset control register 0xCF9"
        )

    def test_missing_reason_is_none(self, rcm, monkeypatch):
        self._dmesg(rcm, monkeypatch, "nothing to see\n")
        assert rcm.read_amd_reset_reason() is None

    def test_dmesg_failure_is_none(self, rcm, monkeypatch):
        def boom(*a, **kw):
            raise OSError("no dmesg")

        monkeypatch.setattr(rcm.subprocess, "run", boom)
        assert rcm.read_amd_reset_reason() is None

    def test_summarize_reports_the_amd_cause_when_no_dpm_recorded_one(self, rcm, monkeypatch, tmp_path):
        from sonic_platform.blackbox_manager import BlackBoxManager

        self._dmesg(rcm, monkeypatch, self.WATCHDOG_LINE)
        sw_file = tmp_path / "reboot-cause.txt"
        sw_file.write_text("Unknown")
        manager = rcm.RebootCauseManager(
            mock_pddf_data({}),
            {"REBOOT_CAUSE": {"reboot_cause_file": str(sw_file)}},
            [],
            BlackBoxManager(),
        )
        causes = manager.summarize_reboot_causes()
        assert [c.cause for c in causes] == ["Watchdog"]

    @pytest.mark.parametrize(
        "reason",
        [
            "software wrote 0x6 to reset control register 0xCF9",
            "software issued PCI reset",
            "ACPI power state transition occurred",
        ],
    )
    def test_a_software_only_reset_is_none(self, rcm, monkeypatch, reason):
        self._dmesg(rcm, monkeypatch, f"x86/amd: Previous system reset reason [0x00080800]: {reason}\n")
        assert rcm.read_amd_reset_reason() is None

    def test_summarize_reports_an_unmapped_hardware_reason_when_no_dpm_recorded_one(self, rcm, monkeypatch, tmp_path):
        from sonic_platform.blackbox_manager import BlackBoxManager

        self._dmesg(
            rcm,
            monkeypatch,
            "x86/amd: Previous system reset reason [0x08000800]: "
            "an uncorrected error caused a data fabric sync flood event\n",
        )
        sw_file = tmp_path / "reboot-cause.txt"
        sw_file.write_text("Unknown")
        manager = rcm.RebootCauseManager(
            mock_pddf_data({}),
            {"REBOOT_CAUSE": {"reboot_cause_file": str(sw_file)}},
            [],
            BlackBoxManager(),
        )
        hw = [c for c in manager.summarize_reboot_causes() if c.source == "cpu"]
        assert [(c.cause, c.chassis_reboot_cause_category) for c in hw] == [
            ("an uncorrected error caused a data fabric sync flood event", "REBOOT_CAUSE_HARDWARE_OTHER")
        ]

    @pytest.mark.parametrize("latest_known", [False, True])
    def test_summarize_names_only_the_latest_dpm_cause_when_unknown(
        self, rcm, monkeypatch, tmp_path, latest_known
    ):
        from dataclasses import replace
        from datetime import UTC, datetime

        from sonic_platform.blackbox_manager import BlackBoxManager

        self._dmesg(rcm, monkeypatch, self.SHUTDOWN_LINE)
        older = replace(rcm.UNKNOWN_HW_REBOOT_CAUSE, timestamp=datetime(2026, 10, 29, 11, tzinfo=UTC))
        latest = replace(
            rcm.UNKNOWN_HW_REBOOT_CAUSE,
            timestamp=datetime(2026, 10, 29, 12, tzinfo=UTC),
            cause="Power Loss" if latest_known else "unknown",
            chassis_reboot_cause_category="REBOOT_CAUSE_POWER_LOSS" if latest_known else "REBOOT_CAUSE_HARDWARE_OTHER",
        )
        monkeypatch.setattr(rcm, "squash_dpms_powerups_to_cause_per_reboot", lambda _: [older, latest])
        sw_file = tmp_path / "reboot-cause.txt"
        sw_file.write_text("Unknown")
        manager = rcm.RebootCauseManager(
            mock_pddf_data({}),
            {"REBOOT_CAUSE": {"reboot_cause_file": str(sw_file)}},
            [],
            BlackBoxManager(),
        )
        causes = manager.summarize_reboot_causes()
        assert [(c.cause, c.timestamp) for c in causes if c.type == rcm.RebootCause.Type.HARDWARE] == [
            ("unknown", datetime(2026, 10, 29, 11, tzinfo=UTC)),
            (
                "Power Loss" if latest_known else "internal CPU shutdown event occurred",
                datetime(2026, 10, 29, 12, tzinfo=UTC),
            ),
        ]
>>>>>>> cb4aa24c5 (NOS-21526: [platform] Fall back to the AMD FCH reset reason for unexplained hardware reboots (#12072))
