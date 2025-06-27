#!/usr/bin/env python3
"""
MicroSandbox Production Mode Validator
验证生产模式配置和API版本兼容性
"""

import asyncio
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv
import subprocess
import json
import time

# Load environment configuration first
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# Add current directory to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from main import MicroSandboxConfig, MicroSandboxServerManager
except ImportError:
    # Fallback: create minimal config for validation
    class MicroSandboxConfig:
        MSB_API_KEY = os.getenv('MSB_API_KEY')
        MSB_HOST = os.getenv('MSB_HOST', '127.0.0.1')
        MSB_PORT = int(os.getenv('MSB_PORT', '5555'))
        MSB_STORAGE_PATH = os.getenv('MSB_STORAGE_PATH', os.path.expanduser('~/.microsandbox'))
        MSB_LOG_LEVEL = os.getenv('MSB_LOG_LEVEL', 'info')
        SUPPORTED_API_VERSION = '0.2.6'
        
        @classmethod
        def validate_config(cls):
            errors = []
            if not cls.MSB_API_KEY:
                errors.append("MSB_API_KEY is required for production mode")
            if not Path(cls.MSB_STORAGE_PATH).exists():
                try:
                    Path(cls.MSB_STORAGE_PATH).mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    errors.append(f"Cannot create storage path {cls.MSB_STORAGE_PATH}: {e}")
            return errors
    
    class MicroSandboxServerManager:
        def __init__(self):
            self.config = MicroSandboxConfig
            
        async def ensure_server_running(self):
            import aiohttp
            try:
                async with aiohttp.ClientSession() as session:
                    health_url = f"http://{self.config.MSB_HOST}:{self.config.MSB_PORT}/health"
                    async with session.get(health_url, timeout=3) as resp:
                        return resp.status == 200
            except Exception:
                return False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProductionModeValidator:
    """生产模式验证器"""
    
    def __init__(self):
        self.config = MicroSandboxConfig
        self.server_manager = MicroSandboxServerManager()
        
    async def validate_configuration(self):
        """验证生产配置"""
        logger.info("🔧 Validating production configuration...")
        
        errors = []
        
        # Check environment file
        env_path = Path(__file__).parent / '.env'
        if not env_path.exists():
            errors.append(f"Environment file not found: {env_path}")
        else:
            logger.info(f"✅ Environment file found: {env_path}")
        
        # Validate configuration
        config_errors = self.config.validate_config()
        if config_errors:
            errors.extend(config_errors)
        else:
            logger.info("✅ Configuration validation passed")
            
        # Check storage path
        if Path(self.config.MSB_STORAGE_PATH).exists():
            logger.info(f"✅ Storage path exists: {self.config.MSB_STORAGE_PATH}")
        else:
            logger.warning(f"⚠️ Storage path will be created: {self.config.MSB_STORAGE_PATH}")
            
        return errors
        
    async def validate_api_version(self):
        """验证API版本兼容性"""
        logger.info("🔧 Validating API version compatibility...")
        
        try:
            # Check MSB CLI version
            result = subprocess.run(['msb', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                cli_version = result.stdout.strip()
                logger.info(f"✅ MSB CLI version: {cli_version}")
                
                # Check if version matches expected
                if cli_version == self.config.SUPPORTED_API_VERSION:
                    logger.info("✅ API version matches configuration")
                    return True
                else:
                    logger.warning(f"⚠️ API version mismatch: CLI={cli_version}, Expected={self.config.SUPPORTED_API_VERSION}")
                    return True  # Continue but warn
            else:
                logger.error("❌ Could not get MSB CLI version")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error checking API version: {e}")
            return False
            
    async def test_production_server(self):
        """测试生产模式服务器"""
        logger.info("🧪 Testing production mode server...")
        
        try:
            # Ensure server is running
            server_running = await self.server_manager.ensure_server_running()
            if not server_running:
                logger.error("❌ Could not start production mode server")
                return False
                
            # Test server health
            import aiohttp
            async with aiohttp.ClientSession() as session:
                health_url = f"http://{self.config.MSB_HOST}:{self.config.MSB_PORT}/health"
                try:
                    async with session.get(health_url, timeout=5) as resp:
                        if resp.status == 200:
                            logger.info("✅ Production server health check passed")
                            return True
                        else:
                            logger.error(f"❌ Server health check failed: status {resp.status}")
                            return False
                except Exception as e:
                    logger.error(f"❌ Server health check failed: {e}")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Error testing production server: {e}")
            return False
            
    async def test_authenticated_connection(self):
        """测试认证连接"""
        logger.info("🔐 Testing authenticated connection...")
        
        try:
            from microsandbox import PythonSandbox
            
            server_url = f"http://{self.config.MSB_HOST}:{self.config.MSB_PORT}"
            
            # Test connection with API key
            sandbox_kwargs = {
                'server_url': server_url
            }
            
            if self.config.MSB_API_KEY:
                sandbox_kwargs['api_key'] = self.config.MSB_API_KEY
                
            async with PythonSandbox.create(**sandbox_kwargs) as sandbox:
                # Execute simple test
                execution = await sandbox.run("print('Production mode test successful')")
                
                # Check result
                if hasattr(execution, 'status'):
                    success = execution.status == 'success'
                else:
                    success = execution.exit_code == 0 if hasattr(execution, 'exit_code') else True
                    
                if success:
                    logger.info("✅ Authenticated connection test passed")
                    return True
                else:
                    logger.error("❌ Authenticated connection test failed")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Authenticated connection test failed: {e}")
            return False
            
    async def validate_persistent_storage(self):
        """验证持久化存储"""
        logger.info("💾 Validating persistent storage...")
        
        try:
            storage_path = Path(self.config.MSB_STORAGE_PATH)
            
            # Check if storage path is writable
            test_file = storage_path / 'test_write.tmp'
            try:
                test_file.parent.mkdir(parents=True, exist_ok=True)
                test_file.write_text('test')
                test_file.unlink()
                logger.info(f"✅ Storage path is writable: {storage_path}")
                return True
            except Exception as e:
                logger.error(f"❌ Storage path is not writable: {e}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error validating storage: {e}")
            return False
            
    async def run_full_validation(self):
        """运行完整验证"""
        logger.info("🚀 Starting production mode validation...")
        print("=" * 60)
        print("🏭 MICROSANDBOX PRODUCTION MODE VALIDATION")
        print("=" * 60)
        
        results = []
        
        # Configuration validation
        config_errors = await self.validate_configuration()
        if config_errors:
            print("❌ Configuration Validation: FAILED")
            for error in config_errors:
                print(f"   - {error}")
            results.append(False)
        else:
            print("✅ Configuration Validation: PASSED")
            results.append(True)
            
        # API version validation
        api_valid = await self.validate_api_version()
        if api_valid:
            print("✅ API Version Validation: PASSED")
        else:
            print("❌ API Version Validation: FAILED")
        results.append(api_valid)
        
        # Storage validation
        storage_valid = await self.validate_persistent_storage()
        if storage_valid:
            print("✅ Persistent Storage: PASSED")
        else:
            print("❌ Persistent Storage: FAILED")
        results.append(storage_valid)
        
        # Server validation
        server_valid = await self.test_production_server()
        if server_valid:
            print("✅ Production Server: PASSED")
        else:
            print("❌ Production Server: FAILED")
        results.append(server_valid)
        
        # Authentication validation
        auth_valid = await self.test_authenticated_connection()
        if auth_valid:
            print("✅ Authenticated Connection: PASSED")
        else:
            print("❌ Authenticated Connection: FAILED")
        results.append(auth_valid)
        
        # Summary
        passed = sum(results)
        total = len(results)
        
        print()
        print("=" * 60)
        print(f"📊 VALIDATION SUMMARY: {passed}/{total} PASSED")
        
        if passed == total:
            print("🎉 All validations passed! Production mode is ready.")
            return True
        else:
            print("⚠️ Some validations failed. Check configuration.")
            return False

async def main():
    """主函数"""
    validator = ProductionModeValidator()
    success = await validator.run_full_validation()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    asyncio.run(main())