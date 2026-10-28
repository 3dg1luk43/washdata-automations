# Sharing a template

One template per pull request, and a template is one file: `automation/<id>.yaml`, where `<id>` is
lowercase letters, digits and `_`. The quickest start is **Share your own template** at the bottom of
WashData's Automations tab: it opens GitHub's editor here with a starting file, and saving it opens the
pull request form. Every template is reviewed before it is merged, because templates switch real
devices.

Do not edit `catalog.json`, `library.json`, the README's list or `source_url`: they are generated after
the merge.

## What WashData shows

The tile's text is the first paragraph of the description. Comment lines above `blueprint:` set the
rest, all optional:

```yaml
# icon: plug
# device_types: [dryer, washer_dryer]
# tags: [anti-crease, smart plug]
blueprint:
  name: "WashData: end a long dryer anti-crease phase"
  description: >-
    One or two sentences: what it does and when.


    Needs WashData 0.5.9 or newer.
```

- `icon`: `plug`, `light`, `bell`, `dryer`, `washer`, `dishwasher`, `timer` or `power`.
- `device_types`: WashData device types (`washing_machine`, `dryer`, `washer_dryer`, `dishwasher`,
  `pump`, `generic`, `other`), or leave it out for all.
- `tags`: up to 3, lowercase.
- `Needs WashData <version> or newer.` in the description: the oldest WashData it works on.

## Rules

- `author:` set to your name or GitHub handle (shown in WashData).
- Short text: name up to 60 characters, description up to 400 with a first paragraph of up to 200.
  Put detail in the input descriptions.
- Input `washdata_device`: a device selector filtered to `integration: ha_washdata`. Trigger on
  WashData's triggers (`trigger: ha_washdata.<type>`, targeted at that input).
- Give every other input a default where one makes sense: the template then installs in one click.
- Say plainly what it switches or sends and what can go wrong; start that paragraph with `Risk:` and
  WashData highlights it. Never start a heating appliance's program. Restoring a plug's power is fine
  when the description says so and the user can limit it. Let a new cycle cancel anything still
  waiting.
- No `!include`, `!secret` or `!env_var`. No em dash characters.

## Checks

Every pull request runs the rules above (`python tools/library.py check`, which names each broken
rule) and installs each template on a real Home Assistant with WashData, through Home Assistant's own
blueprint and automation validation. The run's summary previews the tile. To run the rules locally:

```bash
pip install pyyaml
python tools/library.py check
```

The full check, from a `ha_washdata` clone:

```bash
cp ../washdata-automations/tests/test_templates.py tests/test_washdata_templates.py
WASHDATA_TEMPLATES=../washdata-automations pytest tests/test_washdata_templates.py
```
