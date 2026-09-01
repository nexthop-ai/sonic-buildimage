import pytest
from unittest.mock import MagicMock, patch

import os
from bgpcfgd.directory import Directory
from bgpcfgd.template import TemplateFabric
from . import swsscommon_test
from .util import load_constants
import bgpcfgd.managers_device_global
from swsscommon import swsscommon
from copy import deepcopy

#
# Constants -----------------------------------------------------------------------------------------------------------
#

TEMPLATE_PATH = os.path.abspath('../../dockers/docker-fpm-frr/frr')
BASE_PATH = os.path.abspath('../sonic-bgpcfgd/tests/data/general/peer-group.conf/')
INTERNAL_BASE_PATH = os.path.abspath('../sonic-bgpcfgd/tests/data/internal/peer-group.conf/')
WCMP_BASE_PATH = os.path.abspath('../sonic-bgpcfgd/tests/data/wcmp/')
global_constants = {
    "bgp":  {
        "traffic_shift_community" :"12345:12345",
        "internal_community_match_tag" : "1001"
    }
}

#
# Helpers -------------------------------------------------------------------------------------------------------------
#

def constructor(check_internal=False):
    cfg_mgr = MagicMock()
    def get_text():
        text = []
        for line in cfg_mgr.changes.split('\n'):
            if line.lstrip().startswith('!'):
                continue
            text.append(line)
        text += ["     "]
        return text
    def update():
        if check_internal:
            cfg_mgr.changes = get_string_from_file("/result_chasiss_packet.conf", INTERNAL_BASE_PATH)
        else:
            cfg_mgr.changes = get_string_from_file("/result_all.conf")
    def push(cfg):
        cfg_mgr.changes += cfg + "\n"
    def get_config():
        return cfg_mgr.changes
    cfg_mgr.get_text = get_text
    cfg_mgr.update = update
    cfg_mgr.push = push
    cfg_mgr.get_config = get_config

    constants = deepcopy(global_constants)
    common_objs = {
        'directory': Directory(),
        'cfg_mgr':   cfg_mgr,
        'tf':        TemplateFabric(TEMPLATE_PATH),
        'constants': constants
    }
    mgr = bgpcfgd.managers_device_global.DeviceGlobalCfgMgr(common_objs, "CONFIG_DB", swsscommon.CFG_BGP_DEVICE_GLOBAL_TABLE_NAME)
    cfg_mgr.update()
    return mgr

#
# TSA -----------------------------------------------------------------------------------------------------------------
#

@patch('bgpcfgd.managers_device_global.DeviceGlobalCfgMgr.get_chassis_tsa_status')
@patch('bgpcfgd.managers_device_global.log_debug')
def test_isolate_device(mocked_log_info, mock_get_chassis_tsa_status):
    m = constructor()

    mock_get_chassis_tsa_status.return_value = "false"
    res = m.set_handler("STATE", {"tsa_enabled": "true"})
    assert res, "Expect True return value for set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr::Done")
    assert m.cfg_mgr.get_config() == get_string_from_file("/result_all_isolate.conf")

    curr_cfg = m.cfg_mgr.get_config()
    mock_get_chassis_tsa_status.return_value = "true"
    res = m.set_handler("STATE", {"tsa_enabled": "true"})
    assert res, "Expect True return value for set_handler"
    assert m.cfg_mgr.get_config() == curr_cfg


@patch('bgpcfgd.managers_device_global.DeviceGlobalCfgMgr.get_chassis_tsa_status')
@patch('bgpcfgd.managers_device_global.log_debug')
def test_isolate_device_internal_session(mocked_log_info, mock_get_chassis_tsa_status):
    m = constructor(check_internal=True)

    mock_get_chassis_tsa_status.return_value = "false"
    res = m.set_handler("STATE", {"tsa_enabled": "true"})
    assert res, "Expect True return value for set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr::Done")
    assert m.cfg_mgr.get_config() == get_string_from_file("/result_chassis_packet_isolate.conf", INTERNAL_BASE_PATH)

    curr_cfg = m.cfg_mgr.get_config()
    mock_get_chassis_tsa_status.return_value = "true"
    res = m.set_handler("STATE", {"tsa_enabled": "true"})
    assert res, "Expect True return value for set_handler"
    assert m.cfg_mgr.get_config() == curr_cfg


