"""Storage-layer exceptions.

The concrete repository translates backend errors (e.g. ``sqlite3.Error``)
into these, so SQL details never leak upward past the storage boundary.
"""

from __future__ import annotations


class StorageError(Exception):
    """Base class for all storage-layer failures."""


class MigrationError(StorageError):
    """A schema migration failed or the migration set is inconsistent."""


class ConstraintViolation(StorageError):
    """The database rejected a write (e.g. a CHECK constraint fired)."""


class RowNotFound(StorageError):
    """A write targeted a row that does not exist."""
