import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import logging
from typing import Dict, Any, Optional, List
import os

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
            # Создаем сообщение
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.sender_name} <{self.email}>" if self.sender_name else self.email
            msg['To'] = recipient
            msg['Subject'] = subject or "Сообщение от TelegramSender"
            
            # Добавляем текст (поддержка HTML)
            if '<' in message and '>' in message:
                # HTML сообщение
                html_part = MIMEText(message, 'html', 'utf-8')
                msg.attach(html_part)
                
                # Создаем текстовую версию (упрощенно)
                import re
                text_message = re.sub(r'<[^>]+>', '', message)
                text_part = MIMEText(text_message, 'plain', 'utf-8')
                msg.attach(text_part)
            else:
                # Обычное текстовое сообщение
                text_part = MIMEText(message, 'plain', 'utf-8')
                msg.attach(text_part)
            
            # Отправляем сообщение
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
    
    async def send_with_attachments(self, recipient: str, message: str, subject: str, 
                                  attachments: List[str] = None) -> bool:
        """Отправка email с вложениями"""
        try:
            # Создаем сообщение
            msg = MIMEMultipart()
            msg['From'] = f"{self.sender_name} <{self.email}>" if self.sender_name else self.email
            msg['To'] = recipient
            msg['Subject'] = subject
            
            # Добавляем текст
            text_part = MIMEText(message, 'plain', 'utf-8')
            msg.attach(text_part)
            
            # Добавляем вложения
            if attachments:
                for file_path in attachments:
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, "rb") as attachment:
                                part = MIMEBase('application', 'octet-stream')
                                part.set_payload(attachment.read())
                            
                            encoders.encode_base64(part)
                            filename = os.path.basename(file_path)
                            part.add_header(
                                'Content-Disposition',
                                f'attachment; filename= {filename}',
                            )
                            msg.attach(part)
                            
                        except Exception as e:
                            logger.error(f"Error attaching file {file_path}: {e}")
            
            # Отправляем
            smtp = aiosmtplib.SMTP(hostname=self.smtp_host, port=self.smtp_port)
            await smtp.connect()
            
            if self.use_tls:
                await smtp.starttls()
            
            await smtp.login(self.email, self.password)
            await smtp.send_message(msg)
            await smtp.quit()
            
            logger.info(f"Email with attachments sent to {recipient}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending email with attachments to {recipient}: {e}")
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