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
"""tools/library.py: the rules, and the files it generates after a merge. PyYAML only."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("washdata_library", ROOT / "tools" / "library.py")
library = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = library
_spec.loader.exec_module(library)

GOOD = """# icon: plug
# device_types: [dryer]
# tags: [smart plug]
blueprint:
  name: "WashData: cut the plug"
  description: >-
    Cuts the plug.


    Needs WashData 0.5.9 or newer.
  domain: automation
  author: Alex
  input:
    washdata_device:
      name: Dryer
      selector:
        device:
          filter:
            - integration: ha_washdata
triggers:
  - trigger: ha_washdata.cycle_finished
    target:
      device_id: !input washdata_device
actions: []
"""


def _template(tmp_path: Path, text: str, bp_id: str = "cut_plug") -> library.Template:
    path = tmp_path / f"{bp_id}.yaml"
    path.write_text(text, encoding="utf-8")
    return library.Template(path)


def test_header_and_description_give_the_catalog_entry(tmp_path: Path) -> None:
    t = _template(tmp_path, GOOD)
    assert t.check() == []
    assert t.catalog_entry() == {
        "device_types": ["dryer"], "min_version": "0.5.9", "tags": ["smart plug"], "icon": "plug",
    }
    bare = _template(tmp_path, "\n".join(GOOD.splitlines()[3:]).replace("Needs WashData 0.5.9 or newer.", "Done."))
    assert bare.check() == []
    assert bare.catalog_entry() == {"device_types": ["all"], "min_version": "", "tags": []}


@pytest.mark.parametrize(("change", "message"), [
    (("author: Alex", "author: "), "author is missing"),
    (("Cuts the plug.", "word " * 50), "first paragraph"),
    (("# icon: plug", "# icon: skull"), "# icon: must be one of"),
    (("# tags: [smart plug]", "# tags: [Smart Plug]"), "# tags:"),
    (("# device_types: [dryer]", "# device_types: [all, dryer]"), "either [all]"),
    (("author: Alex", "author: !secret me"), "only the !input tag"),
    (("author: Alex", "author: !include x.yaml"), "only the !input tag"),
    (("washdata_device:", "device:"), "washdata_device"),
    (("- integration: ha_washdata", "- integration: zha"), "filtered to integration"),
    (("device_id: !input washdata_device", "device_id: washdata_device"), "target it at"),
    (("trigger: ha_washdata.cycle_finished", "trigger: state"), "every trigger is a WashData trigger"),
    (("triggers:", "trigger:"), "triggers: and actions:"),
    (("Needs WashData 0.5.9 or newer.", "Needs WashData 0.5.8 or newer."), "0.5.9 or newer"),
    (("Needs WashData 0.5.9 or newer.", "Needs WashData v1 or newer."), "version line"),
    (("Cuts the plug.", "Cuts \u2014 the plug."), "em dash"),
])
def test_a_broken_rule_is_named(tmp_path: Path, change: tuple[str, str], message: str) -> None:
    errors = _template(tmp_path, GOOD.replace(*change)).check()
    assert any(message in e for e in errors), errors


def test_a_bad_file_name_is_named(tmp_path: Path) -> None:
    assert any("file name" in e for e in _template(tmp_path, GOOD, "Cut-Plug").check())


def test_the_risk_paragraph_is_found(tmp_path: Path) -> None:
    text = GOOD.replace("Cuts the plug.", "Cuts the plug.\n\n\n    Risk: it switches a\n    relay.")
    t = _template(tmp_path, text)
    assert t.check() == []
    assert t.risk == "Risk: it switches a relay."
    assert library.library_entry(t)["inputs"][0]["required"] is True


def test_source_url_is_set_or_corrected() -> None:
    url = library.SOURCE_URL.format("cut_plug")
    added = library.with_source_url(GOOD, "cut_plug")
    assert f"  domain: automation\n  source_url: {url}\n" in added
    wrong = GOOD.replace("  author: Alex", "  author: Alex\n  source_url: https://example.com/x.yaml")
    assert library.with_source_url(wrong, "cut_plug") == wrong.replace("https://example.com/x.yaml", url)
    assert library.with_source_url(added, "cut_plug") == added
    four = GOOD.replace("\n  ", "\n    ")
    assert f"    domain: automation\n    source_url: {url}\n" in library.with_source_url(four, "cut_plug")


def test_build_writes_the_catalog_readme_and_source_urls(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "automation").mkdir()
    (tmp_path / "automation" / "cut_plug.yaml").write_text(GOOD, encoding="utf-8")
    (tmp_path / "automation" / "broken.yaml").write_text(GOOD.replace("author: Alex", "author: "), encoding="utf-8")
    shutil.copy(ROOT / "README.md", tmp_path / "README.md")
    for name in ("ROOT", "CATALOG", "LIBRARY", "README"):
        monkeypatch.setattr(library, name, tmp_path / getattr(library, name).relative_to(ROOT))
    monkeypatch.setattr(library, "load_all", lambda root=tmp_path: [
        library.Template(p) for p in sorted((tmp_path / "automation").glob("*.yaml"))
    ])
    assert library.build(check_only=True) == 1
    assert library.build() == 0
    assert json.loads((tmp_path / "catalog.json").read_text())  == {
        "cut_plug": {"device_types": ["dryer"], "min_version": "0.5.9", "tags": ["smart plug"], "icon": "plug"},
    }
    site = json.loads((tmp_path / "library.json").read_text())["templates"]
    assert [t["id"] for t in site] == ["cut_plug"]
    entry = site[0]
    assert entry["name"] == "Cut the plug"
    assert entry["summary"] == "Cuts the plug."
    assert entry["risk"] == ""
    assert entry["author"] == "Alex"
    assert entry["min_version"] == "0.5.9"
    assert entry["inputs"] == [{"key": "washdata_device", "name": "Dryer", "description": "", "required": True}]
    assert entry["urls"]["raw"].endswith("/main/automation/cut_plug.yaml")
    assert "blueprint_url=https%3A%2F%2Fgithub.com%2F" in entry["urls"]["import"]
    readme = (tmp_path / "README.md").read_text()
    assert "[Cut the plug](automation/cut_plug.yaml)" in readme
    assert "broken" not in readme
    assert library.SOURCE_URL.format("cut_plug") in (tmp_path / "automation" / "cut_plug.yaml").read_text()
    assert library.build(check_only=True) == 0
