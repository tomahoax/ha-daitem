# Contributing

Thanks for your interest. A few pointers before proposing a change.

## Scope of the two repositories

The project is deliberately split, as the Home Assistant architecture requires:

- [pydaitem](https://github.com/tomahoax/pydaitem) holds **all the API access code**
  (authentication, endpoints, models). Protocol fixes go there.
- **ha-daitem** (this repository) only adapts it to Home Assistant: entities, coordinator,
  config flow. No direct HTTP call belongs here.

## Environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_dev.txt
pre-commit install
```

To work on both repositories at once without going through PyPI:

```bash
pip install -e ../pydaitem
```

Careful: Home Assistant reinstalls the dependency if the installed version does not
satisfy the manifest pin, which would overwrite your editable install. Keep the versions
aligned.

## Before proposing a change

```bash
ruff check custom_components tests && ruff format custom_components tests
mypy custom_components
pytest
```

The same checks run in CI, plus `hassfest` and HACS validation.

## Tests

Tests must **never** call the live API or drive an alarm. The library is always replaced
by a double (see `tests/conftest.py`).

Any change to the config flow must stay covered: that is a Home Assistant quality scale
requirement.

## Constraints to keep in mind

Several behaviours are not preferences but measured constraints of the API. Please do not
"optimise" them without measurements to back it up:

- The panel accepts **one session at a time**, across all accounts, so we never hold a
  long-lived session.
- Shortening the polling interval would lock the user out of the mobile app.
- The API exposes no open/closed detector state. There is no point trying to create one.

## Reporting a bug

Include the Home Assistant version, the integration version and the `pydaitem` version,
with the relevant logs. **Strip any personal data**: tokens, serial numbers, address,
email addresses, alarm code.
