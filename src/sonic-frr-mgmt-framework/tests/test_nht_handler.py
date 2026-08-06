"""Tests for NEXTHOP_TRACKING handler in frrcfgd (unified mode).

Covers:
  - nht_handler vtysh command construction for both VRFs and AFIs
  - neighbor_tracking enable/disable + delete semantics
  - resolve_via_default enable/disable for default and user VRFs
  - VRF context handling (default = root scope, user VRF = wrapped)
  - Invalid-key and invalid-AFI rejection
"""
from unittest.mock import MagicMock, NonCallableMagicMock, patch

# Mock external modules frrcfgd imports at module load time.
swsscommon_module_mock = MagicMock(ConfigDBConnector=NonCallableMagicMock)
mockmapping = {
    'swsscommon.swsscommon': swsscommon_module_mock,
    'bgpcfgd': MagicMock(),
    'bgpcfgd.managers_bfd': MagicMock(),
    'bgpcfgd.directory': MagicMock(),
    'bgpcfgd.log': MagicMock(),
    'bgpcfgd.utils': MagicMock(),
}

with patch.dict('sys.modules', **mockmapping):
    from frrcfgd.frrcfgd import BGPConfigDaemon


def _make_daemon():
    """Construct a minimal BGPConfigDaemon for handler testing.

    __new__ bypasses the full __init__ (which would open CONFIG_DB, spawn
    threads, etc.). DEFAULT_VRF is a class attribute on BGPConfigDaemon, so
    it's accessible without instance initialization.
    """
    daemon = BGPConfigDaemon.__new__(BGPConfigDaemon)
    daemon._BGPConfigDaemon__run_command = MagicMock(return_value=True)
    return daemon


def _cmd(daemon):
    """Return the command list passed to the most recent __run_command call."""
    return daemon._BGPConfigDaemon__run_command.call_args[0][1]


# ---------------------------------------------------------------------------
# Default VRF — commands emit at root scope (no vrf/exit-vrf wrapper)
# ---------------------------------------------------------------------------

def test_default_vrf_ipv4_enable():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", {"neighbor_tracking": "true"})

    cmd = _cmd(daemon)
    assert cmd[:3] == ['vtysh', '-c', 'configure terminal']
    assert 'ip nht arp-tracking' in cmd
    # Default VRF must NOT wrap in vrf/exit-vrf
    assert 'vrf default' not in ' '.join(cmd)
    assert 'exit-vrf' not in cmd


def test_default_vrf_ipv6_enable():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv6", {"neighbor_tracking": "true"})

    cmd = _cmd(daemon)
    assert 'ipv6 nht nd-tracking' in cmd
    assert 'exit-vrf' not in cmd


# ---------------------------------------------------------------------------
# User VRF — commands wrapped in 'vrf X' / 'exit-vrf' context, ordering matters
# ---------------------------------------------------------------------------

def test_user_vrf_ipv4_enable_ordering():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "Vrf_blue|ipv4", {"neighbor_tracking": "true"})

    cmd = _cmd(daemon)
    assert cmd[:3] == ['vtysh', '-c', 'configure terminal']
    vrf_i = cmd.index('vrf Vrf_blue')
    cmd_i = cmd.index('ip nht arp-tracking')
    exit_i = cmd.index('exit-vrf')
    # configure terminal → vrf X → command → exit-vrf, in order
    assert 2 < vrf_i < cmd_i < exit_i


def test_user_vrf_ipv6_enable_ordering():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "Vrf_blue|ipv6", {"neighbor_tracking": "true"})

    cmd = _cmd(daemon)
    vrf_i = cmd.index('vrf Vrf_blue')
    cmd_i = cmd.index('ipv6 nht nd-tracking')
    exit_i = cmd.index('exit-vrf')
    assert vrf_i < cmd_i < exit_i


# ---------------------------------------------------------------------------
# Disable / delete — both forms emit the 'no' command
# ---------------------------------------------------------------------------

def test_disable_emits_no_form():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", {"neighbor_tracking": "false"})

    cmd = _cmd(daemon)
    assert 'no ip nht arp-tracking' in cmd
    # Bare positive form must not appear when disabling
    assert 'ip nht arp-tracking' not in [c for c in cmd if not c.startswith('no ')]


def test_delete_treated_as_disable():
    """DELETE (data=None) and explicit neighbor_tracking=false both emit 'no ...'."""
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "Vrf_blue|ipv6", None)

    cmd = _cmd(daemon)
    assert 'vrf Vrf_blue' in cmd
    assert 'no ipv6 nht nd-tracking' in cmd
    assert 'exit-vrf' in cmd


# ---------------------------------------------------------------------------
# Input validation — bad key or AFI must not reach vtysh
# ---------------------------------------------------------------------------

def test_invalid_key_format_does_not_run():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default", {"neighbor_tracking": "true"})

    # No '|' in key → handler must early-return without invoking vtysh.
    daemon._BGPConfigDaemon__run_command.assert_not_called()


def test_invalid_afi_does_not_run():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipvX", {"neighbor_tracking": "true"})

    # Unknown AFI → handler must early-return without invoking vtysh.
    daemon._BGPConfigDaemon__run_command.assert_not_called()


def test_empty_vrf_name_does_not_run():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "|ipv4", {"neighbor_tracking": "true"})

    # Empty vrf_name (e.g., "|ipv4") passes the length check but must
    # early-return without invoking vtysh.
    daemon._BGPConfigDaemon__run_command.assert_not_called()


