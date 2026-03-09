"""
Сервис ИИ: чтение системного промпта из файла, выбор API по минимальному ping.
Поддержка: OpenAI (GPT-4o-mini), Yandex GPT, GigaChat.
GigaChat: GIGACHAT_CREDENTIALS = ключ авторизации (Base64 из ЛК) или client_id:client_secret.
"""
import asyncio
import base64
import logging
import os
import time
import uuid
from typing import Optional

from dotenv import load_dotenv

from config.loader import load_system_prompt

load_dotenv()
logger = logging.getLogger(__name__)

# Переменные окружения
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID")
GIGACHAT_CREDENTIALS = os.getenv("GIGACHAT_CREDENTIALS") or os.getenv("GIGACHAT_API_KEY")
GIGACHAT_CLIENT_ID = os.getenv("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = os.getenv("GIGACHAT_CLIENT_SECRET")

# Таймаут для ping и запроса (секунды)
PING_TIMEOUT = 10
REQUEST_TIMEOUT = 60


def _get_available_providers() -> list[str]:
    """Возвращает список провайдеров, для которых заданы ключи."""
    providers = []
    if OPENAI_API_KEY and OPENAI_API_KEY.strip():
        providers.append("openai")
    if YANDEX_API_KEY and YANDEX_API_KEY.strip() and YANDEX_FOLDER_ID:
        providers.append("yandex")
    has_giga = (
        (GIGACHAT_CREDENTIALS and GIGACHAT_CREDENTIALS.strip())
        or (GIGACHAT_CLIENT_ID and GIGACHAT_CLIENT_SECRET)
    )
    if has_giga:
        providers.append("gigachat")
    return providers


def get_ai_env_hint() -> str:
    """Подсказка для .env: какие переменные нужны для ИИ."""
    parts = [
        "Нужен хотя бы один провайдер в .env:",
        "• OpenAI: OPENAI_API_KEY=sk-...",
        "• Yandex GPT: YANDEX_API_KEY=... и YANDEX_FOLDER_ID=...",
        "• GigaChat: GIGACHAT_CREDENTIALS=ключ_из_ЛК (Base64) или GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET",
    ]
    return " ".join(parts)


async def _ping_openai() -> float:
    """Пинг OpenAI (минимальный запрос). Возвращает время в секундах или 1e9 при ошибке."""
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
        start = time.perf_counter()
        await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "1"}],
                max_tokens=5,
            ),
            timeout=PING_TIMEOUT,
        )
        return time.perf_counter() - start
    except Exception as e:
        logger.debug("OpenAI ping failed: %s", e)
        return 1e9


async def _ping_yandex() -> float:
    """Пинг Yandex GPT. Возвращает время в секундах или 1e9 при ошибке."""
    try:
        import aiohttp
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest",
            "completionOptions": {"stream": False, "maxTokens": "5"},
            "messages": [{"role": "user", "text": "1"}],
        }
        start = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=PING_TIMEOUT)) as resp:
                if resp.status != 200:
                    return 1e9
                await resp.json()
        return time.perf_counter() - start
    except Exception as e:
        logger.debug("Yandex ping failed: %s", e)
        return 1e9


def _get_gigachat_auth_key() -> Optional[str]:
    """Ключ авторизации (Base64) для OAuth. GIGACHAT_CREDENTIALS или base64(client_id:secret)."""
    if GIGACHAT_CREDENTIALS and GIGACHAT_CREDENTIALS.strip():
        return GIGACHAT_CREDENTIALS.strip()
    if GIGACHAT_CLIENT_ID and GIGACHAT_CLIENT_SECRET:
        raw = f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}"
        return base64.b64encode(raw.encode()).decode()
    return None


_gigachat_token_cache: Optional[tuple[str, float]] = None  # (token, expires_at)


