# Copyright 2026 Nexthop Systems Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import glob
import importlib.machinery
import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

import docker
import pytest

# container_checker has no .py suffix, so load it by path. Its SONiC-only imports are
# stubbed when absent so the test runs off-box.
for _mod in ("sonic_py_common", "swsscommon"):
    if _mod not in sys.modules:
        try:
            __import__(_mod)
        except ImportError:
            sys.modules[_mod] = MagicMock()

_MONIT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(_MONIT_DIR)))
# Each per-branch sidecar snapshot can stand in for the host checker, so all of them are
# held to the tests below.
_SIDECAR_COPIES = sorted(glob.glob(os.path.join(
    _REPO_ROOT, "dockers", "docker-*-sidecar", "systemd_scripts", "container_checker_*")))
_CHECKERS = [os.path.join(_MONIT_DIR, "container_checker")] + _SIDECAR_COPIES


def _load(path):
    name = "container_checker_" + os.path.relpath(path, _REPO_ROOT).replace(os.sep, "_").replace("-", "_")
    loader = importlib.machinery.SourceFileLoader(name, path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module


@pytest.fixture(params=_CHECKERS, ids=lambda p: os.path.relpath(p, _REPO_ROOT))
def checker(request):
    return _load(request.param)


def test_all_sidecar_copies_are_covered():
    assert len(_SIDECAR_COPIES) == 13


@patch("docker.DockerClient")
def test_running_from_dockers_ignores_removed(mock_docker_client, checker):
    ctr = MagicMock()
    ctr.name = "swss"
    ctr.labels = {}
    mock_docker_client.return_value.containers.list.return_value = [ctr]

    assert checker.get_current_running_from_dockers() == {"swss"}
    mock_docker_client.return_value.containers.list.assert_called_once_with(
        filters={"status": "running"}, ignore_removed=True)


@pytest.mark.parametrize("error", [docker.errors.APIError("boom"), docker.errors.DockerException("boom")])
@patch("docker.DockerClient")
def test_running_from_dockers_failure_returns_none(mock_docker_client, error, checker):
    mock_docker_client.return_value.containers.list.side_effect = error

    assert checker.get_current_running_from_dockers() is None


@patch("docker.DockerClient", side_effect=docker.errors.DockerException("dockerd unreachable"))
def test_unreachable_dockerd_returns_none(mock_docker_client, checker):
    assert checker.get_current_running_from_dockers() is None


def test_main_fails_without_events_when_running_set_unknown(checker):
    # A failed enumeration fails the check but must not report every expected container as down.
    with patch.object(checker, "publish_events") as mock_publish, \
            patch.object(checker, "get_current_running_from_dockers", return_value=None), \
            patch.object(checker, "get_current_running_from_DB", return_value=set()), \
            patch.object(checker, "get_expected_running_containers", return_value=({"swss", "syncd"}, set())):
        with pytest.raises(SystemExit) as exc:
            checker.main()
    # Non-zero fails the Monit check; 1 is distinct from the down-report exit code 3.
    assert exc.value.code == 1
    mock_publish.assert_not_called()


def test_main_reports_container_that_is_down(checker):
    with patch.object(checker, "publish_events") as mock_publish, \
            patch.object(checker, "get_current_running_from_dockers", return_value={"swss"}), \
            patch.object(checker, "get_current_running_from_DB", return_value=set()), \
            patch.object(checker, "get_expected_running_containers", return_value=({"swss", "syncd"}, set())):
        with pytest.raises(SystemExit) as exc:
            checker.main()
    assert exc.value.code == 3
    mock_publish.assert_called_once_with({"syncd"})


def test_main_counts_container_reported_only_by_state_db(checker):
    with patch.object(checker, "publish_events") as mock_publish, \
            patch.object(checker, "get_current_running_from_dockers", return_value={"swss"}), \
            patch.object(checker, "get_current_running_from_DB", return_value={"syncd"}), \
            patch.object(checker, "get_expected_running_containers", return_value=({"swss", "syncd"}, set())):
        checker.main()
    mock_publish.assert_not_called()