@patch('bgpcfgd.managers_device_global.DeviceGlobalCfgMgr.get_chassis_tsa_status')
@patch('bgpcfgd.managers_device_global.log_debug')
def test_unisolate_device(mocked_log_info, mock_get_chassis_tsa_status):
    m = constructor()

    mock_get_chassis_tsa_status.return_value = "false"

    # By default feature is disabled. Simulate enabled state
    m.directory.put(m.db_name, m.table_name, "tsa_enabled", "true")

    res = m.set_handler("STATE", {"tsa_enabled": "false"})
    assert res, "Expect True return value for set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr::Done")
    assert m.cfg_mgr.get_config() == get_string_from_file("/result_all_unisolate.conf")

    curr_cfg = m.cfg_mgr.get_config()
    mock_get_chassis_tsa_status.return_value = "true"
    res = m.set_handler("STATE", {"tsa_enabled": "false"})
    assert res, "Expect True return value for set_handler"
    assert m.cfg_mgr.get_config() == curr_cfg


@patch('bgpcfgd.managers_device_global.DeviceGlobalCfgMgr.get_chassis_tsa_status')
@patch('bgpcfgd.managers_device_global.log_debug')
def test_unisolate_device_internal_session(mocked_log_info, mock_get_chassis_tsa_status):
    m = constructor(check_internal=True)

    mock_get_chassis_tsa_status.return_value = "false"

    # By default feature is disabled. Simulate enabled state
    m.directory.put(m.db_name, m.table_name, "tsa_enabled", "true")

    res = m.set_handler("STATE", {"tsa_enabled": "false"})
    assert res, "Expect True return value for set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr::Done")
    assert m.cfg_mgr.get_config() == get_string_from_file("/result_chassis_packet_unisolate.conf", INTERNAL_BASE_PATH)

    curr_cfg = m.cfg_mgr.get_config()
    mock_get_chassis_tsa_status.return_value = "true"
    res = m.set_handler("STATE", {"tsa_enabled": "false"})
    assert res, "Expect True return value for set_handler"
    assert m.cfg_mgr.get_config() == curr_cfg


@patch('bgpcfgd.managers_device_global.DeviceGlobalCfgMgr.get_chassis_tsa_status')
def test_check_state_and_get_tsa_routemaps(mock_get_chassis_tsa_status):
    m = constructor()

    mock_get_chassis_tsa_status.return_value = "false"
    m.set_handler("STATE", {"tsa_enabled": "true"})
    res = m.check_state_and_get_tsa_routemaps(m.cfg_mgr.get_config())
    assert res == get_string_from_file("/result_isolate.conf")

    mock_get_chassis_tsa_status.return_value = "true"
    m.set_handler("STATE", {"tsa_enabled": "true"})
    res = m.check_state_and_get_tsa_routemaps(m.cfg_mgr.get_config())
    assert res == get_string_from_file("/result_isolate.conf")

    mock_get_chassis_tsa_status.return_value = "false"
    m.set_handler("STATE", {"tsa_enabled": "false"})
    res = m.check_state_and_get_tsa_routemaps(m.cfg_mgr.get_config())
    assert res == ""

    mock_get_chassis_tsa_status.return_value = "true"
    m.set_handler("STATE", {"tsa_enabled": "false"})
    res = m.check_state_and_get_tsa_routemaps(m.cfg_mgr.get_config())
    assert res == get_string_from_file("/result_isolate.conf")


def test_get_tsa_routemaps():
    m = constructor()
    assert m.get_ts_routemaps([], m.tsa_template) == ""

    res = m.get_ts_routemaps(m.cfg_mgr.get_text(), m.tsa_template)
    expected_res = get_string_from_file("/result_isolate.conf")
    assert res == expected_res


