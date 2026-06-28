"""
Zenic CLI — Helpers de Plantillas
==================================

Funciones auxiliares para la generacion de templates de conectores,
incluyendo la conversion de nombres y la generacion de codigo
de autenticacion especifico para cada tipo de auth.
"""

from __future__ import annotations

# ── Tipos de autenticacion soportados ──────────────────────────

VALID_AUTH_TYPES: list[str] = [
    "api_key",
    "basic",
    "oauth2",
    "oauth1",
    "mtls",
    "custom",
    "none",
]

# ── Mapeo de tipo de auth a campos requeridos ──────────────────

AUTH_REQUIRED_FIELDS: dict[str, list[str]] = {
    "api_key": ["api_key"],
    "basic": ["username", "password"],
    "oauth2": ["client_id", "client_secret", "token_url"],
    "oauth1": ["consumer_key", "consumer_secret"],
    "mtls": ["cert_path", "key_path"],
    "custom": ["token"],
    "none": [],
}

# ── Mapeo de tipo de auth a campos opcionales ─────────────────

AUTH_OPTIONAL_FIELDS: dict[str, list[str]] = {
    "api_key": ["header_name", "query_name", "location"],
    "basic": [],
    "oauth2": [
        "authorize_url",
        "redirect_uri",
        "scopes",
        "access_token",
        "refresh_token",
    ],
    "oauth1": [
        "access_token",
        "access_token_secret",
        "request_token_url",
        "authorize_url",
        "access_token_url",
    ],
    "mtls": ["ca_path", "cert_password"],
    "custom": ["headers", "query_params", "token_prefix", "expires_at"],
    "none": [],
}

# ── Mapeo de tipo de auth a imports ─────────────────────────

AUTH_IMPORTS: dict[str, str] = {
    "api_key": "from src.sdk.auth import APIKeyAuth",
    "basic": "from src.sdk.auth import BasicAuth",
    "oauth2": "from src.sdk.auth import OAuth2Auth",
    "oauth1": "from src.sdk.auth import OAuth1Auth",
    "mtls": "from src.sdk.auth import MTLSAuth",
    "custom": "from src.sdk.auth import CustomAuth",
    "none": "",
}

# ── Mapeo de tipo de auth a setup code ─────────────────────

AUTH_SETUP_CODES: dict[str, str] = {
    "api_key": '''\
    # -- Configuracion de Autenticacion -------------------------
    _API_KEY: str = ""

    @property
    def auth_provider(self):
        """Proveedor de autenticacion API Key."""
        if self._API_KEY and not self._auth_provider:
            from src.sdk.auth import APIKeyAuth
            self._auth_provider = APIKeyAuth(
                api_key=self._API_KEY,
                header_name="X-API-Key",
                location="header",
            )
        return self._auth_provider''',
    "basic": '''\
    # -- Configuracion de Autenticacion -------------------------
    _USERNAME: str = ""
    _PASSWORD: str = ""

    @property
    def auth_provider(self):
        """Proveedor de autenticacion Basic Auth."""
        if self._USERNAME and self._PASSWORD and not self._auth_provider:
            from src.sdk.auth import BasicAuth
            self._auth_provider = BasicAuth(
                username=self._USERNAME,
                password=self._PASSWORD,
            )
        return self._auth_provider''',
    "oauth2": '''\
    # -- Configuracion de Autenticacion -------------------------
    _CLIENT_ID: str = ""
    _CLIENT_SECRET: str = ""
    _TOKEN_URL: str = ""

    @property
    def auth_provider(self):
        """Proveedor de autenticacion OAuth2."""
        if self._CLIENT_ID and not self._auth_provider:
            from src.sdk.auth import OAuth2Auth
            self._auth_provider = OAuth2Auth(
                client_id=self._CLIENT_ID,
                client_secret=self._CLIENT_SECRET,
                token_url=self._TOKEN_URL,
            )
        return self._auth_provider''',
    "oauth1": '''\
    # -- Configuracion de Autenticacion -------------------------
    _CONSUMER_KEY: str = ""
    _CONSUMER_SECRET: str = ""

    @property
    def auth_provider(self):
        """Proveedor de autenticacion OAuth1."""
        if self._CONSUMER_KEY and not self._auth_provider:
            from src.sdk.auth import OAuth1Auth
            self._auth_provider = OAuth1Auth(
                consumer_key=self._CONSUMER_KEY,
                consumer_secret=self._CONSUMER_SECRET,
            )
        return self._auth_provider''',
    "mtls": '''\
    # -- Configuracion de Autenticacion -------------------------
    _CERT_PATH: str = ""
    _KEY_PATH: str = ""

    @property
    def auth_provider(self):
        """Proveedor de autenticacion mTLS."""
        if self._CERT_PATH and self._KEY_PATH and not self._auth_provider:
            from src.sdk.auth import MTLSAuth
            self._auth_provider = MTLSAuth(
                cert_path=self._CERT_PATH,
                key_path=self._KEY_PATH,
            )
        return self._auth_provider''',
    "custom": '''\
    # -- Configuracion de Autenticacion -------------------------
    _TOKEN: str = ""

    @property
    def auth_provider(self):
        """Proveedor de autenticacion personalizada."""
        if self._TOKEN and not self._auth_provider:
            from src.sdk.auth import CustomAuth
            self._auth_provider = CustomAuth(
                token=self._TOKEN,
                token_prefix="Bearer",
            )
        return self._auth_provider''',
}

