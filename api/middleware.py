"""
Auth mezi Next.js a Python: sdílený secret v hlavičce, ne veřejný endpoint.
Viz master_plan.md sekce 5.3: "Python backend není přímo přístupný z internetu
(pouze přes Next.js proxy)". Tahle hlavička je DRUHÁ vrstva (defense in depth),
ne náhrada za síťovou izolaci — nasazení musí síťově zabránit přímému přístupu
k Python portu zvenčí, secret header sám o sobě to nezaručí.
"""

from fastapi import Header, HTTPException

from utils.config import settings


async def verify_internal_secret(x_internal_secret: str | None = Header(default=None)) -> None:
    if not settings.NEXT_JS_SECRET:
        if settings.ENVIRONMENT == "production":
            raise HTTPException(status_code=500, detail="NEXT_JS_SECRET není nastaven v produkci.")
        return  # dev bez secretu povoleno, ale hlasitě neověřeno — viz log níže

    if x_internal_secret != settings.NEXT_JS_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid internal secret.")
