"""
Configuration Management for Voice Conversation Generator
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from dataclasses import dataclass, field


@dataclass
class AppConfig:
    """Application configuration"""
    name: str = "Voice Conversation Generator"
    environment: str = "development"
    version: str = "1.0.0"
    debug: bool = True


@dataclass
class StorageConfig:
    """Storage configuration"""
    type: str = "local"  # local, gcs, s3
    local: Dict[str, Any] = field(default_factory=lambda: {
        "base_path": "data/conversations",
        "create_dirs": True
    })
    gcs: Dict[str, Any] = field(default_factory=lambda: {
        "bucket": "",
        "project_id": ""
    })
    s3: Dict[str, Any] = field(default_factory=lambda: {
        "bucket": "",
        "region": "us-west-2"
    })


@dataclass
class ProvidersConfig:
    """Provider configuration"""
    llm: Dict[str, Any] = field(default_factory=lambda: {
        "type": "openai",
        "model": "gpt-4"
    })
    tts: Dict[str, Any] = field(default_factory=lambda: {
        "type": "openai",
        "model": "tts-1",
        "default_voice": "onyx"
    })
    stt: Optional[Dict[str, Any]] = None


@dataclass
class DatabaseConfig:
    """Database configuration"""
    enabled: bool = False
    url: str = ""


@dataclass
class LiveKitConfig:
    """LiveKit configuration"""
    enabled: bool = False
    url: str = ""
    api_key: str = ""
    api_secret: str = ""


@dataclass
class Config:
    """Main configuration class"""
    app: AppConfig = field(default_factory=AppConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    livekit: LiveKitConfig = field(default_factory=LiveKitConfig)

    @classmethod
    def load_from_file(cls, config_path: str = None) -> 'Config':
        """Load configuration from YAML file

        Args:
            config_path: Path to configuration file (defaults to config.yaml)

        Returns:
            Config object
        """
        if config_path is None:
            # Try multiple locations
            possible_paths = [
                Path("config.yaml"),
                Path("src/voice_conversation_generator/config.yaml"),
                Path("../config.yaml")
            ]
            for path in possible_paths:
                if path.exists():
                    config_path = str(path)
                    break

        config = cls()

        # Load from file if it exists
        if config_path and Path(config_path).exists():
            with open(config_path, 'r') as f:
                yaml_data = yaml.safe_load(f)

            # Update config with YAML data
            if yaml_data:
                if 'app' in yaml_data:
                    config.app = AppConfig(**yaml_data['app'])
                if 'storage' in yaml_data:
                    config.storage = StorageConfig(**yaml_data['storage'])
                if 'providers' in yaml_data:
                    config.providers = ProvidersConfig(**yaml_data['providers'])
                if 'database' in yaml_data:
                    config.database = DatabaseConfig(**yaml_data['database'])
                if 'livekit' in yaml_data:
                    config.livekit = LiveKitConfig(**yaml_data['livekit'])

        return config

    @classmethod
    def load_from_env(cls) -> 'Config':
        """Load configuration from environment variables

        Returns:
            Config object with values from environment
        """
        # Load .env.local files
        load_dotenv(".env.local")
        load_dotenv("../.env.local")

        config = cls()

        # Override with environment variables
        config.app.environment = os.getenv('APP_ENVIRONMENT', config.app.environment)
        config.app.debug = os.getenv('APP_DEBUG', 'true').lower() == 'true'

        # Storage
        config.storage.type = os.getenv('STORAGE_TYPE', config.storage.type)
        if os.getenv('STORAGE_BASE_PATH'):
            config.storage.local['base_path'] = os.getenv('STORAGE_BASE_PATH')

        # Providers
        if os.getenv('LLM_PROVIDER'):
            config.providers.llm['type'] = os.getenv('LLM_PROVIDER')
        if os.getenv('LLM_MODEL'):
            config.providers.llm['model'] = os.getenv('LLM_MODEL')
        if os.getenv('TTS_PROVIDER'):
            config.providers.tts['type'] = os.getenv('TTS_PROVIDER')

        # Database
        if os.getenv('DATABASE_URL'):
            config.database.enabled = True
            config.database.url = os.getenv('DATABASE_URL')

        # LiveKit
        if os.getenv('LIVEKIT_URL'):
            config.livekit.enabled = True
            config.livekit.url = os.getenv('LIVEKIT_URL')
            config.livekit.api_key = os.getenv('LIVEKIT_API_KEY', '')
            config.livekit.api_secret = os.getenv('LIVEKIT_API_SECRET', '')

        return config

    @classmethod
    def load(cls, config_path: str = None) -> 'Config':
        """Load configuration from file and environment

        Args:
            config_path: Optional path to config file

        Returns:
            Config object with merged configuration
        """
        # Start with file config
        config = cls.load_from_file(config_path)

        # Override with environment variables
        env_config = cls.load_from_env()

        # Merge environment into file config
        # (Environment takes precedence)
        if os.getenv('APP_ENVIRONMENT'):
            config.app.environment = env_config.app.environment
        if os.getenv('STORAGE_TYPE'):
            config.storage.type = env_config.storage.type

        # Merge provider configs
        if os.getenv('LLM_PROVIDER') or os.getenv('LLM_MODEL'):
            config.providers.llm.update(env_config.providers.llm)
        if os.getenv('TTS_PROVIDER'):
            config.providers.tts.update(env_config.providers.tts)

        # Use environment database if set
        if env_config.database.enabled:
            config.database = env_config.database

        # Use environment LiveKit if set
        if env_config.livekit.enabled:
            config.livekit = env_config.livekit

        return config

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'app': {
                'name': self.app.name,
                'environment': self.app.environment,
                'version': self.app.version,
                'debug': self.app.debug
            },
            'storage': {
                'type': self.storage.type,
                'local': self.storage.local,
                'gcs': self.storage.gcs,
                's3': self.storage.s3
            },
            'providers': {
                'llm': self.providers.llm,
                'tts': self.providers.tts,
                'stt': self.providers.stt
            },
            'database': {
                'enabled': self.database.enabled,
                'url': self.database.url
            },
            'livekit': {
                'enabled': self.livekit.enabled,
                'url': self.livekit.url,
                'api_key': self.livekit.api_key,
                'api_secret': self.livekit.api_secret
            }
        }

    def save_to_file(self, config_path: str):
        """Save configuration to YAML file

        Args:
            config_path: Path to save configuration
        """
        with open(config_path, 'w') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration instance

    Returns:
        Global Config object
    """
    global _config
    if _config is None:
        _config = Config.load()
    return _config


def set_config(config: Config):
    """Set the global configuration instance

    Args:
        config: Config object to set as global
    """
    global _config
    _config = config