<<<<<<< HEAD
#!/usr/bin/env python
=======
# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Presence-detection behaviour tests.

What is pinned here is the contract of nexthop.fpga_presence_monitor and its
use by Chassis.get_change_event():

* a device whose presence changed is reported once, as
  {device_type: {index: '1' inserted | '0' removed}};
* a device with a live UIO presence interrupt is reported when that UIO fires,
  and a device without one is polled instead;
* a timed wait returns when its deadline passes; an indefinite wait keeps
  waiting instead of returning empty or spinning.

Everything is driven through wait_for_event() and the fake hardware below --
never through the monitor's attributes -- so it stays free to change how it
tracks UIO devices, registers them with epoll, or caches presence.

Additionally, tests for the logic that instantiates the correct ports
(pluggable vs. CPO) are also added here.
"""

import copy
import io
import math
import select
from unittest.mock import Mock, create_autospec
>>>>>>> 461c9f22a (NOS-3924: Do not populate _cpo_list for non-CPO platforms (#12466))

import pytest
import sys
import copy
import time

from fixtures.fake_swsscommon import fake_swsscommon_modules
from fixtures.mock_imports_unit_tests import mock_syslog_modules
from fixtures.test_helpers_chassis import setup_patch_for_chassis_init
<<<<<<< HEAD
from unittest.mock import Mock, patch, create_autospec


# Test constants
NUM_TEST_SFPS = 32
=======
from fixtures.test_helpers_common import mock_pddf_data
>>>>>>> 461c9f22a (NOS-3924: Do not populate _cpo_list for non-CPO platforms (#12466))

# Xcvr presence states used by xcvrd
XCVR_INSERTED = "1"
XCVR_REMOVED = "0"


@pytest.fixture(scope="module")
def chassis_module():
    """Loads the module before all tests. This is to let conftest.py inject deps first."""
    from sonic_platform import chassis

    yield chassis


@pytest.fixture(scope="module")
def mock_sfps():
    """
    Fixture providing autospec'ed mock SFP objects for testing.
    Creates a list of mock SFPs and attaches them to the chassis.
    """
    mock_sfps = []
    from sonic_platform_base.sfp_base import SfpBase

    for i in range(1, NUM_TEST_SFPS + 1):
        # autospec helps catch typos or changes in the real interface early.
        sfp_mock = create_autospec(SfpBase)
        sfp_mock.get_name.return_value = f"Ethernet{i}"
        sfp_mock.get_position_in_parent.return_value = str(i)
        mock_sfps.append(sfp_mock)

    return mock_sfps


class SfpTestHelper:
    """
    Helper class for managing SFP state changes in tests.
    Provides utilities for simulating SFP insertion/removal events.
    """

    def __init__(self):
        self.sfp_state = {}
        self.change_events = {}

    def update_state(self, mock_sfps, state):
        """
        Update the state of mock SFPs and track change events.

        Args:
            mock_sfps: List of mock SFP objects
            state: New state (XCVR_INSERTED or XCVR_REMOVED)
        """
        assert state in [XCVR_INSERTED, XCVR_REMOVED]

        for mock_sfp in mock_sfps:
            port_num = mock_sfp.get_position_in_parent()
            if self.sfp_state.get(port_num) != state:
                self.change_events[port_num] = state
            self.sfp_state[port_num] = state
            mock_sfp.get_presence = Mock(return_value=(state == XCVR_INSERTED))

    def get_change_events(self):
        """
        Get and clear the current change events.

        Returns:
            Tuple of (success, events_dict) matching chassis.get_change_event() format
        """
        change_events = copy.deepcopy(self.change_events)
        self.change_events.clear()
        return (True, {"sfp": change_events})

    def clear_events(self):
        """Clear all tracked change events."""
        self.change_events.clear()

    def get_current_state(self, port_num):
        """Get the current state of a specific port."""
        return self.sfp_state.get(port_num)

    def set_all_inserted(self, mock_sfps):
        """Set all SFPs to inserted state."""
        self.update_state(mock_sfps, XCVR_INSERTED)

    def set_all_removed(self, mock_sfps):
        """Set all SFPs to removed state."""
        self.update_state(mock_sfps, XCVR_REMOVED)


class TestChassisSfpIntegration:
    """Test class for Chassis and SFP events functionality."""

    def test_get_change_event_initial_state(self, chassis_module, mock_sfps):
        """Test that initial call to get_change_event() returns no events (initializes cache only)."""
        sfp_test_helper = SfpTestHelper()
        with setup_patch_for_chassis_init(pddf_plugin_data={}):
            chassis = chassis_module.Chassis()
            chassis._sfp_list = mock_sfps

            # Set initial state
            inserted_sfps = mock_sfps[0 : NUM_TEST_SFPS // 2]
            removed_sfps = mock_sfps[NUM_TEST_SFPS // 2 :]

<<<<<<< HEAD
            sfp_test_helper.update_state(inserted_sfps, XCVR_INSERTED)
            sfp_test_helper.update_state(removed_sfps, XCVR_REMOVED)

            # First call should return no events (just initializes cache)
            result = chassis.get_change_event(timeout=100)
            expected = (True, {"sfp": {}})  # Empty events on first call

            assert result == expected

    def test_get_change_event_no_change_short_timeout(self, chassis_module, mock_sfps):
        """Test change event detection with short timeout and no changes."""
        sfp_test_helper = SfpTestHelper()
        with setup_patch_for_chassis_init(pddf_plugin_data={}):
            chassis = chassis_module.Chassis()
            chassis._sfp_list = mock_sfps

            # Set initial state
            sfp_test_helper.update_state(mock_sfps, XCVR_INSERTED)
            chassis.get_change_event(timeout=100)  # First call initializes cache (returns empty)
            sfp_test_helper.clear_events()  # Clear events from initialization

            # Small timeout test - no change
            result = chassis.get_change_event(timeout=1)
            expected = sfp_test_helper.get_change_events()

            assert result == expected

    def test_get_change_event_no_change_long_timeout(self, chassis_module, mock_sfps):
        """Test change event detection with long timeout and no changes."""
        sfp_test_helper = SfpTestHelper()
        with setup_patch_for_chassis_init(pddf_plugin_data={}):
            chassis = chassis_module.Chassis()
            chassis._sfp_list = mock_sfps

            # Set initial state
            sfp_test_helper.update_state(mock_sfps, XCVR_INSERTED)
            chassis.get_change_event(timeout=100)  # First call initializes cache (returns empty)
            sfp_test_helper.clear_events()  # Clear events from initialization

            # Large timeout test - no change (mock time to avoid actual waiting)
            start_time = time.monotonic()
            with patch("time.sleep") as mock_sleep, patch("time.monotonic") as mock_monotonic:
                mock_monotonic.side_effect = [start_time + i for i in range(20)]
                result = chassis.get_change_event(timeout=10 * 1000)
                expected = sfp_test_helper.get_change_events()

                assert result == expected

    def test_get_change_event_partial_change(self, chassis_module, mock_sfps):
        """Test change event detection with partial SFP state changes."""
        sfp_test_helper = SfpTestHelper()
        with setup_patch_for_chassis_init(pddf_plugin_data={}):
            chassis = chassis_module.Chassis()
            chassis._sfp_list = mock_sfps

            # Set initial state
            inserted_sfps = mock_sfps[0 : NUM_TEST_SFPS // 2]
            removed_sfps = mock_sfps[NUM_TEST_SFPS // 2 :]

            sfp_test_helper.update_state(inserted_sfps, XCVR_INSERTED)
            sfp_test_helper.update_state(removed_sfps, XCVR_REMOVED)
            chassis.get_change_event(timeout=100)  # First call initializes cache (returns empty)
            sfp_test_helper.clear_events()  # Clear events from initialization

            # Final change test - a subset of SFPs
            sfp_test_helper.update_state(inserted_sfps[0 : NUM_TEST_SFPS // 4], XCVR_REMOVED)
            sfp_test_helper.update_state(removed_sfps[0 : NUM_TEST_SFPS // 4], XCVR_INSERTED)

            result = chassis.get_change_event()
            expected = sfp_test_helper.get_change_events()

            assert result == expected

    def test_get_change_event_all_inserted(self, chassis_module, mock_sfps):
        """Test change event when all SFPs are inserted after initialization."""
        sfp_test_helper = SfpTestHelper()
        with setup_patch_for_chassis_init(pddf_plugin_data={}):
            chassis = chassis_module.Chassis()
            chassis._sfp_list = mock_sfps

            # Start with all removed
            sfp_test_helper.set_all_removed(mock_sfps)
            chassis.get_change_event(timeout=100)  # First call initializes cache (returns empty)

            # Now insert all SFPs
            sfp_test_helper.set_all_inserted(mock_sfps)
            result = chassis.get_change_event()
            expected = sfp_test_helper.get_change_events()

            assert result == expected

    def test_get_change_event_all_removed(self, chassis_module, mock_sfps):
        """Test change event when all SFPs are removed after initialization."""
        sfp_test_helper = SfpTestHelper()
        with setup_patch_for_chassis_init(pddf_plugin_data={}):
            chassis = chassis_module.Chassis()
            chassis._sfp_list = mock_sfps

            # Start with all inserted
            sfp_test_helper.set_all_inserted(mock_sfps)
            chassis.get_change_event(timeout=100)  # First call initializes cache (returns empty)

            # Now remove all SFPs
            sfp_test_helper.set_all_removed(mock_sfps)
            result = chassis.get_change_event()
            expected = sfp_test_helper.get_change_events()

            assert result == expected
=======
        warnings = [call.args[0] for call in logger.log_warning.call_args_list]
        assert any("PDDF" in w and SFP_KEY in w for w in warnings), warnings


# ==========================================================================
# Splitting front panel ports between the SFP and CPO lists
# ==========================================================================

class TestPortLists:
    class _StubPort:
        def __init__(self, index, pddf_data, pddf_plugin_data):
            self.index = index

    class StubSfp(_StubPort):
        pass

    class StubCpo(_StubPort):
        pass

    @pytest.fixture
    def chassis_with_ports(self, chassis_module, monkeypatch):
        """Factory for a Chassis whose PDDF data declares the given port types.

        The real Sfp/Cpo need far more PDDF data than port classification
        does, so PddfChassis builds stubs instead.
        """
        from sonic_platform_pddf_base import pddf_chassis

        monkeypatch.setattr(pddf_chassis, "Sfp", self.StubSfp)
        monkeypatch.setattr(pddf_chassis, "Cpo", self.StubCpo)

        def _build(port_types):
            pddf_data = mock_pddf_data({"PLATFORM": {"num_ports": len(port_types)}})
            pddf_data.get_device_type.side_effect = (
                lambda port_key: port_types[int(port_key[len("PORT"):]) - 1])
            # Non-empty plugin data, or PddfChassis discards pddf_data and
            # loads the on-switch JSON instead.
            with setup_patch_for_chassis_init(pddf_plugin_data={}):
                return chassis_module.Chassis(
                    pddf_data=pddf_data, pddf_plugin_data={"PLATFORM": {}})

        return _build

    @pytest.mark.parametrize("port_types, sfp_types, cpo_types", [
        pytest.param(["OSFP", "OSFP"], [StubSfp, StubSfp], [],
                     id="pluggable-only"),
        pytest.param(["CPO", "CPO"], [], [StubCpo, StubCpo],
                     id="cpo-only"),
        pytest.param(["CPO", "OSFP", "CPO"],
                     [type(None), StubSfp, type(None)],
                     [StubCpo, type(None), StubCpo],
                     id="mixed"),
    ])
    def test_ports_are_listed_by_physical_port(
            self, chassis_with_ports, port_types, sfp_types, cpo_types):
        """A platform with one kind of port leaves the other list empty; a
        mixed one pads both with None at the other kind's ports."""
        chassis = chassis_with_ports(port_types)

        assert [type(sfp) for sfp in chassis._sfp_list] == sfp_types
        assert [type(cpo) for cpo in chassis._cpo_list] == cpo_types
>>>>>>> 461c9f22a (NOS-3924: Do not populate _cpo_list for non-CPO platforms (#12466))
