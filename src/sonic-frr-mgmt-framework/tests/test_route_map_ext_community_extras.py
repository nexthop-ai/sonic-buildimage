"""
Unit tests for three FRR extcommunity route-map capabilities that existed in
the backend (bgp_routemap.c) but were unwired in frrcfgd/yang:

- match extcommunity <LIST> [exact-match|any]  (match_ext_community_mode)
- match extcommunity-limit <N>                 (match_ext_community_limit)
- set extended-comm-list <LIST> delete         (set_ext_community_delete)
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


def _calls(run_cmd):
    return [_render(c[0][1]) for c in run_cmd.call_args_list]


# --- match_ext_community_mode -----------------------------------------------

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_no_mode(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community': 'COLOR_SET',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'match extcommunity COLOR_SET' in combined
    assert 'exact-match' not in combined
    assert ' any' not in combined.replace('COLOR_SET any', 'X')  # no bare 'any' suffix


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_exact_match(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community': 'COLOR_SET',
        'match_ext_community_mode': 'EXACT_MATCH',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'match extcommunity COLOR_SET exact-match' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_any(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community': 'COLOR_SET',
        'match_ext_community_mode': 'ANY',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'match extcommunity COLOR_SET any' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_mode_removed_keeps_list(run_cmd):
    """Removing only the mode (list stays) must fall back to the bare form,
    not clear the whole match condition."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community': 'COLOR_SET',
        'match_ext_community_mode': 'ANY',
    })
    run_cmd.reset_mock()
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community': 'COLOR_SET',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'match extcommunity COLOR_SET' in combined
    assert 'no match extcommunity' not in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_field_removed_clears(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community': 'COLOR_SET',
        'match_ext_community_mode': 'ANY',
    })
    run_cmd.reset_mock()
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'no match extcommunity' in combined


# --- match_ext_community_limit -----------------------------------------------

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_limit_set(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community_limit': '3',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'match extcommunity-limit 3' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_limit_removed(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community_limit': '3',
    })
    run_cmd.reset_mock()
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'no match extcommunity-limit' in combined


# --- set_ext_community_delete -------------------------------------------------

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_delete(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'set_ext_community_delete': 'OLD_SET',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'set extended-comm-list OLD_SET delete' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_delete_removed(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'set_ext_community_delete': 'OLD_SET',
    })
    run_cmd.reset_mock()
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'no set extended-comm-list' in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_set_ext_community_delete_target_changed(run_cmd):
    """Changing set_ext_community_delete from one list name to another must
    apply the new target, not leave the old one referenced."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'set_ext_community_delete': 'OLD_SET',
    })
    run_cmd.reset_mock()
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'set_ext_community_delete': 'NEW_SET',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'set extended-comm-list NEW_SET delete' in combined


# --- update scenarios: changing an already-set value -------------------------

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_mode_changed_exact_to_any(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community': 'COLOR_SET',
        'match_ext_community_mode': 'EXACT_MATCH',
    })
    run_cmd.reset_mock()
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community': 'COLOR_SET',
        'match_ext_community_mode': 'ANY',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'match extcommunity COLOR_SET any' in combined
    assert 'exact-match' not in combined


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_match_ext_community_limit_value_changed(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.route_map = {'POLICY': {'10': 'permit'}}
    hdlr = [h for t, h in daemon.table_handler_list if t == 'ROUTE_MAP']
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community_limit': '3',
    })
    run_cmd.reset_mock()
    hdlr[0]('ROUTE_MAP', 'POLICY|10', {
        'route_operation': 'permit',
        'match_ext_community_limit': '5',
    })
    combined = ' '.join(_calls(run_cmd))
    assert 'match extcommunity-limit 5' in combined
