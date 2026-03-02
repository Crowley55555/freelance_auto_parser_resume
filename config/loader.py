"""
Загрузка конфигурации: селекторы из JSON и системный промпт из файла.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent
SELECTORS_PATH = CONFIG_DIR / "selectors.json"
SYSTEM_PROMPT_PATH = CONFIG_DIR / "system_prompt.txt"


def load_selectors() -> dict:
    """Загружает селекторы из config/selectors.json."""
    try:
        with open(SELECTORS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Не удалось загрузить селекторы из %s: %s. Используются значения по умолчанию.", SELECTORS_PATH, e)
        return {
            "order": {
                "description": ".b-post__txt, .b-post__body",
                "cover_letter_input": "textarea[name='descr'], #descr",
                "submit_button": "input[type='submit'], button[type='submit']",
                "resume_file_input": "input[type='file']",
            },
            "success": {"indicator": ".b-notify__success, .success-message"},
            "captcha": {"indicator": ".captcha, .g-recaptcha"},
        }


def load_system_prompt() -> str:
    """Читает системный промпт из config/system_prompt.txt."""
    try:
        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning("Файл системного промпта не найден: %s", SYSTEM_PROMPT_PATH)
        return "Ты — опытный Python-разработчик. Пиши краткое сопроводительное письмо к отклику на заказ. Стиль: конкретный, технический, без воды."
