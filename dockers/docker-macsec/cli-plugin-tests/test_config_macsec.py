import sys

from unittest import mock
from click.testing import CliRunner
from click.shell_completion import ShellComplete

sys.path.append('../cli/config/plugins/')
import macsec


class _TestShellComplete(ShellComplete):
    name = 'test'
    source_template = ''


def _get_completions(cli, args, incomplete):
    comp = _TestShellComplete(cli, {}, cli.name or 'macsec', '_COMPLETE')
    return [c.value for c in comp.get_completions(args, incomplete)]


profile_name = "test"
primary_cak = "2363647040534355560e000802065d574d400e000e030307075f0e5050000e5541"
primary_ckn = "01234567890123456789012345678912"


class TestConfigMACsec(object):
    def test_plugin_registration(self):
        cli = mock.MagicMock()
        macsec.register(cli)
        cli.add_command.assert_called_once_with(macsec.macsec)

    def test_default_profile(self, mock_cfgdb):
        cfgdb = mock_cfgdb
        runner = CliRunner()
        result = runner.invoke(macsec.macsec,
                ["profile", "add", profile_name, "--primary_cak=" + primary_cak,"--primary_ckn=" + primary_ckn],
                obj=cfgdb)
        assert result.exit_code == 0
        profile_table = cfgdb.get_entry("MACSEC_PROFILE", profile_name)
        assert profile_table
        assert profile_table["priority"] == "255"
        assert profile_table["cipher_suite"] == "GCM-AES-128"
        assert profile_table["primary_cak"] == primary_cak
        assert profile_table["primary_ckn"] == primary_ckn
        assert profile_table["policy"] == "security"
        assert "enable_replay_protect" not in profile_table
        assert "replay_window" not in profile_table
        assert profile_table["send_sci"] == "true"
        assert "rekey_period" not in profile_table

        result = runner.invoke(macsec.macsec, ["profile", "del", profile_name], obj=cfgdb)
        assert result.exit_code == 0, "exit code: {}, Exception: {}, Traceback: {}".format(result.exit_code, result.exception, result.exc_info)
        profile_table = cfgdb.get_entry("MACSEC_PROFILE", profile_name)
        assert not profile_table

    def test_macsec_valid_profile(self, mock_cfgdb):
        cfgdb = mock_cfgdb
        runner = CliRunner()

        profile_name = "test"
        profile_map = {
            "primary_cak": "3946080a0407070303530256560a04504650530352565e731f1a5c4f524f4b5a5e547b79777c6663754b5e465253050d0d0503565a48470b0b030604020c520a54",
            "primary_ckn": "01234567890123456789012345678912",
            "priority": 64,
            "cipher_suite": "GCM-AES-XPN-256",
            "policy": "integrity_only",
            "enable_replay_protect": None,
            "replay_window": 100,
            "no_send_sci": None,
            "rekey_period": 30 * 60,
        }
        options = [profile_name]
        for k, v in profile_map.items():
            options.append("--" + k)
            if v is not None:
                options[-1] += "=" + str(v)

        result = runner.invoke(macsec.macsec, ["profile", "add"] + options, obj=cfgdb)
        assert result.exit_code == 0, "exit code: {}, Exception: {}, Traceback: {}".format(result.exit_code, result.exception, result.exc_info)
        profile_table = cfgdb.get_entry("MACSEC_PROFILE", profile_name)
        assert profile_table
        assert profile_table["priority"] == str(profile_map["priority"])
        assert profile_table["cipher_suite"] == profile_map["cipher_suite"]
        assert profile_table["primary_cak"] == profile_map["primary_cak"]
        assert profile_table["primary_ckn"] == profile_map["primary_ckn"]
        assert profile_table["policy"] == profile_map["policy"]
        if "enable_replay_protect" in profile_map:
            assert "enable_replay_protect" in profile_table and profile_table["enable_replay_protect"] == "true"
            assert profile_table["replay_window"] == str(profile_map["replay_window"])
        if "send_sci" in profile_map:
            assert profile_table["send_sci"] == "true"
        if "no_send_sci" in profile_map:
            assert profile_table["send_sci"] == "false"
        if "rekey_period" in profile_map:
            assert profile_table["rekey_period"] == str(profile_map["rekey_period"])

    def test_macsec_invalid_profile(self, mock_cfgdb):
        cfgdb = mock_cfgdb
        runner = CliRunner()

        # Loss primary cak and primary ckn
        result = runner.invoke(macsec.macsec, ["profile", "add", "test"], obj=cfgdb)
        assert result.exit_code != 0

        # Invalid primary cak
        result = runner.invoke(macsec.macsec, ["profile", "add", "test",
                "--primary_cak=abcdfghjk90123456789012345678912","--primary_ckn=01234567890123456789012345678912",
                "--cipher_suite=GCM-AES-128"], obj=cfgdb)
        assert result.exit_code != 0

        # Invalid primary cak length
        result = runner.invoke(macsec.macsec, ["profile", "add", "test",
                "--primary_cak=01234567890123456789012345678912","--primary_ckn=01234567890123456789012345678912",
                "--cipher_suite=GCM-AES-256"], obj=cfgdb)
        assert result.exit_code != 0


    def test_macsec_port(self, mock_cfgdb):
        cfgdb = mock_cfgdb
        runner = CliRunner()

        result = runner.invoke(macsec.macsec, ["profile", "add", "test",
                "--primary_cak=2363647040534355560e000802065d574d400e000e030307075f0e5050000e5541","--primary_ckn=01234567890123456789012345678912"],
                obj=cfgdb)
        assert result.exit_code == 0, "exit code: {}, Exception: {}, Traceback: {}".format(result.exit_code, result.exception, result.exc_info)
        result = runner.invoke(macsec.macsec, ["port", "add", "Ethernet0", "test"], obj=cfgdb)
        assert result.exit_code == 0, "exit code: {}, Exception: {}, Traceback: {}".format(result.exit_code, result.exception, result.exc_info)
        port_table = cfgdb.get_entry("PORT", "Ethernet0")
        assert port_table 
        assert port_table["macsec"] == "test"
        assert port_table["admin_status"] == "up"

        result = runner.invoke(macsec.macsec, ["profile", "del", "test"], obj=cfgdb)
        assert result.exit_code != 0

        result = runner.invoke(macsec.macsec, ["port", "del", "Ethernet0"], obj=cfgdb)
        assert result.exit_code == 0, "exit code: {}, Exception: {}, Traceback: {}".format(result.exit_code, result.exception, result.exc_info)
        port_table = cfgdb.get_entry("PORT", "Ethernet0")
        assert "macsec" not in port_table or not port_table["macsec"]
        assert port_table["admin_status"] == "up"

        # Test deleting on port without it enabled
        result = runner.invoke(macsec.macsec, ["port", "del", "Ethernet0"], obj=cfgdb)
        assert result.exit_code == 0, "exit code: {}, Exception: {}, Traceback: {}".format(result.exit_code, result.exception, result.exc_info)


    def test_macsec_invalid_operation(self, mock_cfgdb):
        cfgdb = mock_cfgdb
        runner = CliRunner()

        # Enable nonexisted profile 
        result = runner.invoke(macsec.macsec, ["port", "add", "Ethernet0", "test"], obj=cfgdb)
        assert result.exit_code != 0

        # Delete nonexisted profile
        result = runner.invoke(macsec.macsec, ["profile", "del", "test"], obj=cfgdb)
        assert result.exit_code != 0

        result = runner.invoke(macsec.macsec, ["profile", "add", "test", "--primary_cak=2363647040534355560e000802065d574d400e000e030307075f0e5050000e5541","--primary_ckn=01234567890123456789012345678912"], obj=cfgdb)
        assert result.exit_code == 0, "exit code: {}, Exception: {}, Traceback: {}".format(result.exit_code, result.exception, result.exc_info)
        # Repeat add profile
        result = runner.invoke(macsec.macsec, ["profile", "add", "test", "--primary_cak=2363647040534355560e000802065d574d400e000e030307075f0e5050000e5541","--primary_ckn=01234567890123456789012345678912"], obj=cfgdb)
        assert result.exit_code != 0


