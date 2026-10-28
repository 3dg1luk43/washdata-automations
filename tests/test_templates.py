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
"""Every template in the WashData automation library, on a real Home Assistant.

CI copies this file into a ha_washdata checkout's ``tests/`` (so its fixtures
and the autouse service-schema guard apply) and points ``WASHDATA_TEMPLATES``
at this repository. ``tools/library.py check`` holds the file rules; here every
template goes through Home Assistant's own loader and schemas, WashData's
trigger types and device types, WashData's library parser where the checkout
has it, an install through HA's real ``blueprint/save`` and the validation HA's
automation editor runs, against a real WashData device. The dryer anti-crease
template is also run end to end.

Run locally from a ha_washdata checkout:

    cp ../washdata-automations/tests/test_templates.py tests/test_washdata_templates.py
    WASHDATA_TEMPLATES=../washdata-automations pytest tests/test_washdata_templates.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from homeassistant.components.automation.config import (
    AUTOMATION_BLUEPRINT_SCHEMA,
    async_validate_config_item,
)
from homeassistant.components.blueprint.models import Blueprint
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util import yaml as yaml_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

import custom_components.ha_washdata as washdata  # (import before the loader: phcc ships its own custom_components)
from custom_components.ha_washdata.const import DEVICE_TRIGGER_TYPES, DEVICE_TYPES, DOMAIN

COMPONENT = Path(washdata.__file__).parent
ROOT = Path(os.environ.get("WASHDATA_TEMPLATES") or Path(__file__).resolve().parents[1])
BP_DIR = ROOT / "automation"


def _import_library():
    spec = importlib.util.spec_from_file_location("washdata_library", ROOT / "tools" / "library.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


library = _import_library()
TEMPLATES = {t.id: t for t in library.load_all(ROOT)}
BLUEPRINT_IDS = sorted(TEMPLATES)


def _load(bp_id: str) -> dict[str, Any]:
    return yaml_util.load_yaml_dict(BP_DIR / f"{bp_id}.yaml")


def _blueprint(bp_id: str) -> Blueprint:
    return Blueprint(
        _load(bp_id), path=f"{bp_id}.yaml", expected_domain="automation",
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )


def _manifest_version() -> tuple[int, ...]:
    raw = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))["version"]
    return tuple(int(x) for x in re.findall(r"\d+", raw)[:3])


# ─── The files ───────────────────────────────────────────────────────────────


def test_there_are_templates() -> None:
    assert BLUEPRINT_IDS


@pytest.mark.parametrize("bp_id", BLUEPRINT_IDS)
def test_template_passes_the_library_rules(bp_id: str) -> None:
    assert TEMPLATES[bp_id].check() == []


@pytest.mark.parametrize("bp_id", BLUEPRINT_IDS)
def test_blueprint_loads_with_home_assistant(bp_id: str) -> None:
    """HA's loader, its blueprint schema and the automation's own schema all accept it."""
    Blueprint(_load(bp_id), path=f"{bp_id}.yaml", expected_domain="automation", schema=BLUEPRINT_SCHEMA)
    bp = _blueprint(bp_id)
    assert bp.validate() is None  # no HA min_version above the one the tests run on
    assert bp.metadata["author"]


@pytest.mark.parametrize("bp_id", BLUEPRINT_IDS)
def test_triggers_and_device_types_are_washdatas(bp_id: str) -> None:
    template = TEMPLATES[bp_id]
    for trig in library.washdata_triggers(template.data):
        assert trig["trigger"].split(".", 1)[1] in set(DEVICE_TRIGGER_TYPES), (bp_id, trig["trigger"])
    types = template.device_types
    assert types == ["all"] or set(types) <= set(DEVICE_TYPES), (bp_id, types)
    if template.min_version:
        # The checkout CI picked is at least the version the template needs.
        assert tuple(int(x) for x in template.min_version.split(".")) <= _manifest_version()


def test_washdata_reads_each_template_whole() -> None:
    """WashData's own parser (the one the panel's list comes from) accepts each
    template and cuts nothing."""
    try:
        from custom_components.ha_washdata import blueprint_catalog  # pylint: disable=import-outside-toplevel
    except ImportError:
        pytest.skip("this WashData checkout has no template library")
    if not hasattr(blueprint_catalog, "async_fetch_library"):
        pytest.skip("this WashData checkout predates the downloaded library")
    version = ".".join(str(x) for x in _manifest_version())
    for bp_id, template in TEMPLATES.items():
        item = blueprint_catalog.describe(bp_id, template.text, template.catalog_entry(), version)
        bp = _blueprint(bp_id)
        assert item["name"] == bp.name
        assert item["description"] == bp.metadata["description"].strip()
        assert item["author"] == bp.metadata["author"]
        assert item["tags"] == template.tags
        assert item["icon"] == template.icon
        assert item["compatible"] is True
        assert [i["key"] for i in item["inputs"]] == list(bp.inputs)


# ─── Installed and used on a real Home Assistant ─────────────────────────────


async def _device_id(hass, entry) -> str:
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    return device.id


def _sample(selector: Any, device_id: str) -> Any:
    """A value an input with this selector accepts, for one with no default."""
    if not isinstance(selector, dict) or not selector:
        return None
    kind, spec = next(iter(selector.items()))
    spec = spec if isinstance(spec, dict) else {}
    multiple = bool(spec.get("multiple"))
    if kind == "entity":
        filters = spec.get("filter") or []
        filters = filters if isinstance(filters, list) else [filters]
        domain = next((f.get("domain") for f in filters if isinstance(f, dict) and f.get("domain")), "sensor")
        value = f"{domain[0] if isinstance(domain, list) else domain}.sample"
    elif kind == "device":
        value = device_id
    elif kind == "number":
        value = spec.get("min", 0)
    elif kind == "boolean":
        value = False
    elif kind in ("text", "template", "area", "floor", "label", "location"):
        value = "sample"
    elif kind == "select":
        options = spec.get("options") or [""]
        value = options[0]["value"] if isinstance(options[0], dict) else options[0]
    elif kind == "time":
        value = "08:00:00"
    elif kind == "duration":
        value = {"minutes": 1}
    elif kind == "target":
        value = {"entity_id": "light.sample"}
    elif kind == "action":
        value = []
    elif kind == "object":
        value = {}
    elif kind == "icon":
        value = "mdi:washing-machine"
    else:
        return None
    return [value] if multiple else value


def _instance(bp_id: str, device_id: str, **inputs: Any) -> dict[str, Any]:
    values = {"washdata_device": device_id, **inputs}
    for key, spec in library.iter_inputs(_load(bp_id)["blueprint"].get("input")):
        if key not in values and "default" not in spec:
            values[key] = _sample(spec.get("selector"), device_id)
    return {
        "id": f"t_{bp_id}",
        "alias": bp_id,
        "use_blueprint": {"path": f"ha_washdata/{bp_id}.yaml", "input": values},
    }


@pytest.mark.parametrize("bp_id", BLUEPRINT_IDS)
async def test_installed_blueprint_validates_as_an_automation(
    hass, setup_washdata_entry, hass_ws_client, tmp_path, bp_id: str
) -> None:
    """The panel's install path: HA's blueprint/save, then an automation with
    only the device filled in (and a sample value for any input with no default),
    through the validation HA's automation editor runs before it saves."""
    hass.config.config_dir = str(tmp_path)
    entry = await setup_washdata_entry("Dryer", device_type="dryer")
    assert await async_setup_component(hass, "automation", {})
    client = await hass_ws_client(hass)
    text = (BP_DIR / f"{bp_id}.yaml").read_text(encoding="utf-8")
    await client.send_json_auto_id({
        "type": "blueprint/save", "domain": "automation",
        "path": f"ha_washdata/{bp_id}", "yaml": text, "source_url": library.SOURCE_URL.format(bp_id),
    })
    res = await client.receive_json()
    assert res["success"], res
    assert (tmp_path / "blueprints" / "automation" / "ha_washdata" / f"{bp_id}.yaml").is_file()

    config = _instance(bp_id, await _device_id(hass, entry))
    validated = await async_validate_config_item(hass, config["id"], config)
    assert validated is not None
    assert validated.validation_status == "ok", validated.validation_error


