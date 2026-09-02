import unittest
from unittest.mock import patch, MagicMock
import sys

import docker

import memory_checker


class TestMemoryChecker(unittest.TestCase):

    @staticmethod
    def _mock_state(mock_docker_client, status, started_at):
        mock_docker_client.return_value.containers.get.return_value.attrs = {
            'State': {'Status': status, 'StartedAt': started_at}}

<<<<<<< HEAD
        result = memory_checker.get_command_result(command)

        self.assertEqual(result, stdout.strip())
        mock_popen.assert_called_once_with(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           universal_newlines=True)
        mock_popen.return_value.communicate.assert_called_once()
        mock_popen.return_value.communicate.assert_called_with()
        self.assertEqual(mock_popen.return_value.returncode, returncode)

    @patch('memory_checker.exit_if_container_stopped')
    @patch('memory_checker.get_command_result')
    def test_get_container_id(self, mock_get_command_result, mock_exit_check):
        container_name = 'your_container'
        command = ['docker', 'ps', '--no-trunc', '--filter', 'name=your_container']
        mock_get_command_result.return_value = ''
=======
    @patch('docker.DockerClient')
    def test_exit_if_container_not_running_still_running(self, mock_docker_client):
        self._mock_state(mock_docker_client, 'running', '2020-01-01T00:00:00.000000000Z')
        self.assertIsNone(memory_checker.exit_if_container_not_running('deadbeef1234'))
