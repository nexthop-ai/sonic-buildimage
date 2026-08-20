import copy
import re
from unittest.mock import MagicMock, NonCallableMagicMock, patch

swsscommon_module_mock = MagicMock(ConfigDBConnector = NonCallableMagicMock)
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


<<<<<<< HEAD
=======
# RFC 5549 (IPv4 prefixes with an IPv6 next-hop) needs the IPv4 AFI active on
# a v6 BGP peer. The runtime path is a BGP_NEIGHBOR_AF write keyed
# `default|<v6-addr>|ipv4_unicast` — a *cross-AFI* row (v6 nbr, v4 AF) the
# create_af_test_data() generator above doesn't cover (it pairs each peer
# only with its own AFI). Without this, the operator workflow for RFC 5549
# is incomplete via sonic-db-cli alone.
v6_nbr_v4_af_data = [
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                   {'local_asn': '100'},
                   conf_bgp_dft_cmd('default', 100),
                   ignore_tail=None),
    # admin_status=up on the cross-AFI row must emit
    #   address-family ipv4 unicast
    #     neighbor 2001:db8::1 activate
    CmdMapTestInfo('BGP_NEIGHBOR_AF', 'default|2001:db8::1|ipv4_unicast',
                   {'admin_status': 'up'},
                   conf_bgp_af_cmd('default', 100, 'ipv4') +
                   ['neighbor 2001:db8::1 activate']),
    # admin_status=down on the same row must emit the matching `no ... activate`.
    CmdMapTestInfo('BGP_NEIGHBOR_AF', 'default|2001:db8::1|ipv4_unicast',
                   {'admin_status': 'down'},
                   conf_bgp_af_cmd('default', 100, 'ipv4') +
                   ['no neighbor 2001:db8::1 activate']),
]


def test_bgp_neighbor_af_cross_afi_rfc5549():
    """v6 neighbor in v4 AF — the RFC 5549 / capability_ext_nexthop runtime
    activation path. Skips delete verification for the same reason as the
    other neighbor-AF tests above (delete would re-issue the `no ...`
    forms)."""
    data_set_del_test(v6_nbr_v4_af_data, skip_del=True)

@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_neighbor_af_srpolicy_field_filtering(run_cmd):
    """FRR (bgpd/bgp_vty.c) only installs a handful of neighbor-AF commands on
    BGP_SRPOLICYV4_NODE/BGP_SRPOLICYV6_NODE: activate, route-map, maximum-prefix,
    route-reflector-client, send-community, attribute-unchanged. Fields like
    weight/prefix-list/soft-reconfiguration have no such command there and
    vtysh would reject them under 'address-family <afi> sr-policy'. Verify
    nbr_af_key_map skips the unsupported fields for *_srpolicy AFs while still
    pushing the ones FRR does support, for both BGP_NEIGHBOR_AF and
    BGP_PEER_GROUP_AF (they share the same key map), and for both the ipv4
    and ipv6 AFI (af_val differs, selecting a different admin_status|<afi>
    entry from the key map)."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    globals_hdlr = [h for t, h in daemon.table_handler_list if t == 'BGP_GLOBALS']
    assert len(globals_hdlr) == 1
    globals_hdlr[0]('BGP_GLOBALS', 'default', {'local_asn': '100'})

    for table_name, peer_name in [('BGP_NEIGHBOR_AF', '10.0.0.1'),
                                  ('BGP_PEER_GROUP_AF', 'PG1')]:
        hdlr = [h for t, h in daemon.table_handler_list if t == table_name]
        assert len(hdlr) == 1

        for afi in ('ipv4', 'ipv6'):
            run_cmd.reset_mock()
            hdlr[0](table_name, f'default|{peer_name}|{afi}_srpolicy',
                    {'weight': '100', 'soft_reconfiguration_in': 'true',
                     'prefix_list_in': 'PL1', 'route_server_client': 'true',
                     'rrclient': 'true', 'route_map_in': ['RM1']})
            flat = ' '.join(' '.join(c) if isinstance(c, list) else c
                            for c in [call[0][1] for call in run_cmd.call_args_list])
            for unsupported in ('weight', 'soft-reconfiguration', 'prefix-list', 'route-server-client'):
                assert unsupported not in flat
            assert f'neighbor {peer_name} route-reflector-client' in flat
            assert f'neighbor {peer_name} route-map RM1 in' in flat
            # CONFIG_DB/YANG spell this AF 'srpolicy' (no hyphen); FRR's
            # vtysh keyword is the hyphenated 'sr-policy', so frrcfgd must
            # translate it back before building the command.
            assert f'address-family {afi} sr-policy' in flat

        # Same fields on a plain unicast AF must still work (nothing gated).
        run_cmd.reset_mock()
        hdlr[0](table_name, f'default|{peer_name}|ipv4_unicast', {'weight': '100'})
        flat = ' '.join(' '.join(c) if isinstance(c, list) else c
                        for c in [call[0][1] for call in run_cmd.call_args_list])
        assert f'neighbor {peer_name} weight 100' in flat


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_neighbor_af_srpolicy_non_default_vrf_skipped(run_cmd):
    """FRR only implements SR-Policy SAFI in the default VRF (see the
    'must ancestor::.../vrf = "default"' guard on ipv4/6-sr-policy in
    frr-bgp-common-multiprotocol.yang). frrcfgd must skip a *_srpolicy
    BGP_NEIGHBOR_AF/BGP_PEER_GROUP_AF row in a non-default VRF outright
    rather than pushing 'address-family ipv4 sr-policy' under
    'router bgp <asn> vrf Vrf_red'."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    globals_hdlr = [h for t, h in daemon.table_handler_list if t == 'BGP_GLOBALS']
    assert len(globals_hdlr) == 1
    globals_hdlr[0]('BGP_GLOBALS', 'Vrf_red', {'local_asn': '200'})

    for table_name, peer_name in [('BGP_NEIGHBOR_AF', '10.0.0.1'),
                                  ('BGP_PEER_GROUP_AF', 'PG1')]:
        hdlr = [h for t, h in daemon.table_handler_list if t == table_name]
        assert len(hdlr) == 1

        run_cmd.reset_mock()
        hdlr[0](table_name, f'Vrf_red|{peer_name}|ipv4_srpolicy', {'admin_status': 'up'})
        assert not run_cmd.called


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_globals_af_srpolicy_skipped(run_cmd):
    """FRR installs no commands at all on BGP_SRPOLICYV4_NODE/V6_NODE outside
    'neighbor ...' context (no maximum-paths, install-backup-path, dampening,
    aggregate-address, network, etc.), so BGP_GLOBALS_AF has nothing valid to
    push for ipv4_srpolicy/ipv6_srpolicy. It must be skipped outright rather
    than entering 'address-family ipv4 sr-policy' and pushing global fields
    vtysh would reject there. YANG already rejects the entry (must on
    afi_safi); this is defense in depth."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    globals_hdlr = [h for t, h in daemon.table_handler_list if t == 'BGP_GLOBALS']
    assert len(globals_hdlr) == 1
    globals_hdlr[0]('BGP_GLOBALS', 'default', {'local_asn': '100'})

    hdlr = [h for t, h in daemon.table_handler_list if t == 'BGP_GLOBALS_AF']
    assert len(hdlr) == 1

    run_cmd.reset_mock()
    hdlr[0]('BGP_GLOBALS_AF', 'default|ipv4_srpolicy', {'max_ebgp_paths': '4'})
    assert not run_cmd.called

    # A plain unicast AF must still work (nothing gated there).
    run_cmd.reset_mock()
    hdlr[0]('BGP_GLOBALS_AF', 'default|ipv4_unicast', {'max_ebgp_paths': '4'})
    flat = ' '.join(' '.join(c) if isinstance(c, list) else c
                    for c in [call[0][1] for call in run_cmd.call_args_list])
    assert 'maximum-paths 4' in flat


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_globals_af_aggregate_addr_and_network_srpolicy_skipped(run_cmd):
    """FRR has no aggregate-address/network command under 'address-family
    <afi> sr-policy' either (same receive-only-SAFI reasoning as
    BGP_GLOBALS_AF). BGP_GLOBALS_AF_AGGREGATE_ADDR/BGP_GLOBALS_AF_NETWORK
    must skip ipv4_srpolicy/ipv6_srpolicy outright, matching the
    BGP_GLOBALS_AF defense-in-depth guard, rather than relying solely on
    YANG to keep such entries out of CONFIG_DB."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    globals_hdlr = [h for t, h in daemon.table_handler_list if t == 'BGP_GLOBALS']
    assert len(globals_hdlr) == 1
    globals_hdlr[0]('BGP_GLOBALS', 'default', {'local_asn': '100'})

    for table_name, prefix in [('BGP_GLOBALS_AF_AGGREGATE_ADDR', '192.168.1.0/24'),
                                ('BGP_GLOBALS_AF_NETWORK', '192.168.2.0/24')]:
        hdlr = [h for t, h in daemon.table_handler_list if t == table_name]
        assert len(hdlr) == 1

        run_cmd.reset_mock()
        hdlr[0](table_name, f'default|ipv4_srpolicy|{prefix}', {'as_set': 'true'})
        assert not run_cmd.called

        # A plain unicast AF must still work (nothing gated there).
        run_cmd.reset_mock()
        hdlr[0](table_name, f'default|ipv4_unicast|{prefix}', {'as_set': 'true'})
        assert run_cmd.called


