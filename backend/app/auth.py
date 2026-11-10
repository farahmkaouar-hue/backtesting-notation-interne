import base64, hashlib, hmac, json, os, time
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .storage import get_user, verify_password

bearer = HTTPBearer()


TOKEN_ISSUER = "backtesting-internal"
TOKEN_AUDIENCE = "backtesting-ui"


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret() -> bytes:
    secret = os.getenv("BACKTESTING_SECRET")
    if secret:
        return secret.encode()
    raise RuntimeError("Configuration invalide: BACKTESTING_SECRET est obligatoire.")

def token(username, role):
    header = _b64encode(json.dumps({"typ": "JWT", "alg": "HS256"}, separators=(",", ":")).encode())
    claims = _b64encode(json.dumps({
        "iss": TOKEN_ISSUER, "aud": TOKEN_AUDIENCE, "sub": username, "role": role,
        "iat": int(time.time()), "exp": int(time.time() + 3600 * 8),
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}"
    signature = _b64encode(hmac.new(_secret(), signing_input.encode(), hashlib.sha256).digest())
    return f"{signing_input}.{signature}"

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    try:
        secret = _secret()
    except RuntimeError as error:
        raise HTTPException(500, str(error))
    try:
        header, payload, signature = credentials.credentials.split(".")
        parsed_header = json.loads(_b64decode(header))
        if parsed_header != {"typ": "JWT", "alg": "HS256"}:
            raise ValueError()
        expected = _b64encode(hmac.new(secret, f"{header}.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        data = json.loads(_b64decode(payload))
        if data["exp"] < time.time() or data.get("iss") != TOKEN_ISSUER or data.get("aud") != TOKEN_AUDIENCE:
            raise ValueError()
        return data
    except (ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, "Jeton invalide ou expiré")

def login(username, password):
    user = get_user(username)
    if not user or not verify_password(password, user["password_hash"]): raise HTTPException(401, "Identifiants invalides")
    if user["status"] != "active":
        raise HTTPException(403, "Compte en attente de validation par un administrateur.")
    return token(user["username"], user["role"])

def require(*roles):
    def check(user=Depends(current_user)):
        if user["role"] not in roles: raise HTTPException(403, "Droit insuffisant")
        return user
    return check
