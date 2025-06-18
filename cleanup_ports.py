#\!/usr/bin/env python3
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_ports():
    ports = [8088, 8089, 8090, 8091, 8092, 5555, 8081, 8082, 8080]
    
    for port in ports:
        try:
            logger.info(f"Cleaning up port {port}...")
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'], 
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    try:
                        subprocess.run(['kill', '-9', pid], timeout=3, check=False)
                        logger.info(f"Killed process {pid} using port {port}")
                    except Exception as e:
                        logger.warning(f"Failed to kill process {pid}: {e}")
            else:
                logger.info(f"Port {port} is free")
                
        except Exception as e:
            logger.warning(f"Error checking port {port}: {e}")

if __name__ == "__main__":
    cleanup_ports()
    logger.info("Port cleanup completed")