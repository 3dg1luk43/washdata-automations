# WashData automation templates

Ready-made Home Assistant [blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/)
for [WashData](https://github.com/3dg1luk43/ha_washdata), the integration that watches washers, dryers
and dishwashers through a smart plug. They appear in the panel's **Automations** tab, which downloads
this library from GitHub: it only works with WashData's online features turned on.

Each template becomes a normal Home Assistant automation, and the automation does the switching:
you can see, edit and turn it off like any other.

<!-- templates:start -->
| Template | For | Author | What it does |
| --- | --- | --- | --- |
| [Turn something on while a cycle runs](automation/cycle_running_indicator.yaml) ([Import](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2F3dg1luk43%2Fwashdata-automations%2Fblob%2Fmain%2Fautomation%2Fcycle_running_indicator.yaml)) | all | WashData | Turns a light, switch or toggle helper on when a WashData cycle starts and off when it ends, also after a false start. |
| [End a long dryer anti-crease phase](automation/dryer_anti_crease_power_cut.yaml) ([Import](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2F3dg1luk43%2Fwashdata-automations%2Fblob%2Fmain%2Fautomation%2Fdryer_anti_crease_power_cut.yaml)) | dryers, washer-dryers | WashData | Ends the anti-crease tumbling some dryers keep up for hours: the set minutes after the program, it switches the plug off between two tumbles and, by default, back on. A new cycle cancels it. |
<!-- templates:end -->

**Import** opens [My Home Assistant](https://my.home-assistant.io/), for a Home Assistant without
WashData's panel or with its online features off.

Share your own: see [CONTRIBUTING](CONTRIBUTING.md). A template is one file; once a pull request is
merged, the Publish workflow generates `catalog.json` (what WashData downloads), `library.json` (what
the [WashData Store](https://3dg1luk43.github.io/washdata-store/templates.html) shows), the list above
and each file's `source_url` (`python tools/library.py build`). Do not edit those by hand.
