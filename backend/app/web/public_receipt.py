"""`GET /r/{receiptNo}` - the public receipt check (build plan §11.6).

A judge scans the QR code on the phone with their own phone and this is what
they get: one page, server-rendered, **no JavaScript at all**, saying whether
the receipt verifies and what the four checks found.

No JavaScript is a security property, not minimalism. The page is reachable from
the open internet through the tunnel and renders data from the database, so the
CSP is `default-src 'none'` with only inline styles and `data:` images allowed -
which means even a stored-XSS payload in a lender name has nothing to execute
in. Everything is also HTML-escaped on the way out; the CSP is the second layer.

The page is deliberately minimal about *content* too (§11.3): without logging in
you learn that a loan was explained, in what language, and that the customer
passed the comprehension check. Not the amount, not who they are.
"""

from __future__ import annotations

import html
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.deps import DbDep, SettingsDep
from app.security.ratelimit import client_identity, limiter
from app.trust import verify as verify_module
from app.trust.ledger import by_number

log = logging.getLogger(__name__)

router = APIRouter(tags=["public"], include_in_schema=False)

# §11.6. `style-src 'unsafe-inline'` is needed because the stylesheet is inline
# (one request, works offline); there is no script-src at all, so 'unsafe-inline'
# here cannot be leveraged into script execution.
_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"

_HEADERS = {
    "Content-Security-Policy": _CSP,
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    # A receipt is immutable, but "immutable" would stop a revoked key being
    # noticed; five minutes is enough to survive a crowd scanning one QR code.
    "Cache-Control": "public, max-age=300",
}

_STYLES = """
*{box-sizing:border-box}
body{margin:0;background:#F3F4F6;color:#1C1C1E;
  font:16px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:560px;margin:0 auto;padding:24px 16px 48px}
.ribbon{background:#002E6E;color:#fff;font-size:12px;padding:8px 16px;text-align:center}
.card{background:#fff;border-radius:20px;padding:22px;margin-top:16px}
.verdict{display:flex;align-items:center;gap:12px}
.mark{width:44px;height:44px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:24px;font-weight:700;color:#fff;flex:0 0 auto}
.ok .mark{background:#12B76A}
.bad .mark{background:#D92D20}
.verdict h1{margin:0;font-size:20px}
.verdict p{margin:2px 0 0;font-size:13px;color:#6B7280}
dl{margin:18px 0 0;display:grid;grid-template-columns:auto 1fr;gap:8px 16px;font-size:14px}
dt{color:#6B7280}
dd{margin:0;font-weight:600;overflow-wrap:anywhere}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:#6B7280;
  margin:0 0 12px}
ul{list-style:none;margin:0;padding:0}
li{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid #F3F4F6;font-size:14px}
li:last-child{border-bottom:0}
.tick{font-weight:700;flex:0 0 auto}
.pass .tick{color:#12B76A}
.fail .tick{color:#D92D20}
.name{font-weight:600;display:block}
.detail{color:#6B7280;font-size:13px}
.hash{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
footer{margin-top:20px;font-size:11px;color:#6B7280;text-align:center;line-height:1.6}
"""


def _page(title: str, body: str) -> str:
    """Wrap a body in the shell. Everything interpolated is pre-escaped."""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='robots' content='noindex,nofollow'>"
        f"<title>{title}</title><style>{_STYLES}</style></head><body>"
        "<div class='ribbon'>Concept demo &middot; Paytm Build for India AI Hackathon "
        "&middot; not the live Paytm app</div>"
        f"<div class='wrap'>{body}</div></body></html>"
    )


def _escape(value: object) -> str:
    """HTML-escape anything, including the `None` a missing field leaves."""
    return html.escape(str(value if value is not None else ""), quote=True)


@router.get("/r/{receipt_no}", response_class=HTMLResponse)
def public_receipt(
    receipt_no: str, request: Request, db: DbDep, settings: SettingsDep
) -> HTMLResponse:
    """Render the receipt check page.

    404 is a rendered page rather than the JSON envelope: this URL is opened by
    a person in a browser, and `{"error": ...}` on screen is not an answer.
    """
    limiter.enforce("public", client_identity(request))

    receipt = by_number(db, receipt_no)
    if receipt is None:
        return HTMLResponse(
            _page(
                "Receipt not found - Spasht",
                "<div class='card bad'><div class='verdict'>"
                "<span class='mark'>?</span><div><h1>Receipt not found</h1>"
                "<p>No receipt with that number exists.</p></div></div></div>",
            ),
            status_code=404,
            headers=_HEADERS,
        )

    result = verify_module.verify(db, receipt, settings)
    payload = receipt.payload
    teachback = payload.get("teachback", [])
    passed = sum(1 for entry in teachback if entry.get("passed"))

    verdict_class = "ok" if result.valid else "bad"
    mark = "&check;" if result.valid else "&times;"
    headline = "Verified" if result.valid else "Not verified"
    subline = (
        "This receipt has not been altered since it was issued."
        if result.valid
        else "This receipt does not match what was signed."
    )

    checks_html = "".join(
        f"<li class='{'pass' if check.ok else 'fail'}'>"
        f"<span class='tick'>{'&check;' if check.ok else '&times;'}</span>"
        f"<span><span class='name'>{_escape(check.name.replace('_', ' ').title())}</span>"
        f"<span class='detail'>{_escape(check.detail)}</span></span></li>"
        for check in result.checks
    )

    body = (
        f"<div class='card {verdict_class}'><div class='verdict'>"
        f"<span class='mark'>{mark}</span><div><h1>{headline}</h1>"
        f"<p>{subline}</p></div></div>"
        "<dl>"
        f"<dt>Receipt</dt><dd>{_escape(receipt.receipt_no)}</dd>"
        f"<dt>Lender</dt><dd>{_escape(payload.get('lender'))}</dd>"
        f"<dt>Product</dt><dd>{_escape(str(payload.get('product', '')).replace('_', ' '))}</dd>"
        f"<dt>Language</dt><dd>{_escape(payload.get('language'))}</dd>"
        f"<dt>Understood</dt><dd>{passed} of {len(teachback)} questions</dd>"
        f"<dt>Issued</dt><dd>{_escape(receipt.created_at.strftime('%d %b %Y, %H:%M UTC'))}</dd>"
        f"<dt>Block</dt><dd>#{receipt.seq}</dd>"
        f"<dt>Hash</dt><dd class='hash'>{_escape(receipt.hash[:32])}&hellip;</dd>"
        "</dl></div>"
        f"<div class='card'><h2>The four checks</h2><ul>{checks_html}</ul></div>"
        "<footer>Spasht receipts are hash-chained and signed with Ed25519.<br>"
        "Synthetic data only. This page shows no personal details.</footer>"
    )

    return HTMLResponse(
        _page(f"Receipt {_escape(receipt.receipt_no)} - Spasht", body),
        headers=_HEADERS,
    )
