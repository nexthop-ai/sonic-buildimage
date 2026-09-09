"""
Unit tests for BGP_MONITORS handling in frrcfgd (NOS-13538).

Covers the admin_status leaf, which sonic-bgp-monitor.yang is the only one
left writable after the monitor row is created: a GCU patch that flips it must
reach FRR as a `neighbor <ip> shutdown` / `no neighbor <ip> shutdown`. Also
covers first-load create already carrying admin_status=down, and rejecting an
invalid value.
"""

from unittest.mock import MagicMock, NonCallableMagicMock, patch

swsscommon_module_mock = MagicMock(ConfigDBConnector=NonCallableMagicMock)

mockmapping = {
    'swsscommon.swsscommon': swsscommon_module_mock,
    'bgpcfgd': MagicMock(),
    'bgpcfgd.managers_bfd': MagicMock(),
    'bgpcfgd.directory': MagicMock(),
    'bgpcfgd.log': MagicMock(),
    'bgpcfgd.utils': MagicMock(),
}

from .conftest import render_vtysh_cmd

MONITOR_IP = '11.0.0.1'
LOCAL_ASN = '65100'

MONITOR_ROW = {
    'admin_status': 'up',
    'asn': LOCAL_ASN,
    'holdtime': '180',
    'keepalive': '60',
    'local_addr': '10.1.0.32',
    'name': 'BGPMonitor',
    'nhopself': '0',
    'rrclient': '0',
}


def _daemon():
    """A BGPConfigDaemon with the BGPMON peer-group and route-maps already in
    place, so a monitor event exercises only the per-neighbor commands."""
    from frrcfgd.frrcfgd import BGPConfigDaemon, BGPPeerGroup

    daemon = BGPConfigDaemon()
    daemon.config_db.serialize_key = lambda key: key
    daemon.bgp_asn = {daemon.DEFAULT_VRF: LOCAL_ASN}
    daemon.bgp_peer_group = {daemon.DEFAULT_VRF: {'BGPMON': BGPPeerGroup(daemon.DEFAULT_VRF)}}
    daemon.route_map = {'FROM_BGPMON': {'10': 'deny'}, 'TO_BGPMON': {'10': 'permit'}}
    return daemon


def _fire(daemon, row):
    """Deliver one BGP_MONITORS row the way ExtConfigDBConnector does: the full
    hash read back from CONFIG_DB, for any single-field change."""
    hdlr = [h for t, h in daemon.table_handler_list if t == 'BGP_MONITORS']
    assert len(hdlr) == 1
    hdlr[0]('BGP_MONITORS', MONITOR_IP, dict(row))


def _commands(run_cmd):
    return [render_vtysh_cmd(call[0][1]) for call in run_cmd.call_args_list]


def _assert_in_order(cmds, expected):
    last = -1
    for fragment in expected:
        matches = [i for i, cmd in enumerate(cmds) if fragment in cmd]
        assert matches, 'missing %s. Commands: %s' % (fragment, cmds)
        assert matches[0] > last, 'out of order at %s. Commands: %s' % (fragment, cmds)
        last = matches[0]


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_monitor_admin_status_down(run_cmd):
    """A row whose admin_status flipped to down must shut the neighbor."""
    run_cmd.return_value = True
    daemon = _daemon()
    _fire(daemon, MONITOR_ROW)

    run_cmd.reset_mock()
    _fire(daemon, dict(MONITOR_ROW, admin_status='down'))

    cmds = _commands(run_cmd)
    assert any("-c 'neighbor %s shutdown'" % MONITOR_IP in cmd for cmd in cmds), \
        'admin_status=down did not reach FRR. Commands: %s' % cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_monitor_admin_status_up(run_cmd):
    """Flipping back to up must clear the shutdown."""
    run_cmd.return_value = True
    daemon = _daemon()
    _fire(daemon, dict(MONITOR_ROW, admin_status='down'))

    run_cmd.reset_mock()
    _fire(daemon, MONITOR_ROW)

    cmds = _commands(run_cmd)
    assert any("-c 'no neighbor %s shutdown'" % MONITOR_IP in cmd for cmd in cmds), \
        'admin_status=up did not reach FRR. Commands: %s' % cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_monitor_add_still_programs_neighbor(run_cmd):
    """The create path is unchanged: remote-as, peer-group, description and
    update-source are still issued, with the admin state applied last."""
    run_cmd.return_value = True
    daemon = _daemon()

    _fire(daemon, MONITOR_ROW)

    cmds = _commands(run_cmd)
    for expected in ("-c 'neighbor %s remote-as %s'" % (MONITOR_IP, LOCAL_ASN),
                     "-c 'neighbor %s peer-group BGPMON'" % MONITOR_IP,
                     "-c 'neighbor %s description BGPMonitor'" % MONITOR_IP,
                     "-c 'neighbor %s update-source 10.1.0.32'" % MONITOR_IP,
                     "-c 'no neighbor %s shutdown'" % MONITOR_IP):
        assert any(expected in cmd for cmd in cmds), \
            'missing %s. Commands: %s' % (expected, cmds)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_monitor_create_with_admin_status_down(run_cmd):
    """First CONFIG_DB appearance already admin_status=down must create the
    neighbor and shut it in the same __add_bgp_monitor call."""
    run_cmd.return_value = True
    daemon = _daemon()
    _fire(daemon, dict(MONITOR_ROW, admin_status='down'))

    cmds = _commands(run_cmd)
    _assert_in_order(cmds, (
        "-c 'neighbor %s remote-as %s'" % (MONITOR_IP, LOCAL_ASN),
        "-c 'neighbor %s peer-group BGPMON'" % MONITOR_IP,
        "-c 'neighbor %s description BGPMonitor'" % MONITOR_IP,
        "-c 'neighbor %s update-source 10.1.0.32'" % MONITOR_IP,
        "-c 'neighbor %s shutdown'" % MONITOR_IP,
    ))
    assert not any("-c 'no neighbor %s shutdown'" % MONITOR_IP in cmd for cmd in cmds), \
        'create-down must not clear shutdown. Commands: %s' % cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_monitor_admin_status_absent_is_no_op(run_cmd):
    """A row without admin_status must not emit a shutdown command either way."""
    run_cmd.return_value = True
    daemon = _daemon()
    row = dict(MONITOR_ROW)
    del row['admin_status']

    _fire(daemon, row)

    cmds = _commands(run_cmd)
    assert not any('shutdown' in cmd for cmd in cmds), \
        'unexpected shutdown command. Commands: %s' % cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.syslog.syslog')
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_monitor_admin_status_invalid(run_cmd, syslog_fn):
    """An unrecognized admin_status must not emit shutdown and must fail the update."""
    run_cmd.return_value = True
    daemon = _daemon()
    _fire(daemon, dict(MONITOR_ROW, admin_status='disabled'))

    cmds = _commands(run_cmd)
    assert not any('shutdown' in cmd for cmd in cmds), \
        'invalid admin_status must not emit shutdown. Commands: %s' % cmds
    err_msgs = [call[0][1] for call in syslog_fn.call_args_list]
    assert any('wrong admin_status value disabled' in msg for msg in err_msgs), \
        'missing invalid-value error. Logs: %s' % err_msgs
    assert any('failed to process BGP monitor %s' % MONITOR_IP in msg for msg in err_msgs), \
        'invalid admin_status did not fail the update. Logs: %s' % err_msgs
