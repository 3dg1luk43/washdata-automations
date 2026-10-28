# WashData - Home Assistant integration for appliance cycle monitoring via smart plugs.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
"""The library's own checks and generated files. Needs only PyYAML.

    python tools/library.py check          # every rule a template must pass
    python tools/library.py build          # catalog.json, library.json, the README list, source_url
    python tools/library.py build --check  # exit 1 if build would change a file
    python tools/library.py summary        # a Markdown preview of every tile
    python tools/library.py washdata-ref   # the ha_washdata branch CI validates against

A template is one file, ``automation/<id>.yaml``. What WashData shows beside
the blueprint comes from comment lines above ``blueprint:``::

    # icon: plug
    # device_types: [dryer, washer_dryer]
    # tags: [anti-crease, smart plug]

all three optional, and from a ``Needs WashData X.Y.Z or newer.`` line in the
description (optional too). Everything else is generated after a merge.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_DIR = ROOT / "automation"
CATALOG = ROOT / "catalog.json"
LIBRARY = ROOT / "library.json"
README = ROOT / "README.md"
REPO = "https://github.com/3dg1luk43/washdata-automations"
SOURCE_URL = REPO + "/blob/main/automation/{}.yaml"
RAW_URL = "https://raw.githubusercontent.com/3dg1luk43/washdata-automations/main/automation/{}.yaml"
IMPORT_URL = "https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url={}"
README_START = "<!-- templates:start -->"
README_END = "<!-- templates:end -->"

ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")
MIN_VERSION_RE = re.compile(r"Needs WashData (\d+\.\d+\.\d+) or newer\.")
HEADER_RE = re.compile(r"^#\s*(icon|device_types|tags)\s*:(.*)$")
# The icons WashData draws (blueprint_catalog.ICONS); it shows its default for
# anything else.
ICONS = ("plug", "light", "bell", "dryer", "washer", "dishwasher", "timer", "power")
DEVICE_INPUT = "washdata_device"
TRIGGER_PREFIX = "ha_washdata."

# Short enough to read at a glance in WashData's library. WashData cuts at
# larger limits of its own, so a template that passes here is shown whole.
NAME_MAX = 60
DESCRIPTION_MAX = 400
FIRST_PARAGRAPH_MAX = 200
AUTHOR_MAX = 40
TAGS_MAX = 3
TAG_MAX = 20
DEVICE_TYPES_MAX = 7
INPUT_NAME_MAX = 50
INPUT_DESCRIPTION_MAX = 200
FILE_MAX_BYTES = 16 * 1024
FIRST_VERSION = (0, 5, 9)  # the first WashData with triggers
DEVICE_LABELS = {
    "all": "all", "washing_machine": "washers", "dryer": "dryers",
    "washer_dryer": "washer-dryers", "dishwasher": "dishwashers", "pump": "pumps",
    "generic": "other appliances", "other": "threshold devices",
}


class Input(str):
    """A ``!input`` reference."""


class _Loader(yaml.SafeLoader):  # pylint: disable=too-many-ancestors
    """``!input`` and no other tag, as WashData parses a downloaded template."""


_Loader.add_constructor("!input", lambda loader, node: Input(loader.construct_scalar(node)))


class Template:
    """One ``automation/<id>.yaml``, parsed. ``errors`` lists every broken rule."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.id = path.stem
        self.text = path.read_text(encoding="utf-8")
        self.errors: list[str] = []
        self.data: dict[str, Any] = {}
        self.blueprint: dict[str, Any] = {}
        self.meta: dict[str, Any] = {}
        self._parse()

    # ── parsing ──────────────────────────────────────────────────────────────

    def _parse(self) -> None:
        if not ID_RE.match(self.id):
            self.errors.append("the file name must be lowercase letters, digits and _ (up to 64)")
        if len(self.text.encode("utf-8")) > FILE_MAX_BYTES:
            self.errors.append(f"the file is over {FILE_MAX_BYTES // 1024} KB")
        if "\u2014" in self.text:
            self.errors.append("no em dash characters")
        try:
            data = yaml.load(self.text, Loader=_Loader)  # noqa: S506 (a SafeLoader)
        except yaml.YAMLError as err:
            msg = str(err).splitlines()[0]
            if "could not determine a constructor" in str(err):
                msg = "only the !input tag is allowed (no !include, !secret or !env_var)"
            self.errors.append(f"not valid YAML: {msg}")
            return
        if not isinstance(data, dict) or not isinstance(data.get("blueprint"), dict):
            self.errors.append("the file must start with a blueprint: section")
            return
        self.data = data
        self.blueprint = data["blueprint"]
        self.meta = self._header()

    def _header(self) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        for line in self.text.splitlines():
            if not line.startswith("#"):
                if line.strip():
                    break
                continue
            match = HEADER_RE.match(line)
            if not match:
                continue
            key, raw = match.group(1), match.group(2).strip()
            try:
                value = yaml.safe_load(raw) if raw else None
            except yaml.YAMLError:
                self.errors.append(f"# {key}: is not readable, e.g. # {key}: {_example(key)}")
                continue
            meta[key] = value
        return meta

    # ── what WashData lists ──────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return str(self.blueprint.get("name") or "").strip()

    @property
    def description(self) -> str:
        return str(self.blueprint.get("description") or "").strip()

    @property
    def summary(self) -> str:
        return self.description.split("\n\n")[0].replace("\n", " ").strip()

    @property
    def display_name(self) -> str:
        """The name without the "WashData: " prefix, capitalised."""
        name = self.name.removeprefix("WashData: ")
        return name[:1].upper() + name[1:]

    @property
    def risk(self) -> str:
        """The description's paragraph that starts with "Risk:", if any."""
        for paragraph in self.description.split("\n\n"):
            paragraph = paragraph.replace("\n", " ").strip()
            if paragraph.startswith("Risk:"):
                return paragraph
        return ""

    @property
    def author(self) -> str:
        return str(self.blueprint.get("author") or "").strip()

    @property
    def min_version(self) -> str:
        match = MIN_VERSION_RE.search(self.description)
        return match.group(1) if match else ""

    @property
    def icon(self) -> str:
        return self.meta.get("icon") or ""

    @property
    def device_types(self) -> list[str]:
        return self.meta.get("device_types") or ["all"]

    @property
    def tags(self) -> list[str]:
        return self.meta.get("tags") or []

    def catalog_entry(self) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "device_types": self.device_types,
            "min_version": self.min_version,
            "tags": self.tags,
        }
        if self.icon:
            entry["icon"] = self.icon
        return entry

    # ── the rules ────────────────────────────────────────────────────────────

    def check(self) -> list[str]:
        """Every rule this template breaks, in plain words (empty: it passes)."""
        if not self.blueprint:
            return self.errors
        errors = list(self.errors)
        bp = self.blueprint
        if bp.get("domain") != "automation":
            errors.append("blueprint: domain must be automation")
        if not self.name:
            errors.append("blueprint: name is missing")
        elif len(self.name) > NAME_MAX:
            errors.append(f"the name is {len(self.name)} characters, up to {NAME_MAX}")
        if not self.description:
            errors.append("blueprint: description is missing")
        elif len(self.description) > DESCRIPTION_MAX:
            errors.append(f"the description is {len(self.description)} characters, up to {DESCRIPTION_MAX}")
        if len(self.description.split("\n\n")[0]) > FIRST_PARAGRAPH_MAX:
            errors.append(
                f"the description's first paragraph (the tile's text) is over {FIRST_PARAGRAPH_MAX} characters"
            )
        if not isinstance(bp.get("author"), str) or not self.author:
            errors.append("blueprint: author is missing (your name or GitHub handle)")
        elif len(self.author) > AUTHOR_MAX:
            errors.append(f"the author is over {AUTHOR_MAX} characters")
        if "Needs WashData" in self.description and not self.min_version:
            errors.append("write the version line as: Needs WashData 0.5.9 or newer.")
        if self.min_version and tuple(int(x) for x in self.min_version.split(".")) < FIRST_VERSION:
            errors.append("WashData triggers need WashData 0.5.9 or newer")
        errors += self._check_header()
        errors += self._check_inputs()
        errors += self._check_triggers()
        return errors

    def _check_header(self) -> list[str]:
        errors = []
        icon = self.meta.get("icon")
        if icon is not None and icon not in ICONS:
            errors.append(f"# icon: must be one of {', '.join(ICONS)}")
        for key, most, longest in (("device_types", DEVICE_TYPES_MAX, 20), ("tags", TAGS_MAX, TAG_MAX)):
            value = self.meta.get(key)
            if value is None or value == []:
                continue
            if (
                not isinstance(value, list) or not value or len(value) > most
                or not all(isinstance(v, str) and 0 < len(v) <= longest and v == v.lower() for v in value)
            ):
                errors.append(f"# {key}: up to {most} lowercase words, e.g. # {key}: {_example(key)}")
        types = self.meta.get("device_types")
        if isinstance(types, list) and "all" in types and len(types) > 1:
            errors.append("# device_types: is either [all] or a list of device types")
        return errors

    def _check_inputs(self) -> list[str]:
        errors = []
        inputs = dict(iter_inputs(self.blueprint.get("input")))
        device = inputs.get(DEVICE_INPUT)
        if device is None:
            errors.append(f"an input named {DEVICE_INPUT} (the WashData device) is missing")
        else:
            selector = (device.get("selector") or {}).get("device") or {}
            if selector.get("filter") != [{"integration": "ha_washdata"}]:
                errors.append(f"{DEVICE_INPUT} must be a device selector filtered to integration: ha_washdata")
            if "default" in device:
                errors.append(f"{DEVICE_INPUT} has no default: WashData fills it in")
        for key, spec in inputs.items():
            if len(str(spec.get("name") or key)) > INPUT_NAME_MAX:
                errors.append(f"input {key}: the name is over {INPUT_NAME_MAX} characters")
            if len(str(spec.get("description") or "")) > INPUT_DESCRIPTION_MAX:
                errors.append(f"input {key}: the description is over {INPUT_DESCRIPTION_MAX} characters")
        return errors

    def _check_triggers(self) -> list[str]:
        errors = []
        data = self.data
        if "triggers" not in data or "actions" not in data:
            errors.append("use Home Assistant's current keys: triggers: and actions:")
            return errors
        if "trigger" in data or "action" in data:
            errors.append("use triggers: and actions:, not trigger: and action:")
        for node in walk({"triggers": data["triggers"], "actions": data["actions"]}):
            if isinstance(node, dict) and ("platform" in node or "service" in node):
                errors.append("use trigger: and action: inside triggers and actions, not platform: or service:")
                break
        triggers = data["triggers"] if isinstance(data["triggers"], list) else [data["triggers"]]
        if not triggers:
            errors.append("there is no trigger")
        for trig in triggers:
            if not (isinstance(trig, dict) and str(trig.get("trigger", "")).startswith(TRIGGER_PREFIX)):
                errors.append("every trigger is a WashData trigger: trigger: ha_washdata.<type>")
                break
        for trig in washdata_triggers(data):
            target = trig.get("target")
            device_id = target.get("device_id") if isinstance(target, dict) else None
            if set(target or {}) != {"device_id"} or not isinstance(device_id, Input) or device_id != DEVICE_INPUT:
                errors.append(f"{trig['trigger']}: target it at device_id: !input {DEVICE_INPUT}")
            extra = set(trig) - {"trigger", "id", "target", "options"}
            if extra:
                errors.append(f"{trig['trigger']}: unknown keys {', '.join(sorted(extra))}")
        return errors


