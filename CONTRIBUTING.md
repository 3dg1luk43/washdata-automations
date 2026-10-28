# Sharing a template

One template per pull request. The quickest start is **Share your own template** at the bottom of
WashData's Automations tab: it opens GitHub's editor here with a starting file, and saving it opens the
pull request form. Every template is reviewed before it is merged, because templates switch real
devices.

## What a PR contains

- `automation/<id>.yaml`: the blueprint. `<id>` is lowercase letters, digits and `_`.
- Its entry in `catalog.json`:

  ```json
  "my_template": {
    "device_types": ["dryer", "washer_dryer"],
    "min_version": "0.5.9",
    "tags": ["smart plug"],
    "icon": "plug"
  }
  ```

  `device_types`: WashData device types, or `["all"]`. `min_version`: the oldest WashData it works on.
  `tags`: up to 3, lowercase. `icon`: `plug`, `light`, `bell`, `dryer`, `washer`, `dishwasher`,
  `timer` or `power`.

## Rules

- `author:` set to your name or GitHub handle (shown in WashData).
- Short text: name up to 60 characters, description up to 400 with a first paragraph of up to 200
  (that paragraph is what the library tile shows). Put detail in the input descriptions.
- The description ends with `Needs WashData <min_version> or newer.`
- `source_url` is the file's own path on `main` in this repository.
- Input `washdata_device`: a device selector filtered to `integration: ha_washdata`. Trigger on
  WashData's triggers (`trigger: ha_washdata.<type>`, targeted at that input).
- Give every other input a default where one makes sense: the template then installs in one click.
- Say plainly what it switches or sends and what can go wrong; start that paragraph with `Risk:` and
  WashData highlights it. Never start a heating appliance's program. Restoring a plug's power is fine
  when the description says so and the user can limit it. Let a new cycle cancel anything still
  waiting.
- No `!include`, `!secret` or `!env_var`. No em dash characters.

## Checks

CI validates every template inside a WashData checkout: Home Assistant's own blueprint and automation
schemas, an install through `blueprint/save`, WashData's library parser, and the rules above. To run
it locally from a `ha_washdata` clone:

```bash
cp ../washdata-automations/tests/test_templates.py tests/test_washdata_templates.py
WASHDATA_TEMPLATES=../washdata-automations pytest tests/test_washdata_templates.py
```