def test_get_tsa_routemaps_for_unnumbered_peers():
    m = constructor()
    tf = TemplateFabric(TEMPLATE_PATH)
    metadata = {
        'localhost': {
            'bgp_asn': '65100',
            'sub_role': 'FrontEnd',
            'switch_type': 'chassis-packet',
            'type': 'LeafRouter',
        }
    }
    rendered_peer_groups = [
        tf.from_file('bgpd/templates/general/peer-group.conf.j2').render(
            CONFIG_DB__DEVICE_METADATA=metadata,
            CONFIG_DB__BGP_BBR={'status': 'disabled'},
        ),
        tf.from_file('bgpd/templates/internal/peer-group.conf.j2').render(
            CONFIG_DB__DEVICE_METADATA=metadata
        ),
        tf.from_file('bgpd/templates/voq_chassis/peer-group.conf.j2').render(
            CONFIG_DB__DEVICE_METADATA=metadata
        ),
    ]

    res = m.get_ts_routemaps('\n'.join(rendered_peer_groups).splitlines(), m.tsa_template)

    assert 'route-map TO_BGP_PEER_UNNUMBERED_V4 permit 20\n  match ip address prefix-list PL_LoopbackV4' in res
    assert 'route-map TO_BGP_PEER_UNNUMBERED_V6 permit 20\n  match ipv6 address prefix-list PL_LoopbackV6' in res
    assert 'route-map TO_BGP_INTERNAL_PEER_UNNUMBERED_V4 permit 20\n  set community no-export additive' in res
    assert 'route-map TO_BGP_INTERNAL_PEER_UNNUMBERED_V6 permit 20\n  set community no-export additive' in res
    assert 'route-map TO_VOQ_CHASSIS_PEER_UNNUMBERED_V4 permit 20\n  set community no-export additive' in res
    assert 'route-map TO_VOQ_CHASSIS_PEER_UNNUMBERED_V6 permit 20\n  set community no-export additive' in res


def test_get_tsb_routemaps():
    m = constructor()
    assert m.get_ts_routemaps([], m.tsb_template) == ""

    res = m.get_ts_routemaps(m.cfg_mgr.get_text(), m.tsb_template)
    expected_res = get_string_from_file("/result_unisolate.conf")
    assert res == expected_res

def get_string_from_file(filename, base_path=BASE_PATH):
    fp = open(base_path + filename, "r")
    cfg = fp.read()
    fp.close()

    return cfg

@patch('bgpcfgd.managers_device_global.log_err')
def test_set_handler_failure_case(mocked_log_info):
    m = constructor()
    res = m.set_handler("STATE", {})
    assert res == False, "Expect False return value for invalid data passed to set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr:: data is None")

def test_del_handler():
    m = constructor()
    res = m.del_handler("STATE")
    assert res, "Expect True return value for del_handler"

@pytest.mark.parametrize(
    "value", [ "invalid_value" ]
)
@patch('bgpcfgd.managers_device_global.log_err')
@patch('bgpcfgd.managers_device_global.DeviceGlobalCfgMgr.get_chassis_tsa_status')
def test_tsa_neg(mock_get_chassis_tsa_status, mocked_log_err, value):
    m = constructor()
    m.cfg_mgr.changes = ""
    mock_get_chassis_tsa_status.return_value = "false"
    res = m.set_handler("STATE", {"tsa_enabled": value})
    assert res, "Expect True return value for set_handler"
    mocked_log_err.assert_called_with("TSA: invalid value({}) is provided".format(value))

#
# W-ECMP --------------------------------------------------------------------------------------------------------------
#

