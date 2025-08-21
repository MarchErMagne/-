from twilio.rest import Client
from twilio.base.exceptions import TwilioException
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class WhatsAppSenderService:
    """Сервис для отправки сообщений через WhatsApp (Twilio)"""
    
    def __init__(self, config: Dict[str, Any]):
        self.account_sid = config["account_sid"]
        self.auth_token = config["auth_token"]
        self.from_number = config.get("from_number", "whatsapp:+14155238886")
        self.client = None
        self.is_connected = False
    
    async def connect(self) -> bool:
        """Подключение к Twilio API"""
        try:
            self.client = Client(self.account_sid, self.auth_token)
            
            # Тестируем подключение
            account = self.client.api.accounts(self.account_sid).fetch()
            
            self.is_connected = True
            logger.info(f"Connected to Twilio WhatsApp, account: {account.friendly_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to Twilio: {e}")
            return False
    
    async def send_message(self, recipient: str, message: str, subject: str = None) -> bool:
        """Отправка WhatsApp сообщения"""
        if not self.is_connected:
            if not await self.connect():
                return False
        
        try:
            # Форматируем номер получателя
            if not recipient.startswith("whatsapp:"):
                if not recipient.startswith("+"):
                    recipient = "+" + recipient
                recipient = f"whatsapp:{recipient}"
            
            # Отправляем сообщение
            message_obj = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=recipient
            )
            
            logger.info(f"WhatsApp message sent to {recipient}, SID: {message_obj.sid}")
            return True
            
        except TwilioException as e:
            logger.error(f"Twilio error sending to {recipient}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending WhatsApp message to {recipient}: {e}")
            return False
    
    async def send_media_message(self, recipient: str, message: str, media_url: str) -> bool:
        """Отправка WhatsApp сообщения с медиа"""
        if not self.is_connected:
            if not await self.connect():
                return False
        
        try:
            # Форматируем номер получателя
            if not recipient.startswith("whatsapp:"):
                if not recipient.startswith("+"):
                    recipient = "+" + recipient
                recipient = f"whatsapp:{recipient}"
            
            # Отправляем сообщение с медиа
            message_obj = self.client.messages.create(
                body=message,
                from_=self.from_number,
                to=recipient,
                media_url=[media_url]
            )
            
            logger.info(f"WhatsApp media message sent to {recipient}, SID: {message_obj.sid}")
            return True
            
        except TwilioException as e:
            logger.error(f"Twilio error sending media to {recipient}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error sending WhatsApp media message to {recipient}: {e}")
            return False
    
    async def get_account_info(self) -> Optional[Dict]:
        """Получение информации об аккаунте"""
        if not self.is_connected:
            if not await self.connect():
                return None
        
        try:
            account = self.client.api.accounts(self.account_sid).fetch()
            return {
                "account_sid": account.sid,
                "friendly_name": account.friendly_name,
                "status": account.status,
                "type": account.type
            }
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None
    
    async def test_connection(self) -> bool:
        """Тест подключения"""
        return await self.connect()