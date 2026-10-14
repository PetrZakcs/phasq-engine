"""
Auth mezi Next.js a Python: sdílený secret v hlavičce, ne veřejný endpoint.
Viz master_plan.md sekce 5.3: "Python backend není přímo přístupný z internetu
(pouze přes Next.js proxy)". Tahle hlavička je DRUHÁ vrstva (defense in depth),
ne náhrada za síťovou izolaci — nasazení musí síťově zabránit přímému přístupu
k Python portu zvenčí, secret header sám o sobě to nezaručí.

Fail-closed (audit 2026-10-14): dřív stačilo nenastavit NEXT_JS_SECRET a
mít ENVIRONMENT jiné než "production" (default je "development") a API
bylo úplně bez autentizace - jedno zapomenuté nastavení při nasazení ho
otevřelo celé. Teď bez secretu vše vrací 503, výjimka jen s explicitním
ENGINE_ALLOW_NO_AUTH=1 a zároveň ENVIRONMENT=development.
"""

import hmac

from fastapi import Header, HTTPException

from utils.config import settings


async def verify_internal_secret(x_internal_secret: str | None = Header(default=None)) -> None:
    if not settings.NEXT_JS_SECRET:
        if settings.ENGINE_ALLOW_NO_AUTH and settings.ENVIRONMENT == "development":
            return
        raise HTTPException(status_code=503, detail="Engine není nakonfigurován (chybí NEXT_JS_SECRET).")

    # compare_digest: porovnání v konstantním čase (žádný timing side-channel)
    if x_internal_secret is None or not hmac.compare_digest(
        x_internal_secret.encode("utf-8"), settings.NEXT_JS_SECRET.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Unauthorized: invalid internal secret.")
