import pytest


class TestACLTcpFlags:
    # Whether each built-in table type (stypes:acl_table_type) accepts a
    # TCP_FLAGS match. Mirrors the name list in sonic-acl's TCP_FLAGS must.
    TCP_FLAGS_BUILTIN_TYPES = {
        "L2": False,
        "L3": True,
        "L3V6": True,
        "L3V4V6": True,
        "MIRROR": True,
        "MIRRORV6": True,
        "MIRROR_DSCP": False,
        "CTRLPLANE": False,
        "ARS": True,
    }

    def test_tcp_flags_builtin_types_classified(self, yang_model):
        # A built-in type added to the enum but not to the TCP_FLAGS must would
        # reject every TCP_FLAGS rule on it; make that a test failure.
        snode = next(yang_model.ctx.find_path(
            "/sonic-acl:sonic-acl/sonic-acl:ACL_TABLE/sonic-acl:ACL_TABLE_LIST/sonic-acl:type"))
        enums = {e.name() for t in snode.type().union_types()
                 if t.base() == t.ENUM for e in t.enums()}
        assert enums == set(self.TCP_FLAGS_BUILTIN_TYPES)

    @pytest.mark.parametrize("table_type,accepted", sorted(TCP_FLAGS_BUILTIN_TYPES.items()))
    def test_tcp_flags_on_builtin_type(self, yang_model, table_type, accepted):
        table = {"ACL_TABLE_NAME": "T", "type": table_type, "stage": "INGRESS"}
        rule = {"ACL_TABLE_NAME": "T", "RULE_NAME": "R", "PRIORITY": "100",
                "IP_PROTOCOL": "6", "TCP_FLAGS": "0x10/0x10"}
        if table_type == "CTRLPLANE":
            table["services"] = ["SSH"]
            rule["PACKET_ACTION"] = "ACCEPT"
        else:
            table["ports"] = ["Ethernet0"]
        if table_type.startswith("MIRROR"):
            rule["MIRROR_INGRESS_ACTION"] = "everflow"
        elif table_type == "ARS":
            rule["DISABLE_ARS_FORWARDING"] = "true"
        elif table_type != "CTRLPLANE":
            rule["PACKET_ACTION"] = "FORWARD"
        data = {
            "sonic-port:sonic-port": {"sonic-port:PORT": {"PORT_LIST": [
                {"name": "Ethernet0", "lanes": "0,1,2,3", "speed": "100000"}]}},
            "sonic-mirror-session:sonic-mirror-session": {"sonic-mirror-session:MIRROR_SESSION": {
                "MIRROR_SESSION_LIST": [{"name": "everflow", "type": "ERSPAN",
                                         "src_ip": "10.1.1.1", "dst_ip": "11.1.1.1"}]}},
            "sonic-acl:sonic-acl": {
                "sonic-acl:ACL_TABLE": {"ACL_TABLE_LIST": [table]},
                "sonic-acl:ACL_RULE": {"ACL_RULE_LIST": [rule]},
            },
        }
        yang_model.load_data(data, None if accepted else "TCP_FLAGS")
