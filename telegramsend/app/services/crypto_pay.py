import hashlib
import hmac
import json
import aiohttp
from typing import Dict, Any, Optional
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class CryptoPay:
    """Сервис для работы с CryptoPay API"""
    
    def __init__(self):
        self.api_token = settings.CRYPTO_PAY_TOKEN
        self.base_url = "https://pay.crypt.bot/api"
        self.webhook_secret = settings.CRYPTO_WEBHOOK_SECRET
    
    async def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict[str, Any]:
        """Выполнение запроса к API"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Crypto-Pay-API-Token": self.api_token,
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, headers=headers, params=data) as response:
                    result = await response.json()
            else:
                async with session.post(url, headers=headers, json=data) as response:
                    result = await response.json()
            
            if not result.get("ok"):
                raise Exception(f"CryptoPay API error: {result.get('error', {}).get('name', 'Unknown error')}")
            
            return result["result"]
    
    async def get_me(self) -> Dict[str, Any]:
        """Получение информации о приложении"""
        return await self._make_request("GET", "/getMe")
    
    async def create_invoice(
        self,
        amount: float,
        currency: str = "USD",
        description: str = "",
        payload: str = "",
        expires_in: int = 3600
    ) -> Dict[str, Any]:
        """Создание инвойса"""
        data = {
            "amount": str(amount),
            "currency_type": "fiat",
            "fiat": currency,
            "description": description,
            "payload": payload,
            "expires_in": expires_in
        }
        
        return await self._make_request("POST", "/createInvoice", data)
    
    async def get_invoice(self, invoice_id: str) -> Dict[str, Any]:
        """Получение информации об инвойсе"""
        return await self._make_request("GET", f"/getInvoices", {"invoice_ids": invoice_id})
    
    async def get_balance(self) -> Dict[str, Any]:
        """Получение баланса"""
        return await self._make_request("GET", "/getBalance")
    
    async def get_exchange_rates(self) -> Dict[str, Any]:
        """Получение курсов валют"""
        return await self._make_request("GET", "/getExchangeRates")
    
    async def get_currencies(self) -> Dict[str, Any]:
        """Получение списка поддерживаемых валют"""
        return await self._make_request("GET", "/getCurrencies")
    
    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Проверка подписи webhook"""
        if not self.webhook_secret:
            return True
        
        expected_signature = hmac.new(
            self.webhook_secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)

def setup_crypto_webhooks(app):
    """Настройка webhook для CryptoPay"""
    from aiohttp import web
    from app.database.database import get_db
    from app.database.models import Payment, User, Subscription, SubscriptionStatus
    from app.config import SUBSCRIPTION_PLANS
    from datetime import datetime, timedelta
    from sqlalchemy import select
    
    async def crypto_webhook(request):
        """Обработчик webhook от CryptoPay"""
        try:
            body = await request.read()
            signature = request.headers.get("crypto-pay-api-signature", "")
            
            crypto_pay = CryptoPay()
            if not crypto_pay.verify_webhook_signature(body, signature):
                logger.warning("Invalid webhook signature")
                return web.Response(status=403)
            
            data = json.loads(body.decode())
            update_type = data.get("update_type")
            payload = data.get("payload", {})
            
            if update_type == "invoice_paid":
                invoice_id = payload.get("invoice_id")
                invoice_payload = payload.get("payload")
                
                if not invoice_payload:
                    logger.warning("No payload in webhook")
                    return web.Response(status=200)
                
                # Находим платеж
                async for db in get_db():
                    result = await db.execute(
                        select(Payment).where(Payment.invoice_id == invoice_payload)
                    )
                    payment = result.scalar_one_or_none()
                    
                    if not payment:
                        logger.warning(f"Payment not found: {invoice_payload}")
                        return web.Response(status=200)
                    
                    if payment.status == "paid":
                        logger.info(f"Payment already processed: {invoice_payload}")
                        return web.Response(status=200)
                    
                    # Обновляем платеж
                    payment.status = "paid"
                    payment.paid_at = datetime.utcnow()
                    payment.crypto_pay_id = invoice_id
                    
                    # Активируем подписку
                    user = await db.get(User, payment.user_id)
                    plan = SUBSCRIPTION_PLANS[payment.plan]
                    
                    user.subscription_plan = payment.plan
                    user.subscription_status = SubscriptionStatus.ACTIVE
                    
                    # Если у пользователя уже есть активная подписка, продлеваем её
                    if user.subscription_expires and user.subscription_expires > datetime.utcnow():
                        user.subscription_expires += timedelta(days=plan["duration_days"])
                    else:
                        user.subscription_expires = datetime.utcnow() + timedelta(days=plan["duration_days"])
                    
                    # Создаем запись подписки
                    subscription = Subscription(
                        user_id=user.id,
                        plan=payment.plan,
                        status=SubscriptionStatus.ACTIVE,
                        expires_at=user.subscription_expires
                    )
                    
                    db.add(subscription)
                    await db.commit()
                    
                    logger.info(f"Subscription activated via webhook for user {user.telegram_id}, plan: {payment.plan}")
                    
                    # Можно отправить уведомление пользователю
                    # await send_subscription_notification(user.telegram_id, plan)
            
            return web.Response(status=200)
            
        except Exception as e:
            logger.error(f"Error processing crypto webhook: {e}", exc_info=True)
            return web.Response(status=500)
    
    app.router.add_post("/crypto_webhook", crypto_webhook)