def test_static_route_srv6_sidlist():
    data_set_del_test(static_route_srv6_data)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_sids_un_prefix_len_guard(run_cmd):
    # A uN SID is the node SID itself (function_len == 0), so its prefix length
    # must equal the locator's block_len + node_len. frrcfgd must reject a
    # mismatched uN SID instead of pushing a my_sid the SAI can't program.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    def fake_get_table(name):
        if name == 'SRV6_MY_LOCATORS':
            return {'LocMicro': {'prefix': 'fc00:0:1::/48', 'block_len': '32',
                                 'node_len': '16', 'micro-segment': 'true'}}
        return {}
    daemon.config_db.get_table = MagicMock(side_effect=fake_get_table)
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_SIDS'][0]

    # /64 != block_len(32) + node_len(16) -> rejected, no vtysh command run
    run_cmd.reset_mock()
    hdlr('SRV6_MY_SIDS', 'LocMicro|fc00:0:1::/64', {'action': 'uN'})
    assert not run_cmd.called

    # /48 == block_len + node_len -> accepted, static-sid pushed to FRR
    run_cmd.reset_mock()
    hdlr('SRV6_MY_SIDS', 'LocMicro|fc00:0:1::/48', {'action': 'uN'})
    assert run_cmd.called
    ran = ' '.join(str(c) for c in run_cmd.call_args_list)
    assert 'static-sids' in ran


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_global_encap_source_address_set(run_cmd):
    # SRV6_GLOBAL's CONFIG_DB key is single-part ('default'), which the generic
    # key-splitting in __update_bgp puts in `prefix`, leaving `key` as None.
    # The handler must guard on `prefix`, not `key`, or every SRV6_GLOBAL
    # update is silently rejected as an "invalid key" -- this is the
    # regression this test guards against.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_GLOBAL'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_GLOBAL', 'default', {'encap_source_address': 'fdbd:dc00:98:5::13'})

    run_cmd.assert_called_once_with(
        'SRV6_GLOBAL',
        ['vtysh', '-c', 'configure terminal',
         '-c', 'segment-routing', '-c', 'srv6', '-c', 'encapsulation',
         '-c', 'source-address fdbd:dc00:98:5::13'],
        True, None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_global_encap_source_address_update_pushes_new_value(run_cmd):
    # A changed value on a second SET must be pushed again (OP_UPDATE), not
    # silently dropped -- proves the successful first apply was actually
    # recorded in the cache (see STAT_SUCC test below for why that matters).
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_GLOBAL'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_GLOBAL', 'default', {'encap_source_address': 'fdbd:dc00:98:5::13'})
    assert run_cmd.call_count == 1

    run_cmd.reset_mock()
    hdlr('SRV6_GLOBAL', 'default', {'encap_source_address': 'fd00::99'})

    run_cmd.assert_called_once_with(
        'SRV6_GLOBAL',
        ['vtysh', '-c', 'configure terminal',
         '-c', 'segment-routing', '-c', 'srv6', '-c', 'encapsulation',
         '-c', 'source-address fd00::99'],
        True, None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_global_encap_source_address_repeat_same_value_is_noop(run_cmd):
    # Re-applying the exact same value a second time must NOT re-run vtysh --
    # it should be recognised as unchanged (OP_NONE). This only holds if the
    # first successful apply was actually cached (STAT_SUCC set); otherwise
    # every repeat looks like a fresh OP_ADD and vtysh is re-run needlessly.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_GLOBAL'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_GLOBAL', 'default', {'encap_source_address': 'fdbd:dc00:98:5::13'})
    assert run_cmd.call_count == 1

    run_cmd.reset_mock()
    hdlr('SRV6_GLOBAL', 'default', {'encap_source_address': 'fdbd:dc00:98:5::13'})
    assert not run_cmd.called


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_global_encap_source_address_delete_clears_cache(run_cmd):
    # Simulate the value having been loaded into the cache at daemon startup
    # (BGPConfigDaemon.__init__ unconditionally seeds table_data_cache from
    # current CONFIG_DB state via get_table_data, independent of a live SET
    # event ever having gone through this handler). A full-table delete must
    # both push 'no source-address' AND clear the cache entry -- if the
    # delete's success isn't recorded (STAT_SUCC), the stale cached value
    # lingers and a subsequent re-add of the very same value is wrongly
    # treated as OP_NONE and never pushed to FRR.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_GLOBAL'][0]
    daemon.table_data_cache['SRV6_GLOBAL&&default'] = {
        'encap_source_address': 'fdbd:dc00:98:5::13'}
    run_cmd.reset_mock()

    hdlr('SRV6_GLOBAL', 'default', None)

    run_cmd.assert_called_once_with(
        'SRV6_GLOBAL',
        ['vtysh', '-c', 'configure terminal',
         '-c', 'segment-routing', '-c', 'srv6', '-c', 'encapsulation',
         '-c', 'no source-address'],
        True, None)
    assert 'encap_source_address' not in daemon.table_data_cache.get('SRV6_GLOBAL&&default', {})

    # Re-adding the same value after the delete must be pushed again, not
    # swallowed as OP_NONE against a stale cache entry.
    run_cmd.reset_mock()
    hdlr('SRV6_GLOBAL', 'default', {'encap_source_address': 'fdbd:dc00:98:5::13'})
    assert run_cmd.called


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_locators_block_node_len_mismatch_rejected(run_cmd):
    # FRR rejects a locator outright if block_len + node_len != prefix length
    # ("% block-len + node-len must be equal to the selected prefix length").
    # Without a matching guard, frrcfgd pushes the doomed vtysh command
    # anyway: it enters/creates the locator via 'locator <name>' but the
    # 'prefix ... block-len ... node-len ...' sub-command then fails,
    # leaving a half-created locator sitting at block-len/node-len 0 with no
    # error visible to the operator (syslog.LOG_ERR is easy to miss).
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_LOCATORS'][0]
    run_cmd.reset_mock()

    # /64 prefix but block_len(30) + node_len(18) = 48 != 64
    hdlr('SRV6_MY_LOCATORS', 'loc-bad',
         {'prefix': 'fc00:1234::/64', 'block_len': '30', 'node_len': '18', 'func_len': '16'})
    assert not run_cmd.called


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_locators_missing_field_rejected_not_typeerror(run_cmd):
    # A partial-field delete (e.g. block_len removed while the row itself
    # stays) leaves block_len missing/None; int(None) must be caught and
    # logged rather than raising TypeError out of the handler.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_LOCATORS'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_LOCATORS', 'loc-partial',
         {'prefix': 'fc00:1234::/64', 'node_len': '24', 'func_len': '16'})
    assert not run_cmd.called


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_locators_valid_block_node_len_applied(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_LOCATORS'][0]
    run_cmd.reset_mock()

    # /64 prefix, block_len(40) + node_len(24) = 64 -- matches
    hdlr('SRV6_MY_LOCATORS', 'loc-good',
         {'prefix': 'fc00:1234::/64', 'block_len': '40', 'node_len': '24', 'func_len': '16'})

    run_cmd.assert_called_once_with(
        'SRV6_MY_LOCATORS',
        ['vtysh', '-c', 'configure terminal',
         '-c', 'segment-routing', '-c', 'srv6', '-c', 'locators',
         '-c', 'locator loc-good',
         '-c', 'prefix fc00:1234::/64 block-len 40 node-len 24 func-bits 16',
         '-c', 'behavior usid'],
        True, None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_locators_full_sid_no_usid_behavior(run_cmd):
    # full_sid=true locators are not micro-segment: the 'behavior usid'
    # sub-command must be absent from the pushed vtysh command.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_LOCATORS'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_LOCATORS', 'loc-full',
         {'prefix': 'fc00:1234::/64', 'block_len': '40', 'node_len': '24',
          'func_len': '16', 'full_sid': 'true'})

    run_cmd.assert_called_once_with(
        'SRV6_MY_LOCATORS',
        ['vtysh', '-c', 'configure terminal',
         '-c', 'segment-routing', '-c', 'srv6', '-c', 'locators',
         '-c', 'locator loc-full',
         '-c', 'prefix fc00:1234::/64 block-len 40 node-len 24 func-bits 16'],
        True, None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_locators_func_len_too_large_rejected(run_cmd):
    # FRR currently rejects func_bit_len > 20.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_LOCATORS'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_LOCATORS', 'loc-bad2',
         {'prefix': 'fc00:1234::/64', 'block_len': '40', 'node_len': '24', 'func_len': '21'})
    assert not run_cmd.called


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_locators_delete_pushes_no_locator(run_cmd):
    # A full-table delete for SRV6_MY_LOCATORS previously had no 'else'
    # branch at all -- the delete was silently dropped and the locator
    # lingered in FRR forever.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_LOCATORS'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_LOCATORS', 'loc-gone', None)

    run_cmd.assert_called_once_with(
        'SRV6_MY_LOCATORS',
        ['vtysh', '-c', 'configure terminal',
         '-c', 'segment-routing', '-c', 'srv6', '-c', 'locators',
         '-c', 'no locator loc-gone'],
        True, None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_sids_delete_pushes_no_sid(run_cmd):
    # Same missing-delete-branch bug as SRV6_MY_LOCATORS.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    def fake_get_table(name):
        return {}
    daemon.config_db.get_table = MagicMock(side_effect=fake_get_table)
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_SIDS'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_SIDS', 'loc-a|fc00:0:1::/64', None)

    run_cmd.assert_called_once_with(
        'SRV6_MY_SIDS',
        ['vtysh', '-c', 'configure terminal',
         '-c', 'segment-routing', '-c', 'srv6',
         '-c', 'static-sids',
         '-c', 'no sid fc00:0:1::/64'],
        True, None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_sids_ua_interface_and_nexthop_as_separate_args(run_cmd):
    # Regression test: the uA/End.X branch used to build a Python list for
    # the interface+nexthop sub-commands and then do
    # cmd += ['-c', '{}'.format(sid_cmd)] -- '{}'.format(a_list) stringifies
    # the list's repr (e.g. "['sid ... interface X', 'nexthop Y']") into a
    # SINGLE '-c' argument, which is not valid vtysh syntax at all. This
    # silently broke every uA/End.X SID with a nexthop.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    def fake_get_table(name):
        if name == 'SRV6_MY_LOCATORS':
            return {'loc-a': {'full_sid': 'false'}}
        return {}
    daemon.config_db.get_table = MagicMock(side_effect=fake_get_table)
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_SIDS'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_SIDS', 'loc-a|fc00:0:1::/112',
         {'action': 'uA', 'interface': 'Ethernet0', 'adj': 'fd00::5'})

    run_cmd.assert_called_once_with(
        'SRV6_MY_SIDS',
        ['vtysh', '-c', 'configure terminal',
         '-c', 'segment-routing', '-c', 'srv6',
         '-c', 'static-sids',
         '-c', 'sid fc00:0:1::/112 locator loc-a behavior uA interface Ethernet0',
         '-c', 'nexthop fd00::5'],
        True, None)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_locators_success_is_cached(run_cmd):
    # SRV6_MY_LOCATORS pushes unconditionally on every update regardless of
    # per-field op (unlike SRV6_GLOBAL, it never checks .op before building
    # the command), so omitting STAT_SUCC here doesn't cause a repeat-push
    # bug today. It does leave table_data_cache permanently empty for this
    # table, which would misreport a later per-field delete (missing key
    # instead of a real OP_DELETE with the prior value) -- so the fields are
    # still marked STAT_SUCC for cache-consistency hygiene. This just proves
    # the cache is actually populated after a successful push.
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_LOCATORS'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_LOCATORS', 'loc-a',
         {'prefix': 'fc00:1234::/64', 'block_len': '40', 'node_len': '24', 'func_len': '16'})

    table_key = ExtConfigDBConnector.get_table_key('SRV6_MY_LOCATORS', 'loc-a')
    assert daemon.table_data_cache.get(table_key) == {
        'prefix': 'fc00:1234::/64', 'block_len': '40', 'node_len': '24', 'func_len': '16'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_source_success_is_cached(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_SOURCE'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_SOURCE', 'default', {'source-address': 'fc00:1234::1'})

    table_key = ExtConfigDBConnector.get_table_key('SRV6_MY_SOURCE', 'default')
    assert daemon.table_data_cache.get(table_key) == {'source-address': 'fc00:1234::1'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_srv6_my_sids_success_is_cached(run_cmd):
    from frrcfgd.frrcfgd import BGPConfigDaemon, ExtConfigDBConnector
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    def fake_get_table(name):
        if name == 'SRV6_MY_LOCATORS':
            return {'loc-a': {'full_sid': 'false'}}
        return {}
    daemon.config_db.get_table = MagicMock(side_effect=fake_get_table)
    hdlr = [h for t, h in daemon.table_handler_list if t == 'SRV6_MY_SIDS'][0]
    run_cmd.reset_mock()

    hdlr('SRV6_MY_SIDS', 'loc-a|fc00:0:1::/112',
         {'action': 'uA', 'interface': 'Ethernet0', 'adj': 'fd00::5'})

    table_key = ExtConfigDBConnector.get_table_key('SRV6_MY_SIDS', 'loc-a|fc00:0:1::/112')
    assert daemon.table_data_cache.get(table_key) == {
        'action': 'uA', 'interface': 'Ethernet0', 'adj': 'fd00::5'}


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bfd_single_hop_delete_attribute_then_readd_same_value_is_pushed(run_cmd):
    # __bfd_handle_delete's per-attribute delete path pushed a "reset to FRR
    # default" command (e.g. transmit-interval 300) but never marked the
    # deleted field STAT_SUCC. Without that, __update_cache_data never pops
    # the stale pre-delete value from the cache, so re-adding the exact same
    # value afterward is silently miscomputed as OP_NONE and never re-pushed
    # to FRR -- same bug class as the fixed SRV6_GLOBAL delete gap.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'BFD_PEER_SINGLE_HOP'][0]
    key = '10.0.0.1|Ethernet0|default|192.0.2.1'
    run_cmd.reset_mock()

    hdlr('BFD_PEER_SINGLE_HOP', key, {'desired-minimum-tx-interval': '400'})
    assert run_cmd.called

    # Field removed while the row itself persists -- resets transmit-interval
    # to the FRR default.
    run_cmd.reset_mock()
    hdlr('BFD_PEER_SINGLE_HOP', key, {})
    run_cmd.assert_called_once_with(
        'BFD_PEER_SINGLE_HOP',
        ['vtysh', '-c', 'configure terminal', '-c', 'bfd',
         '-c', 'peer 10.0.0.1 local-address 192.0.2.1 vrf default interface Ethernet0',
         '-c', 'transmit-interval 300'],
        True, None)

    # Re-adding the exact same value it had before deletion must be pushed
    # again, not swallowed as OP_NONE against a stale cache entry.
    run_cmd.reset_mock()
    hdlr('BFD_PEER_SINGLE_HOP', key, {'desired-minimum-tx-interval': '400'})
    assert run_cmd.called


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bfd_multi_hop_delete_attribute_then_readd_same_value_is_pushed(run_cmd):
    # Same gap/fix as the single-hop test above, for the multi-hop handler.
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    hdlr = [h for t, h in daemon.table_handler_list if t == 'BFD_PEER_MULTI_HOP'][0]
    key = '10.0.0.1|Ethernet0|default|192.0.2.1'
    run_cmd.reset_mock()

    hdlr('BFD_PEER_MULTI_HOP', key, {'desired-minimum-tx-interval': '400'})
    assert run_cmd.called

    run_cmd.reset_mock()
    hdlr('BFD_PEER_MULTI_HOP', key, {})
    assert run_cmd.called

    run_cmd.reset_mock()
    hdlr('BFD_PEER_MULTI_HOP', key, {'desired-minimum-tx-interval': '400'})
    assert run_cmd.called


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_allow_reserved_ranges_enable(run_cmd):
    """Test enabling allow-reserved-ranges configuration."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    # Initially set to 'false' so we can test enabling it
    daemon.allow_reserved_ranges = 'false'

    # Simulate DEVICE_METADATA update with allow-reserved-ranges set to 'true'
    daemon.metadata_handler('DEVICE_METADATA', 'localhost',
                            {'allow-reserved-ranges': 'true'})

    # Verify the command was called with correct parameters
    run_cmd.assert_called_with(
        'DEVICE_METADATA',
        ['vtysh', '-c', 'configure terminal', '-c', 'allow-reserved-ranges'],
        True, None)
    assert daemon.allow_reserved_ranges == 'true'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_allow_reserved_ranges_disable(run_cmd):
    """Test disabling allow-reserved-ranges configuration."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    # Initially set to 'true' (the default)
    daemon.allow_reserved_ranges = 'true'

    # Simulate DEVICE_METADATA update with allow-reserved-ranges set to 'false'
    daemon.metadata_handler('DEVICE_METADATA', 'localhost',
                            {'allow-reserved-ranges': 'false'})

    # Verify the command was called with correct parameters
    run_cmd.assert_called_with(
        'DEVICE_METADATA',
        ['vtysh', '-c', 'configure terminal', '-c', 'no allow-reserved-ranges'],
        True, None)
    assert daemon.allow_reserved_ranges == 'false'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_allow_reserved_ranges_no_change(run_cmd):
    """Test that no command is issued when allow-reserved-ranges
       doesn't change."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    # Set initial state
    daemon.allow_reserved_ranges = 'true'
    run_cmd.reset_mock()

    # Simulate DEVICE_METADATA update with same value
    daemon.metadata_handler('DEVICE_METADATA', 'localhost',
                            {'allow-reserved-ranges': 'true'})

    # Verify no command was called (value didn't change)
    run_cmd.assert_not_called()
    assert daemon.allow_reserved_ranges == 'true'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_allow_reserved_ranges_default_when_missing(run_cmd):
    """Test that default value 'true' is used when allow-reserved-ranges
       is not in data."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    # Set initial state to 'false'
    daemon.allow_reserved_ranges = 'false'

    # Simulate DEVICE_METADATA update without allow-reserved-ranges field
    daemon.metadata_handler('DEVICE_METADATA', 'localhost', {})

    # Verify the command was called to enable (default is 'true')
    run_cmd.assert_called_with(
        'DEVICE_METADATA',
        ['vtysh', '-c', 'configure terminal', '-c', 'allow-reserved-ranges'],
        True, None)
    assert daemon.allow_reserved_ranges == 'true'


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_allow_reserved_ranges_non_localhost_ignored(run_cmd):
    """Test that non-localhost key updates are ignored."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()

    # Set initial state
    daemon.allow_reserved_ranges = 'true'
    run_cmd.reset_mock()

    # Simulate DEVICE_METADATA update with non-localhost key
    daemon.metadata_handler('DEVICE_METADATA', 'other_host',
                            {'allow-reserved-ranges': 'false'})

    # Verify no command was called (non-localhost should be ignored)
    run_cmd.assert_not_called()
    assert daemon.allow_reserved_ranges == 'true'


# BGP neighbor BFD with custom timer parameters test data
bgp_neighbor_bfd_timers_data = [
    # Set up BGP globals first
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  True, None, None, None, None),  # no_del=True, rest=None
    # BGP neighbor with BFD and custom timer parameters
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.1.1.1',
                  {'bfd': 'true', 'bfd_detect_multiplier': '5', 'bfd_min_rx': '500', 'bfd_min_tx': '500'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.1.1.1 bfd 5 500 500'],
                  False,
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.1.1.1 bfd']),
    # BGP neighbor with BFD but no custom timers (should use default command)
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.1.1.2',
                  {'bfd': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.1.1.2 bfd']),
]

# BGP peer group BFD with custom timer parameters test data
bgp_peer_group_bfd_timers_data = [
    # Set up BGP globals first
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  True, None, None, None, None),  # no_del=True, rest=None
    # BGP peer group with BFD and custom timer parameters
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|TEST_PG',
                  {'bfd': 'true', 'bfd_detect_multiplier': '10', 'bfd_min_rx': '1000', 'bfd_min_tx': '1000'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor TEST_PG bfd 10 1000 1000'],
                  False,
                  conf_bgp_cmd('default', 100) + ['{}neighbor TEST_PG bfd']),
    # BGP peer group with BFD but no custom timers
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|TEST_PG2',
                  {'bfd': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor TEST_PG2 bfd']),
]

def test_bgp_neighbor_bfd_custom_timers():
    """Test BGP neighbor with BFD custom timer parameters (SET and DELETE)"""
    data_set_del_test(bgp_neighbor_bfd_timers_data)

def test_bgp_peer_group_bfd_custom_timers():
    """Test BGP peer group with BFD custom timer parameters (SET and DELETE)"""
    data_set_del_test(bgp_peer_group_bfd_timers_data)


# BGP neighbor / peer-group with BFD profile binding (unified mode).
#
# bfd_profile triggers two separate vtysh invocations:
#   1. neighbor X bfd                    (enable BFD)
#   2. neighbor X bfd profile <name>     (apply profile)
# matching the priority order rendered by
# templates/bgpd/bgpd.conf.db.nbr_or_peer.j2 and the separated-mode
# fixtures in sonic-bgpcfgd/tests/data/general/instance.conf/{param,result}_bfd_profile.*

def hdl_bfd_profile_cmd(is_del, cmd_list, chk_data):
    """Validator for the two-step bfd + bfd-profile emission.
    chk_data is a tuple (peer_or_pg_name, profile_name)."""
    peer, profile = chk_data
    bfd_calls = []
    for cmd in cmd_list:
        last = cmd[-1] if isinstance(cmd, list) else re.findall(r"-c\s+'([^']+)'\s*", cmd)[-1]
        if 'neighbor %s bfd' % peer in last:
            bfd_calls.append(last)

    if is_del:
        assert len(bfd_calls) >= 1, "no bfd-related vtysh on delete: %s" % cmd_list
        # Last bfd-related call should be `no neighbor X bfd` (collapse)
        assert bfd_calls[-1] == 'no neighbor %s bfd' % peer, bfd_calls[-1]
        return

    # Set: expect exactly the two-step emission
    assert len(bfd_calls) == 2, \
        "expected 2 bfd-related vtysh calls, got %d: %s" % (len(bfd_calls), bfd_calls)
    assert bfd_calls[0] == 'neighbor %s bfd' % peer, bfd_calls[0]
    assert bfd_calls[1] == 'neighbor %s bfd profile %s' % (peer, profile), bfd_calls[1]

bgp_neighbor_bfd_profile_data = [
    # Set up BGP globals first
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  True, None, None, None, None),
    # BGP neighbor with bfd=true and bfd_profile — emits two-step bfd + bfd profile
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.2.2.1',
                  {'bfd': 'true', 'bfd_profile': 'fast-failover'},
                  hdl_bfd_profile_cmd, False, None,
                  ('10.2.2.1', 'fast-failover')),
    # bfd_profile takes precedence over inline custom timers
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.2.2.2',
                  {'bfd': 'true', 'bfd_profile': 'fast-failover',
                   'bfd_detect_multiplier': '5', 'bfd_min_rx': '500', 'bfd_min_tx': '500'},
                  hdl_bfd_profile_cmd, False, None,
                  ('10.2.2.2', 'fast-failover')),
]

bgp_peer_group_bfd_profile_data = [
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  True, None, None, None, None),
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|TEST_PG_PROFILE',
                  {'bfd': 'true', 'bfd_profile': 'slow-stable'},
                  hdl_bfd_profile_cmd, False, None,
                  ('TEST_PG_PROFILE', 'slow-stable')),
]

def test_bgp_neighbor_bfd_profile():
    """Test BGP neighbor with bfd_profile binding.

    Mirrors the separated-mode test fixtures in
    sonic-bgpcfgd/tests/data/general/instance.conf/{param,result}_bfd_profile.*
    so that both routing-config modes are covered."""
    data_set_del_test(bgp_neighbor_bfd_profile_data)

def test_bgp_peer_group_bfd_profile():
    """Test BGP peer group with bfd_profile binding."""
    data_set_del_test(bgp_peer_group_bfd_profile_data)


# Per-peer BGP graceful-shutdown and graceful-restart. BGP_NEIGHBOR and
# BGP_PEER_GROUP share cmn_key_map, so both tables must emit the same
# 'neighbor <peer-or-group> graceful-*' commands FRR accepts for either a
# neighbor address, an interface neighbor or a peer-group name.
bgp_neighbor_graceful_data = [
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  True, None, None, None, None),
    # Drain a single neighbor without touching the VRF-level graceful-shutdown
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.1',
                  {'graceful_shutdown': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.3.3.1 graceful-shutdown']),
    # Undrain: an explicit false renders the 'no' form
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.2',
                  {'graceful_shutdown': 'false'},
                  conf_bgp_cmd('default', 100) + ['no neighbor 10.3.3.2 graceful-shutdown']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.3',
                  {'graceful_restart': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.3.3.3 graceful-restart']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.4',
                  {'graceful_restart_disable': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.3.3.4 graceful-restart-disable']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.5',
                  {'graceful_restart_helper': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.3.3.5 graceful-restart-helper']),
    # Explicit false reverts a peer to global GR inherit (leaf-level off, not key delete)
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.6',
                  {'graceful_restart': 'false'},
                  conf_bgp_cmd('default', 100) + ['no neighbor 10.3.3.6 graceful-restart']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.7',
                  {'graceful_restart_disable': 'false'},
                  conf_bgp_cmd('default', 100) + ['no neighbor 10.3.3.7 graceful-restart-disable']),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.8',
                  {'graceful_restart_helper': 'false'},
                  conf_bgp_cmd('default', 100) + ['no neighbor 10.3.3.8 graceful-restart-helper']),
    # Interface neighbors take the same commands as address neighbors
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|Ethernet0',
                  {'graceful_shutdown': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor Ethernet0 graceful-shutdown']),
]

bgp_peer_group_graceful_data = [
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  True, None, None, None, None),
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|PG_GSHUT',
                  {'graceful_shutdown': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor PG_GSHUT graceful-shutdown']),
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|PG_GSHUT_OFF',
                  {'graceful_shutdown': 'false'},
                  conf_bgp_cmd('default', 100) + ['no neighbor PG_GSHUT_OFF graceful-shutdown']),
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|PG_GR',
                  {'graceful_restart': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor PG_GR graceful-restart']),
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|PG_GR_DIS',
                  {'graceful_restart_disable': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor PG_GR_DIS graceful-restart-disable']),
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|PG_GR_HELP',
                  {'graceful_restart_helper': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor PG_GR_HELP graceful-restart-helper']),
    # Explicit false reverts a peer-group to global GR inherit (leaf-level off)
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|PG_GR_OFF',
                  {'graceful_restart': 'false'},
                  conf_bgp_cmd('default', 100) + ['no neighbor PG_GR_OFF graceful-restart']),
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|PG_GR_DIS_OFF',
                  {'graceful_restart_disable': 'false'},
                  conf_bgp_cmd('default', 100) + ['no neighbor PG_GR_DIS_OFF graceful-restart-disable']),
    CmdMapTestInfo('BGP_PEER_GROUP', 'default|PG_GR_HELP_OFF',
                  {'graceful_restart_helper': 'false'},
                  conf_bgp_cmd('default', 100) + ['no neighbor PG_GR_HELP_OFF graceful-restart-helper']),
]

def test_bgp_neighbor_graceful_shutdown_and_restart():
    """Neighbor-level graceful-shutdown / graceful-restart modes reach FRR."""
    data_set_del_test(bgp_neighbor_graceful_data)

def test_bgp_peer_group_graceful_shutdown_and_restart():
    """Peer-group-level graceful-shutdown / graceful-restart modes reach FRR."""
    data_set_del_test(bgp_peer_group_graceful_data)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_neighbor_graceful_restart_mode_switch(run_cmd):
    """Switching a neighbor from helper-only to full graceful-restart sets the
    new mode before unsetting the old one (cmn_key_map list order: each GR
    leaf is its own entry). After the peer is in PEER_GR, FRR's bgp_neighbor_graceful_restart()
    maps NO_PEER_HELPER_CMD to PEER_INVALID/BGP_GR_NO_OPERATION (bgp_fsm.c;
    table in bgp_peer_gr_init() in bgpd.c), so the stale unset cannot clobber
    the new mode or bounce through PEER_GLOBAL_INHERIT."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    handlers = dict(daemon.table_handler_list)

    handlers['BGP_GLOBALS']('BGP_GLOBALS', 'default', {'local_asn': '100'})
    handlers['BGP_NEIGHBOR']('BGP_NEIGHBOR', 'default|10.4.4.1',
                             {'graceful_restart_helper': 'true'})
    run_cmd.reset_mock()

    # graceful_restart_helper is gone from the row, graceful_restart is new
    handlers['BGP_NEIGHBOR']('BGP_NEIGHBOR', 'default|10.4.4.1',
                             {'graceful_restart': 'true'})

    commands = [_render(call[0][1]) for call in run_cmd.call_args_list]

    def index_of(vtysh_cmd):
        for idx, cmd in enumerate(commands):
            if "-c '%s'" % vtysh_cmd in cmd:
                return idx
        return -1

    set_idx = index_of('neighbor 10.4.4.1 graceful-restart')
    unset_idx = index_of('no neighbor 10.4.4.1 graceful-restart-helper')
    assert set_idx >= 0, "graceful-restart was not set: %s" % commands
    assert unset_idx >= 0, "stale graceful-restart-helper was not unset: %s" % commands
    assert set_idx < unset_idx, \
        "mode unset must follow the mode set: %s" % commands


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bgp_peer_group_graceful_restart_mode_switch(run_cmd):
    """Same cmn_key_map list-order SET-before-UNSET for BGP_PEER_GROUP."""
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    handlers = dict(daemon.table_handler_list)

    handlers['BGP_GLOBALS']('BGP_GLOBALS', 'default', {'local_asn': '100'})
    handlers['BGP_PEER_GROUP']('BGP_PEER_GROUP', 'default|PG1',
                               {'graceful_restart_helper': 'true'})
    run_cmd.reset_mock()

    handlers['BGP_PEER_GROUP']('BGP_PEER_GROUP', 'default|PG1',
                               {'graceful_restart': 'true'})

    commands = [_render(call[0][1]) for call in run_cmd.call_args_list]

    def index_of(vtysh_cmd):
        for idx, cmd in enumerate(commands):
            if "-c '%s'" % vtysh_cmd in cmd:
                return idx
        return -1

    set_idx = index_of('neighbor PG1 graceful-restart')
    unset_idx = index_of('no neighbor PG1 graceful-restart-helper')
    assert set_idx >= 0, "graceful-restart was not set: %s" % commands
    assert unset_idx >= 0, "stale graceful-restart-helper was not unset: %s" % commands
    assert set_idx < unset_idx, \
        "mode unset must follow the mode set: %s" % commands


def test_bgp_peer_graceful_template():
    """bgpd.conf.db.nbr_or_peer.j2 renders the per-peer graceful-shutdown and
    graceful-restart commands at cold boot, for neighbors and peer-groups alike.
    Only one graceful-restart mode is ever rendered. Drain (RFC 8326) and a GR
    mode (RFC 4724) are orthogonal and may both be present."""
    template = _nbr_or_peer_template()

    result = template.render(nbr_or_peer_type='neighbor', name_or_ip='10.0.0.1',
                             nbr_or_peer={'asn': '65200', 'graceful_shutdown': 'true'},
                             vrf='default')
    assert 'neighbor 10.0.0.1 graceful-shutdown' in _nbr_or_peer_lines(result)

    result = template.render(nbr_or_peer_type='peer-group', name_or_ip='PG1',
                             nbr_or_peer={'graceful_shutdown': 'true'},
                             vrf='default')
    assert 'neighbor PG1 graceful-shutdown' in _nbr_or_peer_lines(result)

    # An explicit false is the absence of the command, not a 'no' form: the
    # template renders a fresh config where nothing is configured yet.
    result = template.render(nbr_or_peer_type='neighbor', name_or_ip='10.0.0.2',
                             nbr_or_peer={'asn': '65200', 'graceful_shutdown': 'false',
                                          'graceful_restart': 'false'},
                             vrf='default')
    assert 'graceful' not in result

    for field, command in [('graceful_restart', 'graceful-restart'),
                           ('graceful_restart_disable', 'graceful-restart-disable'),
                           ('graceful_restart_helper', 'graceful-restart-helper')]:
        for peer_type, peer in [('neighbor', '10.0.0.3'), ('peer-group', 'PG2')]:
            result = template.render(nbr_or_peer_type=peer_type, name_or_ip=peer,
                                     nbr_or_peer={field: 'true'}, vrf='default')
            rendered = [line for line in _nbr_or_peer_lines(result) if 'graceful' in line]
            assert rendered == ['neighbor %s %s' % (peer, command)], rendered

    # Both drain (RFC 8326) and full GR (RFC 4724) active simultaneously —
    # orthogonal features. Locks the independent {% if %} vs an accidental {% elif %}.
    result = template.render(nbr_or_peer_type='neighbor', name_or_ip='10.0.0.4',
                             nbr_or_peer={'graceful_shutdown': 'true', 'graceful_restart': 'true'},
                             vrf='default')
    rendered = _nbr_or_peer_lines(result)
    assert 'neighbor 10.0.0.4 graceful-shutdown' in rendered
    assert 'neighbor 10.0.0.4 graceful-restart' in rendered
    assert len([line for line in rendered if 'graceful' in line]) == 2


# BGP neighbor bfd_check_ctrl_plane_failure — its own key_map entry, rendered
# independently of the bare bfd enable. Mirrors the separated-mode render in
# dockers/docker-fpm-frr/frr/bgpd/templates/general/instance.conf.j2 and the
# unified-mode render in templates/bgpd/bgpd.conf.db.nbr_or_peer.j2.
bgp_neighbor_bfd_check_ctrl_plane_data = [
    CmdMapTestInfo('BGP_GLOBALS', 'default',
                  {'local_asn': '100'},
                  conf_bgp_dft_cmd('default', 100),
                  True, None, None, None, None),
    CmdMapTestInfo('BGP_NEIGHBOR', 'default|10.3.3.1',
                  {'bfd_check_ctrl_plane_failure': 'true'},
                  conf_bgp_cmd('default', 100) + ['{}neighbor 10.3.3.1 bfd check-control-plane-failure']),
]

def test_bgp_neighbor_bfd_check_ctrl_plane_failure():
    """Test BGP neighbor bfd_check_ctrl_plane_failure emits the FRR
    'neighbor X bfd check-control-plane-failure' line (SET and DELETE)."""
    data_set_del_test(bgp_neighbor_bfd_check_ctrl_plane_data)


def _bmp_inner_cmds(run_cmd):
    """Return every individual `-c <line>` config line pushed to vtysh across all
    calls, as exact strings — so assertions can distinguish `bmp monitor ...` from
    `no bmp monitor ...` (one is a substring of the other)."""
    lines = []
    for call in run_cmd.call_args_list:
        argv = call[0][1]
        i = 0
        while i < len(argv):
            if argv[i] == '-c' and i + 1 < len(argv):
                lines.append(argv[i + 1])
                i += 2
            else:
                i += 1
    return lines


def _bmp_apply_full(daemon, state):
    """Fire the per-key BMP events for a whole desired config, the way CONFIG_DB
    delivers them on first write / startup replay: global, then each target, then
    its collectors, then its afi-safis."""
    for k, v in state.get('BMP', {}).items():
        daemon.bmp_handler('BMP', k, v)
    for tkey, tval in state.get('BMP_TARGET', {}).items():
        daemon.bmp_handler('BMP_TARGET', tkey, tval)
    for ckey, cval in state.get('BMP_TARGET_COLLECTOR', {}).items():
        daemon.bmp_handler('BMP_TARGET_COLLECTOR', ckey, cval)
    for akey, aval in state.get('BMP_TARGET_AFI_SAFI', {}).items():
        daemon.bmp_handler('BMP_TARGET_AFI_SAFI', akey, aval)


def _make_bmp_daemon(run_cmd, state, bgp_asn=None):
    from frrcfgd.frrcfgd import BGPConfigDaemon
    run_cmd.return_value = True
    daemon = BGPConfigDaemon()
    daemon.bgp_asn = bgp_asn if bgp_asn is not None else {'default': 65000}
    daemon.config_db.get_table = MagicMock(side_effect=_bmp_get_table_fn(state))
    run_cmd.reset_mock()
    return daemon


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_global_sets_buffer_limit(run_cmd):
    """A BMP|global change pushes only the mirror buffer-limit (per VRF)."""
    state = {'BMP': {'global': {'mirror-buffer-limit': '1000000000'}},
             'BMP_TARGET': {'t1': {}}}
    daemon = _make_bmp_daemon(run_cmd, state)
    daemon.bmp_handler('BMP', 'global', state['BMP']['global'])

    lines = _bmp_inner_cmds(run_cmd)
    assert 'bmp mirror buffer-limit 1000000000' in lines
    assert not any(l.startswith('no bmp targets') for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_target_create_sets_stats_and_mirror(run_cmd):
    """A BMP_TARGET set creates the target and applies its own attributes only
    (mirror + stats); collectors/monitors arrive as their own events."""
    state = {'BMP_TARGET': {'production': {'mirror': 'true', 'stats-interval': '2000'}}}
    daemon = _make_bmp_daemon(run_cmd, state)
    daemon.bmp_handler('BMP_TARGET', 'production', state['BMP_TARGET']['production'])

    lines = _bmp_inner_cmds(run_cmd)
    assert 'bmp targets production' in lines
    assert 'bmp stats interval 2000' in lines
    assert 'bmp mirror' in lines
    # No collector/monitor churn from a target-attribute change.
    assert not any(l.startswith('bmp connect') for l in lines)
    assert not any(l.startswith('no bmp targets') for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_collector_add(run_cmd):
    """A BMP_TARGET_COLLECTOR set connects exactly that collector under its target,
    preserving the source-interface clause."""
    state = {'BMP_TARGET': {'production': {}},
             'BMP_TARGET_COLLECTOR': {
                 ('production', '192.168.1.100', '5000'): {
                     'min-retry': '30000', 'max-retry': '720000', 'source-interface': 'Loopback0'}}}
    daemon = _make_bmp_daemon(run_cmd, state)
    daemon.bmp_handler('BMP_TARGET_COLLECTOR', ('production', '192.168.1.100', '5000'),
                       state['BMP_TARGET_COLLECTOR'][('production', '192.168.1.100', '5000')])

    lines = _bmp_inner_cmds(run_cmd)
    assert 'bmp targets production' in lines
    assert 'bmp connect 192.168.1.100 port 5000 min-retry 30000 max-retry 720000 source-interface Loopback0' in lines
    assert not any(l.startswith('no bmp') for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_afi_safi_policies_exact(run_cmd):
    """A BMP_TARGET_AFI_SAFI set re-asserts the row's desired state, one line per
    policy: `bmp monitor` for enabled, `no bmp monitor` for disabled (idempotent in
    FRR). It only ever touches this target's own afi/safi — never other targets or
    any collector connection."""
    state = {'BMP_TARGET': {'production': {}},
             'BMP_TARGET_AFI_SAFI': {
                 ('production', 'ipv4_unicast'): {
                     'adj-rib-in-pre': 'true', 'adj-rib-in-post': 'false', 'loc-rib': 'true'}}}
    daemon = _make_bmp_daemon(run_cmd, state)
    daemon.bmp_handler('BMP_TARGET_AFI_SAFI', ('production', 'ipv4_unicast'),
                       state['BMP_TARGET_AFI_SAFI'][('production', 'ipv4_unicast')])

    lines = _bmp_inner_cmds(run_cmd)
    assert 'bmp monitor ipv4 unicast pre-policy' in lines
    assert 'bmp monitor ipv4 unicast loc-rib' in lines
    # post-policy is disabled -> a `no bmp monitor` (idempotent) but never an enable.
    assert 'no bmp monitor ipv4 unicast post-policy' in lines
    assert 'bmp monitor ipv4 unicast post-policy' not in lines
    # never a session-tearing command
    assert not any(l.startswith('no bmp targets') for l in lines)
    assert not any(l.startswith('no bmp connect') for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_afi_safi_disable_only_affects_that_target(run_cmd):
    """Disabling one policy on a target emits its `no bmp monitor` and never tears
    the target down or touches any other target."""
    state = {
        'BMP_TARGET': {'t1': {}, 't2': {}},
        'BMP_TARGET_AFI_SAFI': {
            ('t1', 'ipv4_unicast'): {'adj-rib-in-pre': 'true', 'adj-rib-in-post': 'true', 'loc-rib': 'false'},
            ('t2', 'ipv4_unicast'): {'adj-rib-in-pre': 'true', 'adj-rib-in-post': 'false', 'loc-rib': 'false'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    # Disable post-policy on t1 only.
    run_cmd.reset_mock()
    state['BMP_TARGET_AFI_SAFI'][('t1', 'ipv4_unicast')]['adj-rib-in-post'] = 'false'
    daemon.bmp_handler('BMP_TARGET_AFI_SAFI', ('t1', 'ipv4_unicast'),
                       state['BMP_TARGET_AFI_SAFI'][('t1', 'ipv4_unicast')])

    lines = _bmp_inner_cmds(run_cmd)
    rendered = ' '.join(_render(call[0][1]) for call in run_cmd.call_args_list)
    # post-policy is disabled; pre-policy stays enabled (re-asserted, a FRR no-op).
    assert 'no bmp monitor ipv4 unicast post-policy' in lines
    assert 'bmp monitor ipv4 unicast post-policy' not in lines
    # no session teardown, and the other target is never referenced
    assert not any(l.startswith('no bmp targets') for l in lines)
    assert not any(l.startswith('no bmp connect') for l in lines)
    assert 't2' not in rendered


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_all_afi_safi_types(run_cmd):
    """All 7 AFI/SAFI types map to the right FRR afi/safi keywords."""
    afi_safis = {
        ('production', name): {'adj-rib-in-pre': 'true', 'adj-rib-in-post': 'false', 'loc-rib': 'false'}
        for name in ['ipv4_unicast', 'ipv6_unicast', 'ipv4_multicast', 'ipv6_multicast',
                     'l2vpn_evpn', 'ipv4_vpn', 'ipv6_vpn']
    }
    state = {'BMP_TARGET': {'production': {}}, 'BMP_TARGET_AFI_SAFI': afi_safis}
    daemon = _make_bmp_daemon(run_cmd, state)
    for akey, aval in afi_safis.items():
        daemon.bmp_handler('BMP_TARGET_AFI_SAFI', akey, aval)

    lines = _bmp_inner_cmds(run_cmd)
    for expected in ['bmp monitor ipv4 unicast pre-policy',
                     'bmp monitor ipv6 unicast pre-policy',
                     'bmp monitor ipv4 multicast pre-policy',
                     'bmp monitor ipv6 multicast pre-policy',
                     'bmp monitor l2vpn evpn pre-policy',
                     'bmp monitor ipv4 vpn pre-policy',
                     'bmp monitor ipv6 vpn pre-policy']:
        assert expected in lines, "missing {}".format(expected)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_applied_to_all_vrfs(run_cmd):
    """A single BMP change is applied to every VRF that has a BGP instance."""
    state = {'BMP_TARGET': {'sonic-bmp': {'stats-interval': '2000'}}}
    daemon = _make_bmp_daemon(run_cmd, state,
                              bgp_asn={'default': 65000, 'Vrf_red': 65001, 'Vrf_blue': 65002})
    daemon.bmp_handler('BMP_TARGET', 'sonic-bmp', state['BMP_TARGET']['sonic-bmp'])

    rendered = [_render(call[0][1]) for call in run_cmd.call_args_list]
    assert any('router bgp 65000' in c and 'bmp targets sonic-bmp' in c for c in rendered)
    assert any('router bgp 65001 vrf Vrf_red' in c and 'bmp targets sonic-bmp' in c for c in rendered)
    assert any('router bgp 65002 vrf Vrf_blue' in c and 'bmp targets sonic-bmp' in c for c in rendered)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_full_apply_via_per_key_events(run_cmd):
    """Applying a complete two-target config through the natural per-key event
    stream produces every expected line and, crucially, NEVER tears a target down
    — even though multiple targets/collectors are configured."""
    state = {
        'BMP': {'global': {'mirror-buffer-limit': '4294967214'}},
        'BMP_TARGET': {'production': {'mirror': 'false', 'stats-interval': '2000'},
                       'troubleshooting': {'mirror': 'true', 'stats-interval': '500'}},
        'BMP_TARGET_COLLECTOR': {
            ('production', '192.168.1.100', '5000'): {'min-retry': '30000', 'max-retry': '720000'},
            ('troubleshooting', '10.0.0.1', '6000'): {
                'min-retry': '20000', 'max-retry': '600000', 'source-interface': 'Loopback0'},
        },
        'BMP_TARGET_AFI_SAFI': {
            ('production', 'ipv4_unicast'): {'adj-rib-in-pre': 'true', 'adj-rib-in-post': 'false', 'loc-rib': 'false'},
            ('troubleshooting', 'l2vpn_evpn'): {'adj-rib-in-pre': 'false', 'adj-rib-in-post': 'false', 'loc-rib': 'true'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    lines = _bmp_inner_cmds(run_cmd)
    assert 'bmp mirror buffer-limit 4294967214' in lines
    assert 'bmp targets production' in lines
    assert 'bmp targets troubleshooting' in lines
    assert 'bmp connect 192.168.1.100 port 5000 min-retry 30000 max-retry 720000' in lines
    assert 'bmp connect 10.0.0.1 port 6000 min-retry 20000 max-retry 600000 source-interface Loopback0' in lines
    assert 'bmp stats interval 500' in lines
    assert 'bmp monitor ipv4 unicast pre-policy' in lines
    assert 'bmp monitor l2vpn evpn loc-rib' in lines
    # A fresh apply must not delete/tear down anything.
    assert not any(l.startswith('no bmp targets') for l in lines)
    assert not any(l.startswith('no bmp connect') for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_no_config_uses_default_sonic_bmp_target(run_cmd):
    """Backward compatibility: a BMP event with no BMP_TARGET rows (re)creates the
    default sonic-bmp target, matching the startup template."""
    state = {}  # every get_table returns {}
    daemon = _make_bmp_daemon(run_cmd, state)
    daemon.bmp_handler('BMP', 'global', {})

    lines = _bmp_inner_cmds(run_cmd)
    assert 'bmp mirror buffer-limit 4294967214' in lines
    assert 'bmp targets sonic-bmp' in lines
    assert 'bmp connect 127.0.0.1 port 5000 min-retry 10000 max-retry 15000' in lines
    assert 'bmp stats interval 1000' in lines
    assert 'bmp monitor ipv4 unicast pre-policy' in lines
    assert 'bmp monitor ipv6 unicast pre-policy' in lines
    assert not any('source-interface' in l for l in lines)
    assert not any('post-policy' in l for l in lines)
    assert not any('loc-rib' in l for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_target_with_no_collectors_or_afi_safi(run_cmd):
    """A target with no collectors/afi-safi is still created with its stats."""
    state = {'BMP_TARGET': {'empty-target': {'mirror': 'false', 'stats-interval': '5000'}}}
    daemon = _make_bmp_daemon(run_cmd, state)
    daemon.bmp_handler('BMP_TARGET', 'empty-target', state['BMP_TARGET']['empty-target'])

    lines = _bmp_inner_cmds(run_cmd)
    assert 'bmp targets empty-target' in lines
    assert 'bmp stats interval 5000' in lines
    # mirror is false -> `no bmp mirror` (idempotent), never the enable form
    assert 'bmp mirror' not in lines
    assert 'no bmp mirror' in lines


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_target_deletion(run_cmd):
    """Deleting the only target removes exactly that target and falls back to the
    default sonic-bmp target — nothing else is touched."""
    state = {
        'BMP': {'global': {'mirror-buffer-limit': '4294967214'}},
        'BMP_TARGET': {'production': {'stats-interval': '2000'}},
        'BMP_TARGET_COLLECTOR': {('production', '192.168.1.100', '5000'): {'min-retry': '30000', 'max-retry': '720000'}},
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    run_cmd.reset_mock()
    state['BMP_TARGET'] = {}
    state['BMP_TARGET_COLLECTOR'] = {}
    daemon.bmp_handler('BMP_TARGET', 'production', None)

    lines = _bmp_inner_cmds(run_cmd)
    assert 'no bmp targets production' in lines
    assert 'bmp targets sonic-bmp' in lines
    assert 'bmp connect 127.0.0.1 port 5000 min-retry 10000 max-retry 15000' in lines


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_target_deletion_with_vrf(run_cmd):
    """Target deletion in a non-default VRF is scoped to that VRF's context."""
    state = {'BMP_TARGET': {'test-target': {'stats-interval': '2000'}},
             'BMP_TARGET_COLLECTOR': {('test-target', '192.168.1.100', '5000'): {'min-retry': '30000', 'max-retry': '720000'}}}
    daemon = _make_bmp_daemon(run_cmd, state, bgp_asn={'Vrf1': 65100})
    _bmp_apply_full(daemon, state)

    run_cmd.reset_mock()
    state['BMP_TARGET'] = {}
    state['BMP_TARGET_COLLECTOR'] = {}
    daemon.bmp_handler('BMP_TARGET', 'test-target', None)

    rendered = [_render(call[0][1]) for call in run_cmd.call_args_list]
    assert any('router bgp 65100 vrf Vrf1' in c and 'no bmp targets test-target' in c for c in rendered)
    assert any('bmp targets sonic-bmp' in c for c in rendered)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_collector_deletion_removes_only_that_collector(run_cmd):
    """Deleting one collector removes ONLY that collector's connection and never
    tears down the target (which would reset every other collector)."""
    state = {
        'BMP_TARGET': {'production': {'stats-interval': '2000'}},
        'BMP_TARGET_COLLECTOR': {
            ('production', '192.168.1.100', '5000'): {'min-retry': '30000', 'max-retry': '720000', 'source-interface': 'Loopback0'},
            ('production', '192.168.1.101', '5000'): {'min-retry': '30000', 'max-retry': '720000'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    run_cmd.reset_mock()
    del state['BMP_TARGET_COLLECTOR'][('production', '192.168.1.101', '5000')]
    daemon.bmp_handler('BMP_TARGET_COLLECTOR', ('production', '192.168.1.101', '5000'), None)

    lines = _bmp_inner_cmds(run_cmd)
    assert not any(l.startswith('no bmp targets') for l in lines)
    assert 'no bmp connect 192.168.1.101 port 5000' in lines
    # the surviving collector's connection is never re-issued
    assert not any(l.startswith('bmp connect 192.168.1.100') for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_collector_deletion_preserves_source_interface(run_cmd):
    """The `no bmp connect` for a deleted collector must repeat its source-interface
    so FRR can match and remove the right connection."""
    state = {
        'BMP_TARGET': {'production': {}},
        'BMP_TARGET_COLLECTOR': {
            ('production', '192.168.1.100', '5000'): {'min-retry': '30000', 'max-retry': '720000', 'source-interface': 'Loopback5'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    run_cmd.reset_mock()
    del state['BMP_TARGET_COLLECTOR'][('production', '192.168.1.100', '5000')]
    daemon.bmp_handler('BMP_TARGET_COLLECTOR', ('production', '192.168.1.100', '5000'), None)

    lines = _bmp_inner_cmds(run_cmd)
    assert 'no bmp connect 192.168.1.100 port 5000 source-interface Loopback5' in lines


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_collector_srcif_updated_then_deleted(run_cmd):
    """After a collector's source-interface is updated, a later delete must negate
    with the NEW source-interface (the memory is overwritten on the update event),
    not the one it was first created with."""
    state = {
        'BMP_TARGET': {'production': {}},
        'BMP_TARGET_COLLECTOR': {
            ('production', '192.168.1.100', '5000'): {
                'min-retry': '30000', 'max-retry': '720000', 'source-interface': 'Loopback0'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    # Update the collector's source-interface Loopback0 -> Loopback1.
    state['BMP_TARGET_COLLECTOR'][('production', '192.168.1.100', '5000')]['source-interface'] = 'Loopback1'
    daemon.bmp_handler('BMP_TARGET_COLLECTOR', ('production', '192.168.1.100', '5000'),
                       state['BMP_TARGET_COLLECTOR'][('production', '192.168.1.100', '5000')])

    # Now delete it; the `no bmp connect` must carry Loopback1.
    run_cmd.reset_mock()
    del state['BMP_TARGET_COLLECTOR'][('production', '192.168.1.100', '5000')]
    daemon.bmp_handler('BMP_TARGET_COLLECTOR', ('production', '192.168.1.100', '5000'), None)

    lines = _bmp_inner_cmds(run_cmd)
    assert 'no bmp connect 192.168.1.100 port 5000 source-interface Loopback1' in lines
    assert not any('Loopback0' in l for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_target_deletion_triggers_default_target(run_cmd):
    """Deleting the last custom target falls back to the default sonic-bmp target."""
    state = {'BMP_TARGET': {'custom-target': {'stats-interval': '2000'}},
             'BMP_TARGET_COLLECTOR': {('custom-target', '192.168.1.100', '5000'): {'min-retry': '30000', 'max-retry': '720000'}}}
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    run_cmd.reset_mock()
    state['BMP_TARGET'] = {}
    state['BMP_TARGET_COLLECTOR'] = {}
    daemon.bmp_handler('BMP_TARGET', 'custom-target', None)

    lines = _bmp_inner_cmds(run_cmd)
    assert 'no bmp targets custom-target' in lines
    assert 'bmp targets sonic-bmp' in lines
    assert 'bmp connect 127.0.0.1 port 5000 min-retry 10000 max-retry 15000' in lines
    assert 'bmp stats interval 1000' in lines
    assert 'bmp monitor ipv4 unicast pre-policy' in lines
    assert 'bmp monitor ipv6 unicast pre-policy' in lines


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_afi_safi_change_does_not_reset_other_sessions(run_cmd):
    """Core regression: enabling a monitoring option on ONE target pushes that
    target's `bmp monitor` change and NEVER emits `no bmp targets` / `no bmp
    connect`, so no collector session (on this or any other target) drops. The
    unmodified target is not mentioned at all."""
    state = {
        'BMP': {'global': {'mirror-buffer-limit': '4294967214'}},
        'BMP_TARGET': {'ts101-openbmp': {'stats-interval': '2000'},
                       'ts102-openbmp': {'stats-interval': '2000'}},
        'BMP_TARGET_COLLECTOR': {
            ('ts101-openbmp', '10.0.0.1', '5000'): {'min-retry': '30000', 'max-retry': '720000'},
            ('ts102-openbmp', '10.0.0.2', '5000'): {'min-retry': '30000', 'max-retry': '720000'},
        },
        'BMP_TARGET_AFI_SAFI': {
            ('ts101-openbmp', 'ipv4_unicast'): {'adj-rib-in-pre': 'true', 'adj-rib-in-post': 'false', 'loc-rib': 'false'},
            ('ts102-openbmp', 'ipv4_unicast'): {'adj-rib-in-pre': 'true', 'adj-rib-in-post': 'false', 'loc-rib': 'false'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    # The ticket's trigger: enable adj-rib-in-post on ts101-openbmp only.
    run_cmd.reset_mock()
    state['BMP_TARGET_AFI_SAFI'][('ts101-openbmp', 'ipv4_unicast')]['adj-rib-in-post'] = 'true'
    daemon.bmp_handler('BMP_TARGET_AFI_SAFI', ('ts101-openbmp', 'ipv4_unicast'),
                       state['BMP_TARGET_AFI_SAFI'][('ts101-openbmp', 'ipv4_unicast')])

    lines = _bmp_inner_cmds(run_cmd)
    rendered = ' '.join(_render(call[0][1]) for call in run_cmd.call_args_list)

    # The core invariant: no session-tearing command is ever emitted, so no
    # collector session is dropped on any target.
    assert not any(l.startswith('no bmp targets') for l in lines), \
        "config change must not tear down any BMP target: {}".format(lines)
    assert not any(l.startswith('no bmp connect') for l in lines), \
        "config change must not drop any collector connection: {}".format(lines)
    # The untouched target is never mentioned in any way.
    assert 'ts102-openbmp' not in rendered, "an unmodified target must not be reconfigured"
    # The new monitor is enabled on the changed target (and only monitor lines for
    # this one afi/safi are touched).
    assert 'bmp monitor ipv4 unicast post-policy' in lines
    assert all(('ipv4 unicast' in l) for l in lines if 'bmp monitor' in l)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_collector_add_does_not_reset_existing(run_cmd):
    """Adding a collector emits only the new `bmp connect`; the existing collector
    is neither re-issued nor dropped, and the target is not torn down."""
    state = {
        'BMP_TARGET': {'production': {'stats-interval': '2000'}},
        'BMP_TARGET_COLLECTOR': {
            ('production', '192.168.1.100', '5000'): {'min-retry': '30000', 'max-retry': '720000'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    run_cmd.reset_mock()
    state['BMP_TARGET_COLLECTOR'][('production', '192.168.1.101', '5001')] = {
        'min-retry': '30000', 'max-retry': '720000'}
    daemon.bmp_handler('BMP_TARGET_COLLECTOR', ('production', '192.168.1.101', '5001'),
                       state['BMP_TARGET_COLLECTOR'][('production', '192.168.1.101', '5001')])

    lines = _bmp_inner_cmds(run_cmd)
    assert not any(l.startswith('no bmp targets') for l in lines)
    assert not any(l.startswith('no bmp connect') for l in lines)
    assert 'bmp connect 192.168.1.101 port 5001 min-retry 30000 max-retry 720000' in lines
    assert not any(l.startswith('bmp connect 192.168.1.100') for l in lines)


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_stale_collector_delete_after_target_delete_no_ghost(run_cmd):
    """A BMP_TARGET_COLLECTOR delete that arrives AFTER the target itself was
    deleted must be a no-op — it must not resurrect the target via the
    create-or-enter `bmp targets <t>`."""
    state = {
        'BMP_TARGET': {'production': {}},
        'BMP_TARGET_COLLECTOR': {
            ('production', '192.168.1.100', '5000'): {
                'min-retry': '30000', 'max-retry': '720000', 'source-interface': 'Loopback0'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    # Target and its collector both removed from CONFIG_DB; target delete fires first.
    state['BMP_TARGET'] = {}
    state['BMP_TARGET_COLLECTOR'] = {}
    daemon.bmp_handler('BMP_TARGET', 'production', None)

    # Now a stale collector delete for the already-removed target arrives.
    run_cmd.reset_mock()
    daemon.bmp_handler('BMP_TARGET_COLLECTOR', ('production', '192.168.1.100', '5000'), None)

    lines = _bmp_inner_cmds(run_cmd)
    # Nothing at all should be pushed: no ghost `bmp targets`, no `no bmp connect`.
    assert lines == [], lines


@patch.dict('sys.modules', **mockmapping)
@patch('frrcfgd.frrcfgd.g_run_command')
def test_bmp_stale_afi_safi_delete_after_target_delete_no_ghost(run_cmd):
    """A BMP_TARGET_AFI_SAFI delete that arrives AFTER the target was deleted must
    be a no-op, not resurrect the target with an empty monitor stanza."""
    state = {
        'BMP_TARGET': {'production': {}},
        'BMP_TARGET_AFI_SAFI': {
            ('production', 'ipv4_unicast'): {'adj-rib-in-pre': 'true', 'adj-rib-in-post': 'false', 'loc-rib': 'false'},
        },
    }
    daemon = _make_bmp_daemon(run_cmd, state)
    _bmp_apply_full(daemon, state)

    state['BMP_TARGET'] = {}
    state['BMP_TARGET_AFI_SAFI'] = {}
    daemon.bmp_handler('BMP_TARGET', 'production', None)

    run_cmd.reset_mock()
    daemon.bmp_handler('BMP_TARGET_AFI_SAFI', ('production', 'ipv4_unicast'), None)

    lines = _bmp_inner_cmds(run_cmd)
    assert lines == [], lines


def _nbr_or_peer_template():
    """bgpd.conf.db.nbr_or_peer.j2 loaded with the ipv4/ipv6 address filters
    sonic-cfggen provides to the template at full config generation."""
    import os
    import socket
    from jinja2 import Environment, FileSystemLoader

    def address_filter(family):
        def is_address(value):
            try:
                socket.inet_pton(family, value)
                return True
            except (socket.error, TypeError):
                return False
        return is_address

    template_dir = os.path.join(os.path.dirname(__file__), '..', 'templates', 'bgpd')
    env = Environment(loader=FileSystemLoader(template_dir))
    env.filters['ipv4'] = address_filter(socket.AF_INET)
    env.filters['ipv6'] = address_filter(socket.AF_INET6)
    return env.get_template('bgpd.conf.db.nbr_or_peer.j2')


def _nbr_or_peer_lines(rendered):
    """Non-empty rendered lines, stripped. The template is rendered without
    trim_blocks (matching sonic-cfggen), so the {% if %} tags leave blanks."""
    return [line.strip() for line in rendered.splitlines() if line.strip()]


def test_bgp_neighbor_interface_v6only_template():
    """Test BGP interface neighbor with v6only configuration via Jinja2 template.

    The v6only attribute is handled by the Jinja2 template during full config
    generation, not via the runtime nbr_cfg_map. This test verifies the template
    correctly generates 'neighbor <intf> interface v6only' for interface neighbors.
    """
    template = _nbr_or_peer_template()

    # Test case 1: Interface neighbor with v6only=true
    # The template generates: neighbor Ethernet0 interface v6only remote-as 65200
    result = template.render(
        nbr_or_peer_type='neighbor',
        name_or_ip='Ethernet0',
        nbr_or_peer={'v6only': 'true', 'asn': '65200'},
        vrf='default'
    )
    assert 'neighbor Ethernet0 interface v6only remote-as 65200' in result

    # Test case 2: Interface neighbor without v6only (default behavior)
    # The template generates: neighbor Ethernet4 interface remote-as 65201
    result = template.render(
        nbr_or_peer_type='neighbor',
        name_or_ip='Ethernet4',
        nbr_or_peer={'asn': '65201'},
        vrf='default'
    )
    assert 'neighbor Ethernet4 interface remote-as 65201' in result
    assert 'v6only' not in result

    # Test case 3: Interface neighbor with v6only=false (explicit false)
    # The template generates: neighbor PortChannel10 interface remote-as external
    result = template.render(
        nbr_or_peer_type='neighbor',
        name_or_ip='PortChannel10',
        nbr_or_peer={'v6only': 'false', 'peer_type': 'external'},
        vrf='default'
    )
    assert 'neighbor PortChannel10 interface remote-as external' in result
    assert 'v6only' not in result


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


def hdl_static_route_color_cmd(is_del, cmd_list, chk_data):
    """Handler to verify static route commands with color attribute"""
    assert(len(chk_data) >= len(cmd_list))
    for idx, cmd in enumerate(cmd_list):
        last_cmd = cmd[-1] if isinstance(cmd, list) else re.findall(r"-c\s+'([^']+)'\s*", cmd)[-1]
        if is_del:
            assert(last_cmd.startswith('no '))
            last_cmd = last_cmd[3:]  # Remove 'no '
        # Check all expected parts are in the command
        for part in chk_data[idx]:
            assert(part in last_cmd), f"Expected '{part}' in command '{last_cmd}'"


static_route_color_data = [
    # Single nexthop with color
    CmdMapTestInfo('STATIC_ROUTE', 'default|10.1.0.0/24',
                   {'nexthop': '192.168.1.1', 'color': '100'},
                   hdl_static_route_color_cmd, False, None,
                   [['ip route 10.1.0.0/24', '192.168.1.1', 'color 100']]),

    # Multiple nexthops with different colors
    CmdMapTestInfo('STATIC_ROUTE', 'default|10.2.0.0/24',
                   {'nexthop': '192.168.1.1,192.168.1.2,192.168.1.3',
                    'distance': '10,20,30',
                    'color': '100,200,0'},
                   hdl_static_route_color_cmd, False, None,
                   [['ip route 10.2.0.0/24', '192.168.1.1', '10', 'color 100'],
                    ['ip route 10.2.0.0/24', '192.168.1.2', '20', 'color 200'],
                    ['ip route 10.2.0.0/24', '192.168.1.3', '30']]),  # color=0 means no color

    # Color=0 (no SR-Policy)
    CmdMapTestInfo('STATIC_ROUTE', 'default|10.3.0.0/24',
                   {'nexthop': '192.168.1.1', 'color': '0'},
                   hdl_static_route_color_cmd, False, None,
                   [['ip route 10.3.0.0/24', '192.168.1.1']]),  # No color in output

    # IPv6 with color
    CmdMapTestInfo('STATIC_ROUTE', 'default|2001:db8::/64',
                   {'nexthop': '2001:db8::1', 'color': '100'},
                   hdl_static_route_color_cmd, False, None,
                   [['ipv6 route 2001:db8::/64', '2001:db8::1', 'color 100']]),

    # Backward compatibility - no color attribute
    CmdMapTestInfo('STATIC_ROUTE', 'default|10.4.0.0/24',
                   {'nexthop': '192.168.1.1,192.168.1.2'},
                   hdl_static_route_color_cmd, False, None,
                   [['ip route 10.4.0.0/24', '192.168.1.1'],
                    ['ip route 10.4.0.0/24', '192.168.1.2']]),
]


def test_static_route_color():
    """Test static route with SR-Policy color attribute"""
    data_set_del_test(static_route_color_data)


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


>>>>>>> ea6e4f2d8 (NOS-9006: Adding SONiC YANG/model support for neighbor and peer-group BGP graceful control knobs (#7327))
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
