from telethon import TelegramClient, errors
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageTypingAction
import asyncio
import random
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class TelegramSenderService:
    """Сервис для отправки сообщений через Telegram"""
    
    def __init__(self, config: Dict[str, Any]):
        self.api_id = config["api_id"]
        self.api_hash = config["api_hash"]
        self.phone = config["phone"]
        self.session_name = f"session_{self.phone}"
        self.client = None
        self.is_connected = False
    
    async def connect(self) -> bool:
        """Подключение к Telegram"""
        try:
            self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            await self.client.start(phone=self.phone)
            
            if await self.client.is_user_authorized():
                me = await self.client.get_me()
                logger.info(f"Connected to Telegram as {me.first_name} (@{me.username})")
                self.is_connected = True
                return True
            else:
                logger.error("Telegram authorization failed")
                return False
                
        except Exception as e:
            logger.error(f"Error connecting to Telegram: {e}")
            return False
    
    async def disconnect(self):
        """Отключение от Telegram"""
        if self.client and self.is_connected:
            await self.client.disconnect()
            self.is_connected = False
    
    async def send_message(self, recipient: str, message: str, subject: str = None) -> bool:
        """Отправка сообщения"""
        if not self.is_connected:
            if not await self.connect():
                return False
        
        try:
            # Получаем entity получателя
            if recipient.startswith('@'):
                entity = await self.client.get_entity(recipient)
            elif recipient.isdigit():
                entity = await self.client.get_entity(int(recipient))
            else:
                # Пробуем как username без @
                entity = await self.client.get_entity(f"@{recipient}")
            
            # Имитируем печатание
            await self.simulate_typing(entity)
            
            # Отправляем сообщение
            await self.client.send_message(entity, message)
            
            logger.info(f"Message sent to {recipient}")
            return True
            
        except errors.PeerFloodError:
            logger.error(f"Flood error for {recipient}")
            return False
        except errors.UserIsBlockedError:
            logger.error(f"User blocked bot: {recipient}")
            return False
        except errors.ChatWriteForbiddenError:
            logger.error(f"Write forbidden: {recipient}")
            return False
        except errors.PeerIdInvalidError:
            logger.error(f"Invalid peer ID: {recipient}")
            return False
        except Exception as e:
            logger.error(f"Error sending message to {recipient}: {e}")
            return False
    
    async def simulate_typing(self, entity):
        """Имитация печатания"""
        try:
            await self.client(SetTypingRequest(peer=entity, action=SendMessageTypingAction()))
            await asyncio.sleep(random.uniform(0.5, 2.0))
        except Exception:
            pass
    
    async def get_me(self) -> Optional[Dict]:
        """Получение информации о текущем пользователе"""
        if not self.is_connected:
            if not await self.connect():
                return None
        
        try:
            me = await self.client.get_me()
            return {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "username": me.username,
                "phone": me.phone
            }
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None
    
    async def test_connection(self) -> bool:
        """Тест подключения"""
        try:
            if await self.connect():
                me = await self.get_me()
                await self.disconnect()
                return me is not None
            return False
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False