@pytest.mark.parametrize(
    "value,result", [
        pytest.param(
            "true",
            get_string_from_file("/wcmp.set.conf", WCMP_BASE_PATH),
            id="enabled"
        ),
        pytest.param(
            "false",
            get_string_from_file("/wcmp.unset.conf", WCMP_BASE_PATH),
            id="disabled"
        )
    ]
)
@patch('bgpcfgd.managers_device_global.log_debug')
def test_wcmp(mocked_log_info, value, result):
    m = constructor()
    m.cfg_mgr.changes = ""
    if value == "false":
        # By default feature is disabled. Simulate enabled state
        m.directory.put(m.db_name, m.table_name, "wcmp_enabled", "true")
    res = m.set_handler("STATE", {"wcmp_enabled": value})
    assert res, "Expect True return value for set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr::Done")
    assert m.cfg_mgr.get_config() == result

@pytest.mark.parametrize(
    "value", [ "invalid_value" ]
)
@patch('bgpcfgd.managers_device_global.log_err')
def test_wcmp_neg(mocked_log_err, value):
    m = constructor()
    m.cfg_mgr.changes = ""
    res = m.set_handler("STATE", {"wcmp_enabled": value})
    assert res, "Expect True return value for set_handler"
    mocked_log_err.assert_called_with("W-ECMP: invalid value({}) is provided".format(value))

#
# IDF -----------------------------------------------------------------------------------------------------------------
#

@patch('bgpcfgd.managers_device_global.log_debug')
def test_idf_isolation_no_export(mocked_log_info):
    m = constructor()
    res = m.set_handler("STATE", {"idf_isolation_state": "isolated_no_export"})
    assert res, "Expect True return value for set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr::Done")
    assert m.cfg_mgr.get_config() == get_string_from_file("/result_all_idf_isolated_no_export.conf")

@patch('bgpcfgd.managers_device_global.log_debug')
def test_idf_isolation_withdraw_all(mocked_log_info):
    m = constructor()
    res = m.set_handler("STATE", {"idf_isolation_state": "isolated_withdraw_all"})
    assert res, "Expect True return value for set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr::Done")
    assert m.cfg_mgr.get_config() == get_string_from_file("/result_all_idf_isolated_withdraw_all.conf")

@patch('bgpcfgd.managers_device_global.log_debug')
def test_idf_unisolation(mocked_log_info):
    m = constructor()
    # By default feature is unisolated. Simulate a different state
    m.directory.put(m.db_name, m.table_name, "idf_isolation_state", "isolated_no_export")
    res = m.set_handler("STATE", {"idf_isolation_state": "unisolated"})
    assert res, "Expect True return value for set_handler"
    mocked_log_info.assert_called_with("DeviceGlobalCfgMgr::Done")
    assert m.cfg_mgr.get_config() == get_string_from_file("/result_all_idf_unisolated.conf")

def test_check_state_and_get_idf_isolation_routemaps():
    m = constructor()
    m.set_handler("STATE", {"idf_isolation_state": "isolated_no_export"})
    res = m.check_state_and_get_idf_isolation_routemaps()
    assert res == get_string_from_file("/result_idf_isolated.conf")

    m.set_handler("STATE", {"idf_isolation_state": "unisolated"})
    res = m.check_state_and_get_idf_isolation_routemaps()
    assert res == ""

@pytest.mark.parametrize(
    "value", [ "invalid_value" ]
)
@patch('bgpcfgd.managers_device_global.log_err')
def test_idf_neg(mocked_log_err, value):
    m = constructor()
    m.cfg_mgr.changes = ""
    res = m.set_handler("STATE", {"idf_isolation_state": value})
    assert res, "Expect True return value for set_handler"
    mocked_log_err.assert_called_with("IDF: invalid value({}) is provided".format(value))
<<<<<<< HEAD
=======

#
# log-neighbor-changes ------------------------------------------------------------------------------------------------
#

BGP_ASN = "65100"

def seed_bgp_asn(m, asn=BGP_ASN):
    m.directory.put("CONFIG_DB", swsscommon.CFG_DEVICE_METADATA_TABLE_NAME,
                    "localhost", {"bgp_asn": asn})

