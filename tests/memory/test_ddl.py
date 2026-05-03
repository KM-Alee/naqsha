"""Tests for DDL safelist enforcement."""

import pytest

from naqsha.memory.ddl import ForbiddenDDLError, is_ddl_statement, validate_ddl


class TestDDLValidation:
    """Test DDL safelist validation."""

    def test_create_table_allowed(self):
        """CREATE TABLE is permitted."""
        sql = "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)"
        validate_ddl(sql)  # Should not raise

    def test_create_table_if_not_exists_allowed(self):
        """CREATE TABLE IF NOT EXISTS is permitted."""
        sql = "CREATE TABLE IF NOT EXISTS users (id INTEGER, name TEXT)"
        validate_ddl(sql)  # Should not raise

    def test_create_index_allowed(self):
        """CREATE INDEX is permitted."""
        sql = "CREATE INDEX idx_users_name ON users(name)"
        validate_ddl(sql)  # Should not raise

    def test_create_unique_index_allowed(self):
        """CREATE UNIQUE INDEX is permitted."""
        sql = "CREATE UNIQUE INDEX idx_users_email ON users(email)"
        validate_ddl(sql)  # Should not raise

    def test_alter_table_add_column_allowed(self):
        """ALTER TABLE ADD COLUMN is permitted."""
        sql = "ALTER TABLE users ADD COLUMN email TEXT"
        validate_ddl(sql)  # Should not raise

    def test_drop_table_forbidden(self):
        """DROP TABLE is forbidden."""
        sql = "DROP TABLE users"
        with pytest.raises(ForbiddenDDLError, match="Forbidden DDL keyword 'DROP'"):
            validate_ddl(sql)

    def test_drop_index_forbidden(self):
        """DROP INDEX is forbidden."""
        sql = "DROP INDEX idx_users_name"
        with pytest.raises(ForbiddenDDLError, match="Forbidden DDL keyword 'DROP'"):
            validate_ddl(sql)

    def test_delete_forbidden(self):
        """DELETE is forbidden."""
        sql = "DELETE FROM users WHERE id = 1"
        with pytest.raises(ForbiddenDDLError, match="Forbidden DDL keyword 'DELETE'"):
            validate_ddl(sql)

    def test_update_forbidden(self):
        """UPDATE is forbidden."""
        sql = "UPDATE users SET name = 'Alice' WHERE id = 1"
        with pytest.raises(ForbiddenDDLError, match="Forbidden DDL keyword 'UPDATE'"):
            validate_ddl(sql)

    def test_truncate_forbidden(self):
        """TRUNCATE is forbidden."""
        sql = "TRUNCATE TABLE users"
        with pytest.raises(ForbiddenDDLError, match="Forbidden DDL keyword 'TRUNCATE'"):
            validate_ddl(sql)

    def test_insert_forbidden(self):
        """INSERT is forbidden (not a DDL operation)."""
        sql = "INSERT INTO users (name) VALUES ('Alice')"
        with pytest.raises(ForbiddenDDLError, match="Forbidden DDL keyword 'INSERT'"):
            validate_ddl(sql)

    def test_select_not_ddl(self):
        """SELECT is not DDL and should be rejected."""
        sql = "SELECT * FROM users"
        with pytest.raises(ForbiddenDDLError, match="not in safelist"):
            validate_ddl(sql)

    def test_alter_table_drop_column_forbidden(self):
        """ALTER TABLE DROP COLUMN is forbidden."""
        sql = "ALTER TABLE users DROP COLUMN email"
        with pytest.raises(ForbiddenDDLError, match="Forbidden DDL keyword 'DROP'"):
            validate_ddl(sql)

    def test_empty_sql_forbidden(self):
        """Empty SQL is forbidden."""
        with pytest.raises(ForbiddenDDLError, match="Empty SQL statement"):
            validate_ddl("")

    def test_whitespace_only_forbidden(self):
        """Whitespace-only SQL is forbidden."""
        with pytest.raises(ForbiddenDDLError, match="Empty SQL statement"):
            validate_ddl("   \n\t  ")

    def test_case_insensitive_create_table(self):
        """DDL validation is case-insensitive."""
        sql = "create table users (id integer)"
        validate_ddl(sql)  # Should not raise

    def test_case_insensitive_forbidden(self):
        """Forbidden keywords are case-insensitive."""
        sql = "drop table users"
        with pytest.raises(ForbiddenDDLError, match="Forbidden DDL keyword 'DROP'"):
            validate_ddl(sql)


class TestIsDDLStatement:
    """Test DDL statement detection."""

    def test_create_is_ddl(self):
        """CREATE statements are DDL."""
        assert is_ddl_statement("CREATE TABLE users (id INTEGER)")
        assert is_ddl_statement("create index idx on users(id)")

    def test_alter_is_ddl(self):
        """ALTER statements are DDL."""
        assert is_ddl_statement("ALTER TABLE users ADD COLUMN email TEXT")

    def test_drop_is_ddl(self):
        """DROP statements are DDL."""
        assert is_ddl_statement("DROP TABLE users")

    def test_truncate_is_ddl(self):
        """TRUNCATE statements are DDL."""
        assert is_ddl_statement("TRUNCATE TABLE users")

    def test_select_not_ddl(self):
        """SELECT is not DDL."""
        assert not is_ddl_statement("SELECT * FROM users")

    def test_insert_not_ddl(self):
        """INSERT is not DDL."""
        assert not is_ddl_statement("INSERT INTO users VALUES (1, 'Alice')")

    def test_update_not_ddl(self):
        """UPDATE is not DDL."""
        assert not is_ddl_statement("UPDATE users SET name = 'Bob'")

    def test_delete_not_ddl(self):
        """DELETE is not DDL."""
        assert not is_ddl_statement("DELETE FROM users")

    def test_case_insensitive(self):
        """DDL detection is case-insensitive."""
        assert is_ddl_statement("create table users (id integer)")
        assert is_ddl_statement("CREATE TABLE users (id integer)")
        assert is_ddl_statement("CrEaTe TaBlE users (id integer)")
