"""Import every ORM model here so Base.metadata knows all tables.

Alembic's env.py imports this module; a model missing from this list is invisible to
`alembic revision --autogenerate`.
"""

from app.modules.auth.models import OAuthIdentity, RefreshSession
from app.modules.users.models import User

__all__ = ["OAuthIdentity", "RefreshSession", "User"]
