from unittest.mock import MagicMock, patch

import os
from bgpcfgd.directory import Directory
from bgpcfgd.template import TemplateFabric
from . import swsscommon_test

import sys
sys.modules["swsscommon"] = swsscommon_test

from bgpcfgd.managers_nht import NhtMgr

TEMPLATE_PATH = os.path.abspath('../../dockers/docker-fpm-frr/frr')


def constructor():
    """Create NhtMgr instance for testing."""
    cfg_mgr = MagicMock()
    common_objs = {
        'directory': Directory(),
        'cfg_mgr':   cfg_mgr,
        'tf':        TemplateFabric(TEMPLATE_PATH),
        'constants': {},
    }

    m = NhtMgr(common_objs, "CONFIG_DB", "NEXTHOP_TRACKING")
    return m


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_default_vrf_ipv4_enable(mocked_log_info):
    """Test enabling neighbor tracking for default VRF IPv4."""
    m = constructor()
    res = m.set_handler("default|ipv4", {"neighbor_tracking": "true"})
    assert res, "Returns always True"
    mocked_log_info.assert_called_with(
        "NhtMgr: neighbor_tracking=true scheduled for (vrf=default, afi=ipv4)"
    )
    # Verify template output - default VRF has no vrf context
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'ip nht arp-tracking' in rendered
    assert 'vrf ' not in rendered  # default VRF = no vrf context


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_default_vrf_ipv6_enable(mocked_log_info):
    """Test enabling neighbor tracking for default VRF IPv6."""
    m = constructor()
    res = m.set_handler("default|ipv6", {"neighbor_tracking": "true"})
    assert res, "Returns always True"
    mocked_log_info.assert_called_with(
        "NhtMgr: neighbor_tracking=true scheduled for (vrf=default, afi=ipv6)"
    )
    # Verify template output - default VRF has no vrf context
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'ipv6 nht nd-tracking' in rendered
    assert 'vrf ' not in rendered  # default VRF = no vrf context


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_user_vrf_ipv4_enable(mocked_log_info):
    """Test enabling neighbor tracking for user VRF IPv4."""
    m = constructor()
    res = m.set_handler("vrf-blue|ipv4", {"neighbor_tracking": "true"})
    assert res, "Returns always True"
    mocked_log_info.assert_called_with(
        "NhtMgr: neighbor_tracking=true scheduled for (vrf=vrf-blue, afi=ipv4)"
    )
    # Verify the actual template output pushed to cfg_mgr
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'vrf vrf-blue' in rendered
    assert ' ip nht arp-tracking' in rendered  # Note: leading space for VRF context
    assert 'exit-vrf' in rendered


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_user_vrf_ipv6_enable(mocked_log_info):
    """Test enabling neighbor tracking for user VRF IPv6."""
    m = constructor()
    res = m.set_handler("vrf-blue|ipv6", {"neighbor_tracking": "true"})
    assert res, "Returns always True"
    mocked_log_info.assert_called_with(
        "NhtMgr: neighbor_tracking=true scheduled for (vrf=vrf-blue, afi=ipv6)"
    )
    # Verify the actual template output pushed to cfg_mgr
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'vrf vrf-blue' in rendered
    assert ' ipv6 nht nd-tracking' in rendered  # Note: leading space for VRF context
    assert 'exit-vrf' in rendered


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_disable(mocked_log_info):
    """Test disabling neighbor tracking."""
    m = constructor()
    res = m.set_handler("default|ipv4", {"neighbor_tracking": "false"})
    assert res, "Returns always True"
    mocked_log_info.assert_called_with(
        "NhtMgr: neighbor_tracking=false scheduled for (vrf=default, afi=ipv4)"
    )
    # Verify template output - should have "no" prefix
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'no ip nht arp-tracking' in rendered


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_default_value(mocked_log_info):
    """Test default neighbor_tracking value (should be false)."""
    m = constructor()
    res = m.set_handler("default|ipv4", {})
    assert res, "Returns always True"
    mocked_log_info.assert_called_with(
        "NhtMgr: neighbor_tracking=false scheduled for (vrf=default, afi=ipv4)"
    )


@patch('bgpcfgd.managers_nht.log_err')
def test_set_handler_invalid_key_format(mocked_log_err):
    """Test invalid key format (missing AFI)."""
    m = constructor()
    res = m.set_handler("default", {"neighbor_tracking": "true"})
    assert res, "Returns always True"
    mocked_log_err.assert_called_with(
        "NhtMgr: invalid key format 'default', expected 'vrf_name|afi'"
    )


@patch('bgpcfgd.managers_nht.log_err')
def test_set_handler_invalid_afi(mocked_log_err):
    """Test invalid AFI value."""
    m = constructor()
    res = m.set_handler("default|invalid", {"neighbor_tracking": "true"})
    assert res, "Returns always True"
    mocked_log_err.assert_called_with(
        "NhtMgr: invalid AFI 'invalid', expected 'ipv4' or 'ipv6'"
    )


@patch('bgpcfgd.managers_nht.log_err')
def test_set_handler_empty_vrf_name(mocked_log_err):
    """Empty vrf_name ("|ipv4") passes the length check but must early-return."""
    m = constructor()
    res = m.set_handler("|ipv4", {"neighbor_tracking": "true"})
    assert res, "Returns always True"
    mocked_log_err.assert_called_with(
        "NhtMgr: empty vrf_name in key '|ipv4'"
    )


