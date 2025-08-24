from telethon import TelegramClient, errors
from telethon.tl.functions.messages import SetTypingRequest
from telethon.tl.types import SendMessageTypingAction
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
import asyncio
import random
import logging
import re
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
        """Отправка сообщения в личку или группу"""
        if not self.is_connected:
            if not await self.connect():
                return False
        
        try:
            # Определяем тип получателя
            entity = await self.resolve_entity(recipient)
            if not entity:
                logger.error(f"Could not resolve entity: {recipient}")
                return False
            
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
        except errors.ChannelPrivateError:
            logger.error(f"Private channel: {recipient}")
            return False
        except Exception as e:
            logger.error(f"Error sending message to {recipient}: {e}")
            return False
    
    async def resolve_entity(self, identifier: str):
        """Определение типа получателя и получение entity"""
        try:
            # Если это ссылка на группу/канал
            if self.is_invite_link(identifier):
                return await self.join_by_invite_link(identifier)
            
            # Если это обычная ссылка t.me
            if identifier.startswith('https://t.me/'):
                username = identifier.replace('https://t.me/', '').replace('@', '')
                return await self.client.get_entity(username)
            
            # Если начинается с @
            if identifier.startswith('@'):
                return await self.client.get_entity(identifier)
            
            # Если это числовой ID
            if identifier.isdigit():
                user_id = int(identifier)
                # Проверяем, это пользователь или группа
                if user_id > 0:
                    return await self.client.get_entity(user_id)
                else:
                    # Отрицательный ID - группа
                    return await self.client.get_entity(user_id)
            
            # Если это username без @
            if identifier.replace('_', '').replace('.', '').isalnum():
                return await self.client.get_entity(f"@{identifier}")
            
            return None
            
        except Exception as e:
            logger.error(f"Error resolving entity {identifier}: {e}")
            return None
    
    def is_invite_link(self, link: str) -> bool:
        """Проверка, является ли ссылка пригласительной"""
        invite_patterns = [
            r'https://t\.me/\+',
            r'https://t\.me/joinchat/',
            r'https://telegram\.me/joinchat/'
        ]
        
        for pattern in invite_patterns:
            if re.match(pattern, link):
                return True
        return False
    
    async def join_by_invite_link(self, invite_link: str):
        """Присоединение к группе по пригласительной ссылке"""
        try:
            # Извлекаем хеш из ссылки
            if '/+' in invite_link:
                invite_hash = invite_link.split('/+')[1]
            elif 'joinchat/' in invite_link:
                invite_hash = invite_link.split('joinchat/')[1]
            else:
                return None
            
            # Присоединяемся к группе
            updates = await self.client(ImportChatInviteRequest(invite_hash))
            
            # Получаем chat из updates
            if hasattr(updates, 'chats') and updates.chats:
                chat = updates.chats[0]
                logger.info(f"Joined group: {chat.title}")
                return chat
            
            return None
            
        except errors.InviteHashExpiredError:
            logger.error(f"Invite link expired: {invite_link}")
            return None
        except errors.InviteHashInvalidError:
            logger.error(f"Invalid invite link: {invite_link}")
            return None
        except errors.UserAlreadyParticipantError:
            # Уже в группе, получаем её
            logger.info(f"Already in group: {invite_link}")
            try:
                # Пробуем получить группу по хешу
                return await self.client.get_entity(invite_link)
            except:
                return None
        except Exception as e:
            logger.error(f"Error joining by invite link {invite_link}: {e}")
            return None
    
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
    
    async def get_chat_info(self, identifier: str) -> Optional[Dict]:
        """Получение информации о чате/группе"""
        try:
            entity = await self.resolve_entity(identifier)
            if not entity:
                return None
            
            info = {
                "id": entity.id,
                "title": getattr(entity, 'title', None),
                "username": getattr(entity, 'username', None),
                "type": "user" if hasattr(entity, 'first_name') else "group"
            }
            
            if hasattr(entity, 'participants_count'):
                info["participants_count"] = entity.participants_count
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting chat info for {identifier}: {e}")
            return None