def test_log_nbr_disabled():
    m = constructor()
    seed_bgp_asn(m)
    m.cfg_mgr.changes = ""
    res = m.set_handler("STATE", {"log_nbr_state_changes": "false"})
    assert res, "Expect True return value for set_handler"
    cfg = m.cfg_mgr.get_config()
    assert "router bgp %s" % BGP_ASN in cfg
    assert "no bgp log-neighbor-changes" in cfg
    assert m.directory.get(m.db_name, m.table_name, "log_nbr_state_changes") == "false"

def test_log_nbr_enabled():
    m = constructor()
    seed_bgp_asn(m)
    # Simulate a previously-disabled state so re-enabling is an actual change
    m.directory.put(m.db_name, m.table_name, "log_nbr_state_changes", "false")
    m.cfg_mgr.changes = ""
    res = m.set_handler("STATE", {"log_nbr_state_changes": "true"})
    assert res, "Expect True return value for set_handler"
    cfg = m.cfg_mgr.get_config()
    assert "router bgp %s" % BGP_ASN in cfg
    assert "\n  bgp log-neighbor-changes\n" in cfg
    assert m.directory.get(m.db_name, m.table_name, "log_nbr_state_changes") == "true"

def test_log_nbr_up_to_date():
    m = constructor()
    seed_bgp_asn(m)
    # Default is enabled; re-asserting 'true' must not push anything
    m.cfg_mgr.changes = ""
    res = m.set_handler("STATE", {"log_nbr_state_changes": "true"})
    assert res, "Expect True return value for set_handler"
    assert "log-neighbor-changes" not in m.cfg_mgr.get_config()

def test_log_nbr_default_absent():
    m = constructor()
    seed_bgp_asn(m)
    # Absent field leaves the default (enabled) untouched -> no push
    m.cfg_mgr.changes = ""
    res = m.set_handler("STATE", {"tsa_enabled": "false"})
    assert res, "Expect True return value for set_handler"
    assert "log-neighbor-changes" not in m.cfg_mgr.get_config()

def test_log_nbr_no_asn_defers():
    m = constructor()
    # No DEVICE_METADATA/bgp_asn seeded -> cannot build router context, defer.
    m.cfg_mgr.changes = ""
    res = m.set_handler("STATE", {"log_nbr_state_changes": "false"})
    assert not res, "Expect False (not-ready) so the framework replays the update"
    assert "log-neighbor-changes" not in m.cfg_mgr.get_config()
    # Directory unchanged (still default enabled) so the replay re-applies it once
    # the ASN is available.
    assert m.directory.get(m.db_name, m.table_name, "log_nbr_state_changes") == "true"

def test_log_nbr_deferred_then_replayed_on_asn():
    m = constructor()
    m.cfg_mgr.changes = ""
    # SET arrives before the BGP ASN -> configure_log_nbr defers.
    res = m.set_handler("STATE", {"log_nbr_state_changes": "false"})
    assert not res, "Expect False (not-ready) so the framework replays the update"
    assert "log-neighbor-changes" not in m.cfg_mgr.get_config()
    # Directory unchanged (still default enabled) so the replay will re-apply it.
    assert m.directory.get(m.db_name, m.table_name, "log_nbr_state_changes") == "true"
    # Simulate the Manager framework queueing the deferred update (as handler() does
    # when set_handler returns False) and then replaying it once the ASN appears.
    m.set_queue.append(("STATE", {"log_nbr_state_changes": "false"}))
    seed_bgp_asn(m)
    m.on_deps_change()
    cfg = m.cfg_mgr.get_config()
    assert "router bgp %s" % BGP_ASN in cfg
    assert "no bgp log-neighbor-changes" in cfg
    assert m.directory.get(m.db_name, m.table_name, "log_nbr_state_changes") == "false"

@pytest.mark.parametrize(
    "value", [ "invalid_value" ]
)
@patch('bgpcfgd.managers_device_global.log_err')
def test_log_nbr_neg(mocked_log_err, value):
    m = constructor()
    seed_bgp_asn(m)
    m.cfg_mgr.changes = ""
    res = m.set_handler("STATE", {"log_nbr_state_changes": value})
    assert res, "Expect True return value for set_handler"
    mocked_log_err.assert_called_with("DeviceGlobalCfgMgr:: invalid log_nbr_state_changes value '%s'" % value)
