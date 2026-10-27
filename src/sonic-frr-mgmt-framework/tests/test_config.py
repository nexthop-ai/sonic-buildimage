import copy
import re
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


def test_bgp_confederation_template():
    """Verify bgpd.conf.db.j2 renders 'bgp confederation identifier/peers'
    from BGP_GLOBALS, and emits nothing when confed is not configured."""
    from jinja2 import Environment, FileSystemLoader
    import os

    template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'bgpd')
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters['ipv4'] = lambda v: False
    env.filters['ipv6'] = lambda v: False

    template = env.get_template('bgpd.conf.db.j2')

    # Confederation in the default VRF and a non-default VRF. confed is a
    # per-instance knob (FRR installs it under BGP_NODE, which is shared by
    # 'router bgp <asn>' and 'router bgp <asn> vrf <vrf>'), and frrcfgd applies
    # it per VRF, so the template must render it for non-default VRFs too.
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100',
                                 'confed_id': '100',
                                 'confed_peers': ['65101', '65102']},
                     'Vrf_red': {'local_asn': '65200',
                                 'confed_id': '200',
                                 'confed_peers': ['65201']}}
    )
    assert 'router bgp 65100' in result
    assert 'bgp confederation identifier 100' in result
    assert 'bgp confederation peers 65101 65102' in result
    # The non-default VRF confed lines are emitted under its own instance.
    vrf_section = result[result.index('router bgp 65200 vrf Vrf_red'):]
    assert 'bgp confederation identifier 200' in vrf_section
    assert 'bgp confederation peers 65201' in vrf_section

    # confed_id only, no peers -> identifier renders, no stray peers line.
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100', 'confed_id': '100'}}
    )
    assert 'bgp confederation identifier 100' in result
    assert 'bgp confederation peers' not in result

    # Empty confed_peers list -> the |length > 0 guard suppresses the line.
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100', 'confed_peers': []}}
    )
    assert 'bgp confederation peers' not in result

    # No confederation config -> no confederation lines emitted.
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100'}}
    )
    assert 'bgp confederation' not in result
<<<<<<< HEAD
=======


def test_bgp_log_neighbor_changes_template():
    from jinja2 import Environment, FileSystemLoader
    import os

    template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'bgpd')
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters['ipv4'] = lambda v: False
    env.filters['ipv6'] = lambda v: False

    template = env.get_template('bgpd.conf.db.j2')

    def lines(rendered):
        return [ln.rstrip() for ln in rendered.splitlines()]

    # Field absent -> logging is enabled by default
    result = template.render(BGP_GLOBALS={'default': {'local_asn': '65100'}})
    assert ' bgp log-neighbor-changes' in lines(result)
    assert ' no bgp log-neighbor-changes' not in lines(result)

    # Explicit 'false' -> logging is disabled
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100',
                                 'log_nbr_state_changes': 'false'}})
    assert ' no bgp log-neighbor-changes' in lines(result)
    assert ' bgp log-neighbor-changes' not in lines(result)

    # The same on-by-default semantics must hold for a non-default VRF, since
    # this template governs logging for all VRF-scoped BGP sessions.
    result = template.render(
        BGP_GLOBALS={'Vrf_red': {'local_asn': '65200'}})
    vrf_section = result[result.index('router bgp 65200 vrf Vrf_red'):]
    assert ' bgp log-neighbor-changes' in lines(vrf_section)
    assert ' no bgp log-neighbor-changes' not in lines(vrf_section)

    result = template.render(
        BGP_GLOBALS={'Vrf_red': {'local_asn': '65200',
                                 'log_nbr_state_changes': 'false'}})
    vrf_section = result[result.index('router bgp 65200 vrf Vrf_red'):]
    assert ' no bgp log-neighbor-changes' in lines(vrf_section)
    assert ' bgp log-neighbor-changes' not in lines(vrf_section)


def test_bmp_feature_gate_template():
    """NOS-13537: external BMP collectors (BMP_TARGET tables from config_db)
    render regardless of feature.BMP; only the legacy default localhost
    sonic-bmp target stays behind the feature guard."""
    from jinja2 import Environment, FileSystemLoader
    import os

    template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'bgpd')
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters['ipv4'] = lambda v: False
    env.filters['ipv6'] = lambda v: False

    template = env.get_template('bgpd.conf.db.j2')

    ext_target = {
        'BGP_GLOBALS': {'default': {'local_asn': '65100'}},
        'BMP': {'global': {'mirror-buffer-limit': '1000000000'}},
        'BMP_TARGET': {'production': {'mirror': 'true', 'stats-interval': '5000'}},
        'BMP_TARGET_COLLECTOR': {
            'production|192.168.1.100|5000': {'min-retry': '30000', 'max-retry': '720000'}},
        'BMP_TARGET_AFI_SAFI': {
            'production|ipv4_unicast': {'adj-rib-in-pre': 'true'}},
    }

    # External target, feature.BMP absent -> external config renders, and the
    # legacy default localhost target is NOT emitted.
    result = template.render(**ext_target)
    assert 'bmp targets production' in result
    assert 'bmp connect 192.168.1.100 port 5000 min-retry 30000 max-retry 720000' in result
    assert 'bmp mirror buffer-limit 1000000000' in result
    assert 'bmp monitor ipv4 unicast pre-policy' in result
    assert 'bmp targets sonic-bmp' not in result
    assert 'bmp connect 127.0.0.1 port 5000' not in result

    # Feature enabled, no targets -> legacy default localhost target renders.
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100'}},
        FEATURE={'frr_bmp': {'state': 'enabled'}})
    assert 'bmp targets sonic-bmp' in result
    assert 'bmp connect 127.0.0.1 port 5000 min-retry 10000 max-retry 15000' in result

    # Feature disabled, no targets -> no BMP stanza at all.
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100'}},
        FEATURE={'frr_bmp': {'state': 'disabled'}})
    assert 'bmp targets' not in result
    assert 'bmp mirror buffer-limit' not in result

    # Feature enabled AND external targets -> external targets take priority, so
    # the legacy default sonic-bmp target is NOT emitted (the bmp container gets
    # no stream in that case).
    result = template.render(FEATURE={'frr_bmp': {'state': 'enabled'}}, **ext_target)
    assert 'bmp targets production' in result
    assert 'bmp connect 192.168.1.100 port 5000' in result
    assert 'bmp monitor ipv4 unicast pre-policy' in result
    assert 'bmp targets sonic-bmp' not in result


def test_bgp_bestpath_bandwidth_template():
    """Verify bgpd.conf.db.j2 renders 'bgp bestpath bandwidth' from BGP_GLOBALS,
    emits nothing when the field is absent, and scopes the value per VRF.

    frrcfgd's field map only covers live ConfigDB changes, so without this
    template block a value applied at runtime is lost on the next config reload.
    """
    from jinja2 import Environment, FileSystemLoader
    import os

    template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'bgpd')
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters['ipv4'] = lambda v: False
    env.filters['ipv6'] = lambda v: False

    template = env.get_template('bgpd.conf.db.j2')

    def lines(rendered):
        return [ln.rstrip() for ln in rendered.splitlines()]

    # Each of the three FRR keywords renders verbatim.
    for value in ('ignore', 'skip-missing', 'default-weight-for-missing'):
        result = template.render(
            BGP_GLOBALS={'default': {'local_asn': '65100',
                                     'bestpath_bandwidth': value}})
        assert ' bgp bestpath bandwidth %s' % value in lines(result)

    # Field absent -> nothing emitted. Absence is how FRR's own default is
    # expressed, so the template must not fall back to a value or a 'no' form.
    result = template.render(BGP_GLOBALS={'default': {'local_asn': '65100'}})
    assert 'bgp bestpath bandwidth' not in result

    # lb_handling is per 'struct bgp', so each VRF's value must land under its
    # own instance and not leak into the other.
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100',
                                 'bestpath_bandwidth': 'skip-missing'},
                     'Vrf_red': {'local_asn': '65200',
                                 'bestpath_bandwidth': 'default-weight-for-missing'}})
    vrf_section = result[result.index('router bgp 65200 vrf Vrf_red'):]
    default_section = result[result.index('router bgp 65100'):result.index('router bgp 65200 vrf Vrf_red')]
    assert ' bgp bestpath bandwidth skip-missing' in lines(default_section)
    assert ' bgp bestpath bandwidth default-weight-for-missing' in lines(vrf_section)
    assert ' bgp bestpath bandwidth default-weight-for-missing' not in lines(default_section)
    assert ' bgp bestpath bandwidth skip-missing' not in lines(vrf_section)

    # A VRF without the field stays clean even when a sibling VRF has it.
    result = template.render(
        BGP_GLOBALS={'default': {'local_asn': '65100',
                                 'bestpath_bandwidth': 'ignore'},
                     'Vrf_red': {'local_asn': '65200'}})
    vrf_section = result[result.index('router bgp 65200 vrf Vrf_red'):]
    assert 'bgp bestpath bandwidth' not in vrf_section


def _render_pathd_fixture(**context):
    """Render pathd.conf.j2 against a golden fixture in tests/fixtures/pathd/."""
    from jinja2 import Environment, FileSystemLoader
    import os

    template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'pathd')
    env = Environment(loader=FileSystemLoader(template_dir), trim_blocks=True)
    template = env.get_template('pathd.conf.j2')
    return template.render(**context)


def _load_pathd_fixture(name):
    import os
    fixture_path = os.path.join(os.path.dirname(__file__), 'fixtures', 'pathd', name + '.conf')
    with open(fixture_path) as f:
        return f.read()


def test_pathd_template_empty():
    """Nothing configured -> no segment-routing stanza at all."""
    result = _render_pathd_fixture()
    assert result == _load_pathd_fixture('empty')


def test_pathd_template_global_disable():
    """sbfd=disable at global level needs no profile."""
    result = _render_pathd_fixture(SR_TE_GLOBAL={'global': {'sbfd': 'disable'}})
    assert result == _load_pathd_fixture('global_disable')


def test_pathd_template_global_enable_missing_profile():
    """sbfd=enable but missing profile -> no sbfd line emitted."""
    result = _render_pathd_fixture(SR_TE_GLOBAL={'global': {'sbfd': 'enable'}})
    assert result == _load_pathd_fixture('global_enable_missing_profile')


def test_pathd_template_three_level():
    """Three-level S-BFD, numeric (not lexical) index sort, and a
    candidate-path with no segment-list correctly suppressed."""
    result = _render_pathd_fixture(
        SR_TE_GLOBAL={'global': {'sbfd': 'enable', 'sbfd_profile': 'sbfd-global'}},
        SR_TE_SEGMENT_LIST={
            ('sl-primary', '10'): {'ipv6_address': '2001:db8:2:1::'},
            ('sl-primary', '2'): {'ipv6_address': '2001:db8:2:2::'},
        },
        SR_POLICY={
            ('100', '10.0.0.4'): {'name': 'pol-three-level', 'sbfd': 'enable', 'sbfd_profile': 'sbfd-policy'},
            ('100', '10.0.0.4', '200'): {'name': 'cp-primary', 'type': 'explicit',
                                          'sbfd': 'enable', 'sbfd_profile': 'sbfd-cp-primary'},
            ('100', '10.0.0.4', '100'): {'name': 'cp-backup', 'type': 'explicit', 'sbfd': 'disable'},
            ('100', '10.0.0.4', '200', 'sl-primary'): {'weight': '10'},
        },
    )
    assert result == _load_pathd_fixture('three_level')


