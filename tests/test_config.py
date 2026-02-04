"""Tests for configuration management."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from tomorrow.config import Settings, get_settings, reload_settings


class TestSettingsValidation:
    """Tests for settings validation."""
    
    def test_required_api_key(self):
        """Should require tomorrow_api_key."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(tomorrow_api_key="")
        assert "TOMORROW_API_KEY" in str(exc_info.value) or "cannot be empty" in str(exc_info.value)
    
    def test_required_pg_password(self):
        """Should require pg_password."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(tomorrow_api_key="test_key", pg_password="")
        assert "PGPASSWORD" in str(exc_info.value) or "cannot be empty" in str(exc_info.value)
    
    def test_valid_settings(self):
        """Should accept valid settings."""
        settings = Settings(
            tomorrow_api_key="test_api_key_123",
            pg_password="test_password"
        )
        assert settings.tomorrow_api_key == "test_api_key_123"
        assert settings.pg_password == "test_password"
    
    def test_api_key_stripped(self):
        """Should strip whitespace from API key."""
        settings = Settings(tomorrow_api_key="  test_key  ", pg_password="pass")
        assert settings.tomorrow_api_key == "test_key"


class TestDefaultValues:
    """Tests for default configuration values."""
    
    def test_default_database_settings(self):
        """Should have sensible database defaults."""
        settings = Settings(tomorrow_api_key="test", pg_password="test")
        
        assert settings.pg_host == "localhost"
        assert settings.pg_port == 5432
        assert settings.pg_database == "tomorrow"
        assert settings.pg_user == "postgres"
        assert settings.pg_pool_size == 5
        assert settings.pg_pool_timeout_seconds == 30
    
    def test_default_api_settings(self):
        """Should have sensible API defaults."""
        settings = Settings(tomorrow_api_key="test", pg_password="test")
        
        assert settings.tomorrow_api_base_url == "https://api.tomorrow.io/v4"
        assert settings.tomorrow_api_timeout_seconds == 30
        assert settings.tomorrow_api_max_retries == 5
        assert settings.tomorrow_api_retry_delay_seconds == 1.0
    
    def test_default_pipeline_settings(self):
        """Should have sensible pipeline defaults."""
        settings = Settings(tomorrow_api_key="test", pg_password="test")
        
        assert settings.fetch_interval_minutes == 60
        assert settings.fetch_forecast_hours == 120
        assert settings.fetch_historical_hours == 24
        assert settings.data_granularity == "hourly"
    
    def test_default_logging_settings(self):
        """Should have sensible logging defaults."""
        settings = Settings(tomorrow_api_key="test", pg_password="test")
        
        assert settings.log_level == "INFO"
        assert settings.log_format == "json"
    
    def test_default_environment(self):
        """Should default to development environment."""
        settings = Settings(tomorrow_api_key="test", pg_password="test")
        
        assert settings.environment == "development"
        assert settings.debug is False
        assert settings.is_development is True
        assert settings.is_production is False


class TestValidationConstraints:
    """Tests for validation constraints."""
    
    def test_pg_port_range(self):
        """Should validate pg_port is in valid range."""
        with pytest.raises(ValidationError):
            Settings(tomorrow_api_key="test", pg_password="test", pg_port=0)
        
        with pytest.raises(ValidationError):
            Settings(tomorrow_api_key="test", pg_password="test", pg_port=70000)
    
    def test_pg_pool_size_range(self):
        """Should validate pg_pool_size is in valid range."""
        with pytest.raises(ValidationError):
            Settings(tomorrow_api_key="test", pg_password="test", pg_pool_size=0)
        
        with pytest.raises(ValidationError):
            Settings(tomorrow_api_key="test", pg_password="test", pg_pool_size=100)
    
    def test_fetch_interval_range(self):
        """Should validate fetch_interval_minutes is in valid range."""
        with pytest.raises(ValidationError):
            Settings(tomorrow_api_key="test", pg_password="test", fetch_interval_minutes=1)
        
        with pytest.raises(ValidationError):
            Settings(tomorrow_api_key="test", pg_password="test", fetch_interval_minutes=2000)
    
    def test_log_level_valid_values(self):
        """Should only accept valid log levels."""
        settings = Settings(tomorrow_api_key="test", pg_password="test", log_level="DEBUG")
        assert settings.log_level == "DEBUG"
        
        settings = Settings(tomorrow_api_key="test", pg_password="test", log_level="ERROR")
        assert settings.log_level == "ERROR"
    
    def test_data_granularity_valid_values(self):
        """Should only accept valid granularity values."""
        for granularity in ["minutely", "hourly", "daily"]:
            settings = Settings(
                tomorrow_api_key="test",
                pg_password="test",
                data_granularity=granularity
            )
            assert settings.data_granularity == granularity


class TestComputedProperties:
    """Tests for computed properties."""
    
    def test_database_url(self):
        """Should construct correct database URL."""
        settings = Settings(
            tomorrow_api_key="test",
            pg_host="myhost",
            pg_port=5433,
            pg_database="mydb",
            pg_user="myuser",
            pg_password="mypass"
        )
        
        expected = "postgresql://myuser:mypass@myhost:5433/mydb"
        assert settings.database_url == expected
    
    def test_is_production(self):
        """Should correctly identify production environment."""
        dev_settings = Settings(
            tomorrow_api_key="test",
            pg_password="test",
            environment="development"
        )
        assert dev_settings.is_production is False
        
        prod_settings = Settings(
            tomorrow_api_key="test",
            pg_password="test",
            environment="production"
        )
        assert prod_settings.is_production is True
    
    def test_is_development(self):
        """Should correctly identify development environment."""
        dev_settings = Settings(
            tomorrow_api_key="test",
            pg_password="test",
            environment="development"
        )
        assert dev_settings.is_development is True
        
        prod_settings = Settings(
            tomorrow_api_key="test",
            pg_password="test",
            environment="production"
        )
        assert prod_settings.is_development is False


class TestEnvironmentVariables:
    """Tests for environment variable loading."""
    
    @patch.dict(os.environ, {
        "TOMORROW_API_KEY": "env_api_key",
        "PGPASSWORD": "env_password",
        "PGHOST": "env_host",
        "LOG_LEVEL": "DEBUG"
    }, clear=True)
    def test_load_from_environment(self):
        """Should load settings from environment variables."""
        reload_settings()  # Clear cache and reload
        settings = get_settings()
        
        assert settings.tomorrow_api_key == "env_api_key"
        assert settings.pg_password == "env_password"
        assert settings.pg_host == "env_host"
        assert settings.log_level == "DEBUG"
    
    @patch.dict(os.environ, {
        "TOMORROW_API_KEY": "test_key",
        "PGPASSWORD": "test_pass"
    }, clear=True)
    def test_env_defaults_still_apply(self):
        """Should use defaults for unset environment variables."""
        reload_settings()
        settings = get_settings()
        
        # These should still have defaults
        assert settings.pg_host == "localhost"  # default
        assert settings.pg_port == 5432  # default
        assert settings.log_level == "INFO"  # default


class TestSettingsCaching:
    """Tests for settings caching behavior."""
    
    @patch.dict(os.environ, {
        "TOMORROW_API_KEY": "cached_key",
        "PGPASSWORD": "cached_pass"
    }, clear=True)
    def test_settings_cached(self):
        """Should return cached settings on subsequent calls."""
        reload_settings()  # Start fresh
        
        settings1 = get_settings()
        settings2 = get_settings()
        
        # Should be the same object (cached)
        assert settings1 is settings2
    
    @patch.dict(os.environ, {
        "TOMORROW_API_KEY": "original_key",
        "PGPASSWORD": "original_pass"
    }, clear=True)
    def test_reload_settings(self):
        """Should reload settings when explicitly called."""
        reload_settings()
        settings1 = get_settings()
        
        # Change environment
        with patch.dict(os.environ, {"TOMORROW_API_KEY": "new_key", "PGPASSWORD": "new_pass"}):
            reload_settings()
            settings2 = get_settings()
        
        # Should be different after reload
        assert settings1.tomorrow_api_key == "original_key"
        assert settings2.tomorrow_api_key == "new_key"


class TestEnvFile:
    """Tests for .env file loading."""
    
    def test_env_file_example_exists(self):
        """Should have .env.example file."""
        import os
        env_example_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".env.example"
        )
        assert os.path.exists(env_example_path)
    
    def test_env_example_contains_required_vars(self):
        """Should document all required variables."""
        import os
        env_example_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".env.example"
        )
        
        with open(env_example_path) as f:
            content = f.read()
        
        # Should contain required vars
        assert "TOMORROW_API_KEY" in content
        assert "PGHOST" in content
        assert "PGPORT" in content
        assert "PGDATABASE" in content
        assert "PGUSER" in content
        assert "PGPASSWORD" in content


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_whitespace_api_key(self):
        """Should strip whitespace from API key."""
        settings = Settings(tomorrow_api_key="  key_with_spaces  ", pg_password="pass")
        assert settings.tomorrow_api_key == "key_with_spaces"
    
    def test_special_characters_in_password(self):
        """Should handle special characters in password."""
        special_password = "p@$$w0rd!#$%^&*()"
        settings = Settings(tomorrow_api_key="test", pg_password=special_password)
        assert settings.pg_password == special_password
    
    def test_very_long_api_key(self):
        """Should handle long API keys."""
        long_key = "a" * 500
        settings = Settings(tomorrow_api_key=long_key, pg_password="pass")
        assert settings.tomorrow_api_key == long_key
    
    def test_url_with_trailing_slash(self):
        """Should handle API base URL with trailing slash."""
        settings = Settings(
            tomorrow_api_key="test",
            pg_password="pass",
            tomorrow_api_base_url="https://api.example.com/"
        )
        assert settings.tomorrow_api_base_url == "https://api.example.com/"