def _example(key: str) -> str:
    return {"icon": "plug", "device_types": "[dryer, washer_dryer]", "tags": "[smart plug]"}[key]


def iter_inputs(inputs: Any) -> list[tuple[str, dict[str, Any]]]:
    """A blueprint's inputs, sections flattened, in file order."""
    out: list[tuple[str, dict[str, Any]]] = []
    if not isinstance(inputs, dict):
        return out
    for key, value in inputs.items():
        if isinstance(value, dict) and isinstance(value.get("input"), dict):
            out.extend((str(k), v if isinstance(v, dict) else {}) for k, v in value["input"].items())
        else:
            out.append((str(key), value if isinstance(value, dict) else {}))
    return out


def walk(node: Any):
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk(value)


def washdata_triggers(node: Any) -> list[dict[str, Any]]:
    """Every WashData trigger in a template, the ones in wait_for_trigger too."""
    return [
        n for n in walk(node)
        if isinstance(n, dict) and str(n.get("trigger", "")).startswith(TRIGGER_PREFIX)
    ]


def load_all(root: Path = ROOT) -> list[Template]:
    return [Template(p) for p in sorted((root / "automation").glob("*.yaml"))]


# ── generated files ──────────────────────────────────────────────────────────


def with_source_url(text: str, bp_id: str) -> str:
    """The template with ``source_url`` set to its own file on main (HA keeps it
    with an imported blueprint, to update it from). Unchanged if that cannot be
    done safely."""
    url = SOURCE_URL.format(bp_id)
    line = re.compile(r"^([ \t]+source_url:).*$", re.MULTILINE)
    if line.search(text):
        fixed = line.sub(lambda m: f"{m.group(1)} {url}", text, count=1)
    else:
        fixed = re.sub(
            r"^([ \t]+)(domain:[ \t]*automation[ \t]*)$",
            lambda m: f"{m.group(1)}{m.group(2)}\n{m.group(1)}source_url: {url}",
            text, count=1, flags=re.MULTILINE,
        )
    try:
        data = yaml.load(fixed, Loader=_Loader)  # noqa: S506 (a SafeLoader)
        ok = data["blueprint"]["source_url"] == url
    except Exception:  # pylint: disable=broad-exception-caught
        ok = False
    return fixed if ok else text


