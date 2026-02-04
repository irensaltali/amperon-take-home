"""Tests for database migration runner."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from yoyo import get_backend

from tomorrow.migrations import (
    MIGRATIONS_DIR,
    get_database_url,
    run_migrations,
    rollback_migrations,
)


class TestGetDatabaseUrl:
    """Tests for get_database_url function."""

    def test_default_values(self):
        """Should use default values when env vars not set."""
        with patch.dict(os.environ, {}, clear=True):
            url = get_database_url()
            assert url == "postgresql://postgres:postgres@localhost:5432/tomorrow"

    def test_custom_values(self):
        """Should use environment variables when set."""
        env_vars = {
            "PGHOST": "myhost",
            "PGPORT": "5433",
            "PGDATABASE": "mydb",
            "PGUSER": "myuser",
            "PGPASSWORD": "mypass",
        }
        with patch.dict(os.environ, env_vars):
            url = get_database_url()
            assert url == "postgresql://myuser:mypass@myhost:5433/mydb"

    def test_partial_env_vars(self):
        """Should mix env vars with defaults."""
        with patch.dict(os.environ, {"PGHOST": "customhost"}, clear=True):
            url = get_database_url()
            assert "customhost" in url
            assert "postgres:postgres" in url


class TestMigrationsDirectory:
    """Tests for migrations directory setup."""

    def test_migrations_dir_exists(self):
        """Migrations directory should exist."""
        assert MIGRATIONS_DIR.exists()
        assert MIGRATIONS_DIR.is_dir()

    def test_yoyo_ini_exists(self):
        """yoyo.ini configuration file should exist."""
        yoyo_ini = MIGRATIONS_DIR / "yoyo.ini"
        assert yoyo_ini.exists()

    def test_yoyo_ini_content(self):
        """yoyo.ini should have required sections."""
        yoyo_ini = MIGRATIONS_DIR / "yoyo.ini"
        content = yoyo_ini.read_text()

        assert "[DEFAULT]" in content
        assert "sources" in content
        assert "migration_table" in content


class TestRunMigrations:
    """Tests for run_migrations function."""

    @patch("tomorrow.migrations.get_backend")
    @patch("tomorrow.migrations.read_migrations")
    def test_no_pending_migrations(self, mock_read_migrations, mock_get_backend):
        """Should handle case with no pending migrations."""
        mock_backend = MagicMock()
        mock_backend.to_apply.return_value = []
        mock_get_backend.return_value = mock_backend

        mock_migrations = MagicMock()
        mock_read_migrations.return_value = mock_migrations

        # Should not raise
        run_migrations()

        mock_backend.lock.assert_called_once()
        mock_backend.to_apply.assert_called_once_with(mock_migrations)

    @patch("tomorrow.migrations.get_backend")
    @patch("tomorrow.migrations.read_migrations")
    def test_apply_pending_migrations(self, mock_read_migrations, mock_get_backend):
        """Should apply pending migrations."""
        mock_backend = MagicMock()

        mock_migration = MagicMock()
        mock_migration.id = "001_test_migration"

        mock_backend.to_apply.return_value = [mock_migration]
        mock_get_backend.return_value = mock_backend

        mock_migrations = MagicMock()
        mock_read_migrations.return_value = mock_migrations

        run_migrations()

        mock_backend.apply_migrations.assert_called_once_with([mock_migration])

    @patch("tomorrow.migrations.get_backend")
    @patch("tomorrow.migrations.read_migrations")
    def test_migration_failure_rollback(self, mock_read_migrations, mock_get_backend):
        """Should rollback on migration failure."""
        mock_backend = MagicMock()

        mock_migration = MagicMock()
        mock_migration.id = "001_test_migration"

        mock_backend.to_apply.return_value = [mock_migration]
        mock_backend.apply_migrations.side_effect = Exception("DB error")
        mock_get_backend.return_value = mock_backend

        mock_migrations = MagicMock()
        mock_read_migrations.return_value = mock_migrations

        with pytest.raises(SystemExit) as exc_info:
            run_migrations()

        assert exc_info.value.code == 1
        mock_backend.rollback_migrations.assert_called_once_with([mock_migration])


class TestRollbackMigrations:
    """Tests for rollback_migrations function."""

    @patch("tomorrow.migrations.get_backend")
    @patch("tomorrow.migrations.read_migrations")
    def test_rollback_single_migration(self, mock_read_migrations, mock_get_backend):
        """Should rollback specified number of migrations."""
        mock_backend = MagicMock()

        mock_migration = MagicMock()
        mock_migration.id = "001_test_migration"

        mock_backend.to_rollback.return_value = [mock_migration]
        mock_get_backend.return_value = mock_backend

        mock_migrations = MagicMock()
        mock_read_migrations.return_value = mock_migrations

        rollback_migrations(1)

        mock_backend.rollback_migrations.assert_called_once_with([mock_migration])

    @patch("tomorrow.migrations.get_backend")
    @patch("tomorrow.migrations.read_migrations")
    def test_no_migrations_to_rollback(self, mock_read_migrations, mock_get_backend):
        """Should handle case with no migrations to rollback."""
        mock_backend = MagicMock()
        mock_backend.to_rollback.return_value = []
        mock_get_backend.return_value = mock_backend

        mock_migrations = MagicMock()
        mock_read_migrations.return_value = mock_migrations

        # Should not raise
        rollback_migrations(1)

        mock_backend.rollback_migrations.assert_not_called()


@pytest.mark.integration
class TestMigrationsIntegration:
    """Integration tests requiring PostgreSQL."""

    def test_migration_files_have_sql_extension(self):
        """SQL migration files should have .sql extension."""
        for item in MIGRATIONS_DIR.iterdir():
            if item.is_file() and item.name[0].isdigit():
                # Numbered migration files should be .sql
                assert item.suffix == ".sql", f"Migration file must be .sql: {item}"
