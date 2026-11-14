"""Install the OpenCode integration: the two adb wrappers, the Gradle guard, the configuration,
and the plugin, from the copies in this package.

Every file comes from `printed`, so the installer, `banksman admin doctor` and the tests compare
the same content. It writes a file only when its content differs, keeps a backup of a file that it
replaces, and never overwrites the configuration or the inventory.

The OpenCode plugin is a directory with two files. Writing it here instead of publishing it to
npm keeps the install in one tool, and the doctor detects a copy from another version.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import stat
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from banksman import android, printed
from banksman.config import Android, default_config_path
from banksman.doctor import (
    ADB_WRAPPER,
    GRADLE_GUARD,
    GRADLE_GUARD_INIT,
    OPENCODE_CONFIG_FILES,
    OPENCODE_PLUGIN_DIR,
    OPENCODE_PLUGIN_NAME,
    OPENCODE_SHIM,
)
from banksman.errors import BanksmanError

CREATE = "create"
UPDATE = "update"
SKIP = "skip"

# The mode of each file: the executables for everybody, the configuration for its owner only.
EXECUTABLE = 0o755
READABLE = 0o644
PRIVATE = 0o600
_BACKUP = ".bak-"


@dataclass(frozen=True)
class Options:
    """What to install, and where the pieces are."""

    home: Path
    sdk: Path | None = None
    avd_home: Path | None = None
    adb: str | None = None
    config_path: Path | None = None
    adb_files: bool = True
    gradle: bool = True
    plugin: bool = True
    config: bool = True
    overwrite_config: bool = False
    write_config: bool = False

    @property
    def settings(self) -> Android:
        return Android(sdk=self.sdk, avd_home=self.avd_home)

    def target(self, relative: Path) -> Path:
        return self.home / relative

    def configuration(self) -> Path:
        return default_config_path() if self.config_path is None else Path(self.config_path)


@dataclass(frozen=True)
class Action:
    path: Path
    status: str
    content: bytes | None = None
    mode: int = READABLE
    # Why the installer skips or replaces the file, in one sentence for the operator.
    reason: str | None = None


@dataclass
class Plan:
    options: Options
    actions: list[Action] = field(default_factory=list)
    # What the operator must do by hand, such as listing the plugin in opencode.jsonc.
    advice: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def changes(self) -> list[Action]:
        return [action for action in self.actions if action.status in (CREATE, UPDATE)]


def plan(options: Options) -> Plan:
    """Return what an install would do, without writing anything."""
    result = Plan(options)
    adb = _adb(options, result) if options.adb_files else None
    if options.adb_files and adb is not None:
        result.actions.append(
            _action(options.target(ADB_WRAPPER), printed.adb_shim(adb), EXECUTABLE)
        )
        result.actions.append(
            _action(options.target(OPENCODE_SHIM), printed.opencode_shim(), EXECUTABLE)
        )
        result.notes.append(f"the adb wrapper runs {adb}")
        if not _first_on_path(options.target(OPENCODE_SHIM).parent, adb):
            result.notes.append(
                f"{options.target(OPENCODE_SHIM).parent} is not before the Android SDK on the"
                " PATH of this shell: add it to ~/.profile or ~/.bashrc, before the SDK's"
                " platform-tools"
            )
    if options.gradle:
        result.actions += [
            _action(options.target(GRADLE_GUARD_INIT), _text(printed.gradle_guard_init())),
            _action(options.target(GRADLE_GUARD), _text(printed.gradle_guard())),
        ]
    if options.config:
        text = _config_text(options, result)
        existing = options.configuration()
        action = _action(existing, _text(text), PRIVATE)
        if action.status == UPDATE and not options.overwrite_config:
            action = Action(existing, SKIP, reason="the configuration exists; it is not replaced")
            result.advice.append(
                f"{existing} already exists: review it, for example [kinds.emulator] and"
                " [guard] strict"
            )
        result.actions.append(action)
    if options.plugin:
        directory = options.target(OPENCODE_PLUGIN_DIR)
        result.actions += [
            _action(directory / "index.ts", _text(printed.opencode_plugin())),
            _action(directory / "package.json", _text(printed.opencode_plugin_package())),
        ]
        _plugin_listing(options, result)
    return result


def apply(result: Plan) -> list[Action]:
    """Write the changes of a plan, and return the actions that changed a file."""
    written = []
    for action in result.changes:
        if action.content is None:
            continue
        _write(action.path, action.content, action.mode)
        written.append(action)
    return written


def uninstall(options: Options) -> list[Path]:
    """Remove the files that this installer writes, and return what it removed."""
    removed = []
    targets = [
        options.target(OPENCODE_SHIM),
        options.target(ADB_WRAPPER),
        options.target(GRADLE_GUARD_INIT),
        options.target(GRADLE_GUARD),
        options.target(OPENCODE_PLUGIN_DIR) / "index.ts",
        options.target(OPENCODE_PLUGIN_DIR) / "package.json",
    ]
    for path in targets:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        removed.append(path)
    directory = options.target(OPENCODE_PLUGIN_DIR)
    try:
        directory.rmdir()
    except OSError:
        pass
    return removed


def report(result: Plan, *, dry_run: bool) -> str:
    """Return the table of a plan, and the advice for the steps that a person must do."""
    lines = []
    width = max((len(str(action.path)) for action in result.actions), default=0)
    for action in result.actions:
        verb = f"would {action.status}" if dry_run else action.status
        reason = "" if action.reason is None else f"  ({action.reason})"
        lines.append(f"{verb:<12}  {str(action.path):<{width}}{reason}")
    if result.notes:
        lines.append("")
        lines += [f"note: {note}" for note in result.notes]
    if result.advice:
        lines.append("")
        lines += result.advice
    return "\n".join(lines)


def _action(path: Path, content: bytes | str, mode: int = READABLE) -> Action:
    data = content.encode("utf-8") if isinstance(content, str) else content
    if not os.path.lexists(path):
        return Action(path, CREATE, data, mode)
    current = _read(path)
    if current == data:
        return Action(path, SKIP, reason="it is what this banksman writes")
    return Action(path, UPDATE, data, mode, reason="it differs from what this banksman writes")


def _config_text(options: Options, result: Plan) -> str:
    """Return the example configuration, with the SDK that this machine uses."""
    text = printed.opencode_config()
    sdk = options.sdk
    if sdk is None:
        default = Path(android.sdk(Android()))
        if (default / "platform-tools" / "adb").is_file():
            sdk = default
        else:
            sdk = _sdk_from_environment()
    if sdk is None and options.config:
        result.notes.append(
            "cannot find the Android SDK: pass --sdk, or set sdk in the [android] table of the"
            " configuration"
        )
    if sdk is not None:
        text += f"\n[android]\nsdk = {_toml_path(sdk)}\n"
        if options.avd_home is not None:
            text += f"avd_home = {_toml_path(options.avd_home)}\n"
    return text


def _toml_path(path: Path) -> str:
    # A TOML basic string, for the paths of a Linux or macOS home directory.
    return json.dumps(str(Path(path).expanduser()))


def _sdk_from_environment() -> Path | None:
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(name)
        if value and (Path(value) / "platform-tools" / "adb").is_file():
            return Path(value)
    return None


def _adb(options: Options, result: Plan) -> str | None:
    """Return the adb that the wrapper runs, or None with a note when there is none."""
    if options.adb is not None:
        path = Path(options.adb).expanduser()
        if not path.is_file():
            raise BanksmanError(f"{path} does not exist")
        return str(path)
    candidate = Path(android.adb_path(options.settings))
    if candidate.is_file():
        return str(candidate)
    found = shutil.which("adb")
    if found is not None:
        resolved = Path(found).resolve()
        if resolved not in {
            options.target(OPENCODE_SHIM).resolve(),
            options.target(ADB_WRAPPER).resolve(),
        }:
            return found
    result.notes.append(
        "cannot find adb: pass --sdk, or save the wrapper after the SDK is installed"
    )
    return None


def _first_on_path(directory: Path, adb: str | None) -> bool:
    """Whether this directory comes before the directory of the SDK adb on the PATH."""
    entries = [Path(entry or ".") for entry in os.environ.get("PATH", "").split(os.pathsep)]
    wanted = _index(entries, directory)
    if wanted is None:
        return False
    if adb is None:
        return True
    sdk = _index(entries, Path(adb).parent)
    return sdk is None or wanted < sdk


def _index(entries: Sequence[Path], directory: Path) -> int | None:
    for index, entry in enumerate(entries):
        try:
            if entry.resolve() == directory.resolve():
                return index
        except OSError:
            continue
    return None


def _plugin_listing(options: Options, result: Plan) -> None:
    entry = str(options.target(OPENCODE_PLUGIN_DIR))
    snippet = f'"plugins": [{json.dumps(entry)}]'
    if not options.write_config:
        if _listed(options, entry):
            result.notes.append(f"the OpenCode configuration lists the plugin {entry}")
        else:
            result.notes.append(
                f"OpenCode discovers the plugin in {entry}; add {snippet} to opencode.jsonc to"
                " pin it explicitly"
            )
        result.advice.append(
            "deny `banksman admin` and absolute adb paths in the OpenCode permissions, as"
            " docs/install.md shows"
        )
        return
    path = _opencode_config(options)
    if _listed(options, entry):
        result.notes.append(f"{path} lists the plugin already")
        return
    try:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            merged = _merge_plugin(text, entry)
        else:
            merged = _new_config(entry)
    except OSError as exc:
        result.advice.append(f"cannot read {path}: {exc}; list the plugin by hand: {snippet}")
        return
    if merged is None:
        result.advice.append(f"cannot edit {path}; list the plugin by hand: {snippet}")
        return
    result.actions.append(_action(path, _text(merged)))
    result.notes.append(f"{path} gains the plugin in its plugins array (a backup is kept)")


def _opencode_config(options: Options) -> Path:
    for relative in OPENCODE_CONFIG_FILES:
        path = options.target(relative)
        if path.is_file():
            return path
    return options.target(OPENCODE_CONFIG_FILES[0])


def _listed(options: Options, entry: str) -> bool:
    """Whether an OpenCode configuration of the home directory lists the plugin already."""
    for relative in OPENCODE_CONFIG_FILES:
        path = options.target(relative)
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(_strip_jsonc(text))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        plugins = data.get("plugins") if isinstance(data, dict) else None
        for value in plugins if isinstance(plugins, list) else ():
            name = value.get("package") if isinstance(value, dict) else value
            if isinstance(name, str) and (
                name == entry
                or name == OPENCODE_PLUGIN_NAME
                or name.endswith("/" + OPENCODE_PLUGIN_NAME)
            ):
                return True
    return False


def _new_config(entry: str) -> str:
    return (
        "{\n"
        '  "$schema": "https://opencode.ai/config.json",\n'
        f'  "plugins": [{json.dumps(entry)}]\n'
        "}\n"
    )


def _merge_plugin(text: str, entry: str) -> str | None:
    """Insert the plugin into the plugins array of a JSONC document, or return None."""
    array = _plugins_array(text)
    if array is not None:
        start, end = array
        inner = text[start:end]
        last = _last_token_end(inner)
        comma = "," if last and inner[:last].rstrip()[-1:] not in ("", ",") else ""
        merged = (
            (text[: start + last] + comma + text[start + last : end]).rstrip()
            + "\n    "
            + json.dumps(entry)
            + "\n  "
            + text[end:]
        )
    else:
        brace = text.find("{")
        if brace < 0:
            return None
        merged = text[: brace + 1] + f'\n  "plugins": [{json.dumps(entry)}],' + text[brace + 1 :]
    try:
        json.loads(_strip_jsonc(merged))
    except ValueError:
        return None
    return merged


def _last_token_end(text: str) -> int:
    """Return the end of the last token of a JSONC document, without its comments."""
    i = 0
    last = 0
    while i < len(text):
        char = text[i]
        if char in " \t\r\n":
            i += 1
            continue
        if char == '"':
            i = _string_end(text, i)
            last = i
            continue
        if char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline
            continue
        if char == "/" and i + 1 < len(text) and text[i + 1] == "*":
            closing = text.find("*/", i + 2)
            i = len(text) if closing < 0 else closing + 2
            continue
        i += 1
        last = i
    return last


def _plugins_array(text: str) -> tuple[int, int] | None:
    """Return the content of the plugins array, between its brackets."""
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char == '"':
            end = _string_end(text, i)
            if text[i:end] == '"plugins"':
                k = _skip_blank(text, end)
                if k < length and text[k] == ":":
                    k = _skip_blank(text, k + 1)
                    if k < length and text[k] == "[":
                        close = _array_end(text, k)
                        if close is not None:
                            return k + 1, close
            i = end
            continue
        if char == "/" and i + 1 < length and text[i + 1] == "/":
            newline = text.find("\n", i)
            i = length if newline < 0 else newline + 1
            continue
        if char == "/" and i + 1 < length and text[i + 1] == "*":
            closing = text.find("*/", i + 2)
            i = length if closing < 0 else closing + 2
            continue
        i += 1
    return None


def _string_end(text: str, start: int) -> int:
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == '"':
            return i + 1
        i += 1
    return len(text)


def _array_end(text: str, start: int) -> int | None:
    depth = 0
    i = start
    while i < len(text):
        char = text[i]
        if char == '"':
            i = _string_end(text, i)
            continue
        if char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline + 1
            continue
        if char == "/" and i + 1 < len(text) and text[i + 1] == "*":
            closing = text.find("*/", i + 2)
            i = len(text) if closing < 0 else closing + 2
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _skip_blank(text: str, start: int) -> int:
    i = start
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def _strip_jsonc(text: str) -> str:
    """Remove comments and trailing commas, so that json can check the document."""
    out = []
    i = 0
    while i < len(text):
        char = text[i]
        if char == '"':
            end = _string_end(text, i)
            out.append(text[i:end])
            i = end
            continue
        if char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline
            continue
        if char == "/" and i + 1 < len(text) and text[i + 1] == "*":
            closing = text.find("*/", i + 2)
            i = len(text) if closing < 0 else closing + 2
            continue
        out.append(char)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _write(path: Path, content: bytes, mode: int) -> Path | None:
    """Write the content of a file in one step, and return the backup of an earlier file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if os.path.lexists(path):
        backup = _backup_path(path)
        shutil.copy2(path, backup)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    if backup is not None:
        # A backup is private: it can hold a configuration with paths of the user.
        with contextlib.suppress(OSError):
            os.chmod(backup, stat.S_IRUSR | stat.S_IWUSR)
    return backup


def _backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(path.name + _BACKUP + stamp)
    index = 1
    while os.path.lexists(candidate):
        candidate = path.with_name(path.name + _BACKUP + stamp + f"-{index}")
        index += 1
    return candidate


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""


def _text(text: str) -> bytes:
    return text.encode("utf-8")


def describe(options: Options) -> str:
    """Return the paths that this installer manages, for the report of an uninstall."""
    return "\n".join(
        str(options.target(path))
        for path in (
            OPENCODE_SHIM,
            ADB_WRAPPER,
            GRADLE_GUARD_INIT,
            GRADLE_GUARD,
            OPENCODE_PLUGIN_DIR / "index.ts",
            OPENCODE_PLUGIN_DIR / "package.json",
        )
    )
