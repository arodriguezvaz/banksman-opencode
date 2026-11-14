"""banksman admin install-opencode: the plan, the files that it writes, and its removal."""

import json
import os
import stat
from pathlib import Path

from banksman import doctor, install, printed
from banksman.cli import main


def options(home, config_path, **changes):
    settings = {
        "home": home,
        "sdk": home / "sdk",
        "adb": "/bin/sh",
        "config_path": config_path,
    }
    settings.update(changes)
    return install.Options(**settings)


def test_a_plan_writes_nothing(tmp_path, config_path):
    result = install.plan(options(tmp_path, config_path))
    assert result.changes
    assert not (tmp_path / ".local").exists()
    assert not (tmp_path / ".gradle").exists()
    assert not config_path.exists()


def test_an_install_writes_the_files_of_this_banksman(tmp_path, config_path):
    result = install.plan(options(tmp_path, config_path))
    written = install.apply(result)
    assert len(written) == len(result.changes)
    shim = tmp_path / doctor.OPENCODE_SHIM
    assert shim.read_text() == printed.opencode_shim()
    assert stat.S_IMODE(shim.stat().st_mode) == 0o755
    wrapper = tmp_path / doctor.ADB_WRAPPER
    assert wrapper.read_text() == printed.adb_shim("/bin/sh")
    assert (tmp_path / doctor.GRADLE_GUARD_INIT).read_text() == printed.gradle_guard_init()
    assert (tmp_path / doctor.GRADLE_GUARD).read_text() == printed.gradle_guard()
    plugin = tmp_path / doctor.OPENCODE_PLUGIN_DIR
    assert (plugin / "index.ts").read_text() == printed.opencode_plugin()
    assert (plugin / "package.json").read_text() == printed.opencode_plugin_package()
    configuration = config_path.read_text()
    assert "[kinds.emulator]" in configuration
    assert '[android]' in configuration
    assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_a_second_install_changes_nothing(tmp_path, config_path):
    install.apply(install.plan(options(tmp_path, config_path)))
    again = install.plan(options(tmp_path, config_path))
    assert again.changes == []


def test_the_configuration_is_never_replaced(tmp_path, config_path):
    config_path.write_text("# mine\n")
    result = install.plan(options(tmp_path, config_path))
    action = next(each for each in result.actions if each.path == config_path)
    assert action.status == install.SKIP
    install.apply(result)
    assert config_path.read_text() == "# mine\n"


def test_an_explicit_overwrite_keeps_a_backup(tmp_path, config_path):
    config_path.write_text("# mine\n")
    result = install.plan(options(tmp_path, config_path, overwrite_config=True))
    action = next(each for each in result.actions if each.path == config_path)
    assert action.status == install.UPDATE
    install.apply(result)
    assert "[kinds.emulator]" in config_path.read_text()
    backups = list(tmp_path.glob("config.toml.bak-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "# mine\n"
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600


def test_uninstall_removes_only_what_it_wrote(tmp_path, config_path):
    result = install.plan(options(tmp_path, config_path))
    install.apply(result)
    removed = install.uninstall(options(tmp_path, config_path))
    assert removed
    for path in (
        tmp_path / doctor.OPENCODE_SHIM,
        tmp_path / doctor.ADB_WRAPPER,
        tmp_path / doctor.GRADLE_GUARD_INIT,
        tmp_path / doctor.GRADLE_GUARD,
        tmp_path / doctor.OPENCODE_PLUGIN_DIR,
    ):
        assert not path.exists()
    assert config_path.exists()
    assert installed_plugin(tmp_path).exists() is False


def installed_plugin(home):
    return home / doctor.OPENCODE_PLUGIN_DIR / "index.ts"


def test_no_adb_and_no_gradle_write_their_parts_only(tmp_path, config_path):
    result = install.plan(options(tmp_path, config_path, adb_files=False, gradle=False))
    paths = {action.path for action in result.actions}
    assert tmp_path / doctor.OPENCODE_SHIM not in paths
    assert tmp_path / doctor.ADB_WRAPPER not in paths
    assert tmp_path / doctor.GRADLE_GUARD not in paths
    assert tmp_path / doctor.OPENCODE_PLUGIN_DIR / "index.ts" in paths


def test_write_config_adds_the_plugin_and_keeps_the_comments(tmp_path, config_path):
    document = tmp_path / doctor.OPENCODE_CONFIG_FILES[0]
    document.parent.mkdir(parents=True)
    document.write_text(
        '{\n  // my settings\n  "plugins": [\n    "other", // keep it\n  ],\n  "model": "x",\n}\n'
    )
    result = install.plan(options(tmp_path, config_path, write_config=True))
    install.apply(result)
    text = document.read_text()
    assert "// my settings" in text
    assert "// keep it" in text
    parsed = json.loads(install._strip_jsonc(text))
    assert parsed["plugins"] == [
        "other",
        str(tmp_path / doctor.OPENCODE_PLUGIN_DIR),
    ]
    assert parsed["model"] == "x"
    backups = list(document.parent.glob("opencode.jsonc.bak-*"))
    assert len(backups) == 1


def test_write_config_creates_the_document_when_there_is_none(tmp_path, config_path):
    document = tmp_path / doctor.OPENCODE_CONFIG_FILES[0]
    result = install.plan(options(tmp_path, config_path, write_config=True))
    install.apply(result)
    parsed = json.loads(install._strip_jsonc(document.read_text()))
    assert parsed["plugins"] == [str(tmp_path / doctor.OPENCODE_PLUGIN_DIR)]


def test_write_config_does_not_touch_a_document_that_it_cannot_read(tmp_path, config_path):
    document = tmp_path / doctor.OPENCODE_CONFIG_FILES[0]
    document.parent.mkdir(parents=True)
    document.write_text("this is not a document\n")
    result = install.plan(options(tmp_path, config_path, write_config=True))
    action = next((each for each in result.actions if each.path == document), None)
    assert action is None
    assert any("by hand" in advice for advice in result.advice)
    install.apply(result)
    assert document.read_text() == "this is not a document\n"


def test_write_config_does_not_add_a_listed_plugin_twice(tmp_path, config_path):
    document = tmp_path / doctor.OPENCODE_CONFIG_FILES[0]
    document.parent.mkdir(parents=True)
    document.write_text(
        '{\n  "plugins": [\n    {"package": "banksman-opencode"}\n  ]\n}\n'
    )
    result = install.plan(options(tmp_path, config_path, write_config=True))
    action = next((each for each in result.actions if each.path == document), None)
    assert action is None
    assert any("lists the plugin already" in note for note in result.notes)


def test_a_dry_run_of_the_command_writes_nothing(capsys, tmp_path, config_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(doctor, "home_directory", lambda: home)
    sdk = tmp_path / "sdk"
    adb = sdk / "platform-tools" / "adb"
    adb.parent.mkdir(parents=True)
    adb.write_text("#!/bin/sh\n")
    adb.chmod(0o755)
    status = main(
        ["admin", "install-opencode", "--dry-run", "--sdk", str(sdk), "--no-gradle"]
    )
    assert status == 0
    assert "would create" in capsys.readouterr().out
    assert not (home / doctor.OPENCODE_SHIM).exists()
    assert not config_path.exists()


def test_the_assets_travel_with_the_package():
    assert printed.opencode_shim().startswith("#!")
    assert "banksman-opencode" in printed.opencode_plugin()
    assert json.loads(printed.opencode_plugin_package())["name"] == doctor.OPENCODE_PLUGIN_NAME
    assert "[kinds.emulator]" in printed.opencode_config()
