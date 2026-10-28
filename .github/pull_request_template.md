## What it does

<!-- One or two sentences: what it switches or sends, for which appliances, and why. -->

## Tested

<!-- Your Home Assistant and WashData versions, the appliance, and what happened when it ran. -->

- [ ] I ran it on my own Home Assistant through at least one real cycle

## Checklist

- [ ] One template: `automation/<id>.yaml` and its entry in `catalog.json`
- [ ] `author:` is my name or GitHub handle
- [ ] Short name and description (see [CONTRIBUTING](https://github.com/3dg1luk43/washdata-automations/blob/main/CONTRIBUTING.md#rules)); any risk in a `Risk:` paragraph
- [ ] `washdata_device` is a device selector filtered to `integration: ha_washdata`, triggers are WashData triggers
- [ ] A new cycle starting cancels anything still waiting
