import copy
import re
<<<<<<< HEAD
=======
from functools import partial
import pytest
>>>>>>> de5fb8890 (Purge a VRF's cached child rows when its BGP instance is removed)
from unittest.mock import MagicMock, NonCallableMagicMock, patch

def mock_is_vrf_name_valid(name):
    return (isinstance(name, str) and name not in ('.', '..') and
            re.fullmatch(r'[A-Za-z0-9_.][A-Za-z0-9_.-]{0,14}', name) is not None)

def mock_is_interface_name_valid(name):
    return isinstance(name, str) and 0 < len(name) < 16

swsscommon_module_mock = MagicMock(
    ConfigDBConnector=NonCallableMagicMock,
    isInterfaceNameValid=mock_is_interface_name_valid,
    isVrfNameValid=mock_is_vrf_name_valid)
# because can’t use dotted names directly in a call, have to create a dictionary and unpack it using **:
mockmapping = {'swsscommon.swsscommon': swsscommon_module_mock}

@patch.dict('sys.modules', **mockmapping)
def test_contructor():
    from frrcfgd.frrcfgd import BGPConfigDaemon
    daemon = BGPConfigDaemon()
    daemon.start()
    for table, hdlr in daemon.table_handler_list:
        daemon.config_db.subscribe.assert_any_call(table, hdlr)
    daemon.config_db.pubsub.psubscribe.assert_called_once()
    assert(daemon.config_db.sub_thread.is_alive() == True)
    daemon.stop()
    daemon.config_db.pubsub.punsubscribe.assert_called_once()
    assert(daemon.config_db.sub_thread.is_alive() == False)

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_key_and_asn_validation(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    daemon = BGPConfigDaemon()
    normalize_key = daemon._BGPConfigDaemon__normalize_bgp_table_key
    asn_is_valid = daemon._BGPConfigDaemon__bgp_asn_is_valid
    validate_input = daemon._BGPConfigDaemon__validate_bgp_table_input

    assert normalize_key('BGP_NEIGHBOR', 'default|FC00:10::1') == 'default|fc00:10::1'
    assert normalize_key('BGP_NEIGHBOR', 'default|1234') == 'default|1234'
    assert normalize_key('BGP_NEIGHBOR', 'default|Ethernet0') == 'default|Ethernet0'
    assert normalize_key('BGP_PEER_GROUP', 'Vrf-RED_1|PG_V4-1') == 'Vrf-RED_1|PG_V4-1'
    assert normalize_key('BGP_NEIGHBOR_AF', 'default|10.0.0.1|ipv4_unicast') == \
        'default|10.0.0.1|ipv4_unicast'
    assert normalize_key('BGP_GLOBALS_AF', 'default|l2vpn_evpn') == \
        'default|l2vpn_evpn'
    assert normalize_key('ROUTE_REDISTRIBUTE', 'default|static|bgp|ipv6') == \
        'default|static|bgp|ipv6'

    for table, key in (
            ('BGP_NEIGHBOR', None),
            ('BGP_NEIGHBOR', 'vrf name|10.0.0.1'),
            ('BGP_NEIGHBOR', 'default|peer name'),
            ('BGP_PEER_GROUP', 'default|peer' + chr(39) + 'name'),
            ('BGP_NEIGHBOR_AF', 'default|10.0.0.1'),
            ('BGP_GLOBALS', 'default|extra'),
            ('BGP_GLOBALS_AF', 'default|ipv4_unicast' + chr(39) + '-c-bad'),
            ('BGP_NEIGHBOR_AF', 'default|10.0.0.1|ipv4_multicast'),
            ('ROUTE_REDISTRIBUTE', 'default|static|bgp|l2vpn')):
        assert normalize_key(table, key) is None

    for value in (1, '4294967295'):
        assert asn_is_valid(value)
    for value in (True, 0, '4294967296', '65000x', '9' * 5000):
        assert not asn_is_valid(value)

    assert validate_input('BGP_NEIGHBOR', 'default|10.0.0.1',
                          {'name': 'Edge peer "A"',
                           'shutdown_message': 'planned maintenance'}) == \
        'default|10.0.0.1'

    daemon.metadata_asn = '65000'
    daemon.metadata_handler('DEVICE_METADATA', 'localhost',
                            {'bgp_asn': "65000' -c 'bad"})
    assert daemon.metadata_asn == '65000'

    daemon.bgp_global_handler('BGP_GLOBALS', 'vrf name', {'local_asn': '65000'})
    daemon.bgp_global_handler('BGP_GLOBALS', 'default', {'local_asn': '0'})
    daemon.bgp_global_handler('BGP_GLOBALS', 'default', {'confed_id': '0'})
    daemon.bgp_global_handler('BGP_GLOBALS', 'default',
                              {'confed_peers': ['65001', "65002' -c 'bad"]})
    daemon.bgp_neighbor_handler('BGP_NEIGHBOR', 'default|peer name', {'asn': '65001'})
    daemon.bgp_neighbor_handler('BGP_NEIGHBOR', 'default|10.0.0.1', {'asn': '65001x'})
    daemon.bgp_neighbor_handler('BGP_PEER_GROUP', 'default|PG1', {'local_asn': '0'})
    daemon.bgp_neighbor_handler('BGP_NEIGHBOR', 'default|10.0.0.1',
                                {'peer_group_name': "PG1' -c 'bad"})
    daemon.bgp_neighbor_handler('BGP_NEIGHBOR', 'default|10.0.0.1',
                                {'name': 'edge peer\nexit'})
    daemon.bgp_neighbor_handler('BGP_PEER_GROUP', 'default|PG1',
                                {'auth_password': 'secret\nexit'})
    daemon.bgp_table_handler_common('BGP_GLOBALS_LISTEN_PREFIX', 'default|10.0.0.0/24',
                                    {'peer_group': 'PG1\nbad'})
    run_cmd.assert_not_called()
    assert daemon.bgp_message.empty()
    assert not daemon.table_data_cache


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_empty_confed_peers_runtime_update_is_normalized(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    daemon = BGPConfigDaemon()
    update_bgp = MagicMock()
    daemon._BGPConfigDaemon__update_bgp = update_bgp

    daemon.bgp_global_handler(
        'BGP_GLOBALS', 'default',
        {'local_asn': '65000', 'confed_peers': ['']})

    key, del_table, table, data = daemon.bgp_message.get_nowait()
    assert (key, del_table, table) == ('default', False, 'BGP_GLOBALS')
    assert data['local_asn'].data == '65000'
    assert data['confed_peers'].data == []
    update_bgp.assert_called_once()


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_unified_replay_validates_bgp_keys_and_asns(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    daemon = BGPConfigDaemon()
    daemon.config_db.serialize_key.side_effect = (
        lambda key: '|'.join(key) if isinstance(key, tuple) else key)
    replay_entry = daemon._BGPConfigDaemon__replay_table_entry

    for table, key, data in (
            ('BGP_NEIGHBOR', ('vrf name', '10.0.0.1'), {'asn': '65001'}),
            ('BGP_NEIGHBOR', ('default', 'peer name'), {'asn': '65001'}),
            ('BGP_NEIGHBOR', ('default', '10.0.0.1'), {'asn': "65001' -c 'bad"}),
            ('BGP_NEIGHBOR', ('default', '10.0.0.1'),
             {'peer_group_name': "PG1' -c 'bad"}),
            ('BGP_NEIGHBOR', ('default', '10.0.0.1'),
             {'name': 'edge peer\nexit'}),
            ('BGP_GLOBALS_LISTEN_PREFIX', ('default', '10.0.0.0/24'),
             {'peer_group': 'PG1\nbad'}),
            ('BGP_GLOBALS', 'default', {'local_asn': '0'})):
        replay_entry(table, key, data)

    run_cmd.assert_not_called()
    assert daemon.bgp_message.empty()
    assert not daemon.table_data_cache

    update_bgp = MagicMock()
    daemon._BGPConfigDaemon__update_bgp = update_bgp
    replay_entry('BGP_NEIGHBOR', ('default', 'FC00:10::1'), {'asn': '65001'})
    key, del_table, table, data = daemon.bgp_message.get_nowait()
    assert (key, del_table, table) == ('default|fc00:10::1', False, 'BGP_NEIGHBOR')
    assert data['asn'].data == '65001'
    assert data['asn'].op == 1
    update_bgp.assert_called_once()

    update_bgp.reset_mock()
    replay_entry('BGP_GLOBALS', 'default',
                 {'local_asn': '65000', 'confed_peers': ['']})
    key, del_table, table, data = daemon.bgp_message.get_nowait()
    assert (key, del_table, table) == ('default', False, 'BGP_GLOBALS')
    assert data['local_asn'].data == '65000'
    assert data['confed_peers'].data == []
    update_bgp.assert_called_once()


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_dequeue_revalidates_dependent_bgp_updates(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon, CachedDataWithOp
    daemon = BGPConfigDaemon()
    daemon.config_db.serialize_key.side_effect = (
        lambda key: '|'.join(key) if isinstance(key, tuple) else key)
    daemon.config_db.get_table.return_value = {
        ('default', '10.0.0.0/24\nexit'): {'peer_group': 'PG1'},
    }
    apply_dep = daemon._BGPConfigDaemon__apply_dep_vrf_table
    update_bgp = daemon._BGPConfigDaemon__update_bgp

    apply_dep('default', 'BGP_GLOBALS_LISTEN_PREFIX',
              match=lambda data: data.get('peer_group') == 'PG1')
    changed = []
    update_bgp(changed)
    assert changed == []

    daemon.bgp_message.put((
        'default|10.0.0.1', False, 'BGP_NEIGHBOR',
        {'name': CachedDataWithOp('edge peer\nexit',
                                  CachedDataWithOp.OP_ADD)}))
    update_bgp(changed)
    assert changed == []
    run_cmd.assert_not_called()

class CmdMapTestInfo:
    data_buf = {}
    def __init__(self, table, key, data, exp_cmd, no_del = False, neg_cmd = None,
                 chk_data = None, daemons = None, ignore_tail = False):
        self.table_name = table
        self.key = key
        self.data = data
        self.vtysh_cmd = exp_cmd
        self.no_del = no_del
        self.vtysh_neg_cmd = neg_cmd
        self.chk_data = chk_data
        self.daemons = daemons
        self.ignore_tail = ignore_tail
    @classmethod
    def add_test_data(cls, test):
        assert(isinstance(test.data, dict))
        cls.data_buf.setdefault(
                test.table_name, {}).setdefault(test.key, {}).update(test.data)
    @classmethod
    def del_test_data(cls, test):
        assert(test.table_name in cls.data_buf and
               test.key in cls.data_buf[test.table_name])
        cache_data = cls.data_buf[test.table_name][test.key]
        assert(isinstance(test.data, dict))
        for k, v in test.data.items():
            assert(k in cache_data and cache_data[k] == v)
            del(cache_data[k])
    @classmethod
    def get_test_data(cls, test):
        assert(test.table_name in cls.data_buf and
               test.key in cls.data_buf[test.table_name])
        return copy.deepcopy(cls.data_buf[test.table_name][test.key])
    @staticmethod
    def compose_vtysh_cmd(cmd_list, negtive = False):
        result = ['vtysh']
        for cmd in cmd_list:
            cmd = cmd.format('no ' if negtive else '')
            result += ['-c', cmd]
        return result
    def check_running_cmd(self, mock, is_del):
        if is_del:
            vtysh_cmd = self.vtysh_cmd if self.vtysh_neg_cmd is None else self.vtysh_neg_cmd
        else:
            vtysh_cmd = self.vtysh_cmd
        if callable(vtysh_cmd):
            cmds = []
            for call in mock.call_args_list:
                assert(call[0][0] == self.table_name)
                cmds.append(call[0][1])
            vtysh_cmd(is_del, cmds, self.chk_data)
        else:
            if self.ignore_tail is None:
                mock.assert_called_with(self.table_name, self.compose_vtysh_cmd(vtysh_cmd, is_del),
                                        True, self.daemons)
            else:
                mock.assert_called_with(self.table_name, self.compose_vtysh_cmd(vtysh_cmd, is_del),
                                        True, self.daemons, self.ignore_tail)

def hdl_confed_peers_cmd(is_del, cmd_list, chk_data):
    assert(len(chk_data) >= len(cmd_list))
    if is_del:
        chk_data = list(reversed(chk_data))
    for idx, cmd in enumerate(cmd_list):
        # cmd is now a list: ['vtysh', '-c', ..., '-c', last_cmd]
        # Extract last -c value
        last_cmd = cmd[-1] if isinstance(cmd, list) else re.findall(r"-c\s+'([^']+)'\s*", cmd)[-1]
        neg_cmd = False
        if last_cmd.startswith('no '):
            neg_cmd = True
            last_cmd = last_cmd[len('no '):]
        assert(last_cmd.startswith('bgp confederation peers '))
        peer_set = set(last_cmd[len('bgp confederation peers '):].split())
        if is_del or (len(chk_data) >= 3 and idx == 0):
            assert(neg_cmd)
        else:
            assert(not neg_cmd)
        assert(peer_set == chk_data[idx])

conf_cmd = 'configure terminal'
conf_bgp_cmd = lambda vrf, asn: [conf_cmd, 'router bgp %d vrf %s' % (asn, vrf)]
conf_no_bgp_cmd = lambda vrf, asn: [conf_cmd, 'no router bgp %d%s' % (asn, '' if vrf == 'default' else ' vrf %s' % vrf)]
conf_bgp_dft_cmd = lambda vrf, asn: conf_bgp_cmd(vrf, asn) + ['no bgp default ipv4-unicast']
conf_bgp_af_cmd = lambda vrf, asn, af: conf_bgp_cmd(vrf, asn) + ['address-family %s %s' % (af, 'evpn' if af == 'l2vpn' else 'unicast')]

bgp_globals_data = [
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'local_asn': 100},
                       conf_bgp_dft_cmd('default', 100), False, conf_no_bgp_cmd('default', 100), None, None, None),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'router_id': '1.1.1.1'},
                       conf_bgp_cmd('default', 100) + ['{}bgp router-id 1.1.1.1']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'load_balance_mp_relax': 'true'},
                       conf_bgp_cmd('default', 100) + ['{}bgp bestpath as-path multipath-relax ']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'as_path_mp_as_set': 'true'},
                       conf_bgp_cmd('default', 100) + ['bgp bestpath as-path multipath-relax as-set'], False,
                       conf_bgp_cmd('default', 100) + ['bgp bestpath as-path multipath-relax ']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'always_compare_med': 'false'},
                       conf_bgp_cmd('default', 100) + ['no bgp always-compare-med']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'external_compare_router_id': 'true'},
                       conf_bgp_cmd('default', 100) + ['{}bgp bestpath compare-routerid']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'ignore_as_path_length': 'true'},
                       conf_bgp_cmd('default', 100) + ['{}bgp bestpath as-path ignore']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'graceful_restart_enable': 'true'},
                       conf_bgp_cmd('default', 100) + ['{}bgp graceful-restart']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'gr_restart_time': '10'},
                       conf_bgp_cmd('default', 100) + ['{}bgp graceful-restart restart-time 10']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'gr_stale_routes_time': '20'},
                       conf_bgp_cmd('default', 100) + ['{}bgp graceful-restart stalepath-time 20']),
        CmdMapTestInfo('BGP_GLOBALS', 'default', {'gr_preserve_fw_state': 'true'},
                       conf_bgp_cmd('default', 100) + ['{}bgp graceful-restart preserve-fw-state']),
        CmdMapTestInfo('BGP_GLOBALS_AF', 'default|ipv4_unicast', {'ebgp_route_distance': '100',
                                                                  'ibgp_route_distance': '115',
                                                                  'local_route_distance': '238'},
                       conf_bgp_af_cmd('default', 100, 'ipv4') + ['{}distance bgp 100 115 238']),
        CmdMapTestInfo('BGP_GLOBALS_AF', 'default|ipv6_unicast', {'autort': 'rfc8365-compatible'},
                       conf_bgp_af_cmd('default', 100, 'ipv6') + ['{}autort rfc8365-compatible']),
        CmdMapTestInfo('BGP_GLOBALS_AF', 'default|ipv6_unicast', {'advertise-all-vni': 'true'},
                       conf_bgp_af_cmd('default', 100, 'ipv6') + ['{}advertise-all-vni']),
        CmdMapTestInfo('BGP_GLOBALS_AF', 'default|ipv6_unicast', {'advertise-svi-ip': 'true'},
                       conf_bgp_af_cmd('default', 100, 'ipv6') + ['{}advertise-svi-ip']),
        CmdMapTestInfo('BGP_GLOBALS', 'Vrf_red', {'local_asn': 200},
                       conf_bgp_dft_cmd('Vrf_red', 200), False, conf_no_bgp_cmd('Vrf_red', 200), None, None, None),
        CmdMapTestInfo('BGP_GLOBALS', 'Vrf_red', {'med_confed': 'true'},
                       conf_bgp_cmd('Vrf_red', 200) + ['{}bgp bestpath med confed']),
        CmdMapTestInfo('BGP_GLOBALS', 'Vrf_red', {'confed_peers': ['2', '10', '5']},
                       hdl_confed_peers_cmd, True, None, [{'2', '10', '5'}]),
        CmdMapTestInfo('BGP_GLOBALS', 'Vrf_red', {'confed_peers': ['10', '8']},
                       hdl_confed_peers_cmd, False, None, [{'2', '5'}, {'8'}, {'10', '8'}]),
        CmdMapTestInfo('BGP_GLOBALS', 'Vrf_red', {'keepalive': '300', 'holdtime': '900'},
                       conf_bgp_cmd('Vrf_red', 200) + ['{}timers bgp 300 900']),
        CmdMapTestInfo('BGP_GLOBALS', 'Vrf_red', {'max_med_admin': 'true', 'max_med_admin_val': '20'},
                       conf_bgp_cmd('Vrf_red', 200) + ['{}bgp max-med administrative 20']),
        CmdMapTestInfo('BGP_GLOBALS_AF', 'Vrf_red|ipv4_unicast', {'import_vrf': 'Vrf_test'},
                       conf_bgp_af_cmd('Vrf_red', 200, 'ipv4') + ['{}import vrf Vrf_test']),
        CmdMapTestInfo('BGP_GLOBALS_AF', 'Vrf_red|ipv6_unicast', {'import_vrf_route_map': 'test_map'},
                       conf_bgp_af_cmd('Vrf_red', 200, 'ipv6') + ['{}import vrf route-map test_map']),
]

