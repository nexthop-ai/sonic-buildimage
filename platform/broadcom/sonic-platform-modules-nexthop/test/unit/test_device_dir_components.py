#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Sanity tests for the device directory structure.

These tests validate the actual device directory to ensure:
- All platforms and HWSKUs are discoverable
- No directories are silently missed by the discovery logic
- Excluded items are still present (catches stale exclusions)
"""

import json
import os
import sys

import pytest

# Add lib directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from platform_discovery import get_all_platform_paths, render_pddf_json


class TestDeviceDirectoryComponents:
    """Sanity tests for platform components in the device directory."""

    @pytest.mark.parametrize(
        "platform_name,platform_path",
        get_all_platform_paths(),
        ids=lambda p: p[0] if isinstance(p, tuple) else str(p),
    )
    def test_device_components(self, platform_name, platform_path):
        """Verify the platform components configuration files are consistent."""
        # Verify the files containing component configs exist.
        assert os.path.isdir(platform_path), (
            f"Device directory not found: {platform_path}"
        )
        platform_components_json_path = os.path.join(platform_path, "platform_components.json")
        platform_json_path = os.path.join(platform_path, "platform.json")
        pddf_device_j2_path = os.path.join(platform_path, "pddf/pddf-device.json.j2")
        for file_path in [platform_components_json_path, pddf_device_j2_path, platform_json_path]:
            assert os.path.isfile(file_path), (
                f"Expected file is not found: {file_path}"
            )

        with open(platform_components_json_path, "r") as f:
            try:
                platform_components_json = json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"Failed to parse {platform_components_json_path}: {e}")
        with open(platform_json_path, "r") as f:
            try:
                platform_json = json.load(f)
            except json.JSONDecodeError as e:
                pytest.fail(f"Failed to parse {platform_json_path}: {e}")

        try:
            pddf_device_json = render_pddf_json(platform_path, platform_name)
        except (json.JSONDecodeError, Exception) as e:
            pytest.fail(f"Failed to parse {pddf_device_j2_path} after rendering it to json: {e}")

        """
        Number of components in all 3 configs must match
        platform_components.json
        {
            "chassis": {
                "NH-5010-F": {
                    "component": {
                        "SWITCHCARD_FPGA": {},
                        "MEZZCARD_FPGA": {},
                        ...
        }
        """
        chassis_name = next(iter(platform_components_json["chassis"]))
        components_platform_components_json = platform_components_json["chassis"][chassis_name]["component"]
        num_components_platform_components_json = len(components_platform_components_json.keys())
        """
        platform.json
        {
            "chassis": {
                "name": "NH-5010-F",
                "components": [
                    {
                        "name": "SWITCHCARD_FPGA"
                    },
                    {
                        "name": "MEZZCARD_FPGA"
                    },
                    ...
                ]
            }
        }
        """
        components_platform_json = platform_json["chassis"]["components"]
        num_components_platform_json = len(components_platform_json)
        """
        pddf-device.json.j2
        {
            "PLATFORM": {
                "num_components": 38,
                ...
            },
            "COMPONENT1": {
                "name": "SWITCHCARD_FPGA",
                ...
            },
            ...
        }
        """
        num_components_pddf_device = pddf_device_json["PLATFORM"]["num_components"]
        assert num_components_platform_components_json == num_components_platform_json == num_components_pddf_device, (
            f"Number of components mismatch: "
            f"platform_components.json: {num_components_platform_components_json}, "
            f"platform.json: {num_components_platform_json}, "
            f"pddf-device.json.j2: {num_components_pddf_device}"
        )

        # Component names in all 3 configs must match
        component_names_platform_json = [val["name"] for val in components_platform_json]
        component_names_pddf_device = []
        for i in range(num_components_pddf_device):
            assert f"COMPONENT{i+1}" in pddf_device_json, f"pddf-device.json.j2 is missing COMPONENT{i+1}"
            component_names_pddf_device.append(pddf_device_json[f"COMPONENT{i+1}"]["comp_attr"]["name"])
        for component_name in components_platform_components_json.keys():
            assert component_name in component_names_platform_json, f"platform.json is missing component which appears in platform_components.json, with name '{component_name}'"
            assert component_name in component_names_pddf_device, f"rendered pddf-device.json is missing component which appears in platform_components.json, with name '{component_name}'"

    @pytest.mark.parametrize(
        "platform_name,platform_path",
        get_all_platform_paths(),
        ids=lambda p: p[0] if isinstance(p, tuple) else str(p),
    )
    def test_device_chassis_inventory(self, platform_name, platform_path):
        """Verify platform.json chassis inventory matches the pddf-device.json counts.

        PDDF drives what the platform API actually enumerates at runtime, while
        platform.json is what sonic-mgmt reads into duthost.facts as the expected
        values. A platform that symlinks another platform's pddf-device.json but
        keeps its own platform.json (e.g. NH-4020 -> NH-4010) silently drifts here.
        """
        platform_json_path = os.path.join(platform_path, "platform.json")
        with open(platform_json_path, "r") as f:
            try:
                chassis = json.load(f)["chassis"]
            except json.JSONDecodeError as e:
                pytest.fail(f"Failed to parse {platform_json_path}: {e}")

        try:
            pddf_device_json = render_pddf_json(platform_path, platform_name)
        except (json.JSONDecodeError, Exception) as e:
            pytest.fail(f"Failed to render pddf-device.json.j2 for {platform_name}: {e}")

        pddf_platform = pddf_device_json["PLATFORM"]
        num_fantrays = pddf_platform.get("num_fantrays", 0)
        # Thermals are the union of the board, ASIC and FPGA-attached ASIC sensors.
        expected = {
            "thermals": (
                pddf_platform.get("num_temps", 0)
                + pddf_platform.get("num_asic_temps", 0)
                + pddf_platform.get("num_nexthop_fpga_asic_temp_sensors", 0)
            ),
            "fans": num_fantrays * pddf_platform.get("num_fans_pertray", 0),
            "fan_drawers": num_fantrays,
            "psus": pddf_platform.get("num_psus", 0),
            "sfps": pddf_platform.get("num_ports", 0),
        }

        for key, expected_count in expected.items():
            assert key in chassis, (
                f"platform.json chassis is missing the '{key}' section, but "
                f"pddf-device.json enumerates {expected_count} of them"
            )
            assert len(chassis[key]) == expected_count, (
                f"platform.json chassis '{key}' count mismatch: "
                f"platform.json: {len(chassis[key])}, pddf-device.json: {expected_count}"
            )