def catalog_text(templates: list[Template]) -> str:
    """catalog.json: the templates WashData lists, newest file last."""
    return json.dumps({t.id: t.catalog_entry() for t in templates}, indent=2, ensure_ascii=False) + "\n"


def library_entry(t: Template) -> dict[str, Any]:
    """One template as a website shows it (the WashData Store reads library.json)."""
    url = SOURCE_URL.format(t.id)
    return {
        "id": t.id,
        "name": t.display_name,
        "description": t.description,
        "summary": t.summary,
        "risk": t.risk,
        "author": t.author,
        "device_types": t.device_types,
        "min_version": t.min_version,
        "tags": t.tags,
        "icon": t.icon,
        "inputs": [
            {
                "key": key,
                "name": str(spec.get("name") or key).strip(),
                "description": str(spec.get("description") or "").strip(),
                "required": "default" not in spec,
            }
            for key, spec in iter_inputs(t.blueprint.get("input"))
        ],
        "urls": {
            "file": url,
            "raw": RAW_URL.format(t.id),
            "import": IMPORT_URL.format(quote(url, safe="")),
        },
    }


def library_text(templates: list[Template]) -> str:
    """library.json: every listed template with its display text, for websites."""
    return json.dumps(
        {"templates": [library_entry(t) for t in templates]}, indent=2, ensure_ascii=False
    ) + "\n"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def readme_list(templates: list[Template]) -> str:
    rows = [
        "| Template | For | Author | What it does |",
        "| --- | --- | --- | --- |",
    ]
    for t in templates:
        url = SOURCE_URL.format(t.id)
        for_ = ", ".join(DEVICE_LABELS.get(d, d) for d in t.device_types)
        imp = f"[Import]({IMPORT_URL.format(quote(url, safe=''))})"
        rows.append(f"| [{_cell(t.display_name)}](automation/{t.id}.yaml) ({imp}) | {_cell(for_)} | {_cell(t.author)} | {_cell(t.summary)} |")
    if not templates:
        rows = ["No templates yet."]
    return "\n".join(rows)