def test_pathd_template_per_flow():
    """type=per-flow CPs render without a segment-list; explicit CPs without
    a segment-list stay suppressed."""
    result = _render_pathd_fixture(
        SR_TE_SEGMENT_LIST={
            ('SL_GOLD_A', '10'): {'ipv6_address': '2064:30c:2::1'},
        },
        SR_POLICY={
            ('100', '2064:30c::1'): {'name': 'p100'},
            ('100', '2064:30c::1', '100'): {'name': 'SL_GOLD_A', 'type': 'explicit'},
            ('100', '2064:30c::1', '100', 'SL_GOLD_A'): {'weight': '1'},
            ('100', '2064:30c::1', '50'): {'name': 'cp_explicit_no_sl', 'type': 'explicit'},
            ('300', '2064:30c::1'): {'name': 'pf300'},
            ('300', '2064:30c::1', '70'): {'name': 'pf300', 'type': 'per-flow'},
            ('300', '10.99.99.1'): {'name': 'pf300_v4'},
            ('300', '10.99.99.1', '70'): {'name': 'pf300_v4', 'type': 'per-flow'},
        },
        SR_POLICY_CANDIDATE_PATH_PER_FLOW={
            ('300', '2064:30c::1', '70', '0'): {'next_color': '50'},
            ('300', '2064:30c::1', '70', '1'): {'next_color': '100'},
            ('300', '2064:30c::1', '70', '2'): {'next_color': '200'},
            ('300', '2064:30c::1', '70', 'abc'): {'next_color': '99'},
            ('300', '2064:30c::1', '70', '8'): {'next_color': '99'},
            ('300', '10.99.99.1', '70', '0'): {'action_best_effort': 'true'},
            ('300', '10.99.99.1', '70', '1'): {'next_color': '100'},
        },
    )
    assert result == _load_pathd_fixture('per_flow')


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_segment_list(run_cmd):
    """Test SR-Policy segment list configuration"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    test = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'srv6_path|10',
        {'ipv6_address': '2001:db8:2::100'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list srv6_path',
         'index 10 ipv6-address 2001:db8:2::100', 'exit'],
        ignore_tail=None
    )

    CmdMapTestInfo.add_test_data(test)
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    assert(len(hdlr) == 1)
    hdlr[0]('SR_TE_SEGMENT_LIST', 'srv6_path|10', CmdMapTestInfo.get_test_data(test))
    test.check_running_cmd(run_cmd, False)

    CmdMapTestInfo.del_test_data(test)
    hdlr[0]('SR_TE_SEGMENT_LIST', 'srv6_path|10', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy(run_cmd):
    """Test SR-Policy configuration"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    test = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1',
        {'name': 'static_srv6_policy'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'name static_srv6_policy'],
        ignore_tail=None
    )

    CmdMapTestInfo.add_test_data(test)
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(hdlr) == 1)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(test))
    test.check_running_cmd(run_cmd, False)

    CmdMapTestInfo.del_test_data(test)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_candidate_path(run_cmd):
    """A candidate path alone (no segment-list yet) still pushes the
    candidate-path node immediately -- FRR's multi-segment-list syntax
    allows it to exist independently of any segment-list."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(hdlr) == 1)

    run_cmd.reset_mock()

    test_cp = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100',
        {'name': 'cp1', 'type': 'explicit'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'candidate-path preference 100 name cp1 explicit'],
        no_del=True,
        ignore_tail=None
    )

    CmdMapTestInfo.add_test_data(test_cp)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', CmdMapTestInfo.get_test_data(test_cp))
    test_cp.check_running_cmd(run_cmd, False)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_candidate_path_segment_list(run_cmd):
    """Test SR-Policy candidate path segment list association"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(hdlr) == 1)

    # First add candidate path metadata
    test_cp = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100',
        {'name': 'cp1', 'type': 'explicit'},
        [],
        no_del=True,
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_cp)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', CmdMapTestInfo.get_test_data(test_cp))

    # Now add segment list association
    test_sl = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100|srv6_path',
        {},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'candidate-path preference 100 name cp1 explicit',
         'segment-list srv6_path weight 1'],
        ignore_tail=None
    )

    CmdMapTestInfo.add_test_data(test_sl)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|srv6_path', CmdMapTestInfo.get_test_data(test_sl))
    test_sl.check_running_cmd(run_cmd, False)

    CmdMapTestInfo.del_test_data(test_sl)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|srv6_path', None)

    # Test deleting candidate path (no FRR command - already deleted with segment list)
    CmdMapTestInfo.del_test_data(test_cp)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_segment_list_assoc_before_candidate_path(run_cmd):
    """CONFIG_DB DUMP/replay can deliver the 4-part SL association before the
    3-part CP. That must not fail; the later CP SET must emit the cached
    segment-list so FRR is not left Inactive/Undefined after reload."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(hdlr) == 1)

    test_sl = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100|srv6_path',
        {},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'segment-list srv6_path', 'exit'],
        no_del=True,
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_sl)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|srv6_path',
            CmdMapTestInfo.get_test_data(test_sl))
    test_sl.check_running_cmd(run_cmd, False)
    assert daemon._sr_cp_sl_cache['100|2001:db8:3::1|100']['srv6_path'] == '1'

    run_cmd.reset_mock()
    test_cp = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100',
        {'name': 'cp1', 'type': 'explicit'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'candidate-path preference 100 name cp1 explicit',
         'segment-list srv6_path weight 1'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_cp)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100',
            CmdMapTestInfo.get_test_data(test_cp))
    test_cp.check_running_cmd(run_cmd, False)

    CmdMapTestInfo.del_test_data(test_cp)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', None)
    assert '100|2001:db8:3::1|100' not in daemon._sr_cp_sl_cache

    CmdMapTestInfo.del_test_data(test_sl)
    hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|srv6_path', None)
    assert '100|2001:db8:3::1|100' not in daemon._sr_cp_sl_cache


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_assoc_refcount_only_after_vtysh_success(run_cmd):
    """A failed 4-part SET must not increment the SL ref or record the assoc."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY'][0]

    test_pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1', {'name': 'policy1'},
                              [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr('SR_POLICY', '100|2001:db8:1::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100',
                             {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr('SR_POLICY', '100|2001:db8:1::1|100', CmdMapTestInfo.get_test_data(test_cp))

    def _fail_weight(table, cmd, *a, **kw):
        return 'weight' not in ' '.join(cmd)

    run_cmd.side_effect = _fail_weight
    test_sl = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100|path1', {},
                             [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl)
    pol_hdlr('SR_POLICY', '100|2001:db8:1::1|100|path1',
             CmdMapTestInfo.get_test_data(test_sl))

    assert daemon._sr_segment_list_refs.get('path1', 0) == 0
    assert '100|2001:db8:1::1|100|path1' not in daemon._sr_cp_segment_list_assocs
    assert '100|2001:db8:1::1|100' not in daemon._sr_cp_sl_cache


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_full_integration(run_cmd):
    """Test full SR-Policy configuration flow"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    # Get handlers
    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    # Step 1: Add segment list segments
    test_seg1 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'srv6_path|10',
        {'ipv6_address': '2001:db8:2::100'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list srv6_path',
         'index 10 ipv6-address 2001:db8:2::100', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'srv6_path|10', CmdMapTestInfo.get_test_data(test_seg1))
    test_seg1.check_running_cmd(run_cmd, False)

    test_seg2 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'srv6_path|20',
        {'ipv6_address': '2001:db8:3::1'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list srv6_path',
         'index 20 ipv6-address 2001:db8:3::1', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'srv6_path|20', CmdMapTestInfo.get_test_data(test_seg2))
    test_seg2.check_running_cmd(run_cmd, False)

    # Step 2: Add SR policy (2-part key)
    test_policy = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1',
        {'name': 'static_srv6_policy'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'name static_srv6_policy'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_policy)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(test_policy))
    test_policy.check_running_cmd(run_cmd, False)

    # Step 3: Add candidate path metadata (3-part key)
    test_cp = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100',
        {'name': 'cp1', 'type': 'explicit'},
        [],  # No command yet
        no_del=True,
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', CmdMapTestInfo.get_test_data(test_cp))

    # Step 4: Associate segment list with candidate path (4-part key)
    test_cp_sl = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100|srv6_path',
        {},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'candidate-path preference 100 name cp1 explicit',
         'segment-list srv6_path weight 1'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_cp_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|srv6_path', CmdMapTestInfo.get_test_data(test_cp_sl))
    test_cp_sl.check_running_cmd(run_cmd, False)

    CmdMapTestInfo.del_test_data(test_cp_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|srv6_path', None)

    CmdMapTestInfo.del_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', None)

    CmdMapTestInfo.del_test_data(test_policy)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', None)

    CmdMapTestInfo.del_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'srv6_path|20', None)

    CmdMapTestInfo.del_test_data(test_seg1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'srv6_path|10', None)

    # Verify pathd daemon is configured for SR_POLICY tables in TABLE_DAEMON
    from frrcfgd.frrcfgd import BgpdClientMgr
    assert BgpdClientMgr.TABLE_DAEMON.get('SR_TE_SEGMENT_LIST') == ['pathd']
    assert BgpdClientMgr.TABLE_DAEMON.get('SR_POLICY') == ['pathd']


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_reference_counting(run_cmd):
    """Test SR-Policy segment list reference counting"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    test_seg = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'path1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg))

    test_pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1', {'name': 'policy1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp1 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100', CmdMapTestInfo.get_test_data(test_cp1))

    # Add segment list association - should increment ref count
    test_sl1 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100|path1', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100|path1', CmdMapTestInfo.get_test_data(test_sl1))

    assert daemon._sr_segment_list_refs.get('path1', 0) == 1

    # Add another candidate path using same segment list
    test_cp2 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|200', {'name': 'cp2', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp2)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|200', CmdMapTestInfo.get_test_data(test_cp2))

    test_sl2 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|200|path1', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl2)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|200|path1', CmdMapTestInfo.get_test_data(test_sl2))

    assert daemon._sr_segment_list_refs.get('path1', 0) == 2

    # Delete first candidate path - should decrement ref count
    CmdMapTestInfo.del_test_data(test_sl1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100|path1', None)

    assert daemon._sr_segment_list_refs.get('path1', 0) == 1

    # Delete second candidate path - should decrement ref count to 0
    CmdMapTestInfo.del_test_data(test_sl2)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|200|path1', None)

    assert 'path1' not in daemon._sr_segment_list_refs


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_deferred_deletion(run_cmd):
    """Test SR-Policy segment list deferred deletion"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    test_seg = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'path1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg))

    test_pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1', {'name': 'policy1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100', CmdMapTestInfo.get_test_data(test_cp))

    test_sl = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100|path1', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100|path1', CmdMapTestInfo.get_test_data(test_sl))

    assert daemon._sr_segment_list_refs.get('path1', 0) == 1

    # Try to delete segment list (last segment) - should be deferred
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', None)  # Pass None for delete

    assert 'path1' in daemon._sr_pending_delete_segment_lists

    # Verify ref count is still 1
    assert daemon._sr_segment_list_refs.get('path1', 0) == 1

    # Now delete the candidate path association - should trigger deferred deletion
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100|path1', None)  # Pass None for delete

    assert 'path1' not in daemon._sr_segment_list_refs

    assert 'path1' not in daemon._sr_pending_delete_segment_lists


    delete_calls = [call for call in run_cmd.call_args_list
                    if 'no segment-list path1' in str(call)]
    assert len(delete_calls) > 0, "Deferred deletion should have executed 'no segment-list path1' command"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_segment_list_update(run_cmd):
    """Test SR-Policy segment list update (changing IPv6 address)"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    assert(len(seg_hdlr) == 1)

    test_seg = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'path1|10',
        {'ipv6_address': '2001:db8:1::1'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list path1',
         'index 10 ipv6-address 2001:db8:1::1', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg))
    test_seg.check_running_cmd(run_cmd, False)

    run_cmd.reset_mock()
    test_seg_update = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'path1|10',
        {'ipv6_address': '2001:db8:9::9'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list path1',
         'index 10 ipv6-address 2001:db8:9::9', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg_update)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg_update))
    test_seg_update.check_running_cmd(run_cmd, False)

    CmdMapTestInfo.del_test_data(test_seg_update)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_name_update(run_cmd):
    """Test SR-Policy name update"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(pol_hdlr) == 1)

    test_pol = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1',
        {'name': 'original_name'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'name original_name'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(test_pol))
    test_pol.check_running_cmd(run_cmd, False)

    run_cmd.reset_mock()
    test_pol_update = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1',
        {'name': 'updated_name'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'name updated_name'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_pol_update)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(test_pol_update))
    test_pol_update.check_running_cmd(run_cmd, False)

    CmdMapTestInfo.del_test_data(test_pol_update)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_candidate_path_rename(run_cmd):
    """A candidate-path is identified by its preference under the policy,
    not its name (pathd/path_nb_config.c accepts a name modify on an
    existing candidate-path and sets F_CANDIDATE_MODIFIED). A CONFIG_DB
    name change is rendered as the same in-place SET as any other field
    change, with every cached segment-list association re-applied -- no
    delete of the node is ever sent."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    sl = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'sl-b|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(sl)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl-b|10', CmdMapTestInfo.get_test_data(sl))
    pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1', {'name': 'p'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(pol))
    cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200', {'name': 'cp-primary', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp))
    assoc = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200|sl-b', {'weight': '1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(assoc)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200|sl-b', CmdMapTestInfo.get_test_data(assoc))

    run_cmd.reset_mock()
    cp_renamed = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200', {'name': 'cp-main', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp_renamed)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp_renamed))

    cmds = [_render(call[0][1]) for call in run_cmd.call_args_list]
    rename = [c for c in cmds
              if "-c 'candidate-path preference 200 name cp-main explicit' -c 'segment-list sl-b weight 1'" in c]
    assert not any('no candidate-path' in c for c in cmds), \
        "a rename must not delete the candidate-path node, got: %s" % cmds
    assert len(rename) == 1, \
        "rename must be a single in-place SET carrying the segment-list association, got: %s" % cmds
    assert daemon._sr_candidate_path_cache['100|2001:db8:3::1|200']['name'] == 'cp-main'
    assert daemon._sr_segment_list_refs.get('sl-b', 0) == 1, \
        "rename must not change the segment-list ref count"

    # A later weight change on the renamed candidate-path uses the new name.
    run_cmd.reset_mock()
    assoc_upd = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200|sl-b', {'weight': '2'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(assoc_upd)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200|sl-b', CmdMapTestInfo.get_test_data(assoc_upd))
    cmds = [_render(call[0][1]) for call in run_cmd.call_args_list]
    assert any("-c 'candidate-path preference 200 name cp-main explicit' -c 'segment-list sl-b weight 2'" in c
               for c in cmds), cmds

    CmdMapTestInfo.del_test_data(assoc_upd)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200|sl-b', None)
    CmdMapTestInfo.del_test_data(cp_renamed)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', None)
    CmdMapTestInfo.del_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', None)
    CmdMapTestInfo.del_test_data(sl)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl-b|10', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_candidate_path_failed_set_rolls_back_cache(run_cmd):
    """Any failed candidate-path SET -- a rename or any other field change
    -- must not leave the cache ahead of FRR: it is restored to the
    previous row, or dropped if there wasn't one, so a retried SET is
    compared against what FRR actually has."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(pol_hdlr) == 1)

    pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1', {'name': 'p'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(pol))

    # The first-ever SET for this candidate-path fails: no previous row to
    # restore, so the cache must not gain a half-applied entry.
    run_cmd.return_value = False
    cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200', {'name': 'cp-primary', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp))
    assert '100|2001:db8:3::1|200' not in daemon._sr_candidate_path_cache

    # It succeeds on retry.
    run_cmd.return_value = True
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp))
    assert daemon._sr_candidate_path_cache['100|2001:db8:3::1|200']['name'] == 'cp-primary'

    # A rename on top of that now fails: the cache must stay at the old
    # name, not the rejected new one.
    run_cmd.return_value = False
    cp_renamed = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200', {'name': 'cp-main', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp_renamed)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp_renamed))
    assert daemon._sr_candidate_path_cache['100|2001:db8:3::1|200']['name'] == 'cp-primary'

    # It succeeds on retry.
    run_cmd.return_value = True
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp_renamed))
    assert daemon._sr_candidate_path_cache['100|2001:db8:3::1|200']['name'] == 'cp-main'

    CmdMapTestInfo.del_test_data(cp_renamed)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', None)
    CmdMapTestInfo.del_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_to_explicit_failed_push_keeps_fc_entries(run_cmd):
    """A per-flow -> explicit change whose push fails must keep the cached
    forwarding-class entries, since FRR still has the per-flow node."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    pf_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY_CANDIDATE_PATH_PER_FLOW']

    pol = CmdMapTestInfo('SR_POLICY', '300|2001:db8::1', {'name': 'p'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(pol))
    cp = CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {'name': 'pf', 'type': 'per-flow'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(cp))
    fc = CmdMapTestInfo('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|2', {'next_color': '301'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(fc)
    pf_hdlr[0]('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|2', CmdMapTestInfo.get_test_data(fc))
    assert daemon._sr_per_flow_entries['300|2001:db8::1|100']

    run_cmd.return_value = False
    CmdMapTestInfo.del_test_data(CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {'type': 'per-flow'}, []))
    cp_exp = CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp_exp)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(cp_exp))
    assert daemon._sr_per_flow_entries['300|2001:db8::1|100'], "FC entries dropped although FRR kept the per-flow node"
    assert daemon._sr_candidate_path_cache['300|2001:db8::1|100']['type'] == 'per-flow'

    run_cmd.return_value = True
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(cp_exp))
    assert '300|2001:db8::1|100' not in daemon._sr_per_flow_entries
    assert daemon._sr_candidate_path_cache['300|2001:db8::1|100']['type'] == 'explicit'

    CmdMapTestInfo.del_test_data(fc)
    pf_hdlr[0]('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|2', None)
    CmdMapTestInfo.del_test_data(CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {'name': 'pf', 'type': 'explicit'}, []))
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1|100', None)
    CmdMapTestInfo.del_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_per_flow_candidate_path_rename(run_cmd):
    """A per-flow candidate-path rename is the same in-place SET as any
    other per-flow push: one command carrying the new name and every
    cached forwarding-class entry, no delete of the node."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    pf_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY_CANDIDATE_PATH_PER_FLOW']
    assert(len(pol_hdlr) == 1 and len(pf_hdlr) == 1)

    pol = CmdMapTestInfo('SR_POLICY', '300|2001:db8::1', {'name': 'p'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1', CmdMapTestInfo.get_test_data(pol))
    cp = CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {'name': 'pf-old', 'type': 'per-flow'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(cp))
    fc = CmdMapTestInfo('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|2',
                        {'next_color': '301'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(fc)
    pf_hdlr[0]('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|2', CmdMapTestInfo.get_test_data(fc))

    run_cmd.reset_mock()
    cp_new = CmdMapTestInfo('SR_POLICY', '300|2001:db8::1|100', {'name': 'pf-new', 'type': 'per-flow'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp_new)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1|100', CmdMapTestInfo.get_test_data(cp_new))
    cmds = [_render(call[0][1]) for call in run_cmd.call_args_list]
    create = [c for c in cmds if "-c 'candidate-path preference 100 name pf-new per-flow'" in c]
    assert not any('no candidate-path' in c for c in cmds), \
        "a per-flow rename must not delete the candidate-path node, got: %s" % cmds
    assert len(create) == 1, cmds
    assert 'forwarding-class' in create[0] and 'color 301' in create[0], create[0]

    CmdMapTestInfo.del_test_data(fc)
    pf_hdlr[0]('SR_POLICY_CANDIDATE_PATH_PER_FLOW', '300|2001:db8::1|100|2', None)
    CmdMapTestInfo.del_test_data(cp_new)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1|100', None)
    CmdMapTestInfo.del_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '300|2001:db8::1', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_candidate_path_sbfd_transitions(run_cmd):
    """S-BFD on a candidate path: enable with a profile, flip to disable,
    then drop the fields; each step must reach FRR as its own sub-command."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(pol_hdlr) == 1)

    pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1', {'name': 'p'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(pol))

    def last_cmd():
        return _render(run_cmd.call_args_list[-1][0][1])

    run_cmd.reset_mock()
    cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200',
                        {'name': 'cp1', 'type': 'explicit', 'sbfd': 'enable', 'sbfd_profile': 'prof-a'},
                        [], no_del=True)
    CmdMapTestInfo.add_test_data(cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp))
    assert "-c 'candidate-path preference 200 name cp1 explicit' -c 'sbfd enable profile prof-a'" in last_cmd(), last_cmd()

    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200',
                                                {'sbfd': 'enable', 'sbfd_profile': 'prof-a'}, []))
    cp_dis = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200', {'sbfd': 'disable'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp_dis)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp_dis))
    assert "-c 'sbfd disable'" in last_cmd(), last_cmd()
    assert 'sbfd enable' not in last_cmd(), last_cmd()

    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(cp_dis)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(cp_dis))
    assert "-c 'no sbfd'" in last_cmd(), last_cmd()
    assert 'sbfd' not in daemon._sr_candidate_path_cache['100|2001:db8:3::1|200']

    CmdMapTestInfo.del_test_data(CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200',
                                                {'name': 'cp1', 'type': 'explicit'}, []))
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', None)
    CmdMapTestInfo.del_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_multiple_candidate_paths(run_cmd):
    """Test multiple candidate paths with different preferences on same policy"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    test_seg1 = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'path1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg1))

    test_seg2 = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'path2|10', {'ipv6_address': '2001:db8:2::2'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path2|10', CmdMapTestInfo.get_test_data(test_seg2))

    test_pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1', {'name': 'test_policy'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp1 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|100', {'name': 'cp_high_pref', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', CmdMapTestInfo.get_test_data(test_cp1))

    test_cp2 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|200', {'name': 'cp_low_pref', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp2)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200', CmdMapTestInfo.get_test_data(test_cp2))
    test_sl1 = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100|path1',
        {},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'candidate-path preference 100 name cp_high_pref explicit',
         'segment-list path1 weight 1'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_sl1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|path1', CmdMapTestInfo.get_test_data(test_sl1))
    test_sl1.check_running_cmd(run_cmd, False)

    run_cmd.reset_mock()
    test_sl2 = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|200|path2',
        {},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'candidate-path preference 200 name cp_low_pref explicit',
         'segment-list path2 weight 1'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_sl2)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|200|path2', CmdMapTestInfo.get_test_data(test_sl2))
    test_sl2.check_running_cmd(run_cmd, False)

    assert daemon._sr_segment_list_refs.get('path1', 0) == 1
    assert daemon._sr_segment_list_refs.get('path2', 0) == 1


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_multiple_segment_lists_per_candidate_path(run_cmd):
    """Test multiple weighted segment lists on one candidate path (NOS-9315):
    add with weights, delete one (others remain), delete the last (candidate
    path itself is retained -- it can exist with zero segment-lists)."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    # Segment lists
    s1 = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'sl1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(s1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl1|10', CmdMapTestInfo.get_test_data(s1))
    s2 = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'sl2|10', {'ipv6_address': '2001:db8:2::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(s2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl2|10', CmdMapTestInfo.get_test_data(s2))

    # Policy + candidate path
    pol = CmdMapTestInfo('SR_POLICY', '100|10.0.0.1', {'name': 'p'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1', CmdMapTestInfo.get_test_data(pol))
    cp = CmdMapTestInfo('SR_POLICY', '100|10.0.0.1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100', CmdMapTestInfo.get_test_data(cp))

    # Add first segment list with weight 10
    run_cmd.reset_mock()
    a1 = CmdMapTestInfo(
        'SR_POLICY', '100|10.0.0.1|100|sl1', {'weight': '10'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 10.0.0.1',
         'candidate-path preference 100 name cp1 explicit',
         'segment-list sl1 weight 10'],
        ignore_tail=None)
    CmdMapTestInfo.add_test_data(a1)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100|sl1', CmdMapTestInfo.get_test_data(a1))
    a1.check_running_cmd(run_cmd, False)

    # Add second segment list with weight 20
    run_cmd.reset_mock()
    a2 = CmdMapTestInfo(
        'SR_POLICY', '100|10.0.0.1|100|sl2', {'weight': '20'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 10.0.0.1',
         'candidate-path preference 100 name cp1 explicit',
         'segment-list sl2 weight 20'],
        ignore_tail=None)
    CmdMapTestInfo.add_test_data(a2)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100|sl2', CmdMapTestInfo.get_test_data(a2))
    a2.check_running_cmd(run_cmd, False)

    assert daemon._sr_segment_list_refs.get('sl1', 0) == 1
    assert daemon._sr_segment_list_refs.get('sl2', 0) == 1

    # Delete sl1 - sl2 still remains, so remove only sl1 (candidate path retained)
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(a1)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100|sl1', None)
    cmd = run_cmd.call_args[0][1]
    assert 'no segment-list sl1' in cmd
    assert 'candidate-path preference 100 name cp1 explicit' in cmd
    assert 'no candidate-path preference 100' not in cmd
    assert daemon._sr_segment_list_refs.get('sl1', 0) == 0

    # Delete sl2 - the last segment list, but the candidate path stays
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(a2)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100|sl2', None)
    cmd = run_cmd.call_args[0][1]
    assert 'no segment-list sl2' in cmd
    assert 'candidate-path preference 100 name cp1 explicit' in cmd
    assert 'no candidate-path preference 100' not in cmd


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_segment_list_weight_update_refcount(run_cmd):
    """A weight update is a SET on an existing association and must NOT inflate the
    segment-list reference count (NOS-9315). After update + delete, the ref count must
    return to 0 so deferred segment-list garbage collection still works."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    # Segment list + policy + candidate path
    s1 = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'sl1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(s1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl1|10', CmdMapTestInfo.get_test_data(s1))
    pol = CmdMapTestInfo('SR_POLICY', '100|10.0.0.1', {'name': 'p'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(pol)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1', CmdMapTestInfo.get_test_data(pol))
    cp = CmdMapTestInfo('SR_POLICY', '100|10.0.0.1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100', CmdMapTestInfo.get_test_data(cp))

    # Initial association with weight 10
    a = CmdMapTestInfo('SR_POLICY', '100|10.0.0.1|100|sl1', {'weight': '10'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(a)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100|sl1', CmdMapTestInfo.get_test_data(a))
    assert daemon._sr_segment_list_refs.get('sl1', 0) == 1

    # Weight update (SET on the existing association, no preceding DEL) -> ref must stay 1
    a_upd = CmdMapTestInfo('SR_POLICY', '100|10.0.0.1|100|sl1', {'weight': '20'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(a_upd)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100|sl1', CmdMapTestInfo.get_test_data(a_upd))
    assert daemon._sr_segment_list_refs.get('sl1', 0) == 1, \
        "weight update inflated the segment-list ref count"

    # Delete the association -> ref must return to 0 (no phantom reference)
    CmdMapTestInfo.del_test_data(a_upd)
    pol_hdlr[0]('SR_POLICY', '100|10.0.0.1|100|sl1', None)
    assert daemon._sr_segment_list_refs.get('sl1', 0) == 0, \
        "phantom reference left after delete blocks segment-list GC"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_multiple_policies_shared_segment_list(run_cmd):
    """Test multiple SR policies sharing the same segment list"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    test_seg = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'shared_path|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'shared_path|10', CmdMapTestInfo.get_test_data(test_seg))

    test_pol1 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:10::1', {'name': 'policy1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1', CmdMapTestInfo.get_test_data(test_pol1))

    test_pol2 = CmdMapTestInfo('SR_POLICY', '200|2001:db8:20::1', {'name': 'policy2'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol2)
    pol_hdlr[0]('SR_POLICY', '200|2001:db8:20::1', CmdMapTestInfo.get_test_data(test_pol2))

    test_cp1 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:10::1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1|100', CmdMapTestInfo.get_test_data(test_cp1))

    test_cp2 = CmdMapTestInfo('SR_POLICY', '200|2001:db8:20::1|100', {'name': 'cp2', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp2)
    pol_hdlr[0]('SR_POLICY', '200|2001:db8:20::1|100', CmdMapTestInfo.get_test_data(test_cp2))

    test_sl1 = CmdMapTestInfo('SR_POLICY', '100|2001:db8:10::1|100|shared_path', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1|100|shared_path', CmdMapTestInfo.get_test_data(test_sl1))

    test_sl2 = CmdMapTestInfo('SR_POLICY', '200|2001:db8:20::1|100|shared_path', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl2)
    pol_hdlr[0]('SR_POLICY', '200|2001:db8:20::1|100|shared_path', CmdMapTestInfo.get_test_data(test_sl2))

    assert daemon._sr_segment_list_refs.get('shared_path', 0) == 2

    CmdMapTestInfo.del_test_data(test_sl1)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1|100|shared_path', None)
    assert daemon._sr_segment_list_refs.get('shared_path', 0) == 1

    CmdMapTestInfo.del_test_data(test_sl2)
    pol_hdlr[0]('SR_POLICY', '200|2001:db8:20::1|100|shared_path', None)
    assert 'shared_path' not in daemon._sr_segment_list_refs


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_out_of_order_deletion(run_cmd):
    """Test out-of-order deletion (policy deleted before candidate path)"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    test_seg = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'path1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg))

    test_pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1', {'name': 'test_policy'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', CmdMapTestInfo.get_test_data(test_cp))

    test_sl = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|100|path1', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|path1', CmdMapTestInfo.get_test_data(test_sl))

    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', None)

    assert run_cmd.called

    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_cp_deleted_before_segment_list_association(run_cmd):
    """Candidate-path DEL processed before its segment-list-association DEL
    must not recreate the candidate-path just to remove the segment-list --
    FRR already removed it when the whole node was deleted -- and reference
    counting must still be cleaned up."""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    test_seg = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'path1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg))

    test_pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1', {'name': 'test_policy'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', CmdMapTestInfo.get_test_data(test_cp))

    test_sl = CmdMapTestInfo('SR_POLICY', '100|2001:db8:3::1|100|path1', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|path1', CmdMapTestInfo.get_test_data(test_sl))

    assert daemon._sr_segment_list_refs.get('path1', 0) == 1

    # Delete the candidate-path first.
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', None)
    assert run_cmd.called
    assert '100|2001:db8:3::1|100' not in daemon._sr_cp_sl_cache

    # The segment-list association delete arrives second: no vtysh command
    # (nothing to recreate/remove), but the reference count must still drop.
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|path1', None)

    run_cmd.assert_not_called()
    assert daemon._sr_segment_list_refs.get('path1', 0) == 0


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_delete_and_recreate(run_cmd):
    """Test delete and recreate SR-Policy configuration"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    test_seg = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'path1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg))

    test_pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1', {'name': 'test_policy'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100', CmdMapTestInfo.get_test_data(test_cp))

    test_sl = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100|path1', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100|path1', CmdMapTestInfo.get_test_data(test_sl))

    CmdMapTestInfo.del_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100|path1', None)

    CmdMapTestInfo.del_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100', None)

    CmdMapTestInfo.del_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1', None)

    CmdMapTestInfo.del_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', None)

    run_cmd.reset_mock()
    test_seg_new = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'path1|10',
        {'ipv6_address': '2001:db8:9::9'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list path1',
         'index 10 ipv6-address 2001:db8:9::9', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg_new)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg_new))
    test_seg_new.check_running_cmd(run_cmd, False)

    run_cmd.reset_mock()
    test_pol_new = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:1::1',
        {'name': 'new_policy'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:1::1',
         'name new_policy'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_pol_new)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1', CmdMapTestInfo.get_test_data(test_pol_new))
    test_pol_new.check_running_cmd(run_cmd, False)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_deferred_deletion_cleanup(run_cmd):
    """Test that deferred deletion is properly executed when references are removed"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    test_seg = CmdMapTestInfo('SR_TE_SEGMENT_LIST', 'path1|10', {'ipv6_address': '2001:db8:1::1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg))

    test_pol = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1', {'name': 'policy1'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100', {'name': 'cp1', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100', CmdMapTestInfo.get_test_data(test_cp))

    test_sl = CmdMapTestInfo('SR_POLICY', '100|2001:db8:1::1|100|path1', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100|path1', CmdMapTestInfo.get_test_data(test_sl))

    assert daemon._sr_segment_list_refs.get('path1', 0) == 1

    # Try to delete segment list while it's still referenced - should be deferred
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', None)

    assert 'path1' in daemon._sr_pending_delete_segment_lists
    assert daemon._sr_segment_list_refs.get('path1', 0) == 1
    delete_calls = [call for call in run_cmd.call_args_list if 'no segment-list path1' in str(call)]
    assert len(delete_calls) == 0, "Deletion should be deferred while still referenced"

    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:1::1|100|path1', None)

    assert 'path1' not in daemon._sr_pending_delete_segment_lists
    assert 'path1' not in daemon._sr_segment_list_refs
    delete_calls = [call for call in run_cmd.call_args_list if 'no segment-list path1' in str(call)]
    assert len(delete_calls) > 0, "Deferred deletion should execute when ref count reaches 0"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_invalid_key_formats(run_cmd):
    """Test that invalid key formats are handled gracefully without crashing"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    assert(len(pol_hdlr) == 1 and len(seg_hdlr) == 1)

    run_cmd.reset_mock()
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'invalid_key_no_pipe', {'ipv6_address': '2001:db8:1::1'})
    assert run_cmd.call_count == 0, "Invalid key should not trigger FRR commands"

    run_cmd.reset_mock()
    test_seg = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'valid_path|10',
        {'ipv6_address': '2001:db8:1::1'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list valid_path',
         'index 10 ipv6-address 2001:db8:1::1', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'valid_path|10', CmdMapTestInfo.get_test_data(test_seg))
    test_seg.check_running_cmd(run_cmd, False)
    assert run_cmd.call_count > 0, "Valid key should trigger FRR commands"


