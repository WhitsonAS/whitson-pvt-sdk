from typing import Literal

from pydantic import BaseModel, ConfigDict

Outcome = Literal["logged_in", "login_failed", "link_used", "other_login", "not_found"]

CONTENT_SECURITY_POLICY = "default-src 'none'; style-src 'unsafe-inline'"


class Page(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: int
    body: bytes


class _Text(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: int
    succeeded: bool
    heading: str
    line: str


_TEXTS: dict[Outcome, _Text] = {
    "logged_in": _Text(
        status=200,
        succeeded=True,
        heading="Logged in",
        line="You are logged in to whitsonPVT. You can close this window and return to the "
        "terminal.",
    ),
    "login_failed": _Text(
        status=400,
        succeeded=False,
        heading="Login failed",
        line="The whitsonPVT login did not complete. Return to the terminal for details.",
    ),
    "link_used": _Text(
        status=400,
        succeeded=False,
        heading="Link already used",
        line="This login link was already used. Return to the terminal.",
    ),
    "other_login": _Text(
        status=400,
        succeeded=False,
        heading="Unexpected login",
        line="This is not the login this terminal is waiting for.",
    ),
    "not_found": _Text(
        status=404,
        succeeded=False,
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
"""


def login_page(outcome: Outcome) -> Page:
    text = _TEXTS[outcome]
    mark = (
        '<div class="mark ok" aria-hidden="true">&#10003;</div>'
        if text.succeeded
        else '<div class="mark bad" aria-hidden="true">!</div>'
    )
    body = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>{text.heading} - whitsonPVT</title><style>{_STYLE}</style>"
        f'<main><p class="brand">whitsonPVT</p>{mark}<h1>{text.heading}</h1>'
        f"<p>{text.line}</p></main></html>"
    )
    return Page(status=text.status, body=body.encode())