# Add admin status test cases for BGP_NEIGHBOR_AF and BGP_PEER_GROUP_AF
address_families = ['ipv4', 'ipv6', 'l2vpn']
admin_states = [
    ('true', '{}neighbor {} activate'),
    ('false', '{}no neighbor {} activate'),
    ('up', '{}neighbor {} activate'),
    ('down', '{}no neighbor {} activate')
]

def create_af_test_data(table_name):
    # Start with BGP globals setup
    test_data = [
        CmdMapTestInfo('BGP_GLOBALS', 'default',
                      {'local_asn': '100'},
                      conf_bgp_dft_cmd('default', 100),
                      ignore_tail=None)
    ]
    for af in address_families:
        af_key = f"{af}_{'evpn' if af == 'l2vpn' else 'unicast'}"
        if af == 'ipv4':
            entries = [('PG_IPV4_1', 'default')] if table_name == 'BGP_PEER_GROUP_AF' else \
                      [('10.0.0.1', 'default')]
        elif af == 'ipv6':
            entries = [('PG_IPV6_1', 'default')] if table_name == 'BGP_PEER_GROUP_AF' else \
                      [('2001:db8::1', 'default')]
        else:  # l2vpn case
            entries = [('PG_EVPN_1', 'default')] if table_name == 'BGP_PEER_GROUP_AF' else \
                      [('10.0.0.1', 'default')]

        for entry, vrf in entries:
            for status, cmd_template in admin_states:
                test_data.append(
                    CmdMapTestInfo(
                        table_name,
                        f'{vrf}|{entry}|{af_key}',
                        {'admin_status': status},
                        conf_bgp_af_cmd(vrf, 100, af) + [cmd_template.format('', entry)]
                    )
                )
    return test_data