# ── Mapeo de tipo de auth a connect body ───────────────────

AUTH_CONNECT_BODIES: dict[str, str] = {
    "api_key": """\
        if not self._API_KEY:
            self._log_operation("connect", "Error: API key no configurada")
            return False
        if self.auth_provider and not self.auth_provider.validate():
            self._log_operation("connect", "Error: API key invalida")
            return False
        self._connected = True
        self._log_operation("connect", "Conexion exitosa (API Key)")
        return True""",
    "basic": """\
        if not self._USERNAME or not self._PASSWORD:
            self._log_operation("connect", "Error: credenciales Basic no configuradas")
            return False
        if self.auth_provider and not self.auth_provider.validate():
            self._log_operation("connect", "Error: credenciales Basic invalidas")
            return False
        self._connected = True
        self._log_operation("connect", "Conexion exitosa (Basic Auth)")
        return True""",
    "oauth2": """\
        if not self._CLIENT_ID or not self._CLIENT_SECRET:
            self._log_operation("connect", "Error: credenciales OAuth2 no configuradas")
            return False
        if self.auth_provider and not self.auth_provider.validate():
            self._log_operation("connect", "Error: credenciales OAuth2 invalidas")
            return False
        self._connected = True
        self._log_operation("connect", "Conexion exitosa (OAuth2)")
        return True""",
    "oauth1": """\
        if not self._CONSUMER_KEY or not self._CONSUMER_SECRET:
            self._log_operation("connect", "Error: credenciales OAuth1 no configuradas")
            return False
        if self.auth_provider and not self.auth_provider.validate():
            self._log_operation("connect", "Error: credenciales OAuth1 invalidas")
            return False
        self._connected = True
        self._log_operation("connect", "Conexion exitosa (OAuth1)")
        return True""",
    "mtls": """\
        if not self._CERT_PATH or not self._KEY_PATH:
            self._log_operation("connect", "Error: certificados mTLS no configurados")
            return False
        if self.auth_provider and not self.auth_provider.validate():
            self._log_operation("connect", "Error: certificados mTLS invalidos")
            return False
        self._connected = True
        self._log_operation("connect", "Conexion exitosa (mTLS)")
        return True""",
    "custom": """\
        if not self._TOKEN:
            self._log_operation("connect", "Error: token personalizado no configurado")
            return False
        if self.auth_provider and not self.auth_provider.validate():
            self._log_operation("connect", "Error: token personalizado invalido")
            return False
        self._connected = True
        self._log_operation("connect", "Conexion exitosa (Custom Auth)")
        return True""",
}

# ── Mapeo de tipo de auth a validate body ─────────────────

AUTH_VALIDATE_BODIES: dict[str, str] = {
    "none": """\
        # Sin requisitos de autenticacion
        return True""",
    "api_key": """\
        if not self._API_KEY:
            return False
        if self.auth_provider:
            return self.auth_provider.validate()
        return bool(self._API_KEY)""",
    "basic": """\
        if not self._USERNAME or not self._PASSWORD:
            return False
        if self.auth_provider:
            return self.auth_provider.validate()
        return bool(self._USERNAME and self._PASSWORD)""",
    "oauth2": """\
        if not self._CLIENT_ID or not self._CLIENT_SECRET or not self._TOKEN_URL:
            return False
        if self.auth_provider:
            return self.auth_provider.validate()
        return bool(self._CLIENT_ID and self._CLIENT_SECRET)""",
    "oauth1": """\
        if not self._CONSUMER_KEY or not self._CONSUMER_SECRET:
            return False
        if self.auth_provider:
            return self.auth_provider.validate()
        return bool(self._CONSUMER_KEY and self._CONSUMER_SECRET)""",
    "mtls": """\
        if not self._CERT_PATH or not self._KEY_PATH:
            return False
        if self.auth_provider:
            return self.auth_provider.validate()
        return True""",
    "custom": """\
        if not self._TOKEN:
            return False
        if self.auth_provider:
            return self.auth_provider.validate()
        return bool(self._TOKEN)""",
}


def to_class_name(name: str) -> str:
    """
    Convierte un nombre snake_case a CamelCase para nombres de clase.

    Args:
        name: Nombre en formato snake_case (ej: 'mi_conector')

    Retorna:
        Nombre en formato CamelCase (ej: 'MiConector')
    """
    return "".join(part.capitalize() for part in name.split("_"))
