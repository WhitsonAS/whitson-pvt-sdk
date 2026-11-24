from html import escape
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Outcome = Literal["logged_in", "login_failed", "link_used", "other_login", "not_found"]

CONTENT_SECURITY_POLICY = "default-src 'none'; style-src 'unsafe-inline'"

READ_SCOPES = "read"

SCOPES_PATH = "/scopes"


class Page(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: int
    body: bytes


class ScopeForm(BaseModel):
    model_config = ConfigDict(frozen=True)

    nonce: str
    offered: tuple[str, ...] = Field(min_length=1)
    refused: bool


class _Text(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: int
    heading: str
    line: str


_TEXTS: dict[Outcome, _Text] = {
    "logged_in": _Text(
        status=200,
        heading="Logged in",
        line="You are logged in to whitsonPVT. You can close this window and return to the "
        "terminal.",
    ),
    "login_failed": _Text(
        status=400,
        heading="Login failed",
        line="The whitsonPVT login did not complete. Return to the terminal for details.",
    ),
    "link_used": _Text(
        status=400,
        heading="Link already used",
        line="This login link was already used. Return to the terminal.",
    ),
    "other_login": _Text(
        status=400,
        heading="Unexpected login",
        line="This is not the login this terminal is waiting for.",
    ),
    "not_found": _Text(
        status=404,
        heading="Not found",
        line="There is nothing at this address.",
    ),
}

_STYLE = """
:root{--bg:#f3f5f8;--card:#fff;--brand:#0b2f5b;--text:#47515e;--line:#dfe4ea;--ok:#1d7a4a;
--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#0e1621;--card:#16212f;--brand:#9cc1ec;
--text:#b7c2cf;--line:#26354a;--ok:#5cc28f;--bad:#f2867e}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
padding:16px;background:var(--bg);color:var(--text);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
main{width:100%;max-width:400px;padding:32px 24px;background:var(--card);
border:1px solid var(--line);border-radius:12px;text-align:center}
p{margin:0}
.brand{margin-bottom:28px;font-size:18px;font-weight:700;letter-spacing:.02em;color:var(--brand)}
.mark{display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;
margin-bottom:16px;border:2px solid currentColor;border-radius:50%;font-size:22px;font-weight:700}
.ok{color:var(--ok)}
.bad{color:var(--bad)}
h1{margin:0 0 8px;font-size:22px;line-height:1.3;color:var(--brand)}
form{margin-top:20px;text-align:left}
fieldset{margin:0 0 16px;padding:8px 12px;border:1px solid var(--line);border-radius:8px}
legend{padding:0 4px;font-weight:600;color:var(--brand)}
label{display:flex;gap:8px;align-items:center;padding:4px 0;overflow-wrap:anywhere}
button{width:100%;padding:10px;border:1px solid var(--brand);border-radius:8px;font:inherit;
font-weight:600;cursor:pointer;background:var(--brand);color:var(--card)}
button.plain{background:transparent;color:var(--brand)}
.notice{margin-top:12px;color:var(--bad);font-weight:600}
"""

_GROUPS = (("read", "Read"), ("run", "Calculations and other actions"), ("write", "Write"))


def login_page(view: Outcome | ScopeForm) -> Page:
    match view:
        case ScopeForm():
            return Page(status=400 if view.refused else 200, body=_scope_form(view))
        case str():
            text = _TEXTS[view]
            mark = (
                '<div class="mark ok" aria-hidden="true">&#10003;</div>'
                if text.status == 200
                else '<div class="mark bad" aria-hidden="true">!</div>'
            )
            return Page(
                status=text.status,
                body=_document(text.heading, f"{mark}<h1>{text.heading}</h1><p>{text.line}</p>"),
            )


def _scope_form(form: ScopeForm) -> bytes:
    nonce = f'<input type="hidden" name="n" value="{escape(form.nonce)}">'
    members = {group: [s for s in form.offered if _group(s) == group] for group, _ in _GROUPS}
    groups = "".join(
        f"<fieldset><legend>{legend}</legend>"
        f"{''.join(_checkbox(scope) for scope in members[group])}</fieldset>"
        for group, legend in _GROUPS
        if members[group]
    )
    read_only = (
        f'<form method="post" action="{SCOPES_PATH}">{nonce}'
        f'<input type="hidden" name="scope" value="{READ_SCOPES}">'
        '<button class="plain" type="submit">Read only</button></form>'
        if members["read"]
        else ""
    )
    notice = '<p class="notice">Choose at least one scope.</p>' if form.refused else ""
    return _document(
        "Choose access",
        "<h1>Choose access</h1><p>Sign in with only the scopes you keep checked. Your role can "
        f"still narrow what is granted.</p>{notice}"
        f'<form method="post" action="{SCOPES_PATH}">{nonce}{groups}'
        '<button type="submit">Continue to sign in</button></form>'
        f"{read_only}",
    )


def _checkbox(scope: str) -> str:
    name = escape(scope)
    return f'<label><input type="checkbox" name="scope" value="{name}" checked>{name}</label>'


def _group(scope: str) -> str:
    return next((group for group in ("read", "write") if scope.endswith(f":{group}")), "run")


def _document(title: str, content: str) -> bytes:
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>{title} - whitsonPVT</title><style>{_STYLE}</style>"
        f'<main><p class="brand">whitsonPVT</p>{content}</main></html>'
    ).encode()
