from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database.database import get_db
from app.database.models import User, Payment, Subscription, SubscriptionStatus
from app.utils.keyboards import subscription_keyboard, back_keyboard, confirm_keyboard
from app.utils.decorators import handle_errors, log_user_action
from app.services.crypto_pay import CryptoPay
from app.config import SUBSCRIPTION_PLANS
from datetime import datetime, timedelta
import uuid
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(F.text == "💳 Подписка")
@handle_errors
@log_user_action("subscription_menu")
async def subscription_menu(message: types.Message):
    """Меню подписок"""
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await message.answer("Пользователь не найден. Используйте /start")
            return
        
        subscription_text = "💳 <b>Управление подпиской</b>\n\n"
        
        if user.subscription_status == SubscriptionStatus.ACTIVE and user.subscription_expires:
            days_left = (user.subscription_expires - datetime.utcnow()).days
            subscription_text += (
                f"✅ <b>Текущая подписка:</b> {user.subscription_plan.capitalize()}\n"
                f"📅 <b>Действует до:</b> {user.subscription_expires.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏰ <b>Осталось дней:</b> {days_left}\n\n"
            )
            
            if days_left <= 7:
                subscription_text += "⚠️ <b>Подписка скоро истечет! Продлите для продолжения работы.</b>\n\n"
        else:
            subscription_text += "❌ <b>Активной подписки нет</b>\n\n"
        
        subscription_text += "🎯 <b>Доступные тарифы:</b>\n\n"
        
        for plan_id, plan in SUBSCRIPTION_PLANS.items():
            price_usd = plan["price"] / 100
            subscription_text += (
                f"💼 <b>{plan['name']}</b> - ${price_usd:.2f}/мес\n"
                f"📊 Лимиты: {plan['senders_limit']} отправителей, {plan['contacts_limit']:,} контактов\n"
            )
            for feature in plan["features"]:
                subscription_text += f"  ✓ {feature}\n"
            subscription_text += "\n"
        
        await message.answer(
            subscription_text,
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )

@router.callback_query(F.data.startswith("subscribe_"))
@handle_errors
@log_user_action("subscribe_plan")
async def subscribe_plan(callback: types.CallbackQuery):
    """Оформление подписки"""
    plan_id = callback.data.split("_")[1]
    
    if plan_id not in SUBSCRIPTION_PLANS:
        await callback.answer("Неверный план подписки", show_alert=True)
        return
    
    plan = SUBSCRIPTION_PLANS[plan_id]
    
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Создаем платеж
        payment = Payment(
            user_id=user.id,
            invoice_id=str(uuid.uuid4()),
            amount=plan["price"],
            currency="USD",
            status="pending",
            plan=plan_id
        )
        
        db.add(payment)
        await db.commit()
        
        # Создаем инвойс через CryptoPay
        crypto_pay = CryptoPay()
        try:
            invoice = await crypto_pay.create_invoice(
                amount=plan["price"] / 100,  # CryptoPay принимает USD
                currency="USD",
                description=f"Подписка {plan['name']} на 30 дней",
                payload=payment.invoice_id
            )

            payment.crypto_pay_id = str(invoice["invoice_id"])
            await db.commit()
            
            price_usd = plan["price"] / 100
            payment_text = (
                f"💳 <b>Оплата подписки {plan['name']}</b>\n\n"
                f"💰 <b>Стоимость:</b> ${price_usd:.2f}\n"
                f"⏰ <b>Период:</b> 30 дней\n\n"
                f"🔒 <b>Что входит:</b>\n"
            )
            
            for feature in plan["features"]:
                payment_text += f"✓ {feature}\n"
            
            payment_text += (
                f"\n📱 Нажмите кнопку ниже для оплаты через CryptoPay\n"
                f"💎 Принимаем: BTC, ETH, USDT, TON и другие криптовалюты"
            )
            
            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(
                        text="💳 Оплатить",
                        url=invoice["pay_url"]
                    )],
                    [types.InlineKeyboardButton(
                        text="🔄 Проверить оплату",
                        callback_data=f"check_payment_{payment.invoice_id}"
                    )],
                    [types.InlineKeyboardButton(
                        text="◀️ Назад",
                        callback_data="subscription_menu"
                    )]
                ]
            )
            
            await callback.message.edit_text(
                payment_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"Error creating invoice: {e}")
            await callback.answer("Ошибка создания платежа. Попробуйте позже.", show_alert=True)

