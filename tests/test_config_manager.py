"""
Tests for core.config_manager module
"""

import pytest
import tempfile
import yaml
import json
from pathlib import Path
from unittest.mock import patch, mock_open

from core.config_manager import ConfigManager, QueueConfig, RuntimeConfig


class TestQueueConfig:
    """Test QueueConfig dataclass"""
    
    def test_queue_config_creation(self):
        """Test creating QueueConfig"""
        config = QueueConfig(
            name="test_queue",
            description="Test queue for testing",
            consumer_group="test_workers",
            max_length=5000,
            retention_policy="3d"
        )
        
        assert config.name == "test_queue"
        assert config.description == "Test queue for testing"
        assert config.consumer_group == "test_workers"
        assert config.max_length == 5000
        assert config.retention_policy == "3d"
    
    def test_queue_config_defaults(self):
        """Test QueueConfig with default values"""
        config = QueueConfig(
            name="default_queue",
            description="Queue with defaults"
        )
        
        assert config.consumer_group == "workers"
        assert config.max_length == 10000
        assert config.retention_policy == "7d"


class TestRuntimeConfig:
    """Test RuntimeConfig dataclass"""
    
    def test_runtime_config_creation(self):
        """Test creating RuntimeConfig"""
        config = RuntimeConfig(
            queue="code_queue",
            capabilities=["python", "javascript"],
            health_check={"endpoint": "/health", "interval": 30}
        )
        
        assert config.queue == "code_queue"
        assert config.capabilities == ["python", "javascript"]
        assert config.health_check == {"endpoint": "/health", "interval": 30}