# ─── The dryer anti-crease blueprint, run end to end ─────────────────────────

POWER = "sensor.dryer_power"
PLUG = "switch.dryer_plug"


async def _anti_crease(
    hass, setup_washdata_entry, tmp_path, *, plug_device=True,
    options: dict[str, Any] | None = None, **inputs: Any,
):
    """A dryer, its installed blueprint and one automation from it, every input
    but the waits left at its default. With ``plug_device`` the power sensor and
    the plug's switch share a device, as on a smart plug, so the blueprint finds
    the switch through ``trigger.switch_entity``."""
    hass.config.config_dir = str(tmp_path)
    folder = tmp_path / "blueprints" / "automation" / "ha_washdata"
    folder.mkdir(parents=True)
    shutil.copy(BP_DIR / "dryer_anti_crease_power_cut.yaml", folder)
    if plug_device:
        plug_entry = MockConfigEntry(domain="test")
        plug_entry.add_to_hass(hass)
        plug = dr.async_get(hass).async_get_or_create(
            config_entry_id=plug_entry.entry_id, identifiers={("test", "plug")},
        )
        ent_reg = er.async_get(hass)
        for domain, object_id in (("sensor", "dryer_power"), ("switch", "dryer_plug")):
            ent_reg.async_get_or_create(
                domain, "test", object_id, suggested_object_id=object_id,
                device_id=plug.id, config_entry=plug_entry,
            )
    entry = await setup_washdata_entry(
        "Dryer", device_type="dryer", power_sensor=POWER, options=options
    )
    hass.states.async_set(POWER, "0" if options else "3", {"unit_of_measurement": "W"})
    assert await async_setup_component(hass, "system_log", {})
    calls = {
        "off": async_mock_service(hass, "switch", "turn_off"),
        "on": async_mock_service(hass, "switch", "turn_on"),
    }
    done = []
    hass.bus.async_listen("wd_test_done", callback(lambda e: done.append(e.data)))
    values = {
        "wait_minutes": 1, "off_seconds": 2,
        "extra_actions": [{"event": "wd_test_done",
                           "event_data": {"on": "{{ switched_back_on }}"}}],
        **inputs,
    }
    config = _instance("dryer_anti_crease_power_cut", await _device_id(hass, entry), **values)
    assert await async_setup_component(hass, "automation", {"automation": [config]})
    await hass.async_block_till_done()
    assert hass.states.get("automation.dryer_anti_crease_power_cut").state == "on"
    return entry, calls, done