def test_unexpected_neighbor_tracking_value_treated_as_false():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", {"neighbor_tracking": "yes"})

    # Unexpected value → treated as false; "no ip nht arp-tracking" emitted.
    cmd = _cmd(daemon)
    assert "no ip nht arp-tracking" in cmd


# ---------------------------------------------------------------------------
# resolve_via_default — default and user VRFs (unified mode only at runtime)
# ---------------------------------------------------------------------------

def test_default_vrf_resolve_enable():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", {"resolve_via_default": "true"})

    cmd = _cmd(daemon)
    assert 'ip nht resolve-via-default' in cmd
    assert 'no ip nht resolve-via-default' not in cmd
    assert 'exit-vrf' not in cmd


def test_default_vrf_resolve_disable():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv6", {"resolve_via_default": "false"})

    cmd = _cmd(daemon)
    assert 'no ipv6 nht resolve-via-default' in cmd


def test_user_vrf_resolve_enable_ordering():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "Vrf_blue|ipv4", {"resolve_via_default": "true"})

    cmd = _cmd(daemon)
    vrf_i = cmd.index('vrf Vrf_blue')
    resolve_i = cmd.index('ip nht resolve-via-default')
    exit_i = cmd.index('exit-vrf')
    assert vrf_i < resolve_i < exit_i


def test_user_vrf_resolve_disable():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "Vrf_blue|ipv6", {"resolve_via_default": "false"})

    cmd = _cmd(daemon)
    assert 'vrf Vrf_blue' in cmd
    assert 'no ipv6 nht resolve-via-default' in cmd
    assert 'exit-vrf' in cmd


def test_resolve_absent_no_line():
    """Default VRF: absent resolve_via_default emits tracking only, resolve
    untouched (default-VRF resolve is owned by zebra.interfaces.conf.j2)."""
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", {"neighbor_tracking": "true"})

    cmd = _cmd(daemon)
    assert 'ip nht arp-tracking' in cmd
    assert 'resolve-via-default' not in ' '.join(cmd)


def test_user_vrf_resolve_absent_defaults_enabled():
    """User VRF: absent resolve_via_default defaults to enabled, matching the
    boot render in zebra.nht.conf.j2 so runtime and reboot agree."""
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "Vrf_blue|ipv4", {"neighbor_tracking": "true"})

    cmd = _cmd(daemon)
    vrf_i = cmd.index('vrf Vrf_blue')
    resolve_i = cmd.index('ip nht resolve-via-default')
    exit_i = cmd.index('exit-vrf')
    assert vrf_i < resolve_i < exit_i
    assert 'no ip nht resolve-via-default' not in cmd


def test_delete_default_vrf_restores_resolve_default():
    """DELETE disables tracking and restores resolve-via-default to the YANG
    default (enabled) so created-then-deleted matches never-created at runtime."""
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", None)

    cmd = _cmd(daemon)
    assert 'no ip nht arp-tracking' in cmd
    assert 'ip nht resolve-via-default' in cmd
    assert 'no ip nht resolve-via-default' not in cmd


def test_delete_user_vrf_restores_resolve_default():
    """DELETE on a user VRF also restores the enabled default, wrapped in the
    vrf context."""
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "Vrf_blue|ipv6", None)

    cmd = _cmd(daemon)
    vrf_i = cmd.index('vrf Vrf_blue')
    resolve_i = cmd.index('ipv6 nht resolve-via-default')
    exit_i = cmd.index('exit-vrf')
    assert vrf_i < resolve_i < exit_i
    assert 'no ipv6 nht resolve-via-default' not in cmd


def test_both_fields_combined_default():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", {
        "neighbor_tracking": "true",
        "resolve_via_default": "false",
    })

    cmd = _cmd(daemon)
    track_i = cmd.index('ip nht arp-tracking')
    resolve_i = cmd.index('no ip nht resolve-via-default')
    assert track_i < resolve_i


def test_both_fields_combined_user_vrf():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "Vrf_blue|ipv4", {
        "neighbor_tracking": "true",
        "resolve_via_default": "true",
    })

    cmd = _cmd(daemon)
    vrf_i = cmd.index('vrf Vrf_blue')
    track_i = cmd.index('ip nht arp-tracking')
    resolve_i = cmd.index('ip nht resolve-via-default')
    exit_i = cmd.index('exit-vrf')
    assert vrf_i < track_i < resolve_i < exit_i


def test_unexpected_resolve_value_ignored():
    daemon = _make_daemon()
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", {"resolve_via_default": "maybe"})

    cmd = _cmd(daemon)
    assert 'resolve-via-default' not in ' '.join(cmd)


# ---------------------------------------------------------------------------
# Command-execution failure — handler logs ERR and returns cleanly
# ---------------------------------------------------------------------------

def test_run_command_failure_does_not_raise():
    daemon = _make_daemon()
    daemon._BGPConfigDaemon__run_command = MagicMock(return_value=False)

    # vtysh execution failure must not propagate; handler logs and returns.
    daemon.nht_handler("NEXTHOP_TRACKING", "default|ipv4", {"neighbor_tracking": "true"})

    # Verify we reached the run_command call (i.e., not bailed earlier on
    # validation) and that the failure was swallowed.
    daemon._BGPConfigDaemon__run_command.assert_called_once()
