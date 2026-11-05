"""Platform YANG deviation templates (platform-yang-templates/*.yang.j2) against
the Nexthop device tree (device/nexthop/*/feature_capabilities.json).

Each Nexthop platform postinst renders every template with
`j2 <template> /usr/share/sonic/device/<platform>/feature_capabilities.json`
into /usr/local/platform-yang-models/, which sonic_yang (GCU, config replace /
apply-patch) and nhcli load next to the base models. These tests render the
templates the same way (strict undefined variables, like j2) and check that
every template yields a module libyang accepts for every device JSON in the
tree and for a JSON without capability blocks, that the trimming
deviation pins SWITCH_TRIMMING size to the declared constant, and that the
TC_TO_QUEUE_MAP deviation limits tc and qindex to the declared maximums.
"""

import json
import os
import re
from glob import glob

import jinja2
import pytest

CUR_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CUR_DIR, '..', '..', '..'))  # src/sonic-yang-models
REPO_ROOT = os.path.abspath(os.path.join(PROJECT_ROOT, '..', '..'))     # sonic-buildimage
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, 'platform-yang-templates')

TEMPLATES = sorted(os.path.basename(p) for p in glob(os.path.join(TEMPLATE_DIR, '*.yang.j2')))
# Deduplicated by real path: every TH6 SKU symlinks device/nexthop/common/th6/feature_capabilities.json.
DEVICE_CAPABILITIES = sorted({os.path.realpath(p) for p in
                              glob(os.path.join(REPO_ROOT, 'device', 'nexthop', '*', 'feature_capabilities.json'))})
TH6_CAPABILITIES = os.path.realpath(os.path.join(REPO_ROOT, 'device', 'nexthop', 'common', 'th6',
                                                 'feature_capabilities.json'))
TRIMMING_TEMPLATE = 'sonic-trimming-capability.yang.j2'
# Hides its leaf unless the platform opts in, so it deviates when no capabilities are declared.
HIDDEN_BY_DEFAULT_TEMPLATES = {'sonic-sflow-capability.yang.j2'}
TC_QUEUE_TEMPLATE = 'sonic-tc-queue-map-capability.yang.j2'
DNX_CAPABILITIES = [os.path.join(REPO_ROOT, 'device', 'nexthop', platform, 'feature_capabilities.json')
                    for platform in ('x86_64-nexthop_5010-r0', 'x86_64-nexthop_5210-r0040')]

ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_DIR), undefined=jinja2.StrictUndefined)


def render(template, capabilities):
    return ENV.get_template(template).render(**capabilities)


def load_json(path):
    with open(path) as f:
        return json.load(f)


def rel(path):
    return os.path.relpath(path, REPO_ROOT)


def trimming_data(**leaves):
    return {
        "sonic-trimming:sonic-trimming": {
            "sonic-trimming:SWITCH_TRIMMING": {
                "GLOBAL": leaves
            }
        }
    }


def tc_queue_data(tc, qindex):
    return {
        "sonic-tc-queue-map:sonic-tc-queue-map": {
            "sonic-tc-queue-map:TC_TO_QUEUE_MAP": {
                "TC_TO_QUEUE_MAP_LIST": [
                    {"name": "AZURE", "TC_TO_QUEUE_MAP": [{"tc": str(tc), "qindex": str(qindex)}]}
                ]
            }
        }
    }


def test_tree_layout():
    assert TRIMMING_TEMPLATE in TEMPLATES
    assert TC_QUEUE_TEMPLATE in TEMPLATES
    assert DEVICE_CAPABILITIES, "device/nexthop/*/feature_capabilities.json not found"
    assert TH6_CAPABILITIES in DEVICE_CAPABILITIES


@pytest.mark.parametrize("template", TEMPLATES)
@pytest.mark.parametrize("capabilities_file", DEVICE_CAPABILITIES, ids=rel)
def test_template_renders_for_every_device(yang_model, template, capabilities_file):
    yang_model.load_module_str(render(template, load_json(capabilities_file)))


@pytest.mark.parametrize("template", TEMPLATES)
def test_template_renders_empty_module_without_capabilities(yang_model, template):
    rendered = render(template, {})
    has_deviation = re.search(r'^\s*deviation\b', rendered, re.MULTILINE) is not None
    assert has_deviation == (template in HIDDEN_BY_DEFAULT_TEMPLATES), rendered
    yang_model.load_module_str(rendered)


class TestTrimmingCapability:

    @pytest.mark.parametrize("capabilities_file",
                             [p for p in DEVICE_CAPABILITIES if 'trimming_capabilities' in load_json(p)], ids=rel)
    def test_deviation_pins_declared_size(self, yang_model, capabilities_file):
        capabilities = load_json(capabilities_file)
        size = capabilities['trimming_capabilities']['trim_size_fixed']
        yang_model.load_module_str(render(TRIMMING_TEMPLATE, capabilities))

        yang_model.load_data(trimming_data(size=str(size), dscp_value='10', tc_value='1', queue_index='5'))
        yang_model.load_data(trimming_data(queue_index='dynamic'))
        for bad in (size - 1, size + 1):
            yang_model.load_data(trimming_data(size=str(bad)), f"Packet trim size is fixed at {size} bytes")

    def test_th6_declares_392(self):
        assert load_json(TH6_CAPABILITIES)['trimming_capabilities'] == {"trim_size_fixed": 392}

    @pytest.mark.parametrize("size", ["512", "256"])
    def test_th6_rejects_refused_sizes(self, yang_model, size):
        yang_model.load_module_str(render(TRIMMING_TEMPLATE, load_json(TH6_CAPABILITIES)))
        yang_model.load_data(trimming_data(size=size), "Packet trim size is fixed at 392 bytes")

    def test_base_model_alone_accepts_any_size(self, yang_model):
        yang_model.load_data(trimming_data(size='512'))


class TestTcQueueMapCapability:

    @pytest.mark.parametrize("capabilities_file",
                             [p for p in DEVICE_CAPABILITIES if 'qos_capabilities' in load_json(p)], ids=rel)
    def test_deviation_limits_declared_range(self, yang_model, capabilities_file):
        capabilities = load_json(capabilities_file)
        max_tc = capabilities['qos_capabilities']['max_tc']
        max_queue_index = capabilities['qos_capabilities']['max_queue_index']
        yang_model.load_module_str(render(TC_QUEUE_TEMPLATE, capabilities))

        yang_model.load_data(tc_queue_data(0, 0))
        yang_model.load_data(tc_queue_data(max_tc, max_queue_index))
        yang_model.load_data(tc_queue_data(max_tc + 1, 0),
                             f"tc should be in the range [0, {max_tc}]")
        yang_model.load_data(tc_queue_data(0, max_queue_index + 1),
                             f"qindex should be in the range [0, {max_queue_index}]")

    @pytest.mark.parametrize("capabilities_file", DNX_CAPABILITIES, ids=rel)
    def test_dnx_declares_8_tcs_and_8_queues(self, capabilities_file):
        assert load_json(capabilities_file)['qos_capabilities'] == {"max_tc": 7, "max_queue_index": 7}

    @pytest.mark.parametrize("tc", [8, 15])
    def test_dnx_rejects_tc_8_to_15(self, yang_model, tc):
        yang_model.load_module_str(render(TC_QUEUE_TEMPLATE, load_json(DNX_CAPABILITIES[0])))
        yang_model.load_data(tc_queue_data(tc, 0), "Invalid Traffic Class for this platform")

    def test_base_model_alone_accepts_tc_15_and_qindex_9(self, yang_model):
        yang_model.load_data(tc_queue_data(15, 9))
