import aiohttp
import logging
from typing import Dict, Any, Optional
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class SMSSenderService:
    """Сервис для отправки SMS сообщений"""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_key = config["api_key"]
        self.api_url = config.get("api_url", "https://api.sms.ru/sms/send")
        self.sender_name = config.get("sender_name", "")
        self.is_connected = False
    
    async def connect(self) -> bool:
        """Тест подключения к SMS API"""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "api_id": self.api_key,
                    "json": 1
                }
                
                async with session.get(f"{self.api_url.replace('/send', '/my/balance')}", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "OK":
                            self.is_connected = True
                            logger.info("Successfully connected to SMS API")
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error connecting to SMS API: {e}")
            return False
    
    async def send_message(self, recipient: str, message: str, subject: str = None) -> bool:
        """Отправка SMS сообщения"""
        if not self.is_connected:
            if not await self.connect():
                return False
        
        try:
            # Очищаем номер
            phone = recipient.replace("+", "").replace(" ", "").replace("-", "")
            
            params = {
                "api_id": self.api_key,
                "to": phone,
                "msg": message,
                "json": 1
            }
            
            if self.sender_name:
                params["from"] = self.sender_name
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, data=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "OK":
                            logger.info(f"SMS sent to {recipient}")
                            return True
                        else:
                            logger.error(f"SMS API error: {data.get('status_text', 'Unknown error')}")
                            return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error sending SMS to {recipient}: {e}")
            return False
    
    async def get_balance(self) -> Optional[float]:
        """Получение баланса"""
        try:
            async with aiohttp.ClientSession() as session:
                params = {
                    "api_id": self.api_key,
                    "json": 1
                }
                
                async with session.get(f"{self.api_url.replace('/send', '/my/balance')}", params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "OK":
                            return float(data.get("balance", 0))
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting SMS balance: {e}")
            return None
    
    async def test_connection(self) -> bool:
        """Тест подключения"""
        return await self.connect()