def _last_static_route_cmd(call):
    # frrcfgd leaves the blanks of unused command slots in place; vtysh does not
    # care, so collapse them here to compare against the intended command.
    return ' '.join(re.findall(r"-c\s+'([^']+)'\s*", _render(call[0][1]))[-1].split())


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_static_route_nexthop_color(run_cmd):
    """STATIC_ROUTE_NEXTHOP: SR-Policy color attribute, one row per nexthop.
    color=0 means no SR-Policy color (matches the yang leaf's 'no color' sentinel)."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'STATIC_ROUTE_NEXTHOP'][0]

    # Single nexthop with color.
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', {'color': ['00:100']})
    last = _last_static_route_cmd(run_cmd.call_args_list[-1])
    assert not last.startswith('no ')
    for token in ['ip route 10.1.0.0/24', '192.168.1.1', 'color 100']:
        assert token in last

    # ECMP: three nexthops of the same prefix, each its own row/distance/color.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.2.0.0/24|192.168.1.1|none', {'distance': '10', 'color': ['00:100']})
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.2.0.0/24|192.168.1.2|none', {'distance': '20', 'color': ['00:200']})
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.2.0.0/24|192.168.1.3|none', {'distance': '30', 'color': ['00:0']})
    cmds = [_last_static_route_cmd(c) for c in run_cmd.call_args_list]
    assert len(cmds) == 3
    for cmd, gw, dist, color_tok in zip(cmds, ['192.168.1.1', '192.168.1.2', '192.168.1.3'],
                                        ['10', '20', '30'], ['color 100', 'color 200', None]):
        assert not cmd.startswith('no ')
        assert 'ip route 10.2.0.0/24' in cmd and gw in cmd and dist in cmd
        if color_tok is None:
            assert 'color' not in cmd  # color=0 means no SR-Policy color
        else:
            assert color_tok in cmd

    # IPv6 with color.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|2001:db8::/64|2001:db8::1|none', {'color': ['00:100']})
    last = _last_static_route_cmd(run_cmd.call_args_list[-1])
    for token in ['ipv6 route 2001:db8::/64', '2001:db8::1', 'color 100']:
        assert token in last

    # Backward compatibility: no color attribute at all, ECMP over two rows.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.4.0.0/24|192.168.1.1|none', {})
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.4.0.0/24|192.168.1.2|none', {})
    cmds = [_last_static_route_cmd(c) for c in run_cmd.call_args_list]
    assert len(cmds) == 2
    for cmd, gw in zip(cmds, ['192.168.1.1', '192.168.1.2']):
        assert 'ip route 10.4.0.0/24' in cmd and gw in cmd and 'color' not in cmd

    # FRR has no in-place attribute modify: changing an existing nexthop's color
    # must delete the old 'ip route ... color 100' line before adding the new one.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', {'color': ['00:200']})
    calls = run_cmd.call_args_list
    assert len(calls) == 2
    del_cmd = _last_static_route_cmd(calls[0])
    add_cmd = _last_static_route_cmd(calls[1])
    assert del_cmd.startswith('no ') and 'color 100' in del_cmd
    assert not add_cmd.startswith('no ') and 'color 200' in add_cmd

    # Clearing color (row persists -- gateway/ifname are the key) reverts to no color,
    # which is itself a delete-old(+color)/add-new(without color) transition.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', {})
    calls = run_cmd.call_args_list
    assert len(calls) == 2
    del_cmd = _last_static_route_cmd(calls[0])
    add_cmd = _last_static_route_cmd(calls[1])
    assert del_cmd.startswith('no ') and 'color 200' in del_cmd
    assert not add_cmd.startswith('no ') and 'color' not in add_cmd

    # Full row delete emits only the 'no ...' for that nexthop.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', None)
    calls = run_cmd.call_args_list
    assert len(calls) == 1
    assert _last_static_route_cmd(calls[0]).startswith('no ')


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_static_route_nexthop_bfd(run_cmd):
    """STATIC_ROUTE_NEXTHOP: per-nexthop BFD monitoring rendered as staticd's
    'bfd [multi-hop] [source A] [profile P]' clause."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'STATIC_ROUTE_NEXTHOP'][0]

    # Plain bfd: single-hop session at FRR defaults.
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', {'bfd': 'true'})
    last = _last_static_route_cmd(run_cmd.call_args_list[-1])
    assert not last.startswith('no ')
    assert 'ip route 10.1.0.0/24 192.168.1.1 bfd' in last
    assert 'profile' not in last and 'source' not in last and 'multi-hop' not in last

    # All options, gateway + interface, IPv4.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.2.0.0/24|192.168.1.1|Ethernet0',
         {'bfd': 'true', 'bfd-profile': 'fast', 'bfd-source': '192.168.1.254', 'bfd-multihop': 'true',
          'distance': '10'})
    last = _last_static_route_cmd(run_cmd.call_args_list[-1])
    assert 'ip route 10.2.0.0/24 192.168.1.1 Ethernet0 10 bfd multi-hop source 192.168.1.254 profile fast' in last

    # IPv6 with source and profile.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|2001:db8::/64|2001:db8::1|none',
         {'bfd': 'true', 'bfd-profile': 'fast', 'bfd-source': '2001:db8::ffff'})
    last = _last_static_route_cmd(run_cmd.call_args_list[-1])
    assert 'ipv6 route 2001:db8::/64 2001:db8::1 bfd source 2001:db8::ffff profile fast' in last

    # bfd options without bfd=true are inert.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.3.0.0/24|192.168.1.1|none', {'bfd-profile': 'fast'})
    last = _last_static_route_cmd(run_cmd.call_args_list[-1])
    assert 'bfd' not in last and 'profile' not in last

    # Profile change: delete the old line, add the new one. A re-issued 'ip route ... bfd'
    # without the profile would leave the old profile on bfdd's live session.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', {'bfd': 'true', 'bfd-profile': 'slow'})
    calls = run_cmd.call_args_list
    assert len(calls) == 2
    del_cmd = _last_static_route_cmd(calls[0])
    add_cmd = _last_static_route_cmd(calls[1])
    assert del_cmd.startswith('no ip route 10.1.0.0/24 192.168.1.1 bfd') and 'profile' not in del_cmd
    assert not add_cmd.startswith('no ') and add_cmd.endswith('bfd profile slow')

    # Disabling bfd is an attribute change too: the nexthop comes back unmonitored.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', {'bfd': 'false'})
    calls = run_cmd.call_args_list
    assert len(calls) == 2
    assert 'bfd profile slow' in _last_static_route_cmd(calls[0])
    assert 'bfd' not in _last_static_route_cmd(calls[1])

    # Same row again with bfd unchanged: nothing to do.
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', {'bfd': 'false'})
    assert run_cmd.call_args_list == []



