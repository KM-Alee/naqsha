"""DDL safelist enforcement for Dynamic Memory Engine.

Only CREATE TABLE, CREATE INDEX, and ALTER TABLE ADD COLUMN are permitted.
All other DDL operations raise ForbiddenDDLError.
"""

from __future__ import annotations

import re
from typing import Final

# Allowed DDL statement patterns (case-insensitive)
_ALLOWED_DDL_PATTERNS: Final[list[re.Pattern[str]]] = [
    re.compile(r"^\s*CREATE\s+TABLE\s+", re.IGNORECASE),
    re.compile(r"^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+", re.IGNORECASE),
    re.compile(r"^\s*ALTER\s+TABLE\s+\w+\s+ADD\s+COLUMN\s+", re.IGNORECASE),
]

# Forbidden DDL keywords that should never appear
_FORBIDDEN_KEYWORDS: Final[list[str]] = [
    "DROP",
    "DELETE",
    "UPDATE",
    "TRUNCATE",
    "INSERT",
    "REPLACE",
]


class ForbiddenDDLError(Exception):
    """Raised when DDL statement violates the safelist."""

    pass


def validate_ddl(sql: str) -> None:
    """Validate that SQL statement is an allowed DDL operation.

    Args:
        sql: SQL statement to validate

    Raises:
        ForbiddenDDLError: If the statement is not in the safelist
    """
    sql_stripped = sql.strip()

    if not sql_stripped:
        raise ForbiddenDDLError("Empty SQL statement")

    # Check for forbidden keywords first
    sql_upper = sql_stripped.upper()
    for keyword in _FORBIDDEN_KEYWORDS:
        if keyword in sql_upper:
            raise ForbiddenDDLError(
                f"Forbidden DDL keyword '{keyword}' detected. "
                f"Only CREATE TABLE, CREATE INDEX, and ALTER TABLE ADD COLUMN are permitted."
            )

    # Check if it matches any allowed pattern
    for pattern in _ALLOWED_DDL_PATTERNS:
        if pattern.match(sql_stripped):
            return

    # If we get here, it's not an allowed DDL statement
    raise ForbiddenDDLError(
        f"DDL statement not in safelist. "
        f"Only CREATE TABLE, CREATE INDEX, and ALTER TABLE ADD COLUMN are permitted. "
        f"Got: {sql_stripped[:100]}"
    )


def is_ddl_statement(sql: str) -> bool:
    """Check if SQL statement appears to be a DDL statement.

    Args:
        sql: SQL statement to check

    Returns:
        True if the statement looks like DDL (CREATE, ALTER, DROP, etc.)
    """
    sql_stripped = sql.strip().upper()
    ddl_keywords = ["CREATE", "ALTER", "DROP", "TRUNCATE"]
    return any(sql_stripped.startswith(keyword) for keyword in ddl_keywords)