>>>>>>> 328533601 (NOS-15064: [memory_checker] Resolve container ID from the running-container snapshot to avoid transient lookup race (#8983))

    @patch('docker.DockerClient')
    def test_exit_if_container_not_running_restarted_mid_check(self, mock_docker_client):
        self._mock_state(mock_docker_client, 'running', '2100-01-01T00:00:00.000000000Z')
        with self.assertRaises(SystemExit) as cm:
            memory_checker.exit_if_container_not_running('deadbeef1234')
        self.assertEqual(cm.exception.code, 0)

<<<<<<< HEAD
    @patch('memory_checker.exit_if_container_stopped')
    @patch('memory_checker.open', side_effect=FileNotFoundError)
    def test_get_memory_usage(self, mock_open, mock_exit_check):
        container_id = 'your_container_id'
        container_name = 'your_container'
=======
    @patch('docker.DockerClient')
    def test_exit_if_container_not_running_stopped(self, mock_docker_client):
        self._mock_state(mock_docker_client, 'exited', '2020-01-01T00:00:00.000000000Z')
        with self.assertRaises(SystemExit) as cm:
            memory_checker.exit_if_container_not_running('deadbeef1234')
        self.assertEqual(cm.exception.code, 0)

    @patch('docker.DockerClient')
    def test_exit_if_container_not_running_removed(self, mock_docker_client):
        mock_docker_client.return_value.containers.get.side_effect = docker.errors.NotFound('gone')
        with self.assertRaises(SystemExit) as cm:
            memory_checker.exit_if_container_not_running('deadbeef1234')
        self.assertEqual(cm.exception.code, 0)

    @patch('docker.DockerClient')
    def test_exit_if_container_not_running_unconfirmed(self, mock_docker_client):
        mock_docker_client.return_value.containers.get.side_effect = docker.errors.APIError('daemon error')
        self.assertIsNone(memory_checker.exit_if_container_not_running('deadbeef1234'))

    @patch('memory_checker.exit_if_container_not_running')
    @patch('memory_checker.open', side_effect=FileNotFoundError)
    def test_get_memory_usage(self, mock_open, mock_exit_check):
        container_id = 'deadbeef1234'
>>>>>>> 328533601 (NOS-15064: [memory_checker] Resolve container ID from the running-container snapshot to avoid transient lookup race (#8983))
        with self.assertRaises(SystemExit) as cm:
            memory_checker.get_memory_usage(container_id, container_name)
        self.assertEqual(cm.exception.code, 1)
        mock_exit_check.assert_called_once_with(container_id)

    @patch('memory_checker.open', side_effect=FileNotFoundError)
    def test_get_memory_usage_invalid(self, mock_open):
        container_id = '../..'
        container_name = 'your_container'
        with self.assertRaises(SystemExit) as cm:
            memory_checker.get_memory_usage(container_id, container_name)
        self.assertEqual(cm.exception.code, 1)

<<<<<<< HEAD
    @patch('memory_checker.exit_if_container_stopped')
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_get_inactive_cache_usage(self, mock_open, mock_exit_check):
        container_id = 'your_container_id'
        container_name = 'your_container'
=======
    @patch('memory_checker.exit_if_container_not_running')
    @patch('builtins.open', side_effect=FileNotFoundError)
    def test_get_inactive_cache_usage(self, mock_open, mock_exit_check):
        container_id = 'deadbeef1234'
>>>>>>> 328533601 (NOS-15064: [memory_checker] Resolve container ID from the running-container snapshot to avoid transient lookup race (#8983))
        with self.assertRaises(SystemExit) as cm:
            memory_checker.get_inactive_cache_usage(container_id, container_name)
        self.assertEqual(cm.exception.code, 1)
        mock_exit_check.assert_called_once_with(container_id)

    @patch('docker.DockerClient')
    def test_get_running_containers(self, mock_docker_client):
        container = MagicMock()
        container.name = 'your_container'
        container.id = 'deadbeef1234'
        mock_docker_client.return_value.containers.list.return_value = [container]

        result = memory_checker.get_running_containers()

        self.assertEqual(result, {'your_container': 'deadbeef1234'})
        mock_docker_client.return_value.containers.list.assert_called_once_with(
            filters={'status': 'running'}, ignore_removed=True)

    @patch('memory_checker._try_get_container_id', return_value=memory_checker._CONTAINER_NOT_RUNNING)
    def test_exit_if_container_stopped(self, mock_get_id):
        """Container not running - should exit gracefully."""
        with self.assertRaises(SystemExit) as cm:
            memory_checker.exit_if_container_stopped('gnmi')
        self.assertEqual(cm.exception.code, 0)

    @patch('memory_checker._try_get_container_id', return_value='current_id_123')
    def test_exit_if_container_still_running(self, mock_get_id):
        """Container running, no container_id check - should not exit."""
        memory_checker.exit_if_container_stopped('gnmi')

    @patch('memory_checker._try_get_container_id', return_value='new_id_456')
    def test_exit_if_container_restarted(self, mock_get_id):
        """Container running with different ID - should exit gracefully."""
        with self.assertRaises(SystemExit) as cm:
            memory_checker.exit_if_container_stopped('gnmi', container_id='old_id_123')
        self.assertEqual(cm.exception.code, 0)

    @patch('memory_checker._try_get_container_id', return_value='same_id_123')
    def test_exit_if_container_same_id(self, mock_get_id):
        """Container running with same ID - should not exit."""
        memory_checker.exit_if_container_stopped('gnmi', container_id='same_id_123')

    @patch('memory_checker._try_get_container_id', return_value=memory_checker._CONTAINER_NOT_RUNNING)
    def test_exit_if_container_removed(self, mock_get_id):
        """Container gone by ID lookup - should exit gracefully."""
        with self.assertRaises(SystemExit) as cm:
            memory_checker.exit_if_container_stopped('gnmi', container_id='old_id_123')
        self.assertEqual(cm.exception.code, 0)

    @patch('memory_checker._try_get_container_id', return_value=None)
    def test_exit_if_docker_api_error_does_not_exit(self, mock_get_id):
        """Docker API error (None) should not cause graceful exit - let original error path handle it."""
        memory_checker.exit_if_container_stopped('gnmi', container_id='old_id_123')

    @patch('memory_checker.docker')
    def test_try_get_container_id_running(self, mock_docker):
        """Container running - should return its ID."""
        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.status = 'running'
        mock_docker.DockerClient.return_value.containers.get.return_value = mock_container
        result = memory_checker._try_get_container_id('gnmi')
        self.assertEqual(result, 'abc123')

    @patch('memory_checker.docker')
    def test_try_get_container_id_stopped(self, mock_docker):
        """Container exists but stopped - should return _CONTAINER_NOT_RUNNING."""
        mock_container = MagicMock()
        mock_container.id = 'abc123'
        mock_container.status = 'exited'
        mock_docker.DockerClient.return_value.containers.get.return_value = mock_container
        result = memory_checker._try_get_container_id('gnmi')
        self.assertIsInstance(result, memory_checker._ContainerNotRunning)

    @patch('memory_checker.docker')
    def test_try_get_container_id_not_found(self, mock_docker):
        """Container not found - should return _CONTAINER_NOT_RUNNING."""
        import docker as real_docker
        mock_docker.errors.NotFound = real_docker.errors.NotFound
        mock_docker.DockerClient.return_value.containers.get.side_effect = real_docker.errors.NotFound('not found')
        result = memory_checker._try_get_container_id('gnmi')
        self.assertIsInstance(result, memory_checker._ContainerNotRunning)

    @patch('memory_checker.docker')
    def test_try_get_container_id_api_error(self, mock_docker):
        """Docker API error - should return None."""
        import docker as real_docker
        mock_docker.errors.NotFound = real_docker.errors.NotFound
        mock_docker.errors.APIError = real_docker.errors.APIError
        mock_docker.errors.DockerException = real_docker.errors.DockerException
        mock_docker.DockerClient.return_value.containers.get.side_effect = real_docker.errors.APIError('error')
        result = memory_checker._try_get_container_id('gnmi')
        self.assertIsNone(result)

    @patch('syslog.syslog')
    @patch('memory_checker.get_memory_usage')
    @patch('memory_checker.get_inactive_cache_usage')
    def test_check_memory_usage(self, mock_get_inactive_cache_usage, mock_get_memory_usage, mock_syslog):
        container_name = 'your_container'
        container_id = 'deadbeef1234'
        threshold_value = 1024
        memory_usage = 2048
        cache_usage = 512
        mock_get_memory_usage.return_value = str(memory_usage)
        mock_get_inactive_cache_usage.return_value = str(cache_usage)

        with self.assertRaises(SystemExit) as cm:
            memory_checker.check_memory_usage(container_name, container_id, threshold_value)

        self.assertEqual(cm.exception.code, 3)
<<<<<<< HEAD
        mock_get_memory_usage.assert_called_once_with(container_id, container_name)
=======
        mock_get_memory_usage.assert_called_once_with(container_id)
>>>>>>> 328533601 (NOS-15064: [memory_checker] Resolve container ID from the running-container snapshot to avoid transient lookup race (#8983))

if __name__ == '__main__':
    unittest.main()
