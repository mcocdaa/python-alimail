"""Unofficial Python SDK & CLI for the Alibaba Mail (阿里邮箱) OpenAPI.

>>> from alimail import Client
>>> client = Client.from_env()
>>> client.users.list(size=10)["total"]
"""

from ._version import __version__
from .client import Client
from .config import DEFAULT_BASE, SG_BASE, Credentials, load_credentials
from .errors import (
    AlimailError,
    APIError,
    AuthError,
    ConfigError,
    NotFound,
    PermissionDenied,
    RateLimitError,
    ServerError,
    TransportError,
)
from .operations import Operation, all_operations, get_operation

__all__ = [
    "__version__",
    "Client",
    "Credentials",
    "DEFAULT_BASE",
    "SG_BASE",
    "load_credentials",
    "AlimailError",
    "APIError",
    "AuthError",
    "ConfigError",
    "NotFound",
    "PermissionDenied",
    "RateLimitError",
    "ServerError",
    "TransportError",
    "Operation",
    "all_operations",
    "get_operation",
]
