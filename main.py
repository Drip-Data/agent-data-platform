#!/usr/bin/env python3
"""
Agent Data Platform - Main Entry Point
"""

import asyncio
import logging
import os

# Install lightweight stubs when optional dependencies are missing
from core import stubs
stubs.install()

from core.dispatcher_enhanced import main

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    asyncio.run(main())
