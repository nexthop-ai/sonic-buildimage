"""
Unit tests for BGP route-map extended community color configuration.

Tests the frrcfgd handler for translating CONFIG_DB 'color:CC:VALUE' extended
community entries (RFC 9012 Color Extended Community, used for SR-Policy
steering) into FRR vtysh 'set extcommunity color' and 'bgp extcommunity-list
... permit color' commands, alongside the existing route-target/route-origin
markers.
"""

from unittest.mock import MagicMock, NonCallableMagicMock, patch

from .conftest import render_vtysh_cmd as _render

swsscommon_module_mock = MagicMock(ConfigDBConnector=NonCallableMagicMock)
bgpcfgd_managers_bfd_mock = MagicMock()
bgpcfgd_directory_mock = MagicMock()
bgpcfgd_log_mock = MagicMock()
bgpcfgd_utils_mock = MagicMock()

mockmapping = {
    'swsscommon.swsscommon': swsscommon_module_mock,
    'bgpcfgd': MagicMock(),
    'bgpcfgd.managers_bfd': bgpcfgd_managers_bfd_mock,
    'bgpcfgd.directory': bgpcfgd_directory_mock,
    'bgpcfgd.log': bgpcfgd_log_mock,
    'bgpcfgd.utils': bgpcfgd_utils_mock,
}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_color_only(run_cmd):
    """set_ext_community_inline with a single color member."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}

    table = 'ROUTE_MAP'
    key = 'POLICY|10'
    data = {
        'route_operation': 'permit',
        'set_ext_community_inline': ['color:00:100'],
    }

    run_cmd.reset_mock()

    hdlr = [h for t, h in daemon.table_handler_list if t == table]
    assert len(hdlr) == 1
    hdlr[0](table, key, data)

    calls = [_render(c[0][1]) for c in run_cmd.call_args_list]
    combined = ' '.join(calls)
    assert 'set extcommunity color 00:100' in combined, \
        f"Expected color set command not found. Calls: {calls}"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_color_mixed_with_rt(run_cmd):
    """set_ext_community_inline with both route-target and color members
    must emit two separate 'set extcommunity' commands (FRR requires one
    command per keyword type)."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}

    table = 'ROUTE_MAP'
    key = 'POLICY|10'
    data = {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1', 'color:00:100'],
    }

    run_cmd.reset_mock()

    hdlr = [h for t, h in daemon.table_handler_list if t == table]
    hdlr[0](table, key, data)

    calls = [_render(c[0][1]) for c in run_cmd.call_args_list]
    combined = ' '.join(calls)
    assert 'set extcommunity rt 65000:1' in combined, \
        f"Expected rt set command not found. Calls: {calls}"
    assert 'set extcommunity color 00:100' in combined, \
        f"Expected color set command not found. Calls: {calls}"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_color_removed(run_cmd):
    """Removing the color member from an existing route-map statement must
    issue 'no set extcommunity color'."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}

    table = 'ROUTE_MAP'
    key = 'POLICY|10'

    hdlr = [h for t, h in daemon.table_handler_list if t == table]
    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['color:00:100'],
    })

    run_cmd.reset_mock()

    hdlr[0](table, key, {
        'route_operation': 'permit',
    })

    calls = [_render(c[0][1]) for c in run_cmd.call_args_list]
    combined = ' '.join(calls)
    assert 'no set extcommunity color' in combined, \
        f"Expected color clear command not found. Calls: {calls}"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_set_color_standard(run_cmd):
    """EXTENDED_COMMUNITY_SET (STANDARD, match_action ANY) with a color
    member must emit 'bgp extcommunity-list standard NAME permit color ...'."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    table = 'EXTENDED_COMMUNITY_SET'
    key = 'COLOR_SET'
    data = {
        'set_type': 'STANDARD',
        'match_action': 'ANY',
        'community_member': ['color:00:100'],
    }

    run_cmd.reset_mock()

    hdlr = [h for t, h in daemon.table_handler_list if t == table]
    assert len(hdlr) == 1
    hdlr[0](table, key, data)

    calls = [_render(c[0][1]) for c in run_cmd.call_args_list]
    combined = ' '.join(calls)
    assert 'bgp extcommunity-list standard COLOR_SET permit color 00:100' in combined, \
        f"Expected match extcommunity-list color command not found. Calls: {calls}"