async def _settle() -> None:
    """Let the automation run to its next wait. Not async_block_till_done: that
    waits for the run itself, which is parked in a delay until time moves."""
    for _ in range(20):
        await asyncio.sleep(0)


async def _advance(hass, seconds: float) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await _settle()


async def _set_power(hass, watts: str) -> None:
    hass.states.async_set(POWER, watts, {"unit_of_measurement": "W"})
    await _settle()


async def _fire(hass, entry, trigger_type: str, **variables: Any) -> None:
    """Send a WashData trigger through the manager's own hook, so the trigger
    variables (power and switch entity) are the real ones."""
    hass.data[DOMAIN][entry.entry_id]._fire_device_trigger(  # noqa: SLF001
        trigger_type, None, **variables
    )
    await _settle()


# still_tumbling as the manager sends it for a tumble 30 min after the finish.
TUMBLE = {"minutes_since_finish": 30.0, "bursts": 4, "burst_seconds": 40,
          "_minutes": 30.0, "_prev_minutes": None}


async def _tumble(hass, entry, **overrides: Any) -> None:
    await _fire(hass, entry, "still_tumbling", **{**TUMBLE, **overrides})


async def test_anti_crease_cuts_and_restores_the_plug(hass, setup_washdata_entry, tmp_path) -> None:
    entry, calls, done = await _anti_crease(hass, setup_washdata_entry, tmp_path)
    await _set_power(hass, "180")  # the next tumble began before the run
    await _tumble(hass, entry)
    assert not calls["off"]  # waits for a low-power moment
    await _set_power(hass, "2.5")  # between two tumbles
    assert [c.data["entity_id"] for c in calls["off"]] == [[PLUG]]
    assert not calls["on"]
    await _advance(hass, 3)
    assert [c.data["entity_id"] for c in calls["on"]] == [[PLUG]]
    assert done == [{"on": True}]


