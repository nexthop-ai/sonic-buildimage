# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import os
import shlex
import stat
import subprocess

import pytest

import tests.common_utils as utils

TEST_DIR = os.path.dirname(os.path.realpath(__file__))
GNMI_DOCKER_DIR = os.path.join(TEST_DIR, '..', '..', '..', 'dockers', 'docker-sonic-gnmi')
SCRIPT = os.path.join(GNMI_DOCKER_DIR, 'gnmi-native.sh')
TEMPLATE = os.path.join(GNMI_DOCKER_DIR, 'telemetry_vars.j2')
CFGGEN = os.path.join(TEST_DIR, '..', 'sonic-cfggen')

INCORRECT_TELEMETRY_VALUE = 2

SERVER_CRT = '/etc/sonic/tls/server.crt'
SERVER_KEY = '/etc/sonic/tls/server.key'
CA_CRT = '/etc/sonic/tls/ca.crt'


def write_stub(directory, name, body):
    path = os.path.join(directory, name)
    with open(path, 'w') as f:
        f.write('#!/bin/bash\n' + body + '\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
    return path


@pytest.fixture
def run_gnmi_native(tmp_path):
    """Run gnmi-native.sh against a CONFIG_DB given as a dict.

    sonic-cfggen is the real one rendering the real telemetry_vars.j2, fed the
    dict instead of redis. Returns (exit code, argv handed to telemetry, stderr).
    """
    stub_dir = str(tmp_path)
    write_stub(stub_dir, 'sonic-db-cli', 'exit 0')
    # Called as: sonic-cfggen -d -t <template>
    write_stub(stub_dir, 'sonic-cfggen',
               'exec {} {} -a "$TEST_CONFIG_DB" -t "$3"'.format(
                   utils.PYTHON_INTERPRETTER, shlex.quote(CFGGEN)))
    telemetry = write_stub(stub_dir, 'telemetry', 'printf "%s\\n" "$@" > "$TELEMETRY_ARGV_FILE"')
    argv_file = os.path.join(stub_dir, 'telemetry.argv')

    def run(gnmi_table=None, x509=None):
        config_db = {'GNMI': gnmi_table or {}, 'DEVICE_METADATA': {'localhost': {}}}
        if x509 is not None:
            config_db['DEVICE_METADATA']['x509'] = x509
        env = dict(os.environ)
        env.pop('GNMI_LISTENER_MODE', None)
        env.update({
            'PATH': stub_dir + os.pathsep + env['PATH'],
            'TEST_CONFIG_DB': json.dumps(config_db),
            'TELEMETRY_VARS_FILE': TEMPLATE,
            'TELEMETRY_BIN': telemetry,
            'TELEMETRY_ARGV_FILE': argv_file,
        })
        if os.path.exists(argv_file):
            os.remove(argv_file)
        proc = subprocess.run(['bash', SCRIPT], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True)
        argv = []
        if os.path.exists(argv_file):
            with open(argv_file) as f:
                argv = f.read().split('\n')[:-1]
        return proc.returncode, argv, proc.stderr

    return run


def option(argv, name):
    """The value following option `name`, or None when the option is absent."""
    assert argv.count(name) <= 1, argv
    if name not in argv:
        return None
    return argv[argv.index(name) + 1]


def test_no_gnmi_entry_uses_default_port(run_gnmi_native):
    rc, argv, stderr = run_gnmi_native()
    assert rc == 0, stderr
    assert option(argv, '--port') == '8080'


def test_gnmi_entry_without_port_uses_default_port(run_gnmi_native):
    rc, argv, stderr = run_gnmi_native({'gnmi': {'log_level': '2'}})
    assert rc == 0, stderr
    assert option(argv, '--port') == '8080'


def test_gnmi_entry_port_is_used(run_gnmi_native):
    rc, argv, stderr = run_gnmi_native({'gnmi': {'port': '50052', 'log_level': '2'}})
    assert rc == 0, stderr
    assert option(argv, '--port') == '50052'


@pytest.mark.parametrize('port', ['abc', ''])
def test_invalid_port_is_refused(run_gnmi_native, port):
    rc, argv, stderr = run_gnmi_native({'gnmi': {'port': port}})
    assert rc == INCORRECT_TELEMETRY_VALUE
    assert 'Incorrect port value {},'.format(port) in stderr
    assert argv == []


def tls_config(source, entry):
    """run_gnmi_native arguments that put a TLS entry in GNMI|certs or DEVICE_METADATA|x509."""
    if source == 'certs':
        return {'gnmi_table': {'certs': entry}}
    return {'x509': entry}


@pytest.mark.parametrize('source', ['certs', 'x509'])
def test_complete_tls_entry(run_gnmi_native, source):
    entry = {'server_crt': SERVER_CRT, 'server_key': SERVER_KEY, 'ca_crt': CA_CRT}
    rc, argv, stderr = run_gnmi_native(**tls_config(source, entry))
    assert rc == 0, stderr
    assert option(argv, '--server_crt') == SERVER_CRT
    assert option(argv, '--server_key') == SERVER_KEY
    assert option(argv, '--ca_crt') == CA_CRT
    assert '--insecure' not in argv


@pytest.mark.parametrize('source', ['certs', 'x509'])
def test_tls_entry_without_ca_crt(run_gnmi_native, source):
    entry = {'server_crt': SERVER_CRT, 'server_key': SERVER_KEY}
    rc, argv, stderr = run_gnmi_native(**tls_config(source, entry))
    assert rc == 0, stderr
    assert option(argv, '--server_crt') == SERVER_CRT
    assert option(argv, '--server_key') == SERVER_KEY
    assert '--ca_crt' not in argv
    assert 'null' not in argv


@pytest.mark.parametrize('source', ['certs', 'x509'])
@pytest.mark.parametrize('entry', [
    {'server_crt': SERVER_CRT},
    {'server_key': SERVER_KEY},
    {'ca_crt': CA_CRT},
])
def test_tls_entry_missing_a_server_leaf_is_insecure(run_gnmi_native, source, entry):
    rc, argv, stderr = run_gnmi_native(**tls_config(source, entry))
    assert rc == 0, stderr
    assert '--insecure' in argv
    assert '--server_crt' not in argv
    assert '--server_key' not in argv
    assert option(argv, '--ca_crt') == entry.get('ca_crt')
    assert 'null' not in argv