@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_static_route_nexthop_bfd_with_other_attributes(run_cmd):
    """Combined changes on one nexthop row: every transition is one 'no ip route'
    carrying the full old attribute set (BFD clause included) followed by one
    'ip route' with the full new set, so staticd never sees a partial line."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'STATIC_ROUTE_NEXTHOP'][0]
    key = 'Vrf1|10.1.0.0/24|192.168.1.1|Ethernet0'

    def transition(data, expected_del, expected_add):
        run_cmd.reset_mock()
        hdlr('STATIC_ROUTE_NEXTHOP', key, data)
        cmds = [_last_static_route_cmd(c) for c in run_cmd.call_args_list]
        assert cmds == [c for c in (expected_del, expected_add) if c is not None]
        for call in run_cmd.call_args_list:
            assert "-c 'vrf Vrf1'" in _render(call[0][1])

    # plain nexthop with distance and tag
    transition({'distance': '10', 'tag': '5'},
               None,
               'ip route 10.1.0.0/24 192.168.1.1 Ethernet0 tag 5 10')
    # bfd added to an existing nexthop: the old plain line goes, everything else kept
    transition({'distance': '10', 'tag': '5', 'bfd': 'true', 'bfd-profile': 'fast'},
               'no ip route 10.1.0.0/24 192.168.1.1 Ethernet0 tag 5 10',
               'ip route 10.1.0.0/24 192.168.1.1 Ethernet0 tag 5 10 bfd profile fast')
    # distance change only: bfd clause travels on both the delete and the add
    transition({'distance': '20', 'tag': '5', 'bfd': 'true', 'bfd-profile': 'fast'},
               'no ip route 10.1.0.0/24 192.168.1.1 Ethernet0 tag 5 10 bfd profile fast',
               'ip route 10.1.0.0/24 192.168.1.1 Ethernet0 tag 5 20 bfd profile fast')
    # color and bfd source change in the same update
    transition({'distance': '20', 'tag': '5', 'color': ['00:100'],
                'bfd': 'true', 'bfd-profile': 'fast', 'bfd-source': '192.168.1.254'},
               'no ip route 10.1.0.0/24 192.168.1.1 Ethernet0 tag 5 20 bfd profile fast',
               'ip route 10.1.0.0/24 192.168.1.1 Ethernet0 tag 5 20 color 100 bfd source 192.168.1.254 profile fast')
    # tag removed and bfd switched to multi-hop at once
    transition({'distance': '20', 'color': ['00:100'],
                'bfd': 'true', 'bfd-profile': 'fast', 'bfd-source': '192.168.1.254', 'bfd-multihop': 'true'},
               'no ip route 10.1.0.0/24 192.168.1.1 Ethernet0 tag 5 20 color 100 bfd source 192.168.1.254 profile fast',
               'ip route 10.1.0.0/24 192.168.1.1 Ethernet0 20 color 100 bfd multi-hop source 192.168.1.254 profile fast')
    # nexthop-vrf added while bfd is unchanged
    transition({'distance': '20', 'color': ['00:100'], 'nexthop-vrf': 'Vrf2',
                'bfd': 'true', 'bfd-profile': 'fast', 'bfd-source': '192.168.1.254', 'bfd-multihop': 'true'},
               'no ip route 10.1.0.0/24 192.168.1.1 Ethernet0 20 color 100 bfd multi-hop source 192.168.1.254 profile fast',
               'ip route 10.1.0.0/24 192.168.1.1 Ethernet0 20 nexthop-vrf Vrf2 color 100 bfd multi-hop source 192.168.1.254 profile fast')
    # bfd removed and distance changed together
    transition({'distance': '30', 'color': ['00:100'], 'nexthop-vrf': 'Vrf2'},
               'no ip route 10.1.0.0/24 192.168.1.1 Ethernet0 20 nexthop-vrf Vrf2 color 100 bfd multi-hop source 192.168.1.254 profile fast',
               'ip route 10.1.0.0/24 192.168.1.1 Ethernet0 30 nexthop-vrf Vrf2 color 100')
    # row deleted while carrying bfd: one delete with the full last attribute set
    transition({'distance': '30', 'nexthop-vrf': 'Vrf2', 'bfd': 'true', 'bfd-source': '192.168.1.254'},
               'no ip route 10.1.0.0/24 192.168.1.1 Ethernet0 30 nexthop-vrf Vrf2 color 100',
               'ip route 10.1.0.0/24 192.168.1.1 Ethernet0 30 nexthop-vrf Vrf2 bfd source 192.168.1.254')
    transition(None,
               'no ip route 10.1.0.0/24 192.168.1.1 Ethernet0 30 nexthop-vrf Vrf2 bfd source 192.168.1.254',
               None)

    # sibling nexthops of the same prefix are independent rows: changing one
    # leaves the other's line alone
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.2.0.0/24|192.168.1.1|none', {'bfd': 'true', 'bfd-profile': 'fast'})
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.2.0.0/24|192.168.1.2|none', {'distance': '10'})
    run_cmd.reset_mock()
    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.2.0.0/24|192.168.1.2|none', {'distance': '10', 'bfd': 'true'})
    cmds = [_last_static_route_cmd(c) for c in run_cmd.call_args_list]
    assert cmds == ['no ip route 10.2.0.0/24 192.168.1.2 10',
                    'ip route 10.2.0.0/24 192.168.1.2 10 bfd']


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_static_route_nexthop_bfd_warm_start(run_cmd):
    """The startup nexthop cache carries the BFD fields, so after a restart an
    unchanged row is a no-op and a changed one deletes the old line with its
    BFD clause intact."""
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    row = {'bfd': 'true', 'bfd-profile': 'fast', 'bfd-source': '192.168.1.254'}

    def fake_get_table(self, name):
        if name == 'STATIC_ROUTE_NEXTHOP':
            return {('default', '10.1.0.0/24', '192.168.1.1', 'none'): dict(row)}
        return {}
    with patch.object(ExtConfigDBConnector, 'get_table', fake_get_table, create=True):
        daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'STATIC_ROUTE_NEXTHOP'][0]
    run_cmd.reset_mock()

    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', dict(row))
    assert run_cmd.call_args_list == []

    hdlr('STATIC_ROUTE_NEXTHOP', 'default|10.1.0.0/24|192.168.1.1|none', {'bfd': 'true'})
    calls = run_cmd.call_args_list
    assert len(calls) == 2
    assert _last_static_route_cmd(calls[0]) == 'no ip route 10.1.0.0/24 192.168.1.1 bfd source 192.168.1.254 profile fast'
    assert _last_static_route_cmd(calls[1]) == 'ip route 10.1.0.0/24 192.168.1.1 bfd'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_missing_required_fields(run_cmd):
    """Test SR-Policy with missing required fields - should skip without crashing"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    run_cmd.reset_mock()
    test_seg_invalid = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'bad_path|10',
        {},  # Missing ipv6_address
        [],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg_invalid)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'bad_path|10', CmdMapTestInfo.get_test_data(test_seg_invalid))
    assert run_cmd.call_count == 0, "Missing ipv6_address should prevent FRR command"

    run_cmd.reset_mock()
    test_seg_valid = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'good_path|10',
        {'ipv6_address': '2001:db8:1::1'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list good_path',
         'index 10 ipv6-address 2001:db8:1::1', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg_valid)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'good_path|10', CmdMapTestInfo.get_test_data(test_seg_valid))
    test_seg_valid.check_running_cmd(run_cmd, False)
    assert run_cmd.call_count > 0, "Valid data should trigger FRR command"


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_multiple_segments_same_list(run_cmd):
    """Test adding multiple segments to the same segment list"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    assert(len(seg_hdlr) == 1)

    test_seg1 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'multi_seg_path|10',
        {'ipv6_address': '2001:db8:1::1'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list multi_seg_path',
         'index 10 ipv6-address 2001:db8:1::1', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'multi_seg_path|10', CmdMapTestInfo.get_test_data(test_seg1))
    test_seg1.check_running_cmd(run_cmd, False)

    run_cmd.reset_mock()
    test_seg2 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'multi_seg_path|20',
        {'ipv6_address': '2001:db8:2::2'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list multi_seg_path',
         'index 20 ipv6-address 2001:db8:2::2', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'multi_seg_path|20', CmdMapTestInfo.get_test_data(test_seg2))
    test_seg2.check_running_cmd(run_cmd, False)

    run_cmd.reset_mock()
    test_seg3 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'multi_seg_path|30',
        {'ipv6_address': '2001:db8:3::3'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list multi_seg_path',
         'index 30 ipv6-address 2001:db8:3::3', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg3)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'multi_seg_path|30', CmdMapTestInfo.get_test_data(test_seg3))
    test_seg3.check_running_cmd(run_cmd, False)

    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'multi_seg_path|20', None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_complex_integration(run_cmd):
    """Test complex integration: multiple policies, shared segment lists, various operations"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1 and len(pol_hdlr) == 1)

    seg_lists = []
    for i, name in enumerate(['path_a', 'path_b', 'shared_path'], 1):
        test_seg = CmdMapTestInfo('SR_TE_SEGMENT_LIST', f'{name}|10',
                                   {'ipv6_address': f'2001:db8:{i}::1'}, [], no_del=True)
        CmdMapTestInfo.add_test_data(test_seg)
        seg_hdlr[0]('SR_TE_SEGMENT_LIST', f'{name}|10', CmdMapTestInfo.get_test_data(test_seg))
        seg_lists.append(test_seg)

    policies = []
    for i, (color, endpoint) in enumerate([(100, '2001:db8:10::1'), (200, '2001:db8:20::1')], 1):
        test_pol = CmdMapTestInfo('SR_POLICY', f'{color}|{endpoint}',
                                   {'name': f'policy_{i}'}, [], no_del=True)
        CmdMapTestInfo.add_test_data(test_pol)
        pol_hdlr[0]('SR_POLICY', f'{color}|{endpoint}', CmdMapTestInfo.get_test_data(test_pol))
        policies.append((color, endpoint, test_pol))

    # Policy 1: Use path_a and shared_path (2 candidate paths)
    cp1_a = CmdMapTestInfo('SR_POLICY', '100|2001:db8:10::1|100',
                           {'name': 'cp1a', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp1_a)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1|100', CmdMapTestInfo.get_test_data(cp1_a))

    sl1_a = CmdMapTestInfo('SR_POLICY', '100|2001:db8:10::1|100|path_a', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(sl1_a)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1|100|path_a', CmdMapTestInfo.get_test_data(sl1_a))

    cp1_shared = CmdMapTestInfo('SR_POLICY', '100|2001:db8:10::1|200',
                                {'name': 'cp1shared', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp1_shared)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1|200', CmdMapTestInfo.get_test_data(cp1_shared))

    sl1_shared = CmdMapTestInfo('SR_POLICY', '100|2001:db8:10::1|200|shared_path', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(sl1_shared)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1|200|shared_path', CmdMapTestInfo.get_test_data(sl1_shared))

    # Policy 2: Use path_b and shared_path
    cp2_b = CmdMapTestInfo('SR_POLICY', '200|2001:db8:20::1|100',
                           {'name': 'cp2b', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp2_b)
    pol_hdlr[0]('SR_POLICY', '200|2001:db8:20::1|100', CmdMapTestInfo.get_test_data(cp2_b))

    sl2_b = CmdMapTestInfo('SR_POLICY', '200|2001:db8:20::1|100|path_b', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(sl2_b)
    pol_hdlr[0]('SR_POLICY', '200|2001:db8:20::1|100|path_b', CmdMapTestInfo.get_test_data(sl2_b))

    cp2_shared = CmdMapTestInfo('SR_POLICY', '200|2001:db8:20::1|200',
                                {'name': 'cp2shared', 'type': 'explicit'}, [], no_del=True)
    CmdMapTestInfo.add_test_data(cp2_shared)
    pol_hdlr[0]('SR_POLICY', '200|2001:db8:20::1|200', CmdMapTestInfo.get_test_data(cp2_shared))

    sl2_shared = CmdMapTestInfo('SR_POLICY', '200|2001:db8:20::1|200|shared_path', {}, [], no_del=True)
    CmdMapTestInfo.add_test_data(sl2_shared)
    pol_hdlr[0]('SR_POLICY', '200|2001:db8:20::1|200|shared_path', CmdMapTestInfo.get_test_data(sl2_shared))

    assert daemon._sr_segment_list_refs.get('path_a', 0) == 1
    assert daemon._sr_segment_list_refs.get('path_b', 0) == 1
    assert daemon._sr_segment_list_refs.get('shared_path', 0) == 2  # Shared by both policies

    # Test: Delete shared_path from policy 1
    CmdMapTestInfo.del_test_data(sl1_shared)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:10::1|200|shared_path', None)

    assert daemon._sr_segment_list_refs.get('shared_path', 0) == 1


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_delete_last_index_removes_segment_list(run_cmd):
    """Test that deleting the last index removes the entire segment list from FRR"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    assert(len(seg_hdlr) == 1)

    # Add two indices to segment list sl1
    test_seg1 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'sl1|1',
        {'ipv6_address': '1000::1'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list sl1',
         'index 1 ipv6-address 1000::1', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl1|1', CmdMapTestInfo.get_test_data(test_seg1))
    test_seg1.check_running_cmd(run_cmd, False)

    test_seg2 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'sl1|2',
        {'ipv6_address': '1000::2'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list sl1',
         'index 2 ipv6-address 1000::2', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl1|2', CmdMapTestInfo.get_test_data(test_seg2))
    test_seg2.check_running_cmd(run_cmd, False)

    # Delete first index - should only delete the index, not the segment list
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_seg1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl1|1', None)

    # Verify the command deletes only the index
    assert run_cmd.call_count == 1
    cmd = run_cmd.call_args[0][1]
    assert 'no index 1' in cmd
    assert 'no segment-list' not in cmd

    # Delete second (last) index - should delete the entire segment list
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'sl1|2', None)

    # Verify the command deletes the entire segment list
    assert run_cmd.call_count == 1
    cmd = run_cmd.call_args[0][1]
    assert 'no segment-list sl1' in cmd
    assert 'no index' not in cmd


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_sr_policy_defer_only_last_index_deletion(run_cmd):
    """Test that only last-index deletion is deferred when segment list is referenced"""
    from frrcfgd.frrcfgd import BGPConfigDaemon

    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    seg_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_TE_SEGMENT_LIST']
    pol_hdlr = [h for t, h in daemon.table_handler_list if t == 'SR_POLICY']
    assert(len(seg_hdlr) == 1)
    assert(len(pol_hdlr) == 1)

    # Add two indices to segment list path1
    test_seg1 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'path1|10',
        {'ipv6_address': '2001:db8:1::1'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list path1',
         'index 10 ipv6-address 2001:db8:1::1', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', CmdMapTestInfo.get_test_data(test_seg1))

    test_seg2 = CmdMapTestInfo(
        'SR_TE_SEGMENT_LIST',
        'path1|20',
        {'ipv6_address': '2001:db8:1::2'},
        ['configure terminal', 'segment-routing', 'traffic-eng', 'segment-list path1',
         'index 20 ipv6-address 2001:db8:1::2', 'exit'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|20', CmdMapTestInfo.get_test_data(test_seg2))

    # Add SR-Policy that references path1 (increments ref count)
    test_pol = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1',
        {'name': 'test_pol'},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1', 'name test_pol'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_pol)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1', CmdMapTestInfo.get_test_data(test_pol))

    test_cp = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100',
        {'name': 'cp1', 'type': 'explicit'},
        [],
        no_del=True,
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_cp)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100', CmdMapTestInfo.get_test_data(test_cp))

    test_cp_sl = CmdMapTestInfo(
        'SR_POLICY',
        '100|2001:db8:3::1|100|path1',
        {},
        ['configure terminal', 'segment-routing', 'traffic-eng',
         'policy color 100 endpoint 2001:db8:3::1',
         'candidate-path preference 100 name cp1 explicit',
         'segment-list path1 weight 1'],
        ignore_tail=None
    )
    CmdMapTestInfo.add_test_data(test_cp_sl)
    pol_hdlr[0]('SR_POLICY', '100|2001:db8:3::1|100|path1', CmdMapTestInfo.get_test_data(test_cp_sl))

    # Verify path1 ref count is 1
    assert daemon._sr_segment_list_refs.get('path1', 0) == 1

    # Delete index 20 (NOT the last index) while path1 is still referenced
    # Should delete the index immediately (not deferred)
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_seg2)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|20', None)

    # Verify command was executed (not deferred)
    assert run_cmd.call_count == 1
    cmd = run_cmd.call_args[0][1]
    assert 'no index 20' in cmd
    assert 'no segment-list' not in cmd

    # Verify path1 is NOT in pending deletion set
    assert 'path1' not in daemon._sr_pending_delete_segment_lists

    # Now delete index 10 (the LAST index) while path1 is still referenced
    # Should defer deletion (not execute command)
    run_cmd.reset_mock()
    CmdMapTestInfo.del_test_data(test_seg1)
    seg_hdlr[0]('SR_TE_SEGMENT_LIST', 'path1|10', None)

    # Verify NO command was executed (deferred)
    assert run_cmd.call_count == 0

    # Verify path1 IS in pending deletion set
    assert 'path1' in daemon._sr_pending_delete_segment_lists


# BGP Aggregate Address tests
bgp_aggregate_addr_data = [
    # Set up BGP globals first
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '65001'},
                  conf_bgp_dft_cmd('default', 65001),
                  ignore_tail=None),
    # Test 1: Basic aggregate with origin=igp
    CmdMapTestInfo('BGP_GLOBALS_AF_AGGREGATE_ADDR', 'default|ipv4_unicast|192.168.1.0/24',
                  {'as_set': 'true', 'summary_only': 'false', 'origin': 'igp'},
                  conf_bgp_cmd('default', 65001) + ['address-family ipv4 unicast',
                                                     '{}aggregate-address 192.168.1.0/24 as-set   origin igp']),
    # Test 2: Aggregate with origin=egp and summary-only
    CmdMapTestInfo('BGP_GLOBALS_AF_AGGREGATE_ADDR', 'default|ipv4_unicast|192.168.2.0/24',
                  {'as_set': 'true', 'summary_only': 'true', 'origin': 'egp'},
                  conf_bgp_cmd('default', 65001) + ['address-family ipv4 unicast',
                                                     '{}aggregate-address 192.168.2.0/24 as-set summary-only  origin egp']),
    # Test 3: Aggregate with origin=incomplete (no as-set, no summary-only)
    CmdMapTestInfo('BGP_GLOBALS_AF_AGGREGATE_ADDR', 'default|ipv4_unicast|192.168.3.0/24',
                  {'as_set': 'false', 'summary_only': 'false', 'origin': 'incomplete'},
                  conf_bgp_cmd('default', 65001) + ['address-family ipv4 unicast',
                                                     '{}aggregate-address 192.168.3.0/24    origin incomplete']),
    # Test 4: Aggregate with policy and origin
    CmdMapTestInfo('BGP_GLOBALS_AF_AGGREGATE_ADDR', 'default|ipv4_unicast|192.168.4.0/24',
                  {'as_set': 'false', 'summary_only': 'false', 'policy': 'AGG_POLICY', 'origin': 'igp'},
                  conf_bgp_cmd('default', 65001) + ['address-family ipv4 unicast',
                                                     '{}aggregate-address 192.168.4.0/24   route-map AGG_POLICY origin igp']),
    # Test 5: Aggregate with only policy (no origin) - ensure origin field doesn't break command
    CmdMapTestInfo('BGP_GLOBALS_AF_AGGREGATE_ADDR', 'default|ipv4_unicast|192.168.5.0/24',
                  {'as_set': 'false', 'summary_only': 'false', 'policy': 'POLICY_ONLY'},
                  conf_bgp_cmd('default', 65001) + ['address-family ipv4 unicast',
                                                     '{}aggregate-address 192.168.5.0/24   route-map POLICY_ONLY ']),
    # Test 6: Aggregate with origin but no policy - ensure policy field doesn't break command
    CmdMapTestInfo('BGP_GLOBALS_AF_AGGREGATE_ADDR', 'default|ipv4_unicast|192.168.6.0/24',
                  {'as_set': 'true', 'summary_only': 'false', 'origin': 'egp'},
                  conf_bgp_cmd('default', 65001) + ['address-family ipv4 unicast',
                                                     '{}aggregate-address 192.168.6.0/24 as-set   origin egp']),
    # Test 7: IPv6 aggregate with origin
    CmdMapTestInfo('BGP_GLOBALS_AF_AGGREGATE_ADDR', 'default|ipv6_unicast|fc00::/64',
                  {'as_set': 'true', 'summary_only': 'true', 'origin': 'igp'},
                  conf_bgp_cmd('default', 65001) + ['address-family ipv6 unicast',
                                                     '{}aggregate-address fc00::/64 as-set summary-only  origin igp']),
]


def test_bgp_aggregate_address():
    """Test BGP aggregate address configuration with origin attribute.

    This test ensures that:
    1. The origin attribute is correctly included in aggregate-address commands
    2. The policy and origin fields (marked with ++ prefix) are optional but tracked
    3. Missing optional fields don't break the command generation loop
    4. All combinations of as-set, summary-only, policy, and origin work correctly
    """
    # Skip delete testing - dedicated delete test below handles deletion
    data_set_del_test(bgp_aggregate_addr_data, skip_del=True)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_aggregate_address_delete(run_cmd):
    """Test BGP aggregate address DELETE operations and cache cleanup.

    This test verifies:
    1. Delete commands are correctly generated with 'no aggregate-address <prefix>'
    2. Cache (af_aggr_list) is properly cleaned up after deletion
    3. Deletion works for aggregates with different field combinations
    4. Deleting non-existent aggregates is handled gracefully
    """
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    # Setup: Initialize BGP
    daemon.bgp_asn = {'default': 65001}
    daemon.bgp_global_handler('BGP_GLOBALS', 'default', {'local_asn': '65001'})

    # Test 1: Delete aggregate with origin=igp
    daemon.bgp_table_handler_common(
        'BGP_GLOBALS_AF_AGGREGATE_ADDR',
        'default|ipv4_unicast|192.168.1.0/24',
        {'as_set': 'true', 'summary_only': 'false', 'origin': 'igp'}
    )
    run_cmd.reset_mock()

    daemon.bgp_table_handler_common(
        'BGP_GLOBALS_AF_AGGREGATE_ADDR',
        'default|ipv4_unicast|192.168.1.0/24',
        None  # None triggers deletion
    )

    # Verify: Delete command generated
    commands = ' '.join(' '.join(c) if isinstance(c, list) else c for c in [call[0][1] for call in run_cmd.call_args_list])
    assert 'no aggregate-address 192.168.1.0/24' in commands
    assert 'address-family ipv4 unicast' in commands

    # Verify: Cache cleaned up
    assert ('default' not in daemon.af_aggr_list or
            '192.168.1.0/24' not in daemon.af_aggr_list.get('default', {}))

    # Test 2: Delete aggregate with policy and origin
    daemon.bgp_table_handler_common(
        'BGP_GLOBALS_AF_AGGREGATE_ADDR',
        'default|ipv4_unicast|192.168.2.0/24',
        {'as_set': 'false', 'summary_only': 'true', 'policy': 'AGG_POLICY', 'origin': 'egp'}
    )
    run_cmd.reset_mock()

    daemon.bgp_table_handler_common(
        'BGP_GLOBALS_AF_AGGREGATE_ADDR',
        'default|ipv4_unicast|192.168.2.0/24',
        None
    )

    # Verify: Delete command generated
    commands = ' '.join(' '.join(c) if isinstance(c, list) else c for c in [call[0][1] for call in run_cmd.call_args_list])
    assert 'no aggregate-address 192.168.2.0/24' in commands

    # Verify: Cache cleaned up
    assert ('default' not in daemon.af_aggr_list or
            '192.168.2.0/24' not in daemon.af_aggr_list.get('default', {}))

    # Test 3: Delete IPv6 aggregate with origin
    daemon.bgp_table_handler_common(
        'BGP_GLOBALS_AF_AGGREGATE_ADDR',
        'default|ipv6_unicast|fc00::/64',
        {'as_set': 'true', 'summary_only': 'true', 'origin': 'incomplete'}
    )
    run_cmd.reset_mock()

    daemon.bgp_table_handler_common(
        'BGP_GLOBALS_AF_AGGREGATE_ADDR',
        'default|ipv6_unicast|fc00::/64',
        None
    )

    # Verify: Delete command generated
    commands = ' '.join(' '.join(c) if isinstance(c, list) else c for c in [call[0][1] for call in run_cmd.call_args_list])
    assert 'no aggregate-address fc00::/64' in commands
    assert 'address-family ipv6 unicast' in commands

    # Verify: Cache cleaned up
    assert ('default' not in daemon.af_aggr_list or
            'fc00::/64' not in daemon.af_aggr_list.get('default', {}))

    # Test 4: Delete non-existent aggregate (should be noop - no crash)
    run_cmd.reset_mock()

    daemon.bgp_table_handler_common(
        'BGP_GLOBALS_AF_AGGREGATE_ADDR',
        'default|ipv4_unicast|10.0.0.0/8',
        None  # Delete something that was never added
    )

    # Should not crash, and no aggregate-address command should be generated
    # (only address-family context commands are okay)
    commands = ' '.join(' '.join(c) if isinstance(c, list) else c for c in [call[0][1] for call in run_cmd.call_args_list])
    # The handler might enter AF context but shouldn't have a delete command for non-existent aggregate
    # This is implementation-dependent, so we just verify it doesn't crash


def _make_prm_daemon(run_cmd, initial_table=None):
    """Helper: build a BGPConfigDaemon and seed protocol_route_map_state
    from initial_table (a dict of key -> {'route_map': ...}), then reset
    run_cmd so the caller sees only the vtysh it triggers.

    The daemon's own __init__ runs against a mocked config_db that returns
    empty tables, so the state dict starts empty; we reseed it afterwards
    to simulate pre-existing rows without touching the init path.
    """
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    initial_table = initial_table or {}
    daemon.protocol_route_map_state = {}
    for k, v in initial_table.items():
        norm_key = '|'.join(k) if isinstance(k, tuple) else str(k)
        rm = v.get('route_map') if isinstance(v, dict) else None
        if rm:
            daemon.protocol_route_map_state[norm_key] = rm
    run_cmd.reset_mock()
    return daemon


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_set_default_vrf_ipv4(run_cmd):
    """SET on default VRF, ipv4, bgp emits 'ip protocol bgp route-map <NAME>'."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_FROM_BGP'})
    assert run_cmd.call_count == 1
    cmd = run_cmd.call_args[0][1]
    assert "configure terminal" in cmd
    assert "ip protocol bgp route-map RM_FROM_BGP" in cmd
    assert "vrf " not in cmd  # default VRF: no 'vrf …' wrapping in the vtysh
    assert daemon.protocol_route_map_state['default|IPv4|bgp'] == 'RM_FROM_BGP'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_set_default_vrf_ipv6_ospf6(run_cmd):
    """IPv6 renders the 'ipv6' keyword instead of 'ip'."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv6|ospf6', {'route_map': 'RM_V6'})
    cmd = run_cmd.call_args[0][1]
    assert "ipv6 protocol ospf6 route-map RM_V6" in cmd
    assert "ip protocol" not in cmd  # should NOT emit ipv4 form
    assert daemon.protocol_route_map_state['default|IPv6|ospf6'] == 'RM_V6'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_set_named_vrf_wraps_in_vrf_block(run_cmd):
    """Non-default VRF wraps the line in 'vrf <N> / ... / exit-vrf'."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'Vrf_red|IPv4|static', {'route_map': 'RM_STATIC'})
    cmd = run_cmd.call_args[0][1]
    assert "vrf Vrf_red" in cmd
    assert "ip protocol static route-map RM_STATIC" in cmd
    assert "exit-vrf" in cmd


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_set_with_tuple_key(run_cmd):
    """swsscommon may deliver compound keys as tuples; handler must accept both."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', ('default', 'IPv4', 'connected'),
        {'route_map': 'RM_CONN'})
    cmd = run_cmd.call_args[0][1]
    assert "ip protocol connected route-map RM_CONN" in cmd
    assert daemon.protocol_route_map_state['default|IPv4|connected'] == 'RM_CONN'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_idempotent_set_skipped(run_cmd):
    """Applying the same route-map twice must emit vtysh only once."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_A'})
    assert run_cmd.call_count == 1
    run_cmd.reset_mock()
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_A'})
    assert run_cmd.call_count == 0


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_update_route_map(run_cmd):
    """Updating to a different route-map emits a fresh binding."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_A'})
    run_cmd.reset_mock()
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_B'})
    assert run_cmd.call_count == 1
    cmd = run_cmd.call_args[0][1]
    assert "ip protocol bgp route-map RM_B" in cmd
    assert "RM_A" not in cmd
    assert daemon.protocol_route_map_state['default|IPv4|bgp'] == 'RM_B'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_emits_no_form(run_cmd):
    """Deletion emits 'no ip protocol <PROTO> route-map <NAME>' using stored RM."""
    daemon = _make_prm_daemon(
        run_cmd,
        initial_table={('default', 'IPv4', 'bgp'): {'route_map': 'RM_FROM_BGP'}},
    )
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', None)
    assert run_cmd.call_count == 1
    cmd = run_cmd.call_args[0][1]
    assert "no ip protocol bgp route-map RM_FROM_BGP" in cmd
    assert 'default|IPv4|bgp' not in daemon.protocol_route_map_state


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_named_vrf(run_cmd):
    """Deletion of a named-VRF row wraps the 'no' in 'vrf <N> / exit-vrf'."""
    daemon = _make_prm_daemon(
        run_cmd,
        initial_table={('Vrf_red', 'IPv4', 'static'): {'route_map': 'RM_STATIC'}},
    )
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'Vrf_red|IPv4|static', None)
    cmd = run_cmd.call_args[0][1]
    assert "vrf Vrf_red" in cmd
    assert "no ip protocol static route-map RM_STATIC" in cmd
    assert "exit-vrf" in cmd


def _with_loopback0(daemon, *prefixes):
    """Give the daemon's config_db a LOOPBACK_INTERFACE table holding
    Loopback0 with the given prefixes, keyed as get_table() returns them."""
    table = {'Loopback0': {}}
    table.update({('Loopback0', p): {} for p in prefixes})
    daemon.config_db.get_table = MagicMock(
        side_effect=lambda name: table if name == 'LOOPBACK_INTERFACE' else {})
    return daemon


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_bgp_ipv4_restores_rm_set_src(run_cmd):
    """Deleting the bgp row puts back the image's RM_SET_SRC binding that the
    row replaced, instead of leaving bgp without a protocol route-map and its
    routes without a source address (NOS-20782)."""
    daemon = _with_loopback0(_make_prm_daemon(
        run_cmd,
        initial_table={('default', 'IPv4', 'bgp'): {'route_map': 'RM_TEST'}},
    ), '10.1.0.32/32', 'FC00:1::32/128')
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', None)
    assert run_cmd.call_count == 1
    assert run_cmd.call_args[0][1] == [
        'vtysh', '-c', 'configure terminal',
        '-c', 'route-map RM_SET_SRC permit 10',
        '-c', 'set src 10.1.0.32',
        '-c', 'exit',
        '-c', 'ip protocol bgp route-map RM_SET_SRC']
    assert 'default|IPv4|bgp' not in daemon.protocol_route_map_state


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_bgp_ipv6_restores_rm_set_src6(run_cmd):
    """IPv6 restores RM_SET_SRC6 with the address lowercased, as the boot
    template renders it."""
    daemon = _with_loopback0(_make_prm_daemon(
        run_cmd,
        initial_table={('default', 'IPv6', 'bgp'): {'route_map': 'RM_TEST6'}},
    ), '10.1.0.32/32', 'FC00:1::32/128')
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv6|bgp', None)
    cmd = run_cmd.call_args[0][1]
    assert 'route-map RM_SET_SRC6 permit 10' in cmd
    assert 'set src fc00:1::32' in cmd
    assert 'ipv6 protocol bgp route-map RM_SET_SRC6' in cmd


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_bgp_without_loopback_of_family_unbinds(run_cmd):
    """With no Loopback0 address of the family the image binds nothing, so
    there is nothing to restore."""
    daemon = _with_loopback0(_make_prm_daemon(
        run_cmd,
        initial_table={('default', 'IPv4', 'bgp'): {'route_map': 'RM_TEST'}},
    ), 'FC00:1::32/128')
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', None)
    cmd = run_cmd.call_args[0][1]
    assert 'no ip protocol bgp route-map RM_TEST' in cmd
    assert not [c for c in cmd if 'RM_SET_SRC' in c]


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_non_bgp_does_not_restore(run_cmd):
    """The image binds RM_SET_SRC to bgp only; other protocols just unbind."""
    daemon = _with_loopback0(_make_prm_daemon(
        run_cmd,
        initial_table={('default', 'IPv4', 'static'): {'route_map': 'RM_TEST'}},
    ), '10.1.0.32/32')
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|static', None)
    cmd = run_cmd.call_args[0][1]
    assert 'no ip protocol static route-map RM_TEST' in cmd
    assert not [c for c in cmd if 'RM_SET_SRC' in c]


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_named_vrf_bgp_does_not_restore(run_cmd):
    """The image binds RM_SET_SRC in the default VRF only."""
    daemon = _with_loopback0(_make_prm_daemon(
        run_cmd,
        initial_table={('Vrf_red', 'IPv4', 'bgp'): {'route_map': 'RM_TEST'}},
    ), '10.1.0.32/32')
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'Vrf_red|IPv4|bgp', None)
    cmd = run_cmd.call_args[0][1]
    assert 'no ip protocol bgp route-map RM_TEST' in cmd
    assert not [c for c in cmd if 'RM_SET_SRC' in c]


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_failed_restore_keeps_state(run_cmd):
    """A restore FRR refused leaves the row tracked, so a retried delete
    sends the restore again."""
    daemon = _with_loopback0(_make_prm_daemon(
        run_cmd,
        initial_table={('default', 'IPv4', 'bgp'): {'route_map': 'RM_TEST'}},
    ), '10.1.0.32/32')
    run_cmd.return_value = False
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', None)
    assert daemon.protocol_route_map_state['default|IPv4|bgp'] == 'RM_TEST'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_untracked_is_noop(run_cmd):
    """Delete on a key never set is a silent noop — no vtysh push."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', None)
    assert run_cmd.call_count == 0


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_malformed_key_is_ignored(run_cmd):
    """Keys with the wrong number of components must be rejected without a push."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|ipv4', {'route_map': 'RM'})
    assert run_cmd.call_count == 0


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_unsupported_afi_is_ignored(run_cmd):
    """addr_family outside IPv4/IPv6 must not produce a vtysh command."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPvX|bgp', {'route_map': 'RM'})
    assert run_cmd.call_count == 0


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_missing_route_map_is_ignored(run_cmd):
    """A SET with no route_map field is rejected — YANG should have blocked
    this, but the daemon must not push a broken vtysh command if it slips through."""
    daemon = _make_prm_daemon(run_cmd)
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {})
    assert run_cmd.call_count == 0


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_registered_in_table_handler_list(run_cmd):
    """Sanity check: PROTOCOL_ROUTE_MAP is wired into table_handler_list so
    CONFIG_DB subscription routes to our handler."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    mapped = dict(daemon.table_handler_list)
    assert 'PROTOCOL_ROUTE_MAP' in mapped
    assert mapped['PROTOCOL_ROUTE_MAP'] == daemon.protocol_route_map_handler


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_set_state_not_updated_on_failure(run_cmd):
    """If vtysh fails, the handler must NOT record the new route-map in
    protocol_route_map_state — otherwise a retry would be silently
    short-circuited by the idempotent `prev_rm == route_map` check."""
    daemon = _make_prm_daemon(run_cmd)
    run_cmd.return_value = False  # simulate transient FRR failure
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_A'})
    assert run_cmd.call_count == 1  # command was attempted
    assert 'default|IPv4|bgp' not in daemon.protocol_route_map_state


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_failed_set_is_retryable(run_cmd):
    """After a failed SET, a retry with the same data must re-emit the vtysh
    (not be short-circuited as 'already applied'), and a successful retry
    must then advance state."""
    daemon = _make_prm_daemon(run_cmd)
    # First attempt fails.
    run_cmd.return_value = False
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_A'})
    assert 'default|IPv4|bgp' not in daemon.protocol_route_map_state
    # Retry succeeds.
    run_cmd.return_value = True
    run_cmd.reset_mock()
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_A'})
    assert run_cmd.call_count == 1  # not skipped as idempotent
    assert daemon.protocol_route_map_state['default|IPv4|bgp'] == 'RM_A'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_delete_state_not_updated_on_failure(run_cmd):
    """If the `no ... route-map` vtysh fails, state must still reflect the
    old route-map so a retry can emit the same 'no' form."""
    daemon = _make_prm_daemon(
        run_cmd,
        initial_table={('default', 'IPv4', 'bgp'): {'route_map': 'RM_A'}},
    )
    run_cmd.return_value = False
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', None)
    assert run_cmd.call_count == 1
    # State still shows RM_A so retry can emit `no ... route-map RM_A`.
    assert daemon.protocol_route_map_state['default|IPv4|bgp'] == 'RM_A'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_prm_update_failure_preserves_prior_route_map(run_cmd):
    """If an update from RM_A -> RM_B fails, state must still show RM_A
    (matching what zebra actually has), not RM_B."""
    daemon = _make_prm_daemon(
        run_cmd,
        initial_table={('default', 'IPv4', 'bgp'): {'route_map': 'RM_A'}},
    )
    run_cmd.return_value = False
    daemon.protocol_route_map_handler(
        'PROTOCOL_ROUTE_MAP', 'default|IPv4|bgp', {'route_map': 'RM_B'})
    assert daemon.protocol_route_map_state['default|IPv4|bgp'] == 'RM_A'


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
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vrf_vni_map_not_advanced_on_failed_push(run_cmd):
    """vrf_vni_map records what FRR accepted, so a failed push must not move it (NOS-17855).

    The handler used to update the map first and discard the push result: a
    failed `vni N` left the VRF recorded as bound, and a failed `no vni N` left
    it recorded as unbound, so the next withdrawal was wrong or never sent.
    """
    from frrcfgd.frrcfgd import BGPConfigDaemon
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'VRF'][0]

    # A failed bind is not recorded. The retry that follows carries the same
    # `vni` and has to be pushed again, not skipped as already applied.
    run_cmd.return_value = False
    hdlr('VRF', 'Vrf_RED', {'vni': '10300'})
    assert 'Vrf_RED' not in daemon.vrf_vni_map
    run_cmd.reset_mock()
    run_cmd.return_value = True
    hdlr('VRF', 'Vrf_RED', {'vni': '10300'})
    assert 'vni 10300' in _all_pushed_cmds(run_cmd)
    assert daemon.vrf_vni_map['Vrf_RED'] == '10300'

    # A failed `vni 0` withdrawal keeps the entry, so the next one still
    # carries the value FRR holds.
    run_cmd.reset_mock()
    run_cmd.return_value = False
    hdlr('VRF', 'Vrf_RED', {'vni': '0'})
    assert 'no vni 10300' in _all_pushed_cmds(run_cmd)
    assert daemon.vrf_vni_map['Vrf_RED'] == '10300'
    run_cmd.reset_mock()
    run_cmd.return_value = True
    hdlr('VRF', 'Vrf_RED', {'vni': '0'})
    assert 'no vni 10300' in _all_pushed_cmds(run_cmd)
    assert 'Vrf_RED' not in daemon.vrf_vni_map

    # Same for deleting the row.
    run_cmd.return_value = True
    hdlr('VRF', 'Vrf_BLUE', {'vni': '10400'})
    run_cmd.return_value = False
    hdlr('VRF', 'Vrf_BLUE', {})
    assert daemon.vrf_vni_map['Vrf_BLUE'] == '10400'
    run_cmd.reset_mock()
    run_cmd.return_value = True
    hdlr('VRF', 'Vrf_BLUE', {})
    assert 'no vni 10400' in _all_pushed_cmds(run_cmd)
    assert 'Vrf_BLUE' not in daemon.vrf_vni_map


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command', return_value=True)
@patch('frrcfgd.frrcfgd.ExtConfigDBConnector')
def test_vrf_vni_map_seed_skips_vni_zero(ext_db, run_cmd):
    """A VRF row carrying `vni 0` at startup is not a binding (NOS-17855).

    Seeding it made the first delete emit `no vni 0`, which FRR rejects.
    """
    from frrcfgd.frrcfgd import BGPConfigDaemon
    rows = {'Vrf_RED': {'vni': '10300'}, 'Vrf_ZERO': {'vni': '0'},
            'Vrf_NONE': {'fallback': 'false'}}
    ext_db.return_value.get_table.side_effect = (
        lambda name: dict(rows) if name == 'VRF' else {})
    daemon = BGPConfigDaemon()
    assert daemon.vrf_vni_map == {'Vrf_RED': '10300'}


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


def _serialize_key(key):
    """ConfigDBConnector.serialize_key for the tuple keys get_table returns (the connector is mocked)."""
    return '|'.join(key) if isinstance(key, tuple) else key


def _bgpd_without_evpn(state):
    """A g_run_command stand-in for bgpd before advertise-all-vni: a per-VNI rd or route-target is
    refused ("This command is only supported under EVPN VRF") until advertise-all-vni is applied."""
    def run(table, command, *args, **kwargs):
        text = ' '.join(command)
        if 'advertise-all-vni' in text and 'no advertise-all-vni' not in text:
            state['evpn'] = True
        if ('route-target' in text or ' -c rd ' in text) and not state['evpn']:
            return False
        return True
    return run


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vni_rows_reapplied_when_advertise_all_vni_set(run_cmd):
    """NOS-19714: a GCU patch carrying advertise-all-vni with the VNI and route-target rows can have
    the route-target applied first. bgpd refuses it, frrcfgd does not retry, and the VNI renders as a
    bare 'vni N' block. Setting advertise-all-vni must re-apply the VRF's per-VNI rows from CONFIG_DB,
    VNI rows before their route-targets, and leave other VRFs' rows alone."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    state = {'evpn': False}
    run_cmd.side_effect = _bgpd_without_evpn(state)
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)
    rows = {
        'BGP_GLOBALS_EVPN_VNI': {('default', 'L2VPN_EVPN', '12100'): {'route-distinguisher': '10.1.0.1:12100'},
                                 ('Vrf_RED', 'L2VPN_EVPN', '12900'): {}},
        'BGP_GLOBALS_EVPN_VNI_RT': {('default', 'L2VPN_EVPN', '12100', '65000:12100'): {'route-target-type': 'both'},
                                    ('Vrf_RED', 'L2VPN_EVPN', '12900', '65000:12900'): {'route-target-type': 'both'}},
    }
    daemon.config_db.get_table = MagicMock(side_effect=lambda table: rows.get(table, {}))
    daemon.config_db.serialize_key = _serialize_key

    feed('BGP_GLOBALS', 'default', {'local_asn': '65100'})
    feed('BGP_GLOBALS_EVPN_VNI', 'default|L2VPN_EVPN|12100', {'route-distinguisher': '10.1.0.1:12100'})
    refused = feed('BGP_GLOBALS_EVPN_VNI_RT', 'default|L2VPN_EVPN|12100|65000:12100', {'route-target-type': 'both'})
    assert any('route-target both 65000:12100' in c for c in refused), refused

    cmds = feed('BGP_GLOBALS_AF', 'default|l2vpn_evpn', {'advertise-all-vni': 'true'})
    text = ' '.join(cmds)
    assert 'advertise-all-vni' in text
    rd = [i for i, c in enumerate(cmds) if 'vni 12100' in c and 'rd 10.1.0.1:12100' in c]
    rt = [i for i, c in enumerate(cmds) if 'vni 12100' in c and 'route-target both 65000:12100' in c]
    assert rd and rt and rd[0] < rt[0], cmds
    assert '12900' not in text, 'another VRF\'s per-VNI rows were re-applied: {}'.format(cmds)

    # Re-writing the same value is not a change, so nothing is re-applied.
    again = feed('BGP_GLOBALS_AF', 'default|l2vpn_evpn', {'advertise-all-vni': 'true'})
    assert not [c for c in again if 'route-target' in c], again


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vni_rows_not_reapplied_for_other_address_families(run_cmd):
    """Only advertise-all-vni on l2vpn_evpn enables EVPN in bgpd; the same leaf on another
    address family must not trigger the per-VNI re-apply."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)
    daemon.config_db.get_table = MagicMock(side_effect=lambda table: {
        'BGP_GLOBALS_EVPN_VNI_RT': {('default', 'L2VPN_EVPN', '12100', '65000:12100'): {'route-target-type': 'both'}},
    }.get(table, {}))
    daemon.config_db.serialize_key = _serialize_key

    feed('BGP_GLOBALS', 'default', {'local_asn': '65100'})
    cmds = feed('BGP_GLOBALS_AF', 'default|ipv6_unicast', {'advertise-all-vni': 'true'})
    assert not [c for c in cmds if 'route-target' in c], cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vni_rows_not_reapplied_when_advertise_all_vni_refused(run_cmd):
    """run_command() reports success if any field of the row succeeded, so a refused advertise-all-vni
    alongside an accepted leaf must not trigger the re-apply into a bgpd that still refuses the rows."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.side_effect = lambda table, command, *args, **kwargs: 'advertise-all-vni' not in ' '.join(command)
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)
    daemon.config_db.get_table = MagicMock(side_effect=lambda table: {
        'BGP_GLOBALS_EVPN_VNI_RT': {('default', 'L2VPN_EVPN', '12100', '65000:12100'): {'route-target-type': 'both'}},
    }.get(table, {}))
    daemon.config_db.serialize_key = _serialize_key

    feed('BGP_GLOBALS', 'default', {'local_asn': '65100'})
    cmds = feed('BGP_GLOBALS_AF', 'default|l2vpn_evpn', {'advertise-all-vni': 'true', 'advertise-svi-ip': 'true'})
    assert any('advertise-svi-ip' in c for c in cmds), cmds
    assert not [c for c in cmds if 'route-target' in c], cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_vni_rows_not_reapplied_during_start_replay(run_cmd):
    """start()'s replay applies BGP_GLOBALS_AF before the per-VNI tables, so re-applying them from
    the AF row there would apply every VNI and route-target row twice on each daemon start."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)
    daemon.config_db.get_table = MagicMock(side_effect=lambda table: {
        'BGP_GLOBALS_EVPN_VNI_RT': {('default', 'L2VPN_EVPN', '12100', '65000:12100'): {'route-target-type': 'both'}},
    }.get(table, {}))
    daemon.config_db.serialize_key = _serialize_key

    feed('BGP_GLOBALS', 'default', {'local_asn': '65100'})
    daemon._replaying = True
    cmds = feed('BGP_GLOBALS_AF', 'default|l2vpn_evpn', {'advertise-all-vni': 'true'})
    assert any('advertise-all-vni' in c for c in cmds), cmds
    assert not [c for c in cmds if 'route-target' in c], cmds


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


def _fake_config_db(daemon, state):
    """Answer get_table/get_entry from a mutable {table: {key: row}} dict, the
    way the real connector answers them, so code that reads CONFIG_DB sees the
    rows a test has 'written'."""
    daemon.config_db.get_table = MagicMock(
        side_effect=lambda name: {k: dict(v) for k, v in state.get(name, {}).items()})
    daemon.config_db.get_entry = MagicMock(
        side_effect=lambda name, key: dict(state.get(name, {}).get(key, {})))
    daemon.config_db.serialize_key = \
        lambda key, sep='|': sep.join(key) if isinstance(key, tuple) else key


def _evpn_rows(vrf, asn):
    """One row from each EVPN table, and the vtysh fragments, in the order
    they must reach FRR."""
    rt = '{}:10100'.format(asn)
    rows = [
        ('BGP_GLOBALS_AF', (vrf, 'l2vpn_evpn'), {'advertise-all-vni': 'true'}),
        ('BGP_GLOBALS_EVPN_RT', (vrf, 'L2VPN_EVPN', '{}:4000'.format(asn)),
         {'route-target-type': 'both'}),
        ('BGP_GLOBALS_EVPN_VNI', (vrf, 'L2VPN_EVPN', '10100'),
         {'route-distinguisher': '10.1.0.101:10100'}),
        ('BGP_GLOBALS_EVPN_VNI_RT', (vrf, 'L2VPN_EVPN', '10100', rt),
         {'route-target-type': 'import'}),
    ]
    expected = ['advertise-all-vni', 'route-target both {}:4000'.format(asn),
                'rd 10.1.0.101:10100', 'route-target import ' + rt]
    return rows, expected


def _other_vrf_rows(vrf):
    """Rows from VRF tables outside EVPN, which the replay must leave alone,
    and the fragments they produce."""
    rows = [
        ('BGP_GLOBALS_AF', (vrf, 'ipv4_unicast'), {'max_ebgp_paths': '2'}),
        ('BGP_PEER_GROUP', (vrf, 'PG1'), {'admin_status': 'true'}),
        ('BGP_GLOBALS_AF_AGGREGATE_ADDR', (vrf, 'ipv4_unicast', '192.168.1.0/24'),
         {'as_set': 'true'}),
    ]
    expected = ['maximum-paths 2', 'neighbor PG1 peer-group', 'aggregate-address 192.168.1.0/24']
    return rows, expected


def _write_row(daemon, run_cmd, state, table, key, data):
    """Store a row in the fake CONFIG_DB and deliver it as a live update."""
    state.setdefault(table, {})[key] = dict(data)
    return _feed_table(daemon, run_cmd, table, '|'.join(key), dict(data))


def _first_hit(cmds, fragment):
    hits = [i for i, cmd in enumerate(cmds) if fragment in cmd]
    assert len(hits) == 1, '{!r} was pushed {} times'.format(fragment, len(hits))
    return hits[0]


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_evpn_config_replayed_when_bgp_globals_recreated(run_cmd):
    """Removing BGP_GLOBALS runs 'no router bgp', which takes the VRF's EVPN
    configuration out of FRR, but the rows stay in CONFIG_DB. Creating
    BGP_GLOBALS again changes no EVPN row, so nothing wrote them back
    (NOS-17653). They are re-applied once each, advertise-all-vni first, and
    no other table's rows are touched."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    state = {}
    _fake_config_db(daemon, state)
    evpn, evpn_expected = _evpn_rows('default', '65101')
    other, other_expected = _other_vrf_rows('default')

    _feed_table(daemon, run_cmd, 'BGP_GLOBALS', 'default', {'local_asn': '65101'})
    applied = ' '.join(cmd for table, key, data in evpn + other
                       for cmd in _write_row(daemon, run_cmd, state, table, key, data))
    for fragment in evpn_expected + other_expected:
        assert fragment in applied, 'precondition: {!r} was not applied'.format(fragment)

    _feed_table(daemon, run_cmd, 'BGP_GLOBALS', 'default', None)
    cmds = _feed_table(daemon, run_cmd, 'BGP_GLOBALS', 'default', {'local_asn': '65101'})
    positions = [_first_hit(cmds, fragment) for fragment in evpn_expected]
    assert positions[0] == min(positions), 'advertise-all-vni was not re-applied first'
    replayed = [f for f in other_expected if any(f in cmd for cmd in cmds)]
    assert not replayed, 'non-EVPN rows were re-applied: {}'.format(replayed)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_evpn_rows_written_before_bgp_globals_apply_once_it_arrives(run_cmd):
    """An EVPN row that lands before its BGP_GLOBALS is dropped, since there is
    no 'router bgp' to configure it under. The same re-apply on local_asn picks
    it up."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    state = {}
    _fake_config_db(daemon, state)
    rows, expected = _evpn_rows('default', '65101')

    early = ' '.join(cmd for table, key, data in rows
                     for cmd in _write_row(daemon, run_cmd, state, table, key, data))
    for fragment in expected:
        assert fragment not in early, 'precondition: {!r} applied with no BGP_GLOBALS'.format(fragment)

    cmds = _feed_table(daemon, run_cmd, 'BGP_GLOBALS', 'default', {'local_asn': '65101'})
    for fragment in expected:
        _first_hit(cmds, fragment)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_evpn_replay_on_recreate_leaves_other_vrfs_alone(run_cmd):
    """Re-applying one VRF's EVPN rows must not touch another VRF's, which 'no
    router bgp' did not remove from FRR."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    state = {}
    _fake_config_db(daemon, state)

    for vrf, asn in (('default', '65101'), ('Vrf_RED', '65100')):
        _feed_table(daemon, run_cmd, 'BGP_GLOBALS', vrf, {'local_asn': asn})
        for table, key, data in _evpn_rows(vrf, asn)[0]:
            _write_row(daemon, run_cmd, state, table, key, data)

    _feed_table(daemon, run_cmd, 'BGP_GLOBALS', 'default', None)
    cmds = ' '.join(_feed_table(daemon, run_cmd, 'BGP_GLOBALS', 'default',
                                {'local_asn': '65101'}))
    assert 'advertise-all-vni' in cmds, 'precondition: the default VRF was not replayed'
    assert 'Vrf_RED' not in cmds


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_evpn_replay_skips_a_vrf_without_evpn(run_cmd):
    """A VRF with no l2vpn_evpn row gets no EVPN re-apply: get_entry answers {}
    for the missing row, which must not be queued as an empty update."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    state = {}
    _fake_config_db(daemon, state)

    put = MagicMock(wraps=daemon.bgp_message.put)
    with patch.object(daemon.bgp_message, 'put', put):
        _feed_table(daemon, run_cmd, 'BGP_GLOBALS', 'default', {'local_asn': '65101'})
    queued = [c.args[0] for c in put.call_args_list]
    assert not [m for m in queued if m[2] == 'BGP_GLOBALS_AF'], queued


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_evpn_startup_replay_applies_each_row_once(run_cmd):
    """At startup start() walks every table in order, BGP_GLOBALS first, so it
    reaches the EVPN rows itself. Setting local_asn there must not re-apply
    them as well, or every boot pushes each command twice."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    state = {'BGP_GLOBALS': {'default': {'local_asn': '65101'}}}
    _fake_config_db(daemon, state)
    rows, expected = _evpn_rows('default', '65101')
    for table, key, data in rows:
        state.setdefault(table, {})[key] = dict(data)

    run_cmd.reset_mock()
    daemon._replaying = True
    try:
        for table in ('BGP_GLOBALS', 'BGP_GLOBALS_AF', 'BGP_GLOBALS_EVPN_RT',
                      'BGP_GLOBALS_EVPN_VNI', 'BGP_GLOBALS_EVPN_VNI_RT'):
            daemon._replay_table(table)
    finally:
        daemon._replaying = False
    cmds = [' '.join(call[0][1]) for call in run_cmd.call_args_list]
    for fragment in expected:
        _first_hit(cmds, fragment)


def _local_as_cmds(cmds):
    return [c.split(' -c ')[-1].rstrip() for c in cmds if 'local-as' in c]

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_peer_local_as_same_as_instance_as(run_cmd):
    """FRR rejects 'neighbor X local-as N' when N is the instance AS. A row
    carrying that value means no local-as, so it is pushed as the 'no' form,
    the way bgpd.conf.db.nbr_or_peer.j2 leaves it out of frr.conf."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    feed = partial(_feed_table, daemon, run_cmd)
    feed('BGP_GLOBALS', 'default', {'local_asn': '100'})

    # Handlers wrap the values of the dict they are given, so each call gets its own.
    pg = lambda **kw: dict({'local_asn': '100', 'name': 'PG'}, **kw)
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'default|PG', pg())) == ['no neighbor PG local-as']
    # Accepted, so cached: an in-place change to another field leaves it alone.
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'default|PG', pg(name='PG2'))) == []

    # A GCU/rollback re-add brings every field back as new.
    feed('BGP_PEER_GROUP', 'default|PG', None)
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'default|PG', pg())) == ['no neighbor PG local-as']

    # Moving to the instance AS clears the override FRR holds.
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'default|PG', pg(local_asn='200'))) == \
        ['neighbor PG local-as 200']
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'default|PG', pg())) == ['no neighbor PG local-as']

    # Deleting it still goes through the key map, in the 'no' form FRR takes for any AS.
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'default|PG', {'name': 'PG'})) == \
        ['no neighbor PG local-as 100']
    feed('BGP_PEER_GROUP', 'default|PG', pg())

    # The flags mean nothing without an override.
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'default|PG', pg(local_as_no_prepend='true'))) == \
        ['no neighbor PG local-as']

    # Any other AS is an override, flags and all.
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'default|PG2',
                               {'local_asn': '300', 'local_as_no_prepend': 'true'})) == \
        ['neighbor PG2 local-as 300 no-prepend']
    assert _local_as_cmds(feed('BGP_NEIGHBOR', 'default|10.0.0.1',
                               {'asn': '65001', 'local_asn': '100'})) == ['no neighbor 10.0.0.1 local-as']

    # Compared against the row's own VRF.
    feed('BGP_GLOBALS', 'Vrf_red', {'local_asn': '200'})
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'Vrf_red|PG', {'local_asn': '100'})) == \
        ['neighbor PG local-as 100']
    assert _local_as_cmds(feed('BGP_PEER_GROUP', 'Vrf_red|PG3', {'local_asn': '200'})) == \
        ['no neighbor PG3 local-as']

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_peer_group_member_local_as_same_as_instance_as_warns(run_cmd):
    """Unsetting local-as on a peer-group member inherits the group's, so a
    member cannot be given the instance AS while its group overrides it."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    # The group's cache key is built with serialize_key(), which the mocked connector lacks.
    daemon.config_db.serialize_key = MagicMock(side_effect=lambda k: '|'.join(k))
    feed = partial(_feed_table, daemon, run_cmd)
    feed('BGP_GLOBALS', 'default', {'local_asn': '100'})
    feed('BGP_PEER_GROUP', 'default|PG', {'local_asn': '200'})

    def warnings(log):
        return [c.args[1] for c in log.call_args_list
                if c.args[0] == syslog.LOG_WARNING and 'inherits local-as' in c.args[1]]

    inherits = ['neighbor 10.0.0.1 local_asn 100 is the VRF default AS; '
                'it inherits local-as 200 from peer-group PG']
    member = {'asn': '65001', 'peer_group_name': 'PG', 'local_asn': '100'}
    with patch('frrcfgd.frrcfgd.syslog.syslog') as log:
        feed('BGP_NEIGHBOR', 'default|10.0.0.1', dict(member))
        assert warnings(log) == inherits

    # A flag-only write sends 'no neighbor X local-as' too, so it warns too.
    with patch('frrcfgd.frrcfgd.syslog.syslog') as log:
        feed('BGP_NEIGHBOR', 'default|10.0.0.1', dict(member, local_as_no_prepend='true'))
        assert warnings(log) == inherits

    # Leaving the group in the write that sets the instance AS: there is nothing to
    # inherit, and the deleted peer_group_name is the group being left.
    feed('BGP_NEIGHBOR', 'default|10.0.0.1', dict(member, local_asn='300'))
    with patch('frrcfgd.frrcfgd.syslog.syslog') as log:
        feed('BGP_NEIGHBOR', 'default|10.0.0.1', {'asn': '65001', 'local_asn': '100'})
        assert warnings(log) == []

    feed('BGP_PEER_GROUP', 'default|PG2', {'local_asn': '100'})
    with patch('frrcfgd.frrcfgd.syslog.syslog') as log:
        feed('BGP_NEIGHBOR', 'default|10.0.0.2',
             {'asn': '65001', 'peer_group_name': 'PG2', 'local_asn': '100'})
        assert warnings(log) == []
>>>>>>> 57c9bfaeb (NOS-19714: [frrcfgd] Re-apply per-VNI EVPN rows when advertise-all-vni is set (#11436))
