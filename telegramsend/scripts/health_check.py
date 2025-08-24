#!/usr/bin/env python3
"""
Health check script for Docker container
"""

import asyncio
import aiohttp
import sys
import os

async def check_health():
    """Проверяет состояние приложения"""
    try:
        # Проверяем HTTP endpoint
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8000/health', timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('status') == 'ok':
                        print("✅ Health check passed")
                        return True
        
        print("❌ Health check failed")
        return False
        
    except Exception as e:
        print(f"❌ Health check error: {e}")
        return False

if __name__ == "__main__":
    if asyncio.run(check_health()):
        sys.exit(0)
    else:
        sys.exit(1)