def readme_text(current: str, templates: list[Template]) -> str:
    start, end = current.find(README_START), current.find(README_END)
    if start < 0 or end < start:
        raise SystemExit(f"README.md has lost its {README_START} / {README_END} markers")
    return current[: start + len(README_START)] + "\n" + readme_list(templates) + "\n" + current[end:]


def build(check_only: bool = False) -> int:
    """Write every generated file. Only templates that pass ``check`` are listed."""
    templates = load_all()
    good = [t for t in templates if not t.check()]
    for t in templates:
        if t not in good:
            print(f"::warning file=automation/{t.id}.yaml::left out of the library: {'; '.join(t.check())}")
    changed = []
    for t in good:
        fixed = with_source_url(t.text, t.id)
        if fixed != t.text:
            changed.append(t.path)
            if not check_only:
                t.path.write_text(fixed, encoding="utf-8")
    outputs = {
        CATALOG: catalog_text(good),
        LIBRARY: library_text(good),
        README: readme_text(README.read_text(encoding="utf-8"), good),
    }
    for path, text in outputs.items():
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            changed.append(path)
            if not check_only:
                path.write_text(text, encoding="utf-8")
    for path in changed:
        print(f"{'would update' if check_only else 'updated'} {path.relative_to(ROOT)}")
    return 1 if check_only and changed else 0