class TestConfigManager:
    """Test ConfigManager class"""
    
    def test_config_manager_initialization(self):
        """Test ConfigManager initialization"""
        config_manager = ConfigManager()
        assert config_manager is not None
        assert hasattr(config_manager, '_config')
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_load_yaml_config(self, mock_file, mock_exists):
        """Test loading YAML configuration"""
        mock_exists.return_value = True
        
        yaml_content = """
        runtime:
          max_workers: 4
          timeout: 60
        redis:
          host: localhost
          port: 6379
        """
        
        mock_file.return_value.read.return_value = yaml_content
        
        with patch('yaml.safe_load') as mock_yaml:
            mock_yaml.return_value = {
                'runtime': {'max_workers': 4, 'timeout': 60},
                'redis': {'host': 'localhost', 'port': 6379}
            }
            
            config_manager = ConfigManager()
            config_manager._load_config_file('test.yaml')
            
            assert config_manager._config['runtime']['max_workers'] == 4
            assert config_manager._config['redis']['host'] == 'localhost'
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_load_json_config(self, mock_file, mock_exists):
        """Test loading JSON configuration"""
        mock_exists.return_value = True
        
        json_content = '{"test": {"value": 123}}'
        mock_file.return_value.read.return_value = json_content
        
        config_manager = ConfigManager()
        config_manager._load_config_file('test.json')
        
        assert config_manager._config['test']['value'] == 123
    
    def test_get_config_existing_key(self):
        """Test getting existing configuration key"""
        config_manager = ConfigManager()
        config_manager._config = {'test_key': 'test_value'}
        
        value = config_manager.get_config('test_key')
        assert value == 'test_value'
    
    def test_get_config_nonexistent_key(self):
        """Test getting non-existent configuration key"""
        config_manager = ConfigManager()
        config_manager._config = {}
        
        value = config_manager.get_config('nonexistent_key', 'default_value')
        assert value == 'default_value'
    
    def test_get_config_nested_key(self):
        """Test getting nested configuration key"""
        config_manager = ConfigManager()
        config_manager._config = {
            'nested': {
                'deep': {
                    'value': 'found_it'
                }
            }
        }
        
        value = config_manager.get_config('nested.deep.value')
        assert value == 'found_it'
    
    def test_get_runtime_config(self):
        """Test getting runtime configuration"""
        config_manager = ConfigManager()
        config_manager._config = {
            'runtime': {
                'max_workers': 8,
                'timeout': 120,
                'retry_attempts': 3
            }
        }
        
        runtime_config = config_manager.get_runtime_config()
        
        assert runtime_config['max_workers'] == 8
        assert runtime_config['timeout'] == 120
        assert runtime_config['retry_attempts'] == 3
    
    def test_get_runtime_config_defaults(self):
        """Test getting runtime configuration with defaults"""
        config_manager = ConfigManager()
        config_manager._config = {}
        
        runtime_config = config_manager.get_runtime_config()
        
        # Should return default values
        assert 'max_workers' in runtime_config
        assert 'timeout' in runtime_config
    
    def test_get_redis_config(self):
        """Test getting Redis configuration"""
        config_manager = ConfigManager()
        config_manager._config = {
            'redis': {
                'host': 'redis.example.com',
                'port': 6380,
                'db': 1,
                'password': 'secret'
            }
        }
        
        redis_config = config_manager.get_redis_config()
        
        assert redis_config['host'] == 'redis.example.com'
        assert redis_config['port'] == 6380
        assert redis_config['db'] == 1
        assert redis_config['password'] == 'secret'
    
    def test_get_redis_config_defaults(self):
        """Test getting Redis configuration with defaults"""
        config_manager = ConfigManager()
        config_manager._config = {}
        
        redis_config = config_manager.get_redis_config()
        
        # Should return default values
        assert redis_config['host'] == 'localhost'
        assert redis_config['port'] == 6379
        assert redis_config['db'] == 0
    
    def test_get_ports_config(self):
        """Test getting ports configuration"""
        config_manager = ConfigManager()
        config_manager._config = {
            'mcp_servers': {
                'toolscore_mcp': {'port': 8090},
                'python_executor': {'port': 8083},
                'browser_navigator': {'port': 8084}
            }
        }
        
        ports_config = config_manager.get_ports_config()
        
        assert ports_config['mcp_servers']['toolscore_mcp']['port'] == 8090
        assert ports_config['mcp_servers']['python_executor']['port'] == 8083
        assert ports_config['mcp_servers']['browser_navigator']['port'] == 8084
    
    def test_get_llm_config(self):
        """Test getting LLM configuration"""
        config_manager = ConfigManager()
        config_manager._config = {
            'llm': {
                'provider': 'openai',
                'model': 'gpt-4',
                'api_key': 'test_key',
                'max_tokens': 4000,
                'temperature': 0.7
            }
        }
        
        llm_config = config_manager.get_llm_config()
        
        assert llm_config['provider'] == 'openai'
        assert llm_config['model'] == 'gpt-4'
        assert llm_config['max_tokens'] == 4000
        assert llm_config['temperature'] == 0.7
    
    def test_environment_variable_override(self):
        """Test that environment variables override config values"""
        with patch.dict('os.environ', {'REDIS_HOST': 'env.redis.com'}):
            config_manager = ConfigManager()
            config_manager._config = {
                'redis': {'host': 'config.redis.com'}
            }
            
            redis_config = config_manager.get_redis_config()
            assert redis_config['host'] == 'env.redis.com'
    
    def test_config_file_not_found(self):
        """Test handling of missing config file"""
        with patch('os.path.exists', return_value=False):
            config_manager = ConfigManager()
            config_manager._load_config_file('nonexistent.yaml')
            
            # Should not raise an error and should have empty or default config
            assert isinstance(config_manager._config, dict)
    
    def test_invalid_yaml_config(self):
        """Test handling of invalid YAML config"""
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data='invalid: yaml: content:')):
                config_manager = ConfigManager()
                
                # Should handle the error gracefully
                config_manager._load_config_file('invalid.yaml')
                assert isinstance(config_manager._config, dict)
    
    def test_invalid_json_config(self):
        """Test handling of invalid JSON config"""
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data='{invalid json}')):
                config_manager = ConfigManager()
                
                # Should handle the error gracefully
                config_manager._load_config_file('invalid.json')
                assert isinstance(config_manager._config, dict)
    
    def test_get_queue_configs(self):
        """Test getting queue configurations"""
        config_manager = ConfigManager()
        config_manager._config = {
            'queues': {
                'code_queue': {
                    'description': 'Queue for code tasks',
                    'consumer_group': 'code_workers',
                    'max_length': 1000
                },
                'web_queue': {
                    'description': 'Queue for web tasks',
                    'consumer_group': 'web_workers',
                    'max_length': 2000
                }
            }
        }
        
        queue_configs = config_manager.get_queue_configs()
        
        assert len(queue_configs) == 2
        assert 'code_queue' in queue_configs
        assert 'web_queue' in queue_configs
        assert queue_configs['code_queue']['max_length'] == 1000
        assert queue_configs['web_queue']['max_length'] == 2000
    
    def test_get_runtime_configs(self):
        """Test getting runtime configurations"""
        config_manager = ConfigManager()
        config_manager._config = {
            'runtimes': {
                'code_runtime': {
                    'queue': 'code_queue',
                    'capabilities': ['python', 'javascript'],
                    'health_check': {'endpoint': '/health'}
                },
                'web_runtime': {
                    'queue': 'web_queue',
                    'capabilities': ['browser', 'scraping'],
                    'health_check': {'endpoint': '/status'}
                }
            }
        }
        
        runtime_configs = config_manager.get_runtime_configs()
        
        assert len(runtime_configs) == 2
        assert 'code_runtime' in runtime_configs
        assert 'web_runtime' in runtime_configs
        assert runtime_configs['code_runtime']['queue'] == 'code_queue'
        assert runtime_configs['web_runtime']['capabilities'] == ['browser', 'scraping']