async def test_anti_crease_reads_a_kw_sensor_as_watts(hass, setup_washdata_entry, tmp_path) -> None:
    """0.18 kW is a 180 W tumble, not 0.18 W under the 10 W threshold (#481)."""
    entry, calls, _done = await _anti_crease(hass, setup_washdata_entry, tmp_path)
    hass.states.async_set(POWER, "0.18", {"unit_of_measurement": "kW"})
    await _settle()
    await _tumble(hass, entry)
    assert not calls["off"]  # still tumbling at 180 W
    hass.states.async_set(POWER, "0.0025", {"unit_of_measurement": "kW"})
    await _settle()
    assert [c.data["entity_id"] for c in calls["off"]] == [[PLUG]]


async def test_anti_crease_waits_for_its_minutes(hass, setup_washdata_entry, tmp_path) -> None:
    """The wait is the trigger's option now: a tumble before it does nothing,
    the first one after it does."""
    entry, calls, done = await _anti_crease(
        hass, setup_washdata_entry, tmp_path, wait_minutes=20
    )
    await _tumble(hass, entry, _minutes=8.0, _prev_minutes=None, minutes_since_finish=8.0)
    await _advance(hass, 3)
    assert not calls["off"] and not done
    await _tumble(hass, entry, _minutes=21.0, _prev_minutes=8.0, minutes_since_finish=21.0)
    assert [c.data["entity_id"] for c in calls["off"]] == [[PLUG]]
    await _advance(hass, 3)
    assert done == [{"on": True}]


async def test_anti_crease_uses_the_chosen_switch(hass, setup_washdata_entry, tmp_path) -> None:
    entry, calls, done = await _anti_crease(
        hass, setup_washdata_entry, tmp_path, plug_device=False, plug_switch="switch.other_plug",
    )
    await _tumble(hass, entry)
    await _advance(hass, 3)
    assert [c.data["entity_id"] for c in calls["off"]] == [["switch.other_plug"]]
    assert [c.data["entity_id"] for c in calls["on"]] == [["switch.other_plug"]]
    assert done == [{"on": True}]


async def test_anti_crease_leaves_the_plug_off_when_nobody_is_home(
    hass, setup_washdata_entry, tmp_path
) -> None:
    hass.states.async_set("person.alex", "not_home")
    hass.states.async_set("person.sam", "work")
    entry, calls, done = await _anti_crease(
        hass, setup_washdata_entry, tmp_path, presence_entities=["person.alex", "person.sam"],
    )
    await _tumble(hass, entry)
    assert len(calls["off"]) == 1
    await _advance(hass, 3)
    assert not calls["on"]
    assert done == [{"on": False}]


async def test_anti_crease_is_cancelled_by_a_new_cycle(hass, setup_washdata_entry, tmp_path) -> None:
    entry, calls, done = await _anti_crease(hass, setup_washdata_entry, tmp_path)
    await _set_power(hass, "250")
    await _tumble(hass, entry)
    await _fire(hass, entry, "cycle_started")
    await _set_power(hass, "1")
    await _advance(hass, 16 * 60)
    assert not calls["off"] and not calls["on"] and not done


async def test_anti_crease_gives_up_when_the_power_never_drops(
    hass, setup_washdata_entry, tmp_path
) -> None:
    entry, calls, done = await _anti_crease(hass, setup_washdata_entry, tmp_path)
    await _set_power(hass, "250")
    await _tumble(hass, entry)
    await _advance(hass, 15 * 60 + 1)
    await _set_power(hass, "1")
    assert not calls["off"] and not done


async def test_anti_crease_without_a_plug_switch_logs_and_stops(
    hass, setup_washdata_entry, tmp_path, caplog
) -> None:
    entry, calls, done = await _anti_crease(hass, setup_washdata_entry, tmp_path, plug_device=False)
    await _tumble(hass, entry)
    assert not calls["off"] and not done
    assert "no plug switch found" in caplog.text


async def test_anti_crease_end_to_end_on_a_real_dryer(
    hass, setup_washdata_entry, tmp_path, freezer
) -> None:
    """The whole chain on WashData's real detector: a dryer cycle finishes, the
    drum keeps tumbling, and the first tumble past the wait cuts the plug once."""
    entry, calls, done = await _anti_crease(
        hass, setup_washdata_entry, tmp_path, wait_minutes=10, off_seconds=1,
        options=REAL_DRYER,
    )
    manager = hass.data[DOMAIN][entry.entry_id]
    await _feed(hass, freezer, 800, 900)
    await _feed(hass, freezer, 0, 300)
    assert manager.profile_store.get_past_cycles()[-1]["status"] == "completed"
    assert manager._tumble_tracker.armed  # noqa: SLF001
    # Two tumbles before the wait: nothing.
    for _ in range(2):
        await _feed(hass, freezer, 200, 40, step=20)
        await _feed(hass, freezer, 0, 120)
    assert not calls["off"]
    # Past 10 min: the next tumble ends in a cut, once. From here a run may be
    # parked in the blueprint's power-off delay, which only a moving clock ends.
    await _feed(hass, freezer, 0, 300)
    await _feed(hass, freezer, 200, 40, step=20, clock=True)
    await _feed(hass, freezer, 0, 180, clock=True)
    assert [c.data["entity_id"] for c in calls["off"]] == [[PLUG]]
    assert done == [{"on": True}]
    await _feed(hass, freezer, 200, 40, step=20, clock=True)
    await _feed(hass, freezer, 0, 180, clock=True)
    assert len(calls["off"]) == 1


# A dryer on WashData's real detector, its timing shortened like the testbox's.
REAL_DRYER = {
    "min_power": 5.0, "off_delay": 60, "min_off_gap": 60,
    "watchdog_interval": 30, "completion_min_seconds": 300,
}


async def _feed(
    hass, freezer, watts: float, seconds: int, step: int = 30, clock: bool = False
) -> None:
    """Report ``watts`` on the dryer's power sensor every ``step`` s for ``seconds``.

    ``clock``: settle by moving the clock a second at a time while waiting, so an
    automation run parked in a delay finishes instead of blocking the wait."""
    t = 0
    while t < seconds:
        freezer.tick(timedelta(seconds=step))
        hass.states.async_set(POWER, str(watts), {"unit_of_measurement": "W"}, force_update=True)
        async_fire_time_changed(hass, dt_util.utcnow())
        if clock:
            await _block_with_clock(hass, freezer)
        else:
            await hass.async_block_till_done()
        t += step


async def _block_with_clock(hass, freezer) -> None:
    # The loop clock is frozen too, so only zero sleeps; the short real pause
    # lets an executor job (the cycle-end match) finish between two looks.
    waiter = asyncio.ensure_future(hass.async_block_till_done())
    for attempt in range(200):
        await asyncio.sleep(0)
        if waiter.done():
            break
        time.sleep(0.001)
        if attempt % 10 == 9:
            freezer.tick(timedelta(seconds=1))
            async_fire_time_changed(hass, dt_util.utcnow())
    await waiter
