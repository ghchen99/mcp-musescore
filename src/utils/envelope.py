"""Unwrapping the plugin's reply envelope.

Every reply from the QML plugin is wrapped::

    {"status": "success", "result": <what the command returned>}

``status`` is transport-level; the command's own ``success``/``error`` lives
inside ``result``. Code that reaches for ``res["success"]`` on the outer dict
gets ``None`` and silently takes the failure path — which is how the navigation
tools' enrichment became dead code that looked perfectly correct.
"""

from typing import Any


def unwrap(res: Any) -> Any:
    """Return the command's own result, dropping the transport envelope.

    Tolerant of an already-unwrapped value, so it is safe to apply twice.
    """
    if isinstance(res, dict) and "status" in res and "result" in res:
        return res["result"]
    return res


def failed(res: Any) -> bool:
    """True when the reply is an error, at either level."""
    if not isinstance(res, dict):
        return True
    if res.get("status") == "error":
        return True
    inner = unwrap(res)
    if isinstance(inner, dict) and "error" in inner:
        return True
    return inner.get("success") is False if isinstance(inner, dict) else False


def error_text(res: Any) -> str:
    """Best-effort error message from either level."""
    if not isinstance(res, dict):
        return str(res)
    inner = unwrap(res)
    if isinstance(inner, dict) and inner.get("error"):
        return str(inner["error"])
    if res.get("message"):
        return str(res["message"])
    return "unknown error"