# CONFED -----------------------------------------------------------------------------------------------------------
#

def test_confed_set_handler_stores_in_directory():
    m = constructor()
    confed = {"asn": "65100", "peers": "65300"}
    res = m.set_handler("CONFED", confed)
    assert res, "Expect True return value for set_handler"
    slot = m.directory.get_slot(m.db_name, m.table_name)
    assert slot["CONFED"] == confed, "CONFED must be cached in the Directory for the peer templates"

def test_confed_set_handler_does_not_run_tsa():
    m = constructor()
    m.cfg_mgr.changes = ""
    res = m.set_handler("CONFED", {"asn": "65100", "peers": "65300"})
    assert res, "Expect True return value for set_handler"
    # CONFED carries no TSA/W-ECMP/IDF fields, so no FRR config must be pushed
    assert m.cfg_mgr.get_config() == ""

def test_confed_del_handler_removes_from_directory():
    m = constructor()
    m.set_handler("CONFED", {"asn": "65100", "peers": "65300"})
    assert m.directory.path_exist(m.db_name, m.table_name, "CONFED")
    m.cfg_mgr.changes = ""
    res = m.del_handler("CONFED")
    assert res, "Expect True return value for del_handler"
    assert not m.directory.path_exist(m.db_name, m.table_name, "CONFED")
    # CONFED removal must not push any FRR config either
    assert m.cfg_mgr.get_config() == ""

def test_prime_confed_from_config_db_success():
    m = constructor()
    # constructor() does not prime because the swsscommon test double has no
    # ConfigDBConnector; start from a clean slate to exercise the success path.
    if m.directory.path_exist(m.db_name, m.table_name, "CONFED"):
        m.directory.remove(m.db_name, m.table_name, "CONFED")
    confed = {"asn": "65100", "peers": "65300"}
    fake_conn = MagicMock()
    fake_conn.get_table.return_value = {"CONFED": confed}
    with patch.object(bgpcfgd.managers_device_global.swsscommon,
                      "ConfigDBConnector", create=True, return_value=fake_conn):
        m.prime_confed_from_config_db()
    fake_conn.connect.assert_called_once()
    fake_conn.get_table.assert_called_once_with(m.table_name)
    slot = m.directory.get_slot(m.db_name, m.table_name)
    assert slot["CONFED"] == confed, "primed CONFED must be cached in the Directory"

def test_prime_confed_from_config_db_none_table():
    m = constructor()
    if m.directory.path_exist(m.db_name, m.table_name, "CONFED"):
        m.directory.remove(m.db_name, m.table_name, "CONFED")
    fake_conn = MagicMock()
    # get_table() may return None (missing table / transient read); priming must
    # coalesce to {} and neither raise nor store a CONFED entry.
    fake_conn.get_table.return_value = None
    with patch.object(bgpcfgd.managers_device_global.swsscommon,
                      "ConfigDBConnector", create=True, return_value=fake_conn):
        m.prime_confed_from_config_db()
    assert not m.directory.path_exist(m.db_name, m.table_name, "CONFED")

@patch('bgpcfgd.managers_device_global.DeviceGlobalCfgMgr.configure_tsa')
def test_set_handler_unknown_key_does_not_run_tsa(mock_configure_tsa):
    m = constructor()
    m.cfg_mgr.changes = ""
    res = m.set_handler("SOME_UNKNOWN_KEY", {"foo": "bar"})
    assert res, "Expect True return value for set_handler"
    # Only the STATE key drives TSA/W-ECMP/IDF; any other (unknown) key must
    # never fall through to configure_tsa() (regression guard for #28515).
    mock_configure_tsa.assert_not_called()
    assert m.cfg_mgr.get_config() == ""
>>>>>>> d75664d84 (NOS-15445: [bgpcfgd] split confed-external peers into PEER_EXTERNAL peer-groups (#8861))
