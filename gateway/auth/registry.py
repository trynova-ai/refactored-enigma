# gateway/auth/registry.py
import os

from .providers import ClerkProvider, LocalProvider

_provider_map = {
    "clerk": ClerkProvider(),
    "local": LocalProvider(),
    # "auth0": Auth0Provider(), etc…
}

def get_provider():
    return _provider_map[os.getenv("AUTH_PROVIDER", "local")]
