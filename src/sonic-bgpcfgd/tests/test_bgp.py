from unittest.mock import MagicMock, patch

import os
from bgpcfgd.directory import Directory
from bgpcfgd.template import TemplateFabric
from . import swsscommon_test
from .util import load_constants, render_constants
from swsscommon import swsscommon
import bgpcfgd.managers_bgp

TEMPLATE_PATH = os.path.abspath('../../dockers/docker-fpm-frr/frr')

def load_constant_files():
    # Production constants come from the shared build template
    # (files/build_templates/constants.yml.j2), rendered to a temp file, plus
    # the extra test-only constants fixtures under tests/data/constants.
    constant_files = [render_constants()]
    path = "tests/data/constants"
    constant_files += [os.path.abspath(os.path.join(path, name)) for name in os.listdir(path)
               if os.path.isfile(os.path.join(path, name)) and name.startswith("constants")]

    return constant_files


def constructor(constants_path, bgp_router_id="", peer_type="general", with_lo0_ipv4=True, with_lo4096_ipv4=False, vrf=None):
    cfg_mgr = MagicMock()
    constants = load_constants(constants_path)['constants']
    common_objs = {
        'directory': Directory(),
        'cfg_mgr':   cfg_mgr,
        'tf':        TemplateFabric(TEMPLATE_PATH),
        'constants': constants
    }

    return_value_map = {
        "['vtysh', '-H', '/dev/null', '-c', 'show bgp vrfs json']": (0, "{\"vrfs\": {\"default\": {}}}", ""),
        "['vtysh', '-c', 'show bgp vrf default neighbors json']": (0, "{\"10.10.10.1\": {}, \"20.20.20.1\": {}, \"fc00:10::1\": {}, \"DynNbr1\": {}, \"DynNbr2\": {}}", ""),
        "['vtysh', '-c', 'show bgp peer-group DynNbr1 json']": (0, "{\"DynNbr1\":{\"dynamicRanges\":{\"IPv4\":{\"count\":1,\"ranges\":[\"10.255.0.0/24\"]}}}}", ""),
        "['vtysh', '-c', 'show bgp peer-group DynNbr2 json']": (0, "{\"DynNbr2\":{\"dynamicRanges\":{\"IPv4\":{\"count\":1,\"ranges\":[\"192.168.0.0/24\",\"192.168.1.0/24\"]}}}}", "")
    }

    bgpcfgd.managers_bgp.run_command = lambda cmd: return_value_map[str(cmd)]
    m = bgpcfgd.managers_bgp.BGPPeerMgrBase(common_objs, "CONFIG_DB", swsscommon.CFG_BGP_NEIGHBOR_TABLE_NAME, peer_type, True)
    assert m.peer_type == peer_type
    assert m.check_neig_meta == ('bgp' in constants and 'use_neighbors_meta' in constants['bgp'] and constants['bgp']['use_neighbors_meta'])

    localhost_obj = {"bgp_asn": "65100"}
    if len(bgp_router_id) != 0:
        localhost_obj["bgp_router_id"] = bgp_router_id
    m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_METADATA_TABLE_NAME, "localhost", localhost_obj)
    if with_lo4096_ipv4:
        m.directory.put("CONFIG_DB", swsscommon.CFG_LOOPBACK_INTERFACE_TABLE_NAME, "Loopback4096|11.11.11.11/32", {})
    if with_lo0_ipv4:
        m.directory.put("CONFIG_DB", swsscommon.CFG_LOOPBACK_INTERFACE_TABLE_NAME, "Loopback0|11.11.11.11/32", {})
    m.directory.put("CONFIG_DB", swsscommon.CFG_LOOPBACK_INTERFACE_TABLE_NAME, "Loopback0|FC00:1::32/128", {})
    # For VRF-aware tests, populate the appropriate VRF binding attribute
    intf_meta_v4 = {"admin_status": "up"}
    intf_meta_v6 = {"admin_status": "up"}
    if vrf:
        field = "vnet_name" if vrf.startswith("Vnet") else "vrf_name"
        intf_meta_v4[field] = vrf
        intf_meta_v6[field] = vrf
    m.directory.put("LOCAL", "local_addresses", "Ethernet4|30.30.30.30", {"interface": "Ethernet4", "prefixlen": "24"})
    m.directory.put("LOCAL", "local_addresses", "Ethernet8|fc00:20::20", {"interface": "Ethernet8", "prefixlen": "96"})
    m.directory.put("LOCAL", "interfaces", "Ethernet4", intf_meta_v4)
    m.directory.put("LOCAL", "interfaces", "Ethernet8", intf_meta_v6)
    m.directory.put("CONFIG_DB", swsscommon.CFG_BGP_NEIGHBOR_TABLE_NAME, "default|10.10.10.1", {"ip_range": None})

    if m.check_neig_meta:
        m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_NEIGHBOR_METADATA_TABLE_NAME, "TOR", {})

    return m