def check() -> int:
    templates = load_all()
    failed = 0
    names: dict[str, str] = {}
    for t in templates:
        errors = t.check()
        other = names.get(t.name.lower())
        if t.name and other:
            errors.append(f"{other}.yaml already has this name")
        names.setdefault(t.name.lower(), t.id)
        for err in errors:
            print(f"::error file=automation/{t.id}.yaml::{err}")
        failed += bool(errors)
    print(f"{len(templates) - failed} of {len(templates)} templates pass")
    return 1 if failed or not templates else 0


def summary() -> int:
    """What WashData's library will show, for the pull request's reviewer."""
    print("| | Template | Author | Tile text | For | Tags | Needs |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for t in load_all():
        mark = "✅" if not t.check() else "❌"
        print(
            f"| {mark} | {_cell(t.name)} | {_cell(t.author)} | {_cell(t.summary)} | "
            f"{', '.join(t.device_types)} | {', '.join(t.tags)} | {t.min_version or '-'} |"
        )
    return 0


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", text)[:3])


def washdata_ref() -> int:
    """The ha_washdata branch to validate against: main if its release is new
    enough for every template, else the release branch named after the newest
    version a template needs (e.g. 0.5.9) while that release is being prepared."""
    import subprocess  # pylint: disable=import-outside-toplevel
    import urllib.request  # pylint: disable=import-outside-toplevel

    need = max((_version(t.min_version) for t in load_all() if t.min_version), default=FIRST_VERSION)
    url = "https://raw.githubusercontent.com/3dg1luk43/ha_washdata/main/custom_components/ha_washdata/manifest.json"
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (a fixed https URL)
        released = _version(json.load(resp)["version"])
    if released >= need:
        print("main")
        return 0
    branch = ".".join(str(x) for x in need)
    found = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", "https://github.com/3dg1luk43/ha_washdata", branch],
        capture_output=True, check=False,
    )
    if found.returncode == 0:
        print(branch)
        return 0
    print(f"::error::a template needs WashData {branch}, which is neither released nor a branch yet", file=sys.stderr)
    return 1


def main(argv: list[str]) -> int:
    commands = {"check": check, "summary": summary, "washdata-ref": washdata_ref}
    if argv[:1] == ["build"]:
        return build(check_only="--check" in argv)
    if len(argv) != 1 or argv[0] not in commands:
        print(__doc__)
        return 2
    return commands[argv[0]]()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
