#!/usr/bin/env python

# Copyright 2025 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Test configuration for unit tests.

Unit tests run in isolation and require mocks for SONiC dependencies
that are not available during the build process.
"""

import pytest
import sys
from unittest.mock import Mock, patch


@pytest.fixture(scope="function", autouse=True)
def patch_dependencies():
    """Sets up mocked dependencies for all unit tests.

    This fixture is automatically applied to all tests in the unit/ directory.
    It uses function scope, so each test can override the mocked modules if needed.
    """
    # Mock SONiC dependencies that are not available during wheel build.
    # The TlvInfo bases must be real classes: eeprom_utils subclasses them
    # alongside a real mixin, and a Mock co-base is a metaclass conflict.
    class _TlvInfoDecoder:
        def __init__(self, *args, **kwargs):
            pass
    eeprom_tlvinfo = Mock()
    eeprom_tlvinfo.TlvInfoDecoder = _TlvInfoDecoder
    eeprom_tlvinfo.EepromDecodeVisitor = type("EepromDecodeVisitor", (object,), {})
    sonic_eeprom = Mock()
    sonic_eeprom.eeprom_tlvinfo = eeprom_tlvinfo
    mock_modules = {
        "sonic_platform_base": Mock(),
        "sonic_platform_base.sonic_eeprom": sonic_eeprom,
        "sonic_platform_base.sonic_eeprom.eeprom_tlvinfo": eeprom_tlvinfo,
        "sonic_eeprom": sonic_eeprom,
        "sonic_eeprom.eeprom_tlvinfo": eeprom_tlvinfo,
    }

    with patch.dict(sys.modules, mock_modules):
        # Keep the patch active while a test is running
        yield

    # Cleanup is handled automatically by pytest session teardown
