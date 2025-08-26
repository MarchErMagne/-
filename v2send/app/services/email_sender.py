import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import logging
from typing import Dict, Any, Optional, List
import os
import asyncio

logger = logging.getLogger(__name__)

class EmailSenderService:
    """Сервис для отправки email сообщений"""
    
    def __init__(self, config: Dict[str, Any]):
        self.smtp_host = config["smtp_host"]
        self.smtp_port = config["smtp_port"]
        self.email = config["email"]
        self.password = config["password"]
        self.use_tls = config.get("use_tls", True)
        self.sender_name = config.get("sender_name", "")
        self.is_connected = False
        
    async def connect(self) -> bool:
        """Тест подключения к SMTP серверу"""
        try:
            smtp = aiosmtplib.SMTP(hostname=self.smtp_host, port=self.smtp_port)
            await smtp.connect()
            
            if self.use_tls:
                await smtp.starttls()
            
            await smtp.login(self.email, self.password)
            await smtp.quit()
            
            self.is_connected = True
            logger.info(f"Successfully connected to SMTP {self.smtp_host}:{self.smtp_port}")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to SMTP: {e}")
            return False
    
    async def send_message(self, recipient: str, message: str, subject: str = None) -> bool:
        """Отправка email сообщения"""
        try:
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.sender_name} <{self.email}>" if self.sender_name else self.email
            msg['To'] = recipient
            msg['Subject'] = subject or "Сообщение от TelegramSender"
            
            if '<' in message and '>' in message:
                html_part = MIMEText(message, 'html', 'utf-8')
                msg.attach(html_part)
                
                import re
                text_message = re.sub(r'<[^>]+>', '', message)
                text_part = MIMEText(text_message, 'plain', 'utf-8')
                msg.attach(text_part)
            else:
                text_part = MIMEText(message, 'plain', 'utf-8')
                msg.attach(text_part)
            
            smtp = aiosmtplib.SMTP(hostname=self.smtp_host, port=self.smtp_port)
            await smtp.connect()
            
            if self.use_tls:
                await smtp.starttls()
            
            await smtp.login(self.email, self.password)
            await smtp.send_message(msg)
            await smtp.quit()
            
            logger.info(f"Email sent to {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email to {recipient}: {e}")
            return False
    
    async def test_connection(self) -> bool:
        """Тест соединения"""
        return await self.connect()
    
    def get_info(self) -> Dict[str, Any]:
        """Получение информации об отправителе"""
        return {
            "email": self.email,
            "smtp_host": self.smtp_host,
            "smtp_port": self.smtp_port,
            "sender_name": self.sender_name,
            "use_tls": self.use_tls
        }