async def _get_gigachat_access_token() -> Optional[str]:
    """Получает access_token через OAuth (ключ авторизации — Base64). Обновляет раз в ~25 мин."""
    global _gigachat_token_cache
    auth_key = _get_gigachat_auth_key()
    if not auth_key:
        return None
    # Проверка кэша (токен живёт ~30 мин, обновляем за 5 мин до истечения)
    if _gigachat_token_cache:
        token, expires = _gigachat_token_cache
        if time.time() < expires - 300:
            return token
    try:
        import aiohttp
        auth_url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Authorization": f"Basic {auth_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "RqUID": str(uuid.uuid4()),
        }
        body = "scope=GIGACHAT_API_PERS"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                auth_url,
                headers=headers,
                data=body,
                timeout=aiohttp.ClientTimeout(total=PING_TIMEOUT),
            ) as resp:
                if resp.status != 200:
                    err_text = await resp.text()
                    logger.warning("GigaChat OAuth: код %s, ответ: %s", resp.status, err_text[:200])
                    return None
                data = await resp.json()
        token = data.get("access_token") or data.get("accessToken")
        expires_at = data.get("expires_at", 0) or data.get("expiresAt", 0)
        if token:
            # expires_at — Unix timestamp в секундах; токен живёт 30 мин
            exp = float(expires_at) if expires_at else time.time() + 1800
            _gigachat_token_cache = (token, exp)
            return token
        return None
    except Exception as e:
        logger.debug("GigaChat token fetch failed: %s", e)
        return None


async def _ping_gigachat() -> float:
    """Пинг GigaChat. Возвращает время в секунды или 1e9 при ошибке."""
    try:
        import aiohttp
        token = await _get_gigachat_access_token()
        if not token:
            return 1e9
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"model": "GigaChat", "messages": [{"role": "user", "content": "1"}], "max_tokens": 5}
        start = time.perf_counter()
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=PING_TIMEOUT)) as resp:
                if resp.status != 200:
                    return 1e9
                await resp.json()
        return time.perf_counter() - start
    except Exception as e:
        logger.debug("GigaChat ping failed: %s", e)
        return 1e9


async def _select_provider() -> Optional[str]:
    """Выбирает провайдера с наименьшим ping."""
    providers = _get_available_providers()
    if not providers:
        logger.warning("Нет ни одного настроенного ИИ-провайдера в .env")
        return None
    pings = {}
    if "openai" in providers:
        pings["openai"] = await _ping_openai()
    if "yandex" in providers:
        pings["yandex"] = await _ping_yandex()
    if "gigachat" in providers:
        pings["gigachat"] = await _ping_gigachat()
    best = min(pings, key=pings.get)
    if pings[best] >= 1e9:
        logger.warning("Все провайдеры недоступны по ping")
        return None
    logger.info("Выбран ИИ-провайдер: %s (ping %.2f с)", best, pings[best])
    return best


async def _generate_openai(system_prompt: str, user_message: str) -> str:
    import openai
    client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)
    r = await asyncio.wait_for(
        client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1000,
        ),
        timeout=REQUEST_TIMEOUT,
    )
    return (r.choices[0].message.content or "").strip()


async def _generate_yandex(system_prompt: str, user_message: str) -> str:
    import aiohttp
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {"Authorization": f"Api-Key {YANDEX_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt-lite/latest",
        "completionOptions": {"stream": False, "maxTokens": "1000"},
        "messages": [
            {"role": "system", "text": system_prompt},
            {"role": "user", "text": user_message},
        ],
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            resp.raise_for_status()
            data = await resp.json()
    text = (data.get("result", {}).get("alternatives", [{}])[0].get("message", {}).get("text") or "")
    return text.strip()


async def _generate_gigachat(system_prompt: str, user_message: str) -> str:
    import aiohttp
    token = await _get_gigachat_access_token()
    if not token:
        raise RuntimeError("GigaChat: не удалось получить токен. Проверьте GIGACHAT_CREDENTIALS (ключ из ЛК) или GIGACHAT_CLIENT_ID + GIGACHAT_CLIENT_SECRET.")
    url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "model": "GigaChat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 1000,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
            resp.raise_for_status()
            data = await resp.json()
    text = (data.get("choices", [{}])[0].get("message", {}).get("content") or "")
    return text.strip()


# Кэш выбранного провайдера на сессию
_selected_provider: Optional[str] = None


async def generate_cover_letter(task_description: str) -> str:
    """
    Генерирует текст отклика по описанию задачи.
    Системный промпт читается из config/system_prompt.txt.
    Используется провайдер с минимальным ping (кэшируется после первого выбора).
    """
    global _selected_provider
    system_prompt = load_system_prompt()
    if _selected_provider is None:
        _selected_provider = await _select_provider()
    if _selected_provider is None:
        raise RuntimeError(get_ai_env_hint())
    if _selected_provider == "openai":
        return await _generate_openai(system_prompt, task_description)
    if _selected_provider == "yandex":
        return await _generate_yandex(system_prompt, task_description)
    if _selected_provider == "gigachat":
        return await _generate_gigachat(system_prompt, task_description)
    raise RuntimeError(f"Неизвестный провайдер: {_selected_provider}")
