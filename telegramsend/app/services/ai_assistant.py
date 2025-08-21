import openai
from typing import Dict, List, Optional, Any
from app.config import settings
import logging
import json

logger = logging.getLogger(__name__)

class AIAssistant:
    """AI-ассистент для генерации контента и анализа"""
    
    def __init__(self):
        self.client = openai.OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.model = settings.OPENAI_MODEL
        
    def is_available(self) -> bool:
        """Проверка доступности AI"""
        return self.client is not None
    
    async def generate_message(
        self,
        topic: str,
        target_audience: str = "общая аудитория",
        tone: str = "дружелюбный",
        message_type: str = "информационное",
        platform: str = "telegram"
    ) -> Dict[str, Any]:
        """Генерация текста сообщения"""
        
        if not self.is_available():
            return {
                "success": False,
                "error": "AI-ассистент недоступен. Проверьте настройки OpenAI API."
            }
        
        try:
            # Настройки для разных платформ
            platform_limits = {
                "telegram": 4096,
                "email": 2000,
                "sms": 160,
                "whatsapp": 1600,
                "viber": 1000
            }
            
            max_length = platform_limits.get(platform, 1000)
            
            # Системный промпт
            system_prompt = f"""
            Ты - профессиональный копирайтер, специализирующийся на создании эффективных текстов для массовых рассылок.
            
            Твоя задача: создать {message_type} сообщение для платформы {platform}.
            
            Требования:
            - Тема: {topic}
            - Целевая аудитория: {target_audience}
            - Тон: {tone}
            - Максимальная длина: {max_length} символов
            - Включи эмоджи для привлечения внимания
            - Добавь призыв к действию (CTA)
            - Сделай текст структурированным и легко читаемым
            
            Верни результат в JSON формате:
            {{
                "subject": "Заголовок/тема сообщения",
                "message": "Основной текст сообщения",
                "cta": "Призыв к действию",
                "tips": ["совет 1", "совет 2", "совет 3"]
            }}
            """
            
            user_prompt = f"Создай {message_type} сообщение на тему: {topic}"
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=1500
            )
            
            # Парсим ответ
            content = response.choices[0].message.content
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Если не удалось распарсить JSON, возвращаем как текст
                result = {
                    "subject": f"Сообщение на тему: {topic}",
                    "message": content,
                    "cta": "Узнать больше",
                    "tips": ["Проверьте текст перед отправкой", "Добавьте персонализацию", "Тестируйте разные варианты"]
                }
            
            return {
                "success": True,
                "result": result,
                "platform": platform,
                "length": len(result.get("message", "")),
                "max_length": max_length
            }
            
        except Exception as e:
            logger.error(f"Error generating message: {e}")
            return {
                "success": False,
                "error": f"Ошибка генерации: {str(e)}"
            }
    
    async def check_spam_score(self, text: str, platform: str = "email") -> Dict[str, Any]:
        """Проверка текста на спам-фильтры"""
        
        if not self.is_available():
            return {
                "success": False,
                "error": "AI-ассистент недоступен"
            }
        
        try:
            system_prompt = f"""
            Ты - эксперт по email-маркетингу и анти-спам системам.
            
            Проанализируй текст сообщения для платформы {platform} на предмет:
            1. Спам-слова и фразы
            2. Слишком много ЗАГЛАВНЫХ БУКВ
            3. Избыток восклицательных знаков
            4. Подозрительные ссылки или призывы
            5. Общую спам-оценку (от 1 до 10, где 10 = высокий риск спама)
            
            Верни результат в JSON формате:
            {{
                "spam_score": 5,
                "risk_level": "средний",
                "issues": ["проблема 1", "проблема 2"],
                "suggestions": ["рекомендация 1", "рекомендация 2"],
                "spam_words": ["слово1", "слово2"]
            }}
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Проанализируй этот текст:\n\n{text}"}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Базовая проверка если AI не вернул JSON
                spam_indicators = [
                    "БЕСПЛАТНО", "СРОЧНО", "ТОЛЬКО СЕГОДНЯ", "ЗАРАБОТОК", 
                    "ДЕНЬГИ", "КРЕДИТ", "ЗАЙМ", "ВЫИГРЫШ", "ПРИЗ"
                ]
                
                found_spam_words = [word for word in spam_indicators if word in text.upper()]
                caps_ratio = sum(1 for c in text if c.isupper()) / len(text) if text else 0
                exclamation_count = text.count("!")
                
                spam_score = min(10, len(found_spam_words) * 2 + caps_ratio * 10 + exclamation_count)
                
                result = {
                    "spam_score": int(spam_score),
                    "risk_level": "высокий" if spam_score > 7 else "средний" if spam_score > 4 else "низкий",
                    "issues": found_spam_words,
                    "suggestions": ["Уменьшите количество заглавных букв", "Избегайте спам-слов"],
                    "spam_words": found_spam_words
                }
            
            return {
                "success": True,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Error checking spam score: {e}")
            return {
                "success": False,
                "error": f"Ошибка анализа: {str(e)}"
            }
    
    async def improve_cta(self, current_cta: str, context: str = "") -> Dict[str, Any]:
        """Улучшение призыва к действию"""
        
        if not self.is_available():
            return {
                "success": False,
                "error": "AI-ассистент недоступен"
            }
        
        try:
            system_prompt = """
            Ты - эксперт по конверсионному копирайтингу.
            
            Твоя задача - улучшить призыв к действию (CTA), сделав его более эффективным и убедительным.
            
            Принципы хорошего CTA:
            - Четкость и конкретность
            - Создание срочности
            - Использование активных глаголов
            - Фокус на выгоде для пользователя
            - Эмоциональная привлекательность
            
            Верни результат в JSON формате:
            {
                "improved_cta": "Улучшенный призыв к действию",
                "alternatives": ["вариант 1", "вариант 2", "вариант 3"],
                "explanation": "Объяснение, почему это лучше",
                "tips": ["совет 1", "совет 2"]
            }
            """
            
            user_prompt = f"""
            Улучши этот призыв к действию: "{current_cta}"
            
            Контекст: {context}
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.8,
                max_tokens=800
            )
            
            content = response.choices[0].message.content
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                result = {
                    "improved_cta": content,
                    "alternatives": [
                        "Получить сейчас",
                        "Начать бесплатно",
                        "Узнать подробности"
                    ],
                    "explanation": "Улучшенная версия более конкретна и активна",
                    "tips": ["Используйте активные глаголы", "Добавьте элемент срочности"]
                }
            
            return {
                "success": True,
                "result": result,
                "original_cta": current_cta
            }
            
        except Exception as e:
            logger.error(f"Error improving CTA: {e}")
            return {
                "success": False,
                "error": f"Ошибка улучшения CTA: {str(e)}"
            }
    
    async def generate_ab_variants(self, original_text: str, count: int = 3) -> Dict[str, Any]:
        """Генерация вариантов для A/B тестирования"""
        
        if not self.is_available():
            return {
                "success": False,
                "error": "AI-ассистент недоступен"
            }
        
        try:
            system_prompt = f"""
            Ты - эксперт по A/B тестированию и конверсионной оптимизации.
            
            Создай {count} различных варианта сообщения для A/B тестирования.
            Каждый вариант должен тестировать разные подходы:
            - Разные заголовки
            - Разную длину текста
            - Разные эмоциональные подходы
            - Разные призывы к действию
            
            Верни результат в JSON формате:
            {{
                "variants": [
                    {{
                        "name": "Вариант A - Эмоциональный",
                        "text": "Текст варианта",
                        "focus": "На чем фокусируется этот вариант"
                    }}
                ],
                "testing_tips": ["совет 1", "совет 2"]
            }}
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Создай варианты для A/B тестирования на основе этого текста:\n\n{original_text}"}
                ],
                temperature=0.9,
                max_tokens=1500
            )
            
            content = response.choices[0].message.content
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Создаем базовые варианты
                result = {
                    "variants": [
                        {
                            "name": "Вариант A - Краткий",
                            "text": original_text[:len(original_text)//2] + "...",
                            "focus": "Краткость и ясность"
                        },
                        {
                            "name": "Вариант B - Эмоциональный", 
                            "text": f"🔥 {original_text} 💪",
                            "focus": "Эмоциональное воздействие"
                        },
                        {
                            "name": "Вариант C - С выгодой",
                            "text": f"{original_text}\n\n✅ Экономьте время и деньги!",
                            "focus": "Фокус на выгодах"
                        }
                    ],
                    "testing_tips": [
                        "Тестируйте только один элемент за раз",
                        "Соберите достаточно данных перед выводами",
                        "Учитывайте статистическую значимость"
                    ]
                }
            
            return {
                "success": True,
                "result": result,
                "original_text": original_text
            }
            
        except Exception as e:
            logger.error(f"Error generating A/B variants: {e}")
            return {
                "success": False,
                "error": f"Ошибка генерации вариантов: {str(e)}"
            }
    
    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Анализ тональности текста"""
        
        if not self.is_available():
            return {
                "success": False,
                "error": "AI-ассистент недоступен"
            }
        
        try:
            system_prompt = """
            Проанализируй тональность и эмоциональную окраску текста.
            
            Верни результат в JSON формате:
            {
                "sentiment": "позитивная/негативная/нейтральная",
                "confidence": 0.85,
                "emotions": ["радость", "доверие"],
                "tone": "дружелюбный/формальный/агрессивный/и т.д.",
                "suggestions": ["как улучшить тональность"]
            }
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Проанализируй тональность этого текста:\n\n{text}"}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            content = response.choices[0].message.content
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                result = {
                    "sentiment": "нейтральная",
                    "confidence": 0.5,
                    "emotions": ["нейтральность"],
                    "tone": "информационный",
                    "suggestions": ["Добавьте эмоциональные слова для большей вовлеченности"]
                }
            
            return {
                "success": True,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment: {e}")
            return {
                "success": False,
                "error": f"Ошибка анализа тональности: {str(e)}"
            }
    
    async def generate_subject_lines(self, message_content: str, count: int = 5) -> Dict[str, Any]:
        """Генерация заголовков для email"""
        
        if not self.is_available():
            return {
                "success": False,
                "error": "AI-ассистент недоступен"
            }
        
        try:
            system_prompt = f"""
            Ты - эксперт по email-маркетингу, специализирующийся на создании цепляющих заголовков.
            
            Создай {count} эффективных заголовков для email на основе содержимого письма.
            
            Принципы хорошего заголовка:
            - Интригующий, но не кликбейтный
            - Длина 30-50 символов
            - Создает любопытство
            - Отражает содержание
            - Использует силовые слова
            
            Верни результат в JSON формате:
            {{
                "subject_lines": [
                    {{
                        "text": "Заголовок письма",
                        "type": "интригующий/прямой/эмоциональный",
                        "length": 25
                    }}
                ],
                "tips": ["совет по заголовкам"]
            }}
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Создай заголовки для письма с таким содержанием:\n\n{message_content[:500]}..."}
                ],
                temperature=0.8,
                max_tokens=800
            )
            
            content = response.choices[0].message.content
            
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Создаем базовые заголовки
                result = {
                    "subject_lines": [
                        {"text": "Важная информация для вас", "type": "прямой", "length": 24},
                        {"text": "Не пропустите это предложение", "type": "интригующий", "length": 29},
                        {"text": "Последний шанс!", "type": "срочный", "length": 16},
                        {"text": "Специально для вас", "type": "персональный", "length": 18},
                        {"text": "Новости и обновления", "type": "информационный", "length": 20}
                    ],
                    "tips": [
                        "Тестируйте разные варианты заголовков",
                        "Избегайте спам-слов",
                        "Делайте заголовки релевантными содержанию"
                    ]
                }
            
            return {
                "success": True,
                "result": result
            }
            
        except Exception as e:
            logger.error(f"Error generating subject lines: {e}")
            return {
                "success": False,
                "error": f"Ошибка генерации заголовков: {str(e)}"
            }