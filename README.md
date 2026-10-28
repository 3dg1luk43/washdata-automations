# WashData automation templates

Ready-made Home Assistant [blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/)
for [WashData](https://github.com/3dg1luk43/ha_washdata), the integration that watches washers, dryers
and dishwashers through a smart plug. They appear in the panel's **Automations** tab, which downloads
this library from GitHub: it only works with WashData's online features turned on.

Each template becomes a normal Home Assistant automation. WashData never switches anything itself;
the automation does.

| Template | For | What it does |
| --- | --- | --- |
| [End a long dryer anti-crease phase](automation/dryer_anti_crease_power_cut.yaml) | dryers, washer-dryers | Cuts the plug between two tumbles once the dryer keeps tumbling past the set minutes, then by default turns it back on. |
| [Turn something on while a cycle runs](automation/cycle_running_indicator.yaml) | all | A light, switch or helper on at the start, off at the end. |

Without WashData's panel, import one with
[My Home Assistant](https://my.home-assistant.io/redirect/blueprint_import/) and the file's GitHub URL.

Share your own: see [CONTRIBUTING](CONTRIBUTING.md).