# --- list update scenarios: add/remove entries within an existing list -----

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_color_removed_rt_stays(run_cmd):
    """[rt, color] -> [rt]: dropping just the color member must clear the
    color set-action while re-affirming rt, not touch rt at all incorrectly
    and not leave a stale color line."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}

    table = 'ROUTE_MAP'
    key = 'POLICY|10'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]

    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1', 'color:00:100'],
    })

    run_cmd.reset_mock()

    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'set extcommunity rt 65000:1' in combined, \
        f"Expected rt to be re-affirmed. Calls: {combined}"
    assert 'set extcommunity color 00:100' not in combined, \
        f"color must not be re-set. Calls: {combined}"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_color_added_to_existing_rt(run_cmd):
    """[rt] -> [rt, color]: adding color to an existing rt-only statement
    must emit both lines, not just the newly-added one."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}

    table = 'ROUTE_MAP'
    key = 'POLICY|10'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]

    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1'],
    })

    run_cmd.reset_mock()

    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1', 'color:00:100'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'set extcommunity rt 65000:1' in combined
    assert 'set extcommunity color 00:100' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_rt_value_added_within_same_type(run_cmd):
    """[rt:65000:1] -> [rt:65000:1, rt:65000:2]: two values of the SAME
    marker type must combine into a single 'set extcommunity rt' command,
    not two separate ones."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}

    table = 'ROUTE_MAP'
    key = 'POLICY|10'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]

    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1'],
    })

    run_cmd.reset_mock()

    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1', 'route-target:65000:2'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'set extcommunity rt 65000:1 65000:2' in combined, \
        f"Expected combined single rt command. Calls: {combined}"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_rt_value_removed_within_same_type(run_cmd):
    """[rt:65000:1, rt:65000:2] -> [rt:65000:1]: removing one of two values
    of the same type must leave just the remaining one."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}

    table = 'ROUTE_MAP'
    key = 'POLICY|10'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]

    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1', 'route-target:65000:2'],
    })

    run_cmd.reset_mock()

    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['route-target:65000:1'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'set extcommunity rt 65000:1' in combined
    assert '65000:2' not in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_set_color_member_added(run_cmd):
    """EXTENDED_COMMUNITY_SET.community_member growing from [rt] to
    [rt, color] must emit both permit lines on the update."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    table = 'EXTENDED_COMMUNITY_SET'
    key = 'MIX_SET'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]

    hdlr[0](table, key, {
        'set_type': 'STANDARD',
        'match_action': 'ANY',
        'community_member': ['route-target:65000:1'],
    })

    run_cmd.reset_mock()

    hdlr[0](table, key, {
        'set_type': 'STANDARD',
        'match_action': 'ANY',
        'community_member': ['route-target:65000:1', 'color:00:100'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'bgp extcommunity-list standard MIX_SET permit rt 65000:1' in combined
    assert 'bgp extcommunity-list standard MIX_SET permit color 00:100' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_set_color_member_removed(run_cmd):
    """EXTENDED_COMMUNITY_SET.community_member shrinking from [rt, color]
    to [rt] must clear the old members (blind 'no bgp extcommunity-list')
    and only re-add rt, not leave color behind."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    table = 'EXTENDED_COMMUNITY_SET'
    key = 'MIX_SET'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]

    hdlr[0](table, key, {
        'set_type': 'STANDARD',
        'match_action': 'ANY',
        'community_member': ['route-target:65000:1', 'color:00:100'],
    })

    run_cmd.reset_mock()

    hdlr[0](table, key, {
        'set_type': 'STANDARD',
        'match_action': 'ANY',
        'community_member': ['route-target:65000:1'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'bgp extcommunity-list standard MIX_SET permit rt 65000:1' in combined
    assert 'color' not in combined


# --- multiple color values -----------------------------------------------

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_multiple_color_values_combine(run_cmd):
    """Two distinct color values (different CC and/or VALUE) alongside an rt
    must combine into a single 'set extcommunity color CC1:V1 CC2:V2' command
    -- FRR's DEFPY grammar is variadic ('RTLIST...'), confirmed accepted on
    real FRR via vtysh ('set extcommunity color 00:100 01:200')."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}

    table = 'ROUTE_MAP'
    key = 'POLICY|10'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]
    hdlr[0](table, key, {
        'route_operation': 'permit',
        'set_ext_community_inline': ['color:00:100', 'color:01:200', 'route-target:65000:1'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'set extcommunity color 00:100 01:200' in combined, \
        f"Expected combined multi-color command. Calls: {combined}"
    assert 'set extcommunity rt 65000:1' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_set_multiple_color_members_any(run_cmd):
    """ANY match_action: each community_member gets its own permit line, so
    two color members must produce two separate permit lines (OR semantics)."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    table = 'EXTENDED_COMMUNITY_SET'
    key = 'MULTI_COLOR'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]
    hdlr[0](table, key, {
        'set_type': 'STANDARD',
        'match_action': 'ANY',
        'community_member': ['color:00:100', 'color:01:200'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'bgp extcommunity-list standard MULTI_COLOR permit color 00:100' in combined
    assert 'bgp extcommunity-list standard MULTI_COLOR permit color 01:200' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_set_multiple_color_members_all(run_cmd):
    """ALL match_action: all members combine into a single permit line
    (AND semantics) -- two color values must appear together on one line."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    table = 'EXTENDED_COMMUNITY_SET'
    key = 'MULTI_COLOR_ALL'
    hdlr = [h for t, h in daemon.table_handler_list if t == table]
    hdlr[0](table, key, {
        'set_type': 'STANDARD',
        'match_action': 'ALL',
        'community_member': ['color:00:100', 'color:01:200'],
    })

    combined = ' '.join(_render(c[0][1]) for c in run_cmd.call_args_list)
    assert 'bgp extcommunity-list standard MULTI_COLOR_ALL permit color 00:100 color 01:200' in combined, \
        f"Expected combined single-line match. Calls: {combined}"