class TestMacsecGroupErrorMessage(object):
    """Invalid subcommands list available commands in the error message."""
    def test_invalid_subcommand_error_messages(self):
        runner = CliRunner()
        # 'add' is not a subcommand of 'config macsec'
        result = runner.invoke(macsec.macsec, ['add', 'profile'], obj=mock.Mock())
        assert result.exit_code != 0
        assert "No such command 'add'" in result.output
        assert 'port' in result.output
        assert 'profile' in result.output

        # 'remove' is not a subcommand of 'config macsec port'
        result = runner.invoke(macsec.macsec, ['port', 'remove'], obj=mock.Mock())
        assert result.exit_code != 0
        assert "No such command 'remove'" in result.output
        assert 'add' in result.output
        assert 'del' in result.output

        # 'remove' is not a subcommand of 'config macsec profile'
        result = runner.invoke(macsec.macsec, ['profile', 'remove'], obj=mock.Mock())
        assert result.exit_code != 0
        assert "No such command 'remove'" in result.output
        assert 'add' in result.output
        assert 'del' in result.output


class TestMacsecGroupCompletion(object):
    """Tab-completion stops suggesting subcommands after an invalid subcommand."""
    def test_tab_completions(self):
        # valid sequence of tokens + partial token
        tokens_written = [([], 'p'), ([], '')]
        for tokens, partial_token in tokens_written:
            completions = _get_completions(macsec.macsec, tokens, partial_token)
            assert 'port' in completions
            assert 'profile' in completions

        port_profile_completions = [(['port'], ''), (['profile'], '')]
        for tokens, partial_token in port_profile_completions:
            completions = _get_completions(macsec.macsec, tokens, partial_token)
            assert 'add' in completions
            assert 'del' in completions

        invalid_token_sequences = [
            (['add'], 'p'),             # macsec add p
            (['del', 'profile'], 'p'),  # macsec del profile p
            (['port', 'remove'], ''),   # macsec port remove 
        ]
        for tokens, partial_token in invalid_token_sequences:
            completions = _get_completions(macsec.macsec, tokens, partial_token)
            assert completions == []