# Create test data for both neighbor and peer group AF
neighbor_af_data = create_af_test_data('BGP_NEIGHBOR_AF')
peer_group_af_data = create_af_test_data('BGP_PEER_GROUP_AF')

# Create test data for neighbor shutdown
neighbor_shutdown_data = [
    # Set up BGP globals first
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  ignore_tail=None),
    # Then add neighbor shutdown configuration
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.1.1.1',
                  {'admin_status': 'down', 'shutdown_message': 'maintenance'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.1.1.1 shutdown message maintenance']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.1.1.2',
                  {'admin_status': 'false', 'shutdown_message': 'planned outage'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.1.1.2 shutdown message planned outage']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.1.1.4',
                  {'admin_status': 'up'},
                  conf_bgp_cmd('default', 100) + ['{}no neighbor 10.1.1.4 shutdown']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.1.1.5',
                  {'admin_status': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}no neighbor 10.1.1.5 shutdown'])
]

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def data_set_del_test(test_data, run_cmd, skip_del=False):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    daemon = BGPConfigDaemon()
    data_buf = {}
    # add data in list
    for test in test_data:
        run_cmd.reset_mock()
        hdlr = [h for t, h in daemon.table_handler_list if t == test.table_name]
        assert(len(hdlr) == 1)
        CmdMapTestInfo.add_test_data(test)
        hdlr[0](test.table_name, test.key, CmdMapTestInfo.get_test_data(test))
        test.check_running_cmd(run_cmd, False)

    if skip_del:
        return

    # delete data in reverse direction
    for test in reversed(test_data):
        if test.no_del:
            continue
        run_cmd.reset_mock()
        hdlr = [h for t, h in daemon.table_handler_list if t == test.table_name]
        assert(len(hdlr) == 1)
        CmdMapTestInfo.del_test_data(test)
        hdlr[0](test.table_name, test.key, CmdMapTestInfo.get_test_data(test))
        test.check_running_cmd(run_cmd, True)

def test_bgp_globals():
    data_set_del_test(bgp_globals_data)

def test_bgp_neighbor_af():
    # The neighbor AF test cases explicitly verify delete behavior, so skip the delete
    # verification data_set_del_test (else it would try the del of 'no ' commands as well and fail)
    data_set_del_test(neighbor_af_data, skip_del=True)

def test_bgp_peer_group_af():
    # The peer group AF test cases explicitly verify delete behavior, so skip the delete
    # verification data_set_del_test (else it would try the del of 'no ' commands as well and fail)
    data_set_del_test(peer_group_af_data, skip_del=True)

def test_bgp_neighbor_shutdown():
    # The neighbor shutdown msg test cases explicitly verify delete behavior, so skip the delete
    # verification data_set_del_test (else it would try the del of 'no ' commands as well and fail)
    data_set_del_test(neighbor_shutdown_data, skip_del=True)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_neighbor_description_injection(run_cmd):
    """Regression test: shell metacharacters in BGP_NEIGHBOR description must be
    passed as a literal vtysh argument, not interpreted by a shell."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    daemon = BGPConfigDaemon()

    # Seed BGP_GLOBALS to set local ASN (reuse existing test data)
    globals_seed = bgp_globals_data[0]  # local_asn = 100
    CmdMapTestInfo.add_test_data(globals_seed)
    bgp_globals_hdlr = [h for t, h in daemon.table_handler_list if t == 'BGP_GLOBALS'][0]
    bgp_globals_hdlr('BGP_GLOBALS', globals_seed.key, CmdMapTestInfo.get_test_data(globals_seed))

    # Now test BGP_NEIGHBOR description with injection payload
    injection_payload = "'; id #"
    run_cmd.reset_mock()
    nbr_test = CmdMapTestInfo(
        'BGP_NEIGHBOR', 'default|10.0.0.1',
        {'name': injection_payload},
        conf_bgp_cmd('default', 100) + [
            'neighbor 10.0.0.1 description {}'.format(injection_payload)
        ]
    )
    CmdMapTestInfo.add_test_data(nbr_test)
    nbr_hdlr = [h for t, h in daemon.table_handler_list if t == 'BGP_NEIGHBOR'][0]
    nbr_hdlr('BGP_NEIGHBOR', nbr_test.key, CmdMapTestInfo.get_test_data(nbr_test))

    # Verify g_run_command was called with a list (shell=False path)
    assert run_cmd.called, "g_run_command was not called for BGP_NEIGHBOR description"
    for call in run_cmd.call_args_list:
        cmd = call[0][1]
        assert isinstance(cmd, list), \
            "command must be a list (shell=False), got string: {}".format(cmd)
        if any('description' in arg for arg in cmd):
            assert any(injection_payload in arg for arg in cmd), \
                "injection payload not found as literal arg: {}".format(cmd)
<<<<<<< HEAD
=======
# ========== Per-Flow CP Tests ==========


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_cp_emitted_without_segment_list(run_cmd):
    """type=per-flow CP is emitted immediately on receipt (no segment-list wait)."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(hdlr) == 1)

    # Pre-create the parent SR Policy so the handler doesn't reject the CP set
    test_pol = CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1',
        {'name': 'parent_pf'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 300 endpoint 2001:db8::1', 'name parent_pf'],
        no_del=True, ignore_tail=None)
    CmdMapTestInfo.add_test_data(test_pol)
    hdlr[0]('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(test_pol))
    run_cmd.reset_mock()

    test_cp = CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1|100',
        {'name': 'cp_pf', 'type': 'per-flow'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 300 endpoint 2001:db8::1',
         'candidate-path preference 100 name cp_pf per-flow', 'exit'],
        ignore_tail=None)
    CmdMapTestInfo.add_test_data(test_cp)
    hdlr[0]('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(test_cp))
    test_cp.check_running_cmd(run_cmd, False)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_fc_numeric_entry(run_cmd):
    """forwarding-class N color M is emitted for a numeric FC entry."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY'][0]
    pf_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY_CANDIDATE_PATH_PER_FLOW'][0]

    # Set up parent policy + per-flow CP
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1', {'name': 'parent'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1', {}, [], no_del=True, ignore_tail=None)))

    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1|100',
        {'name': 'cp_pf', 'type': 'per-flow'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {}, [], no_del=True, ignore_tail=None)))
    run_cmd.reset_mock()

    # FC=1 -> color 100
    test_fc = CmdMapTestInfo(
        'SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|1',
        {'next_color': '100'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 300 endpoint 2001:db8::1',
         'candidate-path preference 100 name cp_pf per-flow',
         'forwarding-class 1 color 100', 'exit'],
        ignore_tail=None)
    CmdMapTestInfo.add_test_data(test_fc)
    pf_hdlr('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|1',
            CmdMapTestInfo.get_test_data(test_fc))
    test_fc.check_running_cmd(run_cmd, False)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_fc_default_best_effort(run_cmd):
    """Default bucket with action_best_effort emits 'forwarding-class default action best-effort'."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY'][0]
    pf_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY_CANDIDATE_PATH_PER_FLOW'][0]

    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1', {'name': 'parent'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1', {}, [], no_del=True, ignore_tail=None)))
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1|100',
        {'name': 'cp_pf', 'type': 'per-flow'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {}, [], no_del=True, ignore_tail=None)))
    run_cmd.reset_mock()

    test_fc = CmdMapTestInfo(
        'SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|0',
        {'action_best_effort': 'true'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 300 endpoint 2001:db8::1',
         'candidate-path preference 100 name cp_pf per-flow',
         'forwarding-class default action best-effort', 'exit'],
        ignore_tail=None)
    CmdMapTestInfo.add_test_data(test_fc)
    pf_hdlr('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|0',
            CmdMapTestInfo.get_test_data(test_fc))
    test_fc.check_running_cmd(run_cmd, False)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_fc_default_color(run_cmd):
    """Default bucket with next_color emits 'forwarding-class default color N'."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY'][0]
    pf_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY_CANDIDATE_PATH_PER_FLOW'][0]

    CmdMapTestInfo.data_buf.clear()
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1', {'name': 'parent'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1', {}, [], no_del=True, ignore_tail=None)))
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1|100',
        {'name': 'cp_pf_color', 'type': 'per-flow'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {}, [], no_del=True, ignore_tail=None)))
    run_cmd.reset_mock()

    test_fc = CmdMapTestInfo(
        'SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|0',
        {'next_color': '50'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 300 endpoint 2001:db8::1',
         'candidate-path preference 100 name cp_pf_color per-flow',
         'forwarding-class default color 50', 'exit'],
        ignore_tail=None)
    CmdMapTestInfo.add_test_data(test_fc)
    pf_hdlr('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|0',
            CmdMapTestInfo.get_test_data(test_fc))
    test_fc.check_running_cmd(run_cmd, False)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_fc_before_cp(run_cmd):
    """FC entry arriving before the parent CP is cached (no vtysh) and replayed."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY'][0]
    pf_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY_CANDIDATE_PATH_PER_FLOW'][0]

    # Parent policy exists; CP does not yet
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1', {'name': 'parent'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1', {}, [], no_del=True, ignore_tail=None)))
    run_cmd.reset_mock()

    # FC entry arrives early — should be cached, no vtysh issued
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|2',
        {'next_color': '200'}, [], no_del=True, ignore_tail=None))
    pf_hdlr('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|2',
            CmdMapTestInfo.get_test_data(
                CmdMapTestInfo('SR_POLICY_CANDIDATE_PATH_PER_FLOW',
                               '300|2001:db8::1|100|2', {}, [], no_del=True, ignore_tail=None)))
    run_cmd.assert_not_called()

    # Now parent CP arrives — emit creation + cached FC entry in one batch
    test_cp = CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1|100',
        {'name': 'cp_pf', 'type': 'per-flow'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 300 endpoint 2001:db8::1',
         'candidate-path preference 100 name cp_pf per-flow',
         'forwarding-class 2 color 200', 'exit'],
        ignore_tail=None)
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(test_cp))
    test_cp.check_running_cmd(run_cmd, False)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_fc_delete(run_cmd):
    """DEL on an FC entry emits 'no forwarding-class N'."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY'][0]
    pf_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY_CANDIDATE_PATH_PER_FLOW'][0]

    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1', {'name': 'parent'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1', {}, [], no_del=True, ignore_tail=None)))
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1|100',
        {'name': 'cp_pf', 'type': 'per-flow'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {}, [], no_del=True, ignore_tail=None)))
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|1',
        {'next_color': '100'}, [], no_del=True, ignore_tail=None))
    pf_hdlr('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|1',
            CmdMapTestInfo.get_test_data(
                CmdMapTestInfo('SR_POLICY_CANDIDATE_PATH_PER_FLOW',
                               '300|2001:db8::1|100|1', {}, [], no_del=True, ignore_tail=None)))
    run_cmd.reset_mock()

    test_del = CmdMapTestInfo(
        'SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|1',
        {},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 300 endpoint 2001:db8::1',
         'candidate-path preference 100 name cp_pf per-flow',
         'no forwarding-class 1', 'exit'],
        ignore_tail=None)
    pf_hdlr('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|1', None)
    test_del.check_running_cmd(run_cmd, False)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_hostile_cp_name_rejected(run_cmd):
    """N10: M4 hardening — names with shell metacharacters / spaces must
    be rejected by _sr_validate_cp_name; assert run_cmd is never called.
    """
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY'][0]

    # Parent policy must exist so the CP set goes through to the name check
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1',
        {'name': 'parent'}, [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1', {}, [], no_del=True, ignore_tail=None)))

    hostile_names = [
        "name with spaces",
        "name;rm -rf /",
        "name'$(whoami)'",
        "name`pwd`",
        "name|cat /etc/passwd",
        "",                              # empty
        "a" * 300,                       # over max length
    ]
    for hostile in hostile_names:
        run_cmd.reset_mock()
        CmdMapTestInfo.add_test_data(CmdMapTestInfo(
            'SR_POLICY', '300|2001:db8::1|100',
            {'name': hostile, 'type': 'per-flow'},
            [], no_del=True, ignore_tail=None))
        pol_hdlr('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(
            CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {}, [], no_del=True, ignore_tail=None)))
        # _sr_validate_cp_name must bail BEFORE _emit_sr_per_flow_cp runs vtysh.
        # Positively asserting call_count==0 catches "escaped instead of rejected" regressions.
        assert run_cmd.call_count == 0, (
            f"hostile name {hostile!r} reached vtysh: "
            f"{[c[0][1] for c in run_cmd.call_args_list]}"
        )
        # Clean cache between iterations
        CmdMapTestInfo.del_test_data(CmdMapTestInfo(
            'SR_POLICY', '300|2001:db8::1|100',
            {'name': hostile, 'type': 'per-flow'}, [], no_del=True, ignore_tail=None))

    # Control: a valid name DOES emit vtysh — proves the test catches a
    # regression that strips validation outright.
    run_cmd.reset_mock()
    CmdMapTestInfo.add_test_data(CmdMapTestInfo(
        'SR_POLICY', '300|2001:db8::1|100',
        {'name': 'valid_cp_name', 'type': 'per-flow'},
        [], no_del=True, ignore_tail=None))
    pol_hdlr('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(
        CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {}, [], no_del=True, ignore_tail=None)))
    assert run_cmd.call_count >= 1, "control: a valid name must produce vtysh output"


# Hardware BFD offload (NOS-12951): bare/partial BFD enables merge per-field
# offload defaults (3/1000/1000); a complete set passes through unchanged.
bgp_neighbor_bfd_hw_offload_data = [
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  True, None, None, None, None),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.9.9.1',
                  {'bfd': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.9.9.1 bfd 3 1000 1000'],
                  False,
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.9.9.1 bfd']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.9.9.2',
                  {'bfd': 'true', 'bfd_min_rx': '100'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.9.9.2 bfd 3 100 1000'],
                  False,
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.9.9.2 bfd']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.9.9.3',
                  {'bfd': 'true', 'bfd_detect_multiplier': '5', 'bfd_min_rx': '100', 'bfd_min_tx': '100'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.9.9.3 bfd 5 100 100'],
                  False,
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.9.9.3 bfd']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.9.9.4',
                  {'bfd': 'true', 'bfd_detect_multiplier': '5', 'bfd_min_tx': '100'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.9.9.4 bfd 5 1000 100'],
                  False,
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.9.9.4 bfd']),
    # bfd_profile takes precedence over the HW-offload synthetic timers:
    # the profile branch returns before the offload merge, so the two-step
    # bfd + bfd-profile emission appears and no inline timer command does
    # (unified-mode twin of bgpcfgd's test_change_bfd_hw_offload_profile_wins;
    # validator shared with the non-offload profile data sets).
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.9.9.5',
                  {'bfd': 'true', 'bfd_profile': 'fast-failover'},
                  hdl_bfd_profile_cmd, False, None,
                  ('10.9.9.5', 'fast-failover')),
]

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.BGPConfigDaemon._detect_hw_bfd_offload', return_value=True)
def test_bgp_neighbor_bfd_hw_offload_defaults(mock_detect):
    """Under HW offload bare/partial bfd enables merge offload defaults."""
    data_set_del_test(bgp_neighbor_bfd_hw_offload_data)


# Standalone BFD peer tables under hardware BFD offload (NOS-14849): absent
# interval timers must be programmed as 1000 ms instead of inheriting FRR's
# 300 ms default, and the synthetic fields must never enter the table cache.

def _all_pushed_cmds(run_cmd):
    return [arg for call in run_cmd.call_args_list for arg in call.args[1]]


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.BGPConfigDaemon._detect_hw_bfd_offload', return_value=True)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bfd_mhop_unset_timers_hw_offload_injects_defaults(run_cmd, mock_detect):
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'BFD_PEER_MULTI_HOP'][0]
    key = '210.1.1.1|null|Vrf1|170.1.1.1'
    run_cmd.reset_mock()

    hdlr('BFD_PEER_MULTI_HOP', key, {'enabled': 'true'})

    cmds = _all_pushed_cmds(run_cmd)
    assert 'transmit-interval 1000' in cmds
    assert 'receive-interval 1000' in cmds
    assert 'no shutdown' in cmds
    table_key = ExtConfigDBConnector.get_table_key('BFD_PEER_MULTI_HOP', key)
    assert daemon.table_data_cache.get(table_key) == {'enabled': 'true'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.BGPConfigDaemon._detect_hw_bfd_offload', return_value=True)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bfd_shop_unset_timers_hw_offload_injects_defaults(run_cmd, mock_detect):
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'BFD_PEER_SINGLE_HOP'][0]
    key = '10.0.0.1|Ethernet0|default|192.0.2.1'
    run_cmd.reset_mock()

    hdlr('BFD_PEER_SINGLE_HOP', key, {'enabled': 'true'})

    cmds = _all_pushed_cmds(run_cmd)
    assert 'transmit-interval 1000' in cmds
    assert 'receive-interval 1000' in cmds
    table_key = ExtConfigDBConnector.get_table_key('BFD_PEER_SINGLE_HOP', key)
    assert daemon.table_data_cache.get(table_key) == {'enabled': 'true'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.BGPConfigDaemon._detect_hw_bfd_offload', return_value=True)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bfd_mhop_partial_timers_hw_offload_injects_missing_only(run_cmd, mock_detect):
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'BFD_PEER_MULTI_HOP'][0]
    key = '210.1.1.1|null|Vrf1|170.1.1.1'
    run_cmd.reset_mock()

    hdlr('BFD_PEER_MULTI_HOP', key, {'desired-minimum-tx-interval': '100'})

    cmds = _all_pushed_cmds(run_cmd)
    assert 'transmit-interval 100' in cmds
    assert 'receive-interval 1000' in cmds
    assert 'transmit-interval 1000' not in cmds
    table_key = ExtConfigDBConnector.get_table_key('BFD_PEER_MULTI_HOP', key)
    assert daemon.table_data_cache.get(table_key) == {
        'desired-minimum-tx-interval': '100'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.BGPConfigDaemon._detect_hw_bfd_offload', return_value=True)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bfd_mhop_timer_delete_hw_offload_reprograms_default(run_cmd, mock_detect):
    # Removing a timer field must re-program the 1000 ms offload default, not
    # revert to FRR's 300 ms via __bfd_handle_delete / 'no transmit-interval'.
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'BFD_PEER_MULTI_HOP'][0]
    key = '210.1.1.1|null|Vrf1|170.1.1.1'

    hdlr('BFD_PEER_MULTI_HOP', key, {'desired-minimum-tx-interval': '100'})
    run_cmd.reset_mock()

    hdlr('BFD_PEER_MULTI_HOP', key, {'enabled': 'true'})

    cmds = _all_pushed_cmds(run_cmd)
    assert 'transmit-interval 1000' in cmds
    assert 'transmit-interval 300' not in cmds
    assert not any(c.startswith('no transmit-interval') for c in cmds)
    table_key = ExtConfigDBConnector.get_table_key('BFD_PEER_MULTI_HOP', key)
    assert daemon.table_data_cache.get(table_key) == {'enabled': 'true'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.BGPConfigDaemon._detect_hw_bfd_offload', return_value=True)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bfd_mhop_explicit_unsupported_timer_hw_offload_clamped(run_cmd, mock_detect):
    # A present-but-unsupported interval (direct CONFIG_DB write bypassing
    # YANG) must be clamped to 1000 at runtime, matching the cold-boot render;
    # the cache keeps the CONFIG_DB value so later diffs stay correct.
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'BFD_PEER_MULTI_HOP'][0]
    key = '210.1.1.1|null|Vrf1|170.1.1.1'
    run_cmd.reset_mock()

    hdlr('BFD_PEER_MULTI_HOP', key,
         {'enabled': 'true', 'desired-minimum-tx-interval': '300'})

    cmds = _all_pushed_cmds(run_cmd)
    assert 'transmit-interval 1000' in cmds
    assert 'transmit-interval 300' not in cmds
    assert 'receive-interval 1000' in cmds
    table_key = ExtConfigDBConnector.get_table_key('BFD_PEER_MULTI_HOP', key)
    assert daemon.table_data_cache.get(table_key) == {
        'enabled': 'true', 'desired-minimum-tx-interval': '300'}

    # An unrelated update on the row must re-clamp (the stale 300 is OP_NONE
    # then), never re-push 300.
    run_cmd.reset_mock()
    hdlr('BFD_PEER_MULTI_HOP', key,
         {'enabled': 'false', 'desired-minimum-tx-interval': '300'})

    cmds = _all_pushed_cmds(run_cmd)
    assert 'transmit-interval 1000' in cmds
    assert 'transmit-interval 300' not in cmds
    assert daemon.table_data_cache.get(table_key) == {
        'enabled': 'false', 'desired-minimum-tx-interval': '300'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_vni_pushed_and_removed(run_cmd):
    """vrf_handler emits the L3VNI binding on set and withdraws it on clear (NOS-17464).

    The handler had no behavioral coverage, so nothing pinned which commands it
    produces -- only that the table constant said 'mgmtd'.
    """
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'VRF'][0]

    hdlr('VRF', 'Vrf_RED', {'vni': '10300'})
    cmds = _all_pushed_cmds(run_cmd)
    assert 'vrf Vrf_RED' in cmds
    assert 'vni 10300' in cmds
    assert daemon.vrf_vni_map['Vrf_RED'] == '10300'
    # The routing decision rides on these two args, and they are the seam
    # between this test and test_vrf_commands_resolve_to_mgmtd: the table name
    # is what resolves through TABLE_DAEMON, and daemons=None is what says
    # "don't override it". Without these, vrf_handler could pass a different
    # table string or an explicit daemon list and both tests would still pass.
    assert run_cmd.call_args.args[0] == 'VRF'
    assert run_cmd.call_args.args[3] is None

    # vni 0 means unset: the withdrawal carries the previously-applied value,
    # not 0, so it has to come from vrf_vni_map rather than from the new row.
    run_cmd.reset_mock()
    hdlr('VRF', 'Vrf_RED', {'vni': '0'})
    cmds = _all_pushed_cmds(run_cmd)
    assert 'no vni 10300' in cmds
    assert 'Vrf_RED' not in daemon.vrf_vni_map

    # Deleting the row withdraws a live binding the same way.
    run_cmd.reset_mock()
    hdlr('VRF', 'Vrf_BLUE', {'vni': '10400'})
    run_cmd.reset_mock()
    hdlr('VRF', 'Vrf_BLUE', {})
    cmds = _all_pushed_cmds(run_cmd)
    assert 'no vni 10400' in cmds
    assert 'Vrf_BLUE' not in daemon.vrf_vni_map

    # A row with no vni at all is not a VRF/VNI operation -- nothing is pushed.
    run_cmd.reset_mock()
    hdlr('VRF', 'Vrf_GREEN', {'fallback': 'false'})
    assert run_cmd.call_count == 0


@patch.dict('sys.modules', **mockmapping)
def test_vrf_commands_resolve_to_mgmtd():
    """The VRF table's commands reach mgmtd's socket, not zebra's (NOS-17464).

    zebra's vty answers 'mgmtd is not running' and frrcfgd logs that at
    LOG_DEBUG, so a wrong daemon here is silent. Driving run_vtysh_command is
    what catches it; asserting TABLE_DAEMON against itself is not.
    """
    import threading
    from frrcfgd.frrcfgd import BgpdClientMgr

    # __init__ opens sockets to FRR, so build the instance without it and
    # supply only what run_vtysh_command touches.
    mgr = BgpdClientMgr.__new__(BgpdClientMgr)
    mgr.lock = threading.Lock()

    seen = []
    with patch.object(BgpdClientMgr, '_BgpdClientMgr__proc_command',
                      side_effect=lambda cmd, daemons: (seen.append((cmd, daemons)), (True, ''))[1]):
        assert mgr.run_vtysh_command(
            'VRF',
            ['vtysh', '-c', 'configure terminal', '-c', 'vrf Vrf_RED', '-c', 'vni 10300'],
            None)

    assert ('vni 10300', ['mgmtd']) in seen
    assert all(daemons == ['mgmtd'] for _, daemons in seen)
def _feed_table(daemon, run_cmd, table, key, data):
    """Drive one table handler and return the vtysh commands it emitted."""
    run_cmd.reset_mock()
    hdlr = [h for t, h in daemon.table_handler_list if t == table][0]
    hdlr(table, key, data)
    return [' '.join(call[0][1]) for call in run_cmd.call_args_list]

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_cache_dropped_on_bgp_delete(run_cmd):
    """'no router bgp' removes every VRF-scoped table from FRR in one command,
    so their cached rows have to go too. Left behind, they claim values FRR no
    longer holds, and the re-create below diffs against them and emits nothing:
    scalars like rd are diffed against the same cache, so the whole row is lost,
    not just its route-target leaf-lists."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    feed = partial(_feed_table, daemon, run_cmd)

    vni_key = 'default|L2VPN_EVPN|10100'
    vni_data = {'route-distinguisher': '10.1.0.101:10100',
                'import-rts': ['65101:10100'],
                'export-rts': ['65101:10100']}

    feed('BGP_GLOBALS', 'default', {'local_asn': '65101'})
    assert feed('BGP_GLOBALS_EVPN_VNI', vni_key, dict(vni_data))

    feed('BGP_GLOBALS', 'default', {})
    assert not [k for k in daemon.table_data_cache if k.startswith('BGP_GLOBALS_EVPN_VNI&&')]

    feed('BGP_GLOBALS', 'default', {'local_asn': '65101'})
    cmds = ' '.join(feed('BGP_GLOBALS_EVPN_VNI', vni_key, dict(vni_data)))
    assert 'route-target import 65101:10100' in cmds
    assert 'route-target export 65101:10100' in cmds
    assert 'rd 10.1.0.101:10100' in cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_cache_drop_is_scoped_to_its_own_vrf(run_cmd):
    """Deleting one VRF must not evict another VRF's cached rows."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    feed = partial(_feed_table, daemon, run_cmd)

    vni_data = {'route-distinguisher': '10.1.0.101:10100',
                'import-rts': ['65101:10100']}
    for vrf, asn in (('default', '65101'), ('Vrf_RED', '65102')):
        feed('BGP_GLOBALS', vrf, {'local_asn': asn})
        feed('BGP_GLOBALS_EVPN_VNI', '{}|L2VPN_EVPN|10100'.format(vrf), dict(vni_data))

    feed('BGP_GLOBALS', 'default', {})

    remaining = [k for k in daemon.table_data_cache if k.startswith('BGP_GLOBALS_EVPN_VNI&&')]
    assert remaining == ['BGP_GLOBALS_EVPN_VNI&&Vrf_RED|L2VPN_EVPN|10100']


@pytest.mark.parametrize('vrf, asn', [('default', '65101'), ('Vrf-rt', '65100')])
@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_cache_dropped_for_bgp_globals_af(run_cmd, vrf, asn):
    """BGP_GLOBALS_AF has carried import-rts/export-rts far longer than the EVPN
    tables, and is stale by the same mechanism. Covered separately so the fix is
    not read as EVPN-specific, and for a tenant VRF as well as 'default', since
    that is the shape reproduced on hardware for NOS-17644."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    feed = partial(_feed_table, daemon, run_cmd)

    af_key = '{}|l2vpn_evpn'.format(vrf)
    rt = '{}:10100'.format(asn)
    af_data = {'route-distinguisher': '10.1.0.101:10100',
               'import-rts': [rt], 'export-rts': [rt]}

    feed('BGP_GLOBALS', vrf, {'local_asn': asn})
    assert feed('BGP_GLOBALS_AF', af_key, dict(af_data))

    # None takes the del_table branch, which is the path an actual CONFIG_DB
    # row removal follows; the other two tests cover the local_asn OP_DELETE
    # branch with {}.
    feed('BGP_GLOBALS', vrf, None)
    assert not [k for k in daemon.table_data_cache
                if k.startswith('BGP_GLOBALS_AF&&{}|'.format(vrf))]

    feed('BGP_GLOBALS', vrf, {'local_asn': asn})
    cmds = ' '.join(feed('BGP_GLOBALS_AF', af_key, dict(af_data)))
    assert 'router bgp {} vrf {}'.format(asn, vrf) in cmds
    assert 'rd 10.1.0.101:10100' in cmds
    assert 'route-target import {}'.format(rt) in cmds
    assert 'route-target export {}'.format(rt) in cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_cache_rt_added_after_recreate(run_cmd):
    """Adding a route-target to a re-created list is how the stale cache shows up
    in practice: without the purge the re-create emits nothing and the update
    emits only the new target, so the original one never reaches FRR."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)

    af_key = 'Vrf-rt|l2vpn_evpn'
    feed('BGP_GLOBALS', 'Vrf-rt', {'local_asn': '65100'})
    feed('BGP_GLOBALS_AF', af_key, {'import-rts': ['65100:10100']})
    feed('BGP_GLOBALS', 'Vrf-rt', None)
    feed('BGP_GLOBALS', 'Vrf-rt', {'local_asn': '65100'})

    cmds = feed('BGP_GLOBALS_AF', af_key, {'import-rts': ['65100:10100']})
    cmds += feed('BGP_GLOBALS_AF', af_key, {'import-rts': ['65100:10100', '65100:77777']})
    # Replay in order: a target pushed and later withdrawn must not count.
    imported = set()
    for no, rt in re.findall(r'(no )?route-target import (\S+)', ' '.join(cmds)):
        (imported.discard if no else imported.add)(rt)
    assert imported == {'65100:10100', '65100:77777'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_peer_group_state_dropped_on_bgp_delete(run_cmd):
    """'no router bgp' destroys peer-groups along with everything else, but
    bgp_peer_group kept remembering them. A remembered name suppresses the
    'neighbor <pg> peer-group' creation on re-create, and FRR then rejects every
    follow-on attribute command for a peer-group that does not exist."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)

    feed('BGP_GLOBALS', 'default', {'local_asn': '65101'})
    assert 'neighbor PG1 peer-group' in ' '.join(
        feed('BGP_PEER_GROUP', 'default|PG1', {'admin_status': 'true'}))
    assert 'PG1' in daemon.bgp_peer_group.get('default', {})

    feed('BGP_GLOBALS', 'default', None)
    assert 'default' not in daemon.bgp_peer_group

    feed('BGP_GLOBALS', 'default', {'local_asn': '65101'})
    assert 'neighbor PG1 peer-group' in ' '.join(
        feed('BGP_PEER_GROUP', 'default|PG1', {'admin_status': 'true'}))


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_confed_peers_state_dropped_on_bgp_delete(run_cmd):
    """hdl_confed_peers diffs against bgp_confed_peers by way of
    upd_confed_peers, which __update_bgp seeds from it and writes back to, so a
    stale entry suppresses the re-created peers exactly as a stale cache row
    suppresses a leaf-list."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)

    feed('BGP_GLOBALS', 'default', {'local_asn': '65101'})
    assert 'confederation peers' in ' '.join(
        feed('BGP_GLOBALS', 'default', {'local_asn': '65101', 'confed_peers': ['10', '20']}))
    assert daemon.bgp_confed_peers.get('default')

    feed('BGP_GLOBALS', 'default', None)
    assert 'default' not in daemon.bgp_confed_peers

    feed('BGP_GLOBALS', 'default', {'local_asn': '65101'})
    assert 'confederation peers' in ' '.join(
        feed('BGP_GLOBALS', 'default', {'local_asn': '65101', 'confed_peers': ['10', '20']}))


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_state_drop_is_scoped_to_its_own_vrf(run_cmd):
    """Deleting one VRF must not evict another VRF's peer-group or unnumbered
    neighbor state, the same way it must not evict its cached rows. Both are
    asserted -- bgp_peer_group and bgp_intf_nbr."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)

    for vrf, asn in (('default', '65101'), ('Vrf_RED', '65102')):
        feed('BGP_GLOBALS', vrf, {'local_asn': asn})
        feed('BGP_PEER_GROUP', '{}|PG1'.format(vrf), {'admin_status': 'true'})
        feed('BGP_NEIGHBOR', '{}|Ethernet0'.format(vrf), {'admin_status': 'true'})

    assert 'Ethernet0' in daemon.bgp_intf_nbr.get('default', set())

    feed('BGP_GLOBALS', 'default', None)

    assert 'default' not in daemon.bgp_peer_group
    assert 'default' not in daemon.bgp_intf_nbr
    assert 'PG1' in daemon.bgp_peer_group.get('Vrf_RED', {})
    assert 'Ethernet0' in daemon.bgp_intf_nbr.get('Vrf_RED', set())


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_aggregate_state_dropped_on_bgp_delete(run_cmd):
    """Purging the cache is what exposes af_aggr_list. With the cached row gone
    the aggregate re-emits, and a stale af_aggr_list makes hdl_af_aggregate
    prepend 'no aggregate-address' for an aggregate FRR no longer has. FRR
    rejects it, BGPKeyMapList.run_command breaks on the first failure, and the
    real aggregate-address never runs."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)

    key = 'default|ipv4_unicast|192.168.1.0/24'
    feed('BGP_GLOBALS', 'default', {'local_asn': '65101'})
    assert feed('BGP_GLOBALS_AF_AGGREGATE_ADDR', key, {'as_set': 'true'})
    assert '192.168.1.0/24' in daemon.af_aggr_list.get('default', {})

    feed('BGP_GLOBALS', 'default', None)
    assert 'default' not in daemon.af_aggr_list

    feed('BGP_GLOBALS', 'default', {'local_asn': '65101'})
    cmds = ' '.join(feed('BGP_GLOBALS_AF_AGGREGATE_ADDR', key, {'as_set': 'true'}))
    assert 'aggregate-address 192.168.1.0/24' in cmds
    assert 'no aggregate-address' not in cmds
>>>>>>> de5fb8890 (Purge a VRF's cached child rows when its BGP instance is removed)
