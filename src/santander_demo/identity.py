"""JWT verificado; nenhuma autorização usa claims decodificadas sem assinatura."""

import hashlib
import time
from dataclasses import dataclass, field

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from santander_demo.contracts import DemoError


@dataclass(frozen=True)
class Identity:
    claims: dict = field(repr=False)

    def summary(self) -> dict:
        """Pseudônimos estáveis para evidências; não retorna bearer, nome ou email."""
        c = self.claims
        subject = f"{c.get('tid', '')}:{c.get('oid', '')}"
        return {
            "user_ref": hashlib.sha256(subject.encode()).hexdigest()[:12],
            "caller": c.get("azp", c.get("appid", "ausente")),
            "audience": c.get("aud"),
            "token_version": c.get("ver"),
            "delegated": bool(c.get("scp")),
        }


class JwtVerifier:
    def __init__(self, *, key, issuer: str, audience: str, tenant: str):
        self.key, self.issuer, self.audience, self.tenant = key, issuer, audience, tenant

    def verify(self, token: str) -> Identity:
        try:
            claims = jwt.decode(
                token,
                self.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["exp", "iat", "iss", "aud", "tid"]},
                leeway=0,
            )
            if claims["tid"] != self.tenant:
                raise DemoError("AUTH_TENANT")
            return Identity(claims)
        except jwt.InvalidTokenError:
            raise DemoError("AUTH_INVALID_TOKEN") from None


class LocalIssuer:
    """IdP efêmero de TESTE, só em memória. Nunca aceito pelo authorizer Entra."""

    issuer = "https://idp.local.invalid/tenant-demo/v2.0"
    tenant = "tenant-demo"
    audience = "api://santander-local"

    def __init__(self):
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.verifier = JwtVerifier(
            key=self._key.public_key(),
            issuer=self.issuer,
            audience=self.audience,
            tenant=self.tenant,
        )

    def token(self, user="riscos", caller="supervisor", **changes) -> str:
        now = int(time.time())
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "tid": self.tenant,
            "oid": {"riscos": "user-riscos", "ambos": "user-ambos", "sem_grant": "user-sem-grant"}[
                user
            ],
            "sub": f"local-{user}",
            "azp": caller,
            "ver": "2.0",
            "scp": "workshop.invoke",
            "iat": now,
            "exp": now + 600,
        }
        claims.update(changes)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self._key, algorithm="RS256")


def verify_entra(token: str, *, tenant: str, audience: str, version: str) -> Identity:
    """JWKS fixado no tenant; o token não escolhe URL, emissor ou algoritmo."""
    if version not in {"1.0", "2.0"}:
        raise ValueError("Versão Entra deve ser 1.0 ou 2.0")
    from uuid import UUID

    tenant = str(UUID(tenant))
    issuer = (
        f"https://sts.windows.net/{tenant}/"
        if version == "1.0"
        else f"https://login.microsoftonline.com/{tenant}/v2.0"
    )
    jwks = jwt.PyJWKClient(
        f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        timeout=15,
    )
    try:
        key = jwks.get_signing_key_from_jwt(token).key
        return JwtVerifier(key=key, issuer=issuer, audience=audience, tenant=tenant).verify(token)
    except jwt.PyJWTError:
        raise DemoError("AUTH_INVALID_TOKEN") from None