@patch('bgpcfgd.managers_bgp.log_info')
def test_update_peer_up(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("10.10.10.1", {"admin_status": "up"})
        assert res, "Expect True return value for peer update"
        mocked_log_info.assert_called_with("Peer 'default|10.10.10.1' admin state is set to 'up'")

@patch('bgpcfgd.managers_bgp.log_info')
def test_update_peer_up_ipv6(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("fc00:10::1", {"admin_status": "up"})
        assert res, "Expect True return value for peer update"
        mocked_log_info.assert_called_with("Peer 'default|fc00:10::1' admin state is set to 'up'")

@patch('bgpcfgd.managers_bgp.log_info')
def test_update_peer_down(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("10.10.10.1", {"admin_status": "down"})
        assert res, "Expect True return value for peer update"
        mocked_log_info.assert_called_with("Peer 'default|10.10.10.1' admin state is set to 'down'")

@patch('bgpcfgd.managers_bgp.log_err')
def test_update_peer_no_admin_status(mocked_log_err):
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("10.10.10.1", {"anything": "anything"})
        assert res, "Expect True return value for peer update"
        mocked_log_err.assert_called_with("Peer '(default|10.10.10.1)': Can't update the peer. Only 'admin_status' attribute is supported")

@patch('bgpcfgd.managers_bgp.log_err')
def test_update_peer_invalid_admin_status(mocked_log_err):
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("10.10.10.1", {"admin_status": "invalid"})
        assert res, "Expect True return value for peer update"
        mocked_log_err.assert_called_with("Peer 'default|10.10.10.1': Can't update the peer. It has wrong attribute value attr['admin_status'] = 'invalid'")

def test_add_peer():
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value"

def test_add_peer_internal():
    for constant in load_constant_files():
        m = constructor(constant, peer_type="internal", with_lo4096_ipv4=True)
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value"

@patch('bgpcfgd.managers_bgp.log_info')
def test_add_peer_internal_no_router_id_no_lo4096(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant, peer_type="internal")
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert not res, "Expect False return value"
        mocked_log_info.assert_called_with("Additional loopbacks acquired for peer internal, loopback list ['Loopback0', 'Loopback4096']")

def test_add_peer_internal_router_id():
    for constant in load_constant_files():
        m = constructor(constant,  bgp_router_id="8.8.8.8", peer_type="internal", with_lo4096_ipv4=True)
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value"

def test_add_peer_internal_router_id_no_lo4096():
    for constant in load_constant_files():
        m = constructor(constant, bgp_router_id="8.8.8.8", peer_type="internal")

def test_add_peer_router_id():
    for constant in load_constant_files():
        m = constructor(constant, bgp_router_id="8.8.8.8")
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value"

@patch('bgpcfgd.managers_bgp.log_info')
@patch('bgpcfgd.managers_bgp.log_warn')
def test_add_peer_without_lo_ipv4(mocked_log_warn, mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant, with_lo0_ipv4=False)
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert not res, "Expect False return value"
        mocked_log_info.assert_called_with("No additional loopbacks acquired for peer general, loopback list ['Loopback0']")
        mocked_log_warn.assert_called_with("Loopback0 ipv4 address is not presented yet and bgp_router_id not configured")

def test_add_peer_without_lo_ipv4_router_id():
    for constant in load_constant_files():
        m = constructor(constant, bgp_router_id="8.8.8.8", with_lo0_ipv4=False)
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value"

def test_add_peer_ipv6():
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("fc00:20::1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': 'fc00:20::20', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value"

def test_add_peer_in_vnet():
    for constant in load_constant_files():
        m = constructor(constant, vrf="Vnet-10")
        res = m.set_handler("Vnet-10|30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value"

def test_add_peer_ipv6_in_vnet():
    for constant in load_constant_files():
        m = constructor(constant, vrf="Vnet-10")
        res = m.set_handler("Vnet-10|fc00:20::1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': 'fc00:20::20', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value"

@patch('bgpcfgd.managers_bgp.log_debug')
def test_add_peer_vrf_mismatch(mocked_log_debug):
    """Test that a peer in Vrf_0003 cannot pass dependency check using an address only present in Vrf_0002"""
    for constant in load_constant_files():
        m = constructor(constant, vrf="Vrf_0002")
        # Peer is in Vrf_0003 but the local address 30.30.30.30 only exists on Ethernet4 in Vrf_0002
        res = m.set_handler("Vrf_0003|30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert not res, "Expect False: VRF mismatch should block peer addition"

@patch('bgpcfgd.managers_bgp.log_debug')
def test_add_peer_default_vrf_rejects_vrf_bound_interface(mocked_log_debug):
    """Test that a default VRF peer cannot match an interface bound to a non-default VRF"""
    for constant in load_constant_files():
        m = constructor(constant, vrf="Vrf_0002")
        # Peer is in default VRF but local address 30.30.30.30 is on Ethernet4 in Vrf_0002
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert not res, "Expect False: default VRF peer should not match VRF-bound interface"

def test_overlapping_ip_different_vrfs():
    """Test that the same IP on two interfaces in different VRFs matches the correct one"""
    for constant in load_constant_files():
        m = constructor(constant, vrf="Vrf_0002")
        # Add a second interface with the SAME IP but in Vrf_0003
        m.directory.put("LOCAL", "local_addresses", "Ethernet12|30.30.30.30", {"interface": "Ethernet12", "prefixlen": "24"})
        m.directory.put("LOCAL", "interfaces", "Ethernet12", {"admin_status": "up", "vrf_name": "Vrf_0003"})
        # Peer in Vrf_0003 should match Ethernet12, not Ethernet4
        res = m.set_handler("Vrf_0003|30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True: peer in Vrf_0003 should match Ethernet12 (same VRF)"

def test_overlapping_ip_different_vnets():
    """Test that the same IP on two VNET interfaces matches the correct one"""
    for constant in load_constant_files():
        m = constructor(constant, vrf="Vnet-10")
        # Add a second interface with the SAME IP but in Vnet-20
        m.directory.put("LOCAL", "local_addresses", "Ethernet12|30.30.30.30", {"interface": "Ethernet12", "prefixlen": "24"})
        m.directory.put("LOCAL", "interfaces", "Ethernet12", {"admin_status": "up", "vnet_name": "Vnet-20"})
        # Peer in Vnet-20 should match Ethernet12, not Ethernet4
        res = m.set_handler("Vnet-20|30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True: peer in Vnet-20 should match Ethernet12 (same VNET)"

@patch('bgpcfgd.managers_bgp.log_debug')
def test_add_peer_vnet_mismatch(mocked_log_debug):
    """Test that a peer in Vnet-20 cannot pass dependency check using an address only present in Vnet-10"""
    for constant in load_constant_files():
        m = constructor(constant, vrf="Vnet-10")
        # Peer is in Vnet-20 but the local address 30.30.30.30 only exists on Ethernet4 in Vnet-10
        res = m.set_handler("Vnet-20|30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert not res, "Expect False: VNET mismatch should block peer addition"

@patch('bgpcfgd.managers_bgp.log_debug')
def test_add_peer_default_vrf_rejects_vnet_bound_interface(mocked_log_debug):
    """Test that a default VRF peer cannot match an interface bound to a VNET"""
    for constant in load_constant_files():
        m = constructor(constant, vrf="Vnet-10")
        # Peer is in default VRF but local address 30.30.30.30 is on Ethernet4 in Vnet-10
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0', 'rrclient': '0'})
        assert not res, "Expect False: default VRF peer should not match VNET-bound interface"

@patch('bgpcfgd.managers_bgp.log_info')
def test_add_dynamic_peer(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant, peer_type="dynamic")
        m.check_neig_meta = False
        res = m.set_handler("BGPSLBPassive", {"peer_asn": "65200", "ip_range": "10.250.0.0/27", "name": "BGPSLBPassive", "src_address": "10.250.0.1"})
        mocked_log_info.assert_called_with("Peer '(default|BGPSLBPassive)' has been scheduled to be added with attributes '{'peer_asn': '65200', 'ip_range': '10.250.0.0/27', 'name': 'BGPSLBPassive', 'src_address': '10.250.0.1'}'")
        assert res, "Expect True return value"

@patch('bgpcfgd.managers_bgp.log_info')
def test_add_dynamic_peer_ipv6(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant, peer_type="dynamic")
        m.check_neig_meta = False
        res = m.set_handler("BGPSLBPassive", {"peer_asn": "65200", "ip_range": "fc00:20::/64", "name": "BGPSLBPassive", "src_address": "fc00:20::1"})
        mocked_log_info.assert_called_with("Peer '(default|BGPSLBPassive)' has been scheduled to be added with attributes '{'peer_asn': '65200', 'ip_range': 'fc00:20::/64', 'name': 'BGPSLBPassive', 'src_address': 'fc00:20::1'}'")
        assert res, "Expect True return value"

@patch('bgpcfgd.managers_bgp.log_info')
@patch('bgpcfgd.managers_bgp.swsscommon.Table')
@patch('bgpcfgd.managers_bgp.swsscommon.DBConnector')
def modify_dynamic_peer_common(mock_db_conn, mock_table, mocked_log_info, peer, data, update_log, final_log):
    for constant in load_constant_files():
        m = constructor(constant, peer_type="dynamic")
        m.cfg_mgr.push = MagicMock(return_value = None)
        m.check_neig_meta = False
        swsscommon.STATE_BGP_PEER_CONFIGURED_TABLE_NAME = "BGP_PEER_CONFIGURED_TABLE"
        mock_state_db_table = MagicMock()
        mock_table.return_value = mock_state_db_table
        res = m.set_handler(peer, data)
        assert res, "Expect True return value"
        if "update" in m.templates:
            mock_state_db_table.set.assert_called_once_with(peer, list(sorted(data.items())))
            mocked_log_info.assert_any_call(update_log)
            mocked_log_info.assert_called_with(final_log)

def test_add_dynamic_peer_range():
    data = {"peer_asn": "65200", "ip_range": "10.255.0.0/24,10.255.1.0/24", "name": "DynNbr1"}
    peer = "DynNbr1"
    update_log = "Peer '(default|DynNbr1)' ip range is going to be updated. Ranges to delete: [] Ranges to add: ['10.255.1.0/24']"
    final_log = "Peer '(default|DynNbr1)' ip range has been scheduled to be updated with range '10.255.0.0/24,10.255.1.0/24'"
    modify_dynamic_peer_common(peer=peer, data=data, update_log=update_log, final_log=final_log)

def test_modify_dynamic_peer_range():
    data = {"peer_asn": "65200", "ip_range": "10.255.0.0/26", "name": "DynNbr1"}
    peer = "DynNbr1"
    update_log = "Peer '(default|DynNbr1)' ip range is going to be updated. Ranges to delete: ['10.255.0.0/24'] Ranges to add: ['10.255.0.0/26']"
    final_log = "Peer '(default|DynNbr1)' ip range has been scheduled to be updated with range '10.255.0.0/26'"
    modify_dynamic_peer_common(peer=peer, data=data, update_log=update_log, final_log=final_log)

def test_delete_dynamic_peer_range():
    data = {"peer_asn": "65200", "ip_range": "192.168.0.0/24", "name": "DynNbr2"}
    peer = "DynNbr2"
    update_log = "Peer '(default|DynNbr2)' ip range is going to be updated. Ranges to delete: ['192.168.1.0/24'] Ranges to add: []"
    final_log = "Peer '(default|DynNbr2)' ip range has been scheduled to be updated with range '192.168.0.0/24'"
    modify_dynamic_peer_common(peer=peer, data=data, update_log=update_log, final_log=final_log)

@patch('bgpcfgd.managers_bgp.log_warn')
def test_add_peer_no_local_addr(mocked_log_warn):
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("30.30.30.1", {"admin_status": "up"})
        assert res, "Expect True return value"
        mocked_log_warn.assert_called_with("Peer 30.30.30.1. Missing attribute 'local_addr'")

@patch('bgpcfgd.managers_bgp.log_debug')
def test_add_peer_invalid_local_addr(mocked_log_debug):
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("30.30.30.1", {"local_addr": "40.40.40.40", "admin_status": "up"})
        assert not res, "Expect False return value"
        mocked_log_debug.assert_called_with("Peer '30.30.30.1' with local address '40.40.40.40' wait for the corresponding interface to be set")

@patch('bgpcfgd.managers_bgp.log_info')
def test_del_handler(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        m.del_handler("10.10.10.1")
        mocked_log_info.assert_called_with("Peer '(default|10.10.10.1)' has been removed")
    
@patch('bgpcfgd.managers_bgp.log_info')
def test_del_handler_dynamic_template_exists(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant, peer_type="dynamic")
        base_template = "bgpd/templates/" + m.constants["bgp"]["peers"]["dynamic"]["template_dir"] + "/delete.conf.j2"
        if os.path.exists(TEMPLATE_PATH + "/" + base_template):
            mocked_log_info.assert_called_with("Using delete template found at %s" % base_template)
        m.del_handler("10.10.10.1")
        mocked_log_info.assert_called_with("Peer '(default|10.10.10.1)' has been removed")

@patch('bgpcfgd.managers_bgp.log_warn')
def test_del_handler_nonexist_peer(mocked_log_warn):
    for constant in load_constant_files():
        m = constructor(constant)
        m.del_handler("40.40.40.1")
        mocked_log_warn.assert_called_with("Peer '(default|40.40.40.1)' has not been found")

@patch('bgpcfgd.managers_bgp.log_info')
@patch('bgpcfgd.managers_bgp.log_warn')
def test_del_handler_dynamic_nonexist_peer_template_exists(mocked_log_warn, mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant, peer_type="dynamic")
        base_template = "bgpd/templates/" + m.constants["bgp"]["peers"]["dynamic"]["template_dir"] + "/delete.conf.j2"
        if os.path.exists(TEMPLATE_PATH + "/" + base_template):
            mocked_log_info.assert_called_with("Using delete template found at %s" % base_template)
        m.del_handler("40.40.40.1")
        mocked_log_warn.assert_called_with("Peer '(default|40.40.40.1)' has not been found")
<<<<<<< HEAD
=======

# Tests for is_interface_neighbor helper function
def test_is_interface_neighbor():
    from bgpcfgd.managers_bgp import is_interface_neighbor
    # Interface neighbors
    assert is_interface_neighbor("Ethernet0") == True
    assert is_interface_neighbor("Ethernet100") == True
    assert is_interface_neighbor("PortChannel1") == True
    assert is_interface_neighbor("PortChannel100") == True
    assert is_interface_neighbor("Vlan100") == True
    assert is_interface_neighbor("Vlan4094") == True
    # IP addresses (not interface neighbors)
    assert is_interface_neighbor("10.10.10.1") == False
    assert is_interface_neighbor("fc00:10::1") == False
    assert is_interface_neighbor("192.168.1.1") == False

# Tests for interface neighbor with v6only
@patch('bgpcfgd.managers_bgp.log_info')
def test_add_interface_neighbor(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        # Add neighbor metadata entry if check_neig_meta is enabled
        if m.check_neig_meta:
            m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_NEIGHBOR_METADATA_TABLE_NAME, "INTF_NBR", {})
        res = m.set_handler("Ethernet0", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'name': 'INTF_NBR', 'nhopself': '0', 'rrclient': '0'})
        assert res, "Expect True return value for interface neighbor"
        # Verify v6only tracking is set to 'false' by default
        assert ('default', 'Ethernet0') in m.intf_nbr_v6only
        assert m.intf_nbr_v6only[('default', 'Ethernet0')] == 'false'

@patch('bgpcfgd.managers_bgp.log_info')
def test_add_interface_neighbor_v6only(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        # Add neighbor metadata entry if check_neig_meta is enabled
        if m.check_neig_meta:
            m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_NEIGHBOR_METADATA_TABLE_NAME, "INTF_NBR_V6", {})
        res = m.set_handler("Ethernet4", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'name': 'INTF_NBR_V6', 'nhopself': '0', 'rrclient': '0', 'v6only': 'true'})
        assert res, "Expect True return value for interface neighbor with v6only"
        # Verify v6only tracking is set to 'true'
        assert ('default', 'Ethernet4') in m.intf_nbr_v6only
        assert m.intf_nbr_v6only[('default', 'Ethernet4')] == 'true'

@patch('bgpcfgd.managers_bgp.log_info')
def test_add_portchannel_neighbor_v6only(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        # Add neighbor metadata entry if check_neig_meta is enabled
        if m.check_neig_meta:
            m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_NEIGHBOR_METADATA_TABLE_NAME, "PC_NBR", {})
        res = m.set_handler("PortChannel1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'name': 'PC_NBR', 'nhopself': '0', 'rrclient': '0', 'v6only': 'true'})
        assert res, "Expect True return value for PortChannel neighbor with v6only"
        assert ('default', 'PortChannel1') in m.intf_nbr_v6only
        assert m.intf_nbr_v6only[('default', 'PortChannel1')] == 'true'

@patch('bgpcfgd.managers_bgp.log_info')
def test_add_vlan_neighbor_v6only(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        # Add neighbor metadata entry if check_neig_meta is enabled
        if m.check_neig_meta:
            m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_NEIGHBOR_METADATA_TABLE_NAME, "VLAN_NBR", {})
        res = m.set_handler("Vlan100", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'name': 'VLAN_NBR', 'nhopself': '0', 'rrclient': '0', 'v6only': 'true'})
        assert res, "Expect True return value for Vlan neighbor with v6only"
        assert ('default', 'Vlan100') in m.intf_nbr_v6only
        assert m.intf_nbr_v6only[('default', 'Vlan100')] == 'true'

@patch('bgpcfgd.managers_bgp.log_info')
def test_del_interface_neighbor_cleans_v6only_tracking(mocked_log_info):
    for constant in load_constant_files():
        m = constructor(constant)
        # Add neighbor metadata entry if check_neig_meta is enabled
        if m.check_neig_meta:
            m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_NEIGHBOR_METADATA_TABLE_NAME, "INTF_NBR", {})
        # Add interface neighbor with v6only
        m.set_handler("Ethernet8", {'asn': '65200', 'holdtime': '180', 'keepalive': '60', 'name': 'INTF_NBR', 'nhopself': '0', 'rrclient': '0', 'v6only': 'true'})
        assert ('default', 'Ethernet8') in m.intf_nbr_v6only
        # Delete the neighbor
        m.del_handler("Ethernet8")
        # Verify v6only tracking is cleaned up
        assert ('default', 'Ethernet8') not in m.intf_nbr_v6only


# -----------------------------------------------------------------------------
# RFC 5549: capability_ext_nexthop
# -----------------------------------------------------------------------------
def _pushed_cmds(m):
    """Concatenated text of every cfg_mgr.push() call."""
    return "\n".join(call.args[0] for call in m.cfg_mgr.push.call_args_list)


@pytest.mark.parametrize("peer_type,with_lo4096", [("general", False), ("internal", True), ("voq_chassis", False)])
def test_add_peer_capability_ext_nexthop_true_emits_command(peer_type, with_lo4096):
    """When BGP_NEIGHBOR has capability_ext_nexthop=true the rendered instance
    template must emit the FRR 'capability extended-nexthop' line."""
    for constant in load_constant_files():
        m = constructor(constant, peer_type=peer_type, with_lo4096_ipv4=with_lo4096)
        data = {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                'local_addr': '30.30.30.30', 'name': 'TOR',
                'nhopself': '0', 'rrclient': '0',
                'capability_ext_nexthop': 'true'}
        assert m.set_handler("30.30.30.1", data), "Expect True return value"
        assert "neighbor 30.30.30.1 capability extended-nexthop" in _pushed_cmds(m)


@pytest.mark.parametrize("peer_type,with_lo4096", [("general", False), ("internal", True), ("voq_chassis", False)])
def test_add_peer_capability_ext_nexthop_absent_or_false(peer_type, with_lo4096):
    """The capability line must not be emitted if the field is missing or
    explicitly false."""
    for constant in load_constant_files():
        # absent
        m = constructor(constant, peer_type=peer_type, with_lo4096_ipv4=with_lo4096)
        data = {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                'local_addr': '30.30.30.30', 'name': 'TOR',
                'nhopself': '0', 'rrclient': '0'}
        assert m.set_handler("30.30.30.1", data), "Expect True return value"
        assert "capability extended-nexthop" not in _pushed_cmds(m)

        # explicitly false
        m = constructor(constant, peer_type=peer_type, with_lo4096_ipv4=with_lo4096)
        data['capability_ext_nexthop'] = 'false'
        assert m.set_handler("30.30.30.1", data), "Expect True return value"
        assert "capability extended-nexthop" not in _pushed_cmds(m)


def test_add_peer_capability_ext_nexthop_ipv6_peer():
    """RFC 5549's normal deployment is an IPv6 transport carrying v4 routes;
    make sure the line is emitted for v6-addressed neighbors too."""
    for constant in load_constant_files():
        m = constructor(constant)
        data = {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                'local_addr': 'fc00:20::20', 'name': 'TOR',
                'nhopself': '0', 'rrclient': '0',
                'capability_ext_nexthop': 'true'}
        assert m.set_handler("fc00:20::1", data), "Expect True return value"
        assert "neighbor fc00:20::1 capability extended-nexthop" in _pushed_cmds(m)


@patch('bgpcfgd.managers_bgp.log_info')
def test_update_peer_capability_ext_nexthop_true(mocked_log_info):
    """Toggling the field on an already-existing peer issues the FRR
    'neighbor X capability extended-nexthop' command at runtime — no
    config_reload required."""
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("10.10.10.1", {"capability_ext_nexthop": "true"})
        assert res, "Expect True return value for peer update"
        pushed = _pushed_cmds(m)
        assert "neighbor 10.10.10.1 capability extended-nexthop" in pushed
        assert "no neighbor 10.10.10.1 capability extended-nexthop" not in pushed
        mocked_log_info.assert_called_with(
            "Peer 'default|10.10.10.1' capability_ext_nexthop is set to 'true'")


@patch('bgpcfgd.managers_bgp.log_info')
def test_update_peer_capability_ext_nexthop_false(mocked_log_info):
    """Setting capability_ext_nexthop=false must emit the matching 'no' form."""
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("10.10.10.1", {"capability_ext_nexthop": "false"})
        assert res, "Expect True return value for peer update"
        assert "no neighbor 10.10.10.1 capability extended-nexthop" in _pushed_cmds(m)
        mocked_log_info.assert_called_with(
            "Peer 'default|10.10.10.1' capability_ext_nexthop is set to 'false'")


@patch('bgpcfgd.managers_bgp.log_err')
def test_update_peer_capability_ext_nexthop_invalid(mocked_log_err):
    """An invalid value is rejected and logged, with nothing pushed to FRR."""
    for constant in load_constant_files():
        m = constructor(constant)
        m.cfg_mgr.reset_mock()
        res = m.set_handler("10.10.10.1", {"capability_ext_nexthop": "maybe"})
        assert res, "set_handler always returns True for known neighbors"
        assert m.cfg_mgr.push.call_count == 0
        mocked_log_err.assert_called_with(
            "Peer 'default|10.10.10.1': Can't update the peer. "
            "capability_ext_nexthop has wrong attribute value")


def test_update_peer_full_row_with_capability_ext_nexthop():
    """In production the CONFIG_DB subscriber delivers the full BGP_NEIGHBOR
    row on every HSET — admin_status is always present alongside whichever
    field actually changed. Verify capability_ext_nexthop is honored even
    when the row also carries admin_status (no mutually-exclusive elif)."""
    for constant in load_constant_files():
        m = constructor(constant)
        full_row = {'admin_status': 'up', 'asn': '64600', 'holdtime': '10',
                    'keepalive': '3', 'local_addr': '10.0.0.130',
                    'name': 'ARISTA02T1', 'nhopself': '0', 'rrclient': '0',
                    'capability_ext_nexthop': 'true'}
        res = m.set_handler("10.10.10.1", full_row)
        assert res, "Expect True return value for peer update"
        pushed = _pushed_cmds(m)
        # capability line emitted ...
        assert "neighbor 10.10.10.1 capability extended-nexthop" in pushed
        # ... and admin_status branch also ran (idempotent 'no shutdown').
        assert "no neighbor 10.10.10.1 shutdown" in pushed


def test_update_peer_capability_ext_nexthop_non_default_vrf():
    """apply_op wraps the per-neighbor command in 'router bgp <asn> vrf <name>'
    for non-default VRFs (managers_bgp.apply_op). Verify the capability_ext_nexthop
    update path threads through that VRF wrapper correctly — important for
    multi-VRF RFC 5549 deployments."""
    for constant in load_constant_files():
        m = constructor(constant)
        # load_peers() only sees default-VRF neighbors via the mocked vtysh.
        # Seed the (Vrf-red, 10.10.10.1) peer so set_handler routes through
        # update_peer rather than add_peer.
        m.peers.add(("Vrf-red", "10.10.10.1"))
        res = m.set_handler("Vrf-red|10.10.10.1", {"capability_ext_nexthop": "true"})
        assert res, "Expect True return value for peer update"
        pushed = _pushed_cmds(m)
        assert "router bgp 65100 vrf Vrf-red" in pushed
        assert "neighbor 10.10.10.1 capability extended-nexthop" in pushed


# ---------------------------------------------------------------------------
# change_bfd — BFD on an EXISTING neighbor renders in place (no del/add, no
# BGP flap). 10.10.10.1 is already a known peer (mocked vtysh neighbors), so
# set_handler routes through update_peer -> change_bfd.
# ---------------------------------------------------------------------------

def test_change_bfd_bare_enable_on_existing_neighbor():
    """bfd=true on an existing neighbor emits a bare 'neighbor X bfd' through
    the update path (regression for the dropped-on-update gap)."""
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("10.10.10.1", {"bfd": "true"})
        assert res, "Expect True return value for peer update"
        pushed = _pushed_cmds(m)
        assert "neighbor 10.10.10.1 bfd" in pushed


def test_change_bfd_disable():
    """bfd=false emits 'no neighbor X bfd'."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"bfd": "false"})
        assert "no neighbor 10.10.10.1 bfd" in _pushed_cmds(m)


def test_change_bfd_profile():
    """bfd_profile emits the enable line plus 'bfd profile <name>'."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"bfd": "true", "bfd_profile": "fast-failover"})
        pushed = _pushed_cmds(m)
        assert "neighbor 10.10.10.1 bfd" in pushed
        assert "neighbor 10.10.10.1 bfd profile fast-failover" in pushed


def test_change_bfd_inline_timers_clears_stale_profile():
    """Inline timers emit 'neighbor X bfd <m> <rx> <tx>' and first clear any
    stale profile (FRR retains the old profile association otherwise)."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {
            "bfd": "true", "bfd_detect_multiplier": "3",
            "bfd_min_rx": "100", "bfd_min_tx": "100"})
        pushed = _pushed_cmds(m)
        assert "no neighbor 10.10.10.1 bfd profile" in pushed
        assert "neighbor 10.10.10.1 bfd 3 100 100" in pushed


def test_change_bfd_check_ctrl_plane_failure_true():
    """bfd_check_ctrl_plane_failure=true emits the FRR check-control-plane-failure
    line (previously dropped in bgpcfgd mode)."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"bfd": "true", "bfd_check_ctrl_plane_failure": "true"})
        assert "neighbor 10.10.10.1 bfd check-control-plane-failure" in _pushed_cmds(m)


def test_change_bfd_check_ctrl_plane_failure_false():
    """bfd_check_ctrl_plane_failure=false emits the negated form."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"bfd": "true", "bfd_check_ctrl_plane_failure": "false"})
        assert "no neighbor 10.10.10.1 bfd check-control-plane-failure" in _pushed_cmds(m)


# ---------------------------------------------------------------------------
# Hardware BFD offload (NOS-12951): bare/partial BFD enables merge per-field
# offload defaults (3/1000/1000) so the session never registers at FRR's
# unsupported 300 ms defaults. Covers both the add_peer template render and
# the change_bfd update path.
# ---------------------------------------------------------------------------

def test_add_peer_hw_offload_bare_bfd_merges_defaults():
    for constant in load_constant_files():
        m = constructor(constant)
        m.hw_bfd_offload_active = True
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                                           'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0',
                                           'rrclient': '0', 'bfd': 'true'})
        assert res, "Expect True return value"
        assert "neighbor 30.30.30.1 bfd 3 1000 1000" in _pushed_cmds(m)


def test_add_peer_hw_offload_partial_timers_merge():
    for constant in load_constant_files():
        m = constructor(constant)
        m.hw_bfd_offload_active = True
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                                           'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0',
                                           'rrclient': '0', 'bfd': 'true', 'bfd_min_rx': '100'})
        assert res, "Expect True return value"
        assert "neighbor 30.30.30.1 bfd 3 100 1000" in _pushed_cmds(m)


def test_add_peer_hw_offload_empty_string_fields_take_defaults():
    """An empty-string timer field in the row must render the offload default
    (Jinja default() needs the boolean arg to catch '' as well as undefined)."""
    for constant in load_constant_files():
        m = constructor(constant)
        m.hw_bfd_offload_active = True
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                                           'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0',
                                           'rrclient': '0', 'bfd': 'true', 'bfd_min_rx': '',
                                           'bfd_detect_multiplier': '5', 'bfd_min_tx': ''})
        assert res, "Expect True return value"
        assert "neighbor 30.30.30.1 bfd 5 1000 1000" in _pushed_cmds(m)


def test_add_peer_bare_bfd_without_offload_unchanged():
    """No offload -> bare enable, no synthetic timers."""
    for constant in load_constant_files():
        m = constructor(constant)
        res = m.set_handler("30.30.30.1", {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                                           'local_addr': '30.30.30.30', 'name': 'TOR', 'nhopself': '0',
                                           'rrclient': '0', 'bfd': 'true'})
        assert res, "Expect True return value"
        pushed = _pushed_cmds(m)
        assert "neighbor 30.30.30.1 bfd" in pushed
        assert "bfd 3 1000 1000" not in pushed


def test_change_bfd_hw_offload_bare_enable_merges_defaults():
    """The NOS-12951 operator flow: bfd=true on an ESTABLISHED neighbor."""
    for constant in load_constant_files():
        m = constructor(constant)
        m.hw_bfd_offload_active = True
        assert m.set_handler("10.10.10.1", {"bfd": "true"})
        pushed = _pushed_cmds(m)
        assert "neighbor 10.10.10.1 bfd 3 1000 1000" in pushed
        assert "no neighbor 10.10.10.1 bfd profile" in pushed


def test_change_bfd_hw_offload_partial_timers_merge():
    for constant in load_constant_files():
        m = constructor(constant)
        m.hw_bfd_offload_active = True
        assert m.set_handler("10.10.10.1", {"bfd": "true", "bfd_min_rx": "100"})
        assert "neighbor 10.10.10.1 bfd 3 100 1000" in _pushed_cmds(m)


def test_change_bfd_hw_offload_partial_tx_and_multiplier_merge():
    """Explicit bfd_min_tx and bfd_detect_multiplier are honored while the
    absent bfd_min_rx takes the offload default."""
    for constant in load_constant_files():
        m = constructor(constant)
        m.hw_bfd_offload_active = True
        assert m.set_handler("10.10.10.1", {"bfd": "true", "bfd_min_tx": "100",
                                            "bfd_detect_multiplier": "5"})
        assert "neighbor 10.10.10.1 bfd 5 1000 100" in _pushed_cmds(m)


def test_change_bfd_hw_offload_empty_string_fields_take_defaults():
    """A field cleared to an empty string (nhcli field delete leaves '' in the
    row on some paths) must take the offload default, not render an empty
    token that vtysh rejects."""
    for constant in load_constant_files():
        m = constructor(constant)
        m.hw_bfd_offload_active = True
        assert m.set_handler("10.10.10.1", {"bfd": "true", "bfd_min_rx": "",
                                            "bfd_min_tx": "100",
                                            "bfd_detect_multiplier": ""})
        assert "neighbor 10.10.10.1 bfd 3 1000 100" in _pushed_cmds(m)


def test_change_bfd_hw_offload_profile_wins():
    """bfd_profile still takes precedence under offload; no synthetic timers."""
    for constant in load_constant_files():
        m = constructor(constant)
        m.hw_bfd_offload_active = True
        assert m.set_handler("10.10.10.1", {"bfd": "true", "bfd_profile": "fast-failover"})
        pushed = _pushed_cmds(m)
        assert "neighbor 10.10.10.1 bfd profile fast-failover" in pushed
        assert "bfd 3 1000 1000" not in pushed
# -----------------------------------------------------------------------------
# per-peer graceful-shutdown / graceful-restart
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("field,frr_cmd", [
    ("graceful_shutdown", "graceful-shutdown"),
    ("graceful_restart", "graceful-restart"),
    ("graceful_restart_disable", "graceful-restart-disable"),
    ("graceful_restart_helper", "graceful-restart-helper"),
])
def test_add_peer_graceful_knob_renders(field, frr_cmd):
    """A peer created with a graceful knob set renders the matching FRR line."""
    for constant in load_constant_files():
        m = constructor(constant)
        data = {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                'local_addr': '30.30.30.30', 'name': 'TOR',
                'nhopself': '0', 'rrclient': '0', field: 'true'}
        assert m.set_handler("30.30.30.1", data), "Expect True return value"
        assert "neighbor 30.30.30.1 %s" % frr_cmd in _pushed_cmds(m)


def test_add_peer_graceful_absent_or_false():
    """No graceful line is rendered when the fields are missing or false."""
    for constant in load_constant_files():
        base = {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                'local_addr': '30.30.30.30', 'name': 'TOR',
                'nhopself': '0', 'rrclient': '0'}
        m = constructor(constant)
        assert m.set_handler("30.30.30.1", dict(base))
        assert "graceful" not in _pushed_cmds(m)

        m = constructor(constant)
        data = dict(base)
        data.update({'graceful_shutdown': 'false', 'graceful_restart': 'false',
                     'graceful_restart_disable': 'false', 'graceful_restart_helper': 'false'})
        assert m.set_handler("30.30.30.1", data)
        assert "graceful" not in _pushed_cmds(m)


def test_add_peer_graceful_restart_only_one_mode_rendered():
    """The instance template is if/elif, so a config that somehow carries two GR
    modes still renders exactly one line — FRR keeps a single per-peer mode."""
    for constant in load_constant_files():
        m = constructor(constant)
        data = {'asn': '65200', 'holdtime': '180', 'keepalive': '60',
                'local_addr': '30.30.30.30', 'name': 'TOR',
                'nhopself': '0', 'rrclient': '0',
                'graceful_restart': 'true', 'graceful_restart_helper': 'true'}
        assert m.set_handler("30.30.30.1", data)
        pushed = _pushed_cmds(m)
        assert "neighbor 30.30.30.1 graceful-restart\n" in pushed + "\n"
        assert "graceful-restart-helper" not in pushed


@pytest.mark.parametrize("value,expected", [
    ("true", "neighbor 10.10.10.1 graceful-shutdown"),
    ("false", "no neighbor 10.10.10.1 graceful-shutdown"),
])
def test_update_peer_graceful_shutdown(value, expected):
    """Toggling graceful_shutdown on an existing peer issues the command at
    runtime — no peer recreation, no config_reload."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"graceful_shutdown": value})
        pushed = _pushed_cmds(m)
        assert expected in pushed
        if value == "true":
            assert "no neighbor 10.10.10.1 graceful-shutdown" not in pushed


def test_update_peer_graceful_restart_mode_switch_order():
    """Switching GR mode must apply the new mode BEFORE clearing the old one.

    Unsetting the mode a peer is currently in returns it to PEER_GLOBAL_INHERIT
    with a real action (local_Peer_GR_FSM in bgpd/bgpd.c); once the new mode is
    applied the stale 'no' is a PEER_INVALID -> BGP_GR_NO_OPERATION no-op.
    """
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"graceful_restart": "false",
                                            "graceful_restart_helper": "true"})
        pushed = _pushed_cmds(m)
        apply_idx = pushed.index("neighbor 10.10.10.1 graceful-restart-helper")
        clear_idx = pushed.index("no neighbor 10.10.10.1 graceful-restart")
        assert apply_idx < clear_idx, "new GR mode must be applied before the old is cleared"


def test_update_peer_graceful_restart_clear_all():
    """Setting every GR mode false returns the peer to global-inherit."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"graceful_restart": "false",
                                            "graceful_restart_disable": "false",
                                            "graceful_restart_helper": "false"})
        pushed = _pushed_cmds(m)
        for cmd in ("graceful-restart", "graceful-restart-disable", "graceful-restart-helper"):
            assert "no neighbor 10.10.10.1 %s" % cmd in pushed


def test_update_peer_graceful_restart_absent_leaf_is_not_cleared():
    """Intentional gap (same idiom as change_bfd): only fields present in the
    row are written to FRR. After graceful_restart was true, a remaining-hash
    that has graceful_restart_disable=false (HDEL of graceful_restart) emits
    'no ... graceful-restart-disable' but does not unset the stale GR mode.
    Operators who need to revert a peer write the leaf false, not HDEL it.
    """
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"graceful_restart": "true"})
        m.cfg_mgr.reset_mock()
        assert m.set_handler("10.10.10.1", {"graceful_restart_disable": "false"})
        pushed = _pushed_cmds(m)
        assert "no neighbor 10.10.10.1 graceful-restart-disable" in pushed
        assert not any(line.strip() == "no neighbor 10.10.10.1 graceful-restart"
                       for line in pushed.splitlines())


@patch('bgpcfgd.managers_bgp.log_err')
def test_update_peer_graceful_restart_mutually_exclusive(mocked_log_err):
    """YANG rejects two GR modes, but CONFIG_DB can be written directly, so the
    daemon must refuse rather than push a contradictory sequence."""
    for constant in load_constant_files():
        m = constructor(constant)
        m.cfg_mgr.reset_mock()
        assert m.set_handler("10.10.10.1", {"graceful_restart": "true",
                                            "graceful_restart_helper": "true"})
        assert "graceful" not in _pushed_cmds(m)
        mocked_log_err.assert_called_with(
            "Peer 'default|10.10.10.1': graceful_restart, graceful_restart_disable and "
            "graceful_restart_helper are mutually exclusive; got "
            "['graceful_restart', 'graceful_restart_helper']")


@patch('bgpcfgd.managers_bgp.log_err')
def test_update_peer_graceful_is_actionable(mocked_log_err):
    """A graceful-only update must not fall through to the 'no actionable
    attribute' error branch."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"graceful_shutdown": "true"})
        mocked_log_err.assert_not_called()


def test_update_peer_full_row_with_graceful():
    """The CONFIG_DB subscriber delivers the full BGP_NEIGHBOR row on every
    HSET, so graceful knobs must be honored alongside admin_status."""
    for constant in load_constant_files():
        m = constructor(constant)
        assert m.set_handler("10.10.10.1", {"admin_status": "up",
                                            "graceful_shutdown": "true"})
        pushed = _pushed_cmds(m)
        assert "neighbor 10.10.10.1 graceful-shutdown" in pushed
        assert "no neighbor 10.10.10.1 shutdown" in pushed
>>>>>>> ea6e4f2d8 (NOS-9006: Adding SONiC YANG/model support for neighbor and peer-group BGP graceful control knobs (#7327))