@patch('bgpcfgd.managers_nht.log_warn')
def test_set_handler_unexpected_neighbor_tracking_value(mocked_log_warn):
    """Unexpected neighbor_tracking value logs a warning and is treated as false."""
    m = constructor()
    res = m.set_handler("default|ipv4", {"neighbor_tracking": "yes"})
    assert res, "Returns always True"
    mocked_log_warn.assert_called_with(
        "NhtMgr: unexpected neighbor_tracking value 'yes' for key 'default|ipv4', treating as false"
    )


@patch('bgpcfgd.managers_nht.log_info')
def test_del_handler_default_vrf(mocked_log_info):
    """Test deleting neighbor tracking for default VRF."""
    m = constructor()
    m.del_handler("default|ipv4")
    mocked_log_info.assert_called_with(
        "NhtMgr: neighbor_tracking disabled for (vrf=default, afi=ipv4)"
    )


@patch('bgpcfgd.managers_nht.log_info')
def test_del_handler_user_vrf(mocked_log_info):
    """Test deleting neighbor tracking for user VRF."""
    m = constructor()
    m.del_handler("vrf-blue|ipv6")
    mocked_log_info.assert_called_with(
        "NhtMgr: neighbor_tracking disabled for (vrf=vrf-blue, afi=ipv6)"
    )


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_default_vrf_resolve_enable(mocked_log_info):
    """Default VRF resolve_via_default=true -> affirmative, no vrf context."""
    m = constructor()
    res = m.set_handler("default|ipv4", {"resolve_via_default": "true"})
    assert res, "Returns always True"
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'ip nht resolve-via-default' in rendered
    assert 'no ip nht resolve-via-default' not in rendered
    assert 'vrf ' not in rendered  # default VRF = no vrf context
    mocked_log_info.assert_any_call(
        "NhtMgr: resolve_via_default=true scheduled for (vrf=default, afi=ipv4)"
    )


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_default_vrf_resolve_disable(mocked_log_info):
    """Default VRF resolve_via_default=false -> explicit "no" form."""
    m = constructor()
    res = m.set_handler("default|ipv6", {"resolve_via_default": "false"})
    assert res, "Returns always True"
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'no ipv6 nht resolve-via-default' in rendered
    mocked_log_info.assert_any_call(
        "NhtMgr: resolve_via_default=false scheduled for (vrf=default, afi=ipv6)"
    )


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_user_vrf_resolve_ignored(mocked_log_info):
    """User VRF resolve_via_default is ignored in legacy mode (unified-only)."""
    m = constructor()
    res = m.set_handler("vrf-blue|ipv4", {"neighbor_tracking": "true",
                                          "resolve_via_default": "false"})
    assert res, "Returns always True"
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'resolve-via-default' not in rendered
    assert ' ip nht arp-tracking' in rendered  # tracking still handled


@patch('bgpcfgd.managers_nht.log_info')
def test_set_handler_resolve_absent_no_line(mocked_log_info):
    """Absent resolve_via_default emits no resolve line (no-op)."""
    m = constructor()
    res = m.set_handler("default|ipv4", {"neighbor_tracking": "true"})
    assert res, "Returns always True"
    m.cfg_mgr.push.assert_called_once()
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'resolve-via-default' not in rendered


@patch('bgpcfgd.managers_nht.log_warn')
def test_set_handler_unexpected_resolve_value(mocked_log_warn):
    """Unexpected resolve_via_default value logs a warning and is ignored."""
    m = constructor()
    res = m.set_handler("default|ipv4", {"resolve_via_default": "maybe"})
    assert res, "Returns always True"
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'resolve-via-default' not in rendered
    mocked_log_warn.assert_called_with(
        "NhtMgr: unexpected resolve_via_default value 'maybe' for key 'default|ipv4', ignoring"
    )


@patch('bgpcfgd.managers_nht.log_info')
def test_del_handler_default_vrf_restores_resolve_default(mocked_log_info):
    """Delete disables tracking and restores resolve-via-default to the YANG
    default (enabled) for the default VRF, matching never-created at runtime."""
    m = constructor()
    m.del_handler("default|ipv4")
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'no ip nht arp-tracking' in rendered
    assert 'ip nht resolve-via-default' in rendered
    assert 'no ip nht resolve-via-default' not in rendered


@patch('bgpcfgd.managers_nht.log_info')
def test_del_handler_user_vrf_leaves_resolve_untouched(mocked_log_info):
    """User-VRF resolve is unified-mode only, so delete emits no resolve line."""
    m = constructor()
    m.del_handler("vrf-blue|ipv4")
    rendered = m.cfg_mgr.push.call_args[0][0]
    assert 'no ip nht arp-tracking' in rendered
    assert 'resolve-via-default' not in rendered


@patch('bgpcfgd.managers_nht.log_err')
def test_del_handler_invalid_key(mocked_log_err):
    """Test deleting with invalid key format."""
    m = constructor()
    m.del_handler("invalid_key")
    mocked_log_err.assert_called_with(
        "NhtMgr: invalid key format 'invalid_key' on delete"
    )


@patch('bgpcfgd.managers_nht.log_err')
def test_del_handler_empty_vrf_name(mocked_log_err):
    """Empty vrf_name on delete passes the length check but must early-return."""
    m = constructor()
    m.del_handler("|ipv6")
    mocked_log_err.assert_called_with(
        "NhtMgr: empty vrf_name in key '|ipv6' on delete"
    )
