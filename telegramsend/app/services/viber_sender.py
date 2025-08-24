# app/services/viber_sender.py
import aiohttp
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class ViberSenderService:
    """Сервис для отправки сообщений через Viber"""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_key = config["api_key"]
        self.api_url = config.get("api_url", "https://chatapi.viber.com/pa/send_message")
        self.sender_name = config.get("sender_name", "Bot")
        self.is_connected = False
    
    async def connect(self) -> bool:
        """Тест подключения к Viber API"""
        try:
            headers = {
                "X-Viber-Auth-Token": self.api_key,
                "Content-Type": "application/json"
            }
            
            # Тестируем получение информации об аккаунте
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://chatapi.viber.com/pa/get_account_info",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == 0:  # 0 = success в Viber API
                            self.is_connected = True
                            logger.info("Successfully connected to Viber API")
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error connecting to Viber API: {e}")
            return False
    
    async def send_message(self, recipient: str, message: str, subject: str = None) -> bool:
        """Отправка Viber сообщения"""
        if not self.is_connected:
            if not await self.connect():
                return False
        
        try:
            headers = {
                "X-Viber-Auth-Token": self.api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "receiver": recipient,
                "min_api_version": 1,
                "sender": {
                    "name": self.sender_name
                },
                "type": "text",
                "text": message
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == 0:
                            logger.info(f"Viber message sent to {recipient}")
                            return True
                        else:
                            logger.error(f"Viber API error: {data.get('status_message', 'Unknown error')}")
                            return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending Viber message to {recipient}: {e}")
            return False
    
    async def send_image_message(self, recipient: str, message: str, image_url: str) -> bool:
        """Отправка Viber сообщения с изображением"""
        if not self.is_connected:
            if not await self.connect():
                return False
        
        try:
            headers = {
                "X-Viber-Auth-Token": self.api_key,
                "Content-Type": "application/json"
            }
            
            payload = {
                "receiver": recipient,
                "min_api_version": 1,
                "sender": {
                    "name": self.sender_name
                },
                "type": "picture",
                "text": message,
                "media": image_url
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == 0:
                            logger.info(f"Viber image message sent to {recipient}")
                            return True
                        else:
                            logger.error(f"Viber API error: {data.get('status_message', 'Unknown error')}")
                            return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending Viber image message to {recipient}: {e}")
            return False
    
    async def get_account_info(self) -> Optional[Dict]:
        """Получение информации об аккаунте"""
        if not self.is_connected:
            if not await self.connect():
                return None
        
        try:
            headers = {
                "X-Viber-Auth-Token": self.api_key,
                "Content-Type": "application/json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://chatapi.viber.com/pa/get_account_info",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == 0:
                            return data
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting Viber account info: {e}")
            return None
    
    async def test_connection(self) -> bool:
        """Тест подключения"""
        return await self.connect()