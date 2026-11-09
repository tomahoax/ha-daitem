"""What the integration does with a pydaitem error, decided by the error's `remedy`.

pydaitem tells what to do about each error, so the integration maps the remedies once here
instead of matching exception classes in every place that calls the library. A remedy added
by a later pydaitem release falls back to the generic message, as the library asks.
"""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError
from pydaitem import DaitemError, Remedy

from .const import DOMAIN

#: Translation key of the message shown for each remedy (`exceptions` in strings.json).
_KEY_BY_REMEDY = {
    Remedy.RETRY_LATER: "unreachable",
    Remedy.ASK_CREDENTIALS: "auth",
    Remedy.ASK_CODE: "bad_code",
    Remedy.NOT_PERMITTED: "not_permitted",
    Remedy.UNAVAILABLE: "transmitter_offline",
    Remedy.CHECK_STATE: "check_state",
    Remedy.FIX_CALL: "error",
}

#: Errors whose own `code` says more than their remedy: both are "retry later", but the user
#: can do something about a busy panel (close the app) and should know to wait on a limit.
_KEY_BY_CODE = {"session_busy": "session_busy", "rate_limited": "rate_limited"}


def needs_reauth(err: DaitemError) -> bool:
    """Whether only the user can fix it: a refused password or alarm code."""
    return err.remedy in (Remedy.ASK_CREDENTIALS, Remedy.ASK_CODE)


def command_error(err: DaitemError) -> HomeAssistantError:
    """The error to raise when a user action failed, translated, for the frontend."""
    key = _KEY_BY_CODE.get(err.code) or _KEY_BY_REMEDY.get(err.remedy, "error")
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=key,
        # The technical text only reaches the generic message, the others read without it.
        translation_placeholders={**err.placeholders, "error": str(err)},
    )