@router.callback_query(F.data.startswith("check_payment_"))
@handle_errors
async def check_payment(callback: types.CallbackQuery):
    """Проверка статуса платежа"""
    invoice_id = callback.data.split("_", 2)[2]
    
    async for db in get_db():
        result = await db.execute(
            select(Payment).where(Payment.invoice_id == invoice_id)
        )
        payment = result.scalar_one_or_none()
        
        if not payment:
            await callback.answer("Платеж не найден", show_alert=True)
            return
        
        # Проверяем статус через CryptoPay
        crypto_pay = CryptoPay()
        try:
            # Получаем информацию об инвойсе
            invoices = await crypto_pay.get_invoices(invoice_ids=payment.crypto_pay_id)
            
            if not invoices or len(invoices) == 0:
                await callback.answer("Платеж не найден в CryptoPay", show_alert=True)
                return
                
            invoice_data = invoices[0]
            
            if invoice_data.get("status") == "paid":
                # Обновляем платеж
                payment.status = "paid"
                payment.paid_at = datetime.utcnow()
                
                # Активируем подписку
                user = await db.get(User, payment.user_id)
                plan = SUBSCRIPTION_PLANS[payment.plan]
                
                user.subscription_plan = payment.plan
                user.subscription_status = SubscriptionStatus.ACTIVE
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
                
                success_text = (
                    f"🎉 <b>Подписка {plan['name']} активирована!</b>\n\n"
                    f"✅ <b>Статус:</b> Активна\n"
                    f"📅 <b>Действует до:</b> {user.subscription_expires.strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"🎯 <b>Ваши возможности:</b>\n"
                )
                
                for feature in plan["features"]:
                    success_text += f"✓ {feature}\n"
                
                success_text += "\nТеперь вы можете пользоваться всеми функциями бота! 🚀"
                
                keyboard = types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [types.InlineKeyboardButton(text="◀️ Главное меню", callback_data="back_to_menu")]
                    ]
                )
                
                await callback.message.edit_text(
                    success_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
                
                logger.info(f"Subscription activated for user {user.telegram_id}, plan: {payment.plan}")
                
            elif invoice_data.get("status") == "expired":
                payment.status = "expired"
                await db.commit()
                await callback.answer("Платеж истек. Создайте новый.", show_alert=True)
                
            else:
                await callback.answer("Платеж еще не подтвержден. Попробуйте позже.")
                
        except Exception as e:
            logger.error(f"Error checking payment: {e}")
            await callback.answer("Ошибка проверки платежа. Попробуйте позже.", show_alert=True)

@router.callback_query(F.data == "subscription_menu")
@handle_errors
async def back_to_subscription(callback: types.CallbackQuery):
    """Возврат к меню подписок"""
    # Получаем пользователя для меню подписок
    async for db in get_db():
        result = await db.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("Пользователь не найден. Используйте /start")
            return
        
        subscription_text = "💳 <b>Управление подпиской</b>\n\n"
        
        if user.subscription_status == SubscriptionStatus.ACTIVE and user.subscription_expires:
            days_left = (user.subscription_expires - datetime.utcnow()).days
            subscription_text += (
                f"✅ <b>Текущая подписка:</b> {user.subscription_plan.capitalize()}\n"
                f"📅 <b>Действует до:</b> {user.subscription_expires.strftime('%d.%m.%Y %H:%M')}\n"
                f"⏰ <b>Осталось дней:</b> {days_left}\n\n"
            )
            
            if days_left <= 7:
                subscription_text += "⚠️ <b>Подписка скоро истечет! Продлите для продолжения работы.</b>\n\n"
        else:
            subscription_text += "❌ <b>Активной подписки нет</b>\n\n"
        
        subscription_text += "🎯 <b>Доступные тарифы:</b>\n\n"
        
        for plan_id, plan in SUBSCRIPTION_PLANS.items():
            price_usd = plan["price"] / 100
            subscription_text += (
                f"💼 <b>{plan['name']}</b> - ${price_usd:.2f}/мес\n"
                f"📊 Лимиты: {plan['senders_limit']} отправителей, {plan['contacts_limit']:,} контактов\n"
            )
            for feature in plan["features"]:
                subscription_text += f"  ✓ {feature}\n"
            subscription_text += "\n"
        
        await callback.message.edit_text(
            subscription_text,
            parse_mode="HTML",
            reply_markup=subscription_keyboard()
        )