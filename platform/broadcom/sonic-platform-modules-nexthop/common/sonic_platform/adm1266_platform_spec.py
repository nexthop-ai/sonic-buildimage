# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""ADM1266 platform-specific configuration and mappings.

Provides platform-specific data for ADM1266 devices including power rail
mappings, fault tables, signal definitions, and device paths.
"""

from typing import Any, Dict


class Adm1266PlatformSpec:
    """Platform-specific configuration for an ADM1266 device.

    Encapsulates platform-specific data including:
        - Power rail to PDIO mappings for voltage monitoring
        - DPM fault signal definitions and lookup tables
        - Power fault cause descriptions and reboot cause mappings
        - NVMEM device path for blackbox data access

    Attributes:
        name: Device name identifier
        nvmem_path: Path to NVMEM device for blackbox data
        vp_to_pdio_desc: VP (voltage positive) to PDIO mappings
        vh_to_pdio_desc: VH (voltage high) to PDIO mappings
        dpm_signals: DPM signal bit position mappings
        dpm_table: DPM fault code to description lookup
        pdio_input_to_fault_cause: PDIO input to fault cause mappings
    """

    def __init__(self, name: str, pddf_plugin_data: Dict[str, Any]):
        """Initialize platform specification from PDDF plugin data.

        Args:
            name: Device name identifier
            pddf_plugin_data: PDDF plugin data dictionary containing DPM configuration
        """
        self.name = name
        dpm_info = pddf_plugin_data["DPM"][name]
        self.nvmem_path = dpm_info["nvmem_path"]

        self.vpx_to_rail_desc: Dict[int, str] = {
            int(k): v for k, v in dpm_info["vpx_to_rail_desc"].items()
        }
        self.vhx_to_rail_desc: Dict[int, str] = {
            int(k): v for k, v in dpm_info["vhx_to_rail_desc"].items()
        }
        self.dpm_signals: Dict[int, int] = {
            int(k): v for k, v in dpm_info["dpm_signals"].items()
        }
        self.dpm_table: Dict[int, str] = {
            int(k): v for k, v in dpm_info["dpm_table"].items()
        }
        self.pdio_input_to_fault_cause: Dict[int, Dict[str, str]] = {
            int(k): v for k, v in dpm_info["pdio_input_to_fault_cause"].items()
        }

    def get_vpx_to_rail_desc(self) -> Dict[int, str]:
        """Get VP (voltage positive) to rail descriptions.

        Returns:
            Dictionary mapping VP indices to rail descriptions
        """
        return self.vpx_to_rail_desc

    def get_vhx_to_rail_desc(self) -> Dict[int, str]:
        """Get VH (voltage high) to rail descriptions.

        Returns:
            Dictionary mapping VH indices to rail descriptions
        """
        return self.vhx_to_rail_desc

    def get_dpm_signals(self) -> Dict[int, int]:
        """Get DPM signal bit position mappings.

        Returns:
            Dictionary mapping signal names to bit positions
        """
        return self.dpm_signals

    def get_dpm_table(self) -> Dict[int, str]:
        """Get DPM fault code to description lookup table.

        Returns:
            Dictionary mapping fault codes to human-readable descriptions
        """
        return self.dpm_table

    def get_pdio_input_to_fault_cause(self) -> Dict[int, Dict[str, str]]:
        """Get PDIO input to fault cause mappings.

        Returns:
            Dictionary mapping PDIO inputs to fault cause descriptions
        """
        return self.pdio_input_to_fault_cause

    def get_nvmem_path(self) -> str:
        """Get NVMEM device path for blackbox data access.

        Returns:
            Path to NVMEM device file
        """
        return self.nvmem_path

    def get_name(self) -> str:
        """Get device name identifier.

        Returns:
            Device name string
        """
        return self.name
