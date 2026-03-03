"""
Загрузка конфигурации: селекторы из JSON (DRY — одна функция с параметрами) и системный промпт из файла.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent
SELECTORS_PATH = CONFIG_DIR / "selectors.json"
SELECTORS_KWORK_PATH = CONFIG_DIR / "selectors_kwork.json"
SYSTEM_PROMPT_PATH = CONFIG_DIR / "system_prompt.txt"

# Дефолты селекторов по платформам (для fallback при ошибке загрузки файла)
DEFAULT_SELECTORS_FL = {
    "order": {
        "description": ".b-post__txt, .b-post__body",
        "cover_letter_input": "textarea[name='descr'], #descr",
        "submit_button": "input[type='submit'], button[type='submit']",
        "resume_file_input": "input[type='file']",
    },
    "success": {"indicator": ".b-notify__success, .success-message"},
    "captcha": {"indicator": ".captcha, .g-recaptcha"},
}

DEFAULT_SELECTORS_KWORK = {
    "order": {
        "description": ".wysiwyg, .project-description",
        "cover_letter_input": "textarea[name='message'], #message",
        "resume_file_input": "input[type='file']",
    },
}


def load_selectors_json(path: Path, default: dict, log_name: str = "селекторы") -> dict:
    """
    Загружает селекторы из JSON-файла. При ошибке возвращает default.
    Одна реализация для обеих платформ (DRY).
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Не удалось загрузить %s из %s: %s. Используются значения по умолчанию.", log_name, path, e)
        return default


def load_selectors() -> dict:
    """Загружает селекторы fl.ru из config/selectors.json."""
    return load_selectors_json(SELECTORS_PATH, DEFAULT_SELECTORS_FL, "селекторы fl.ru")


def load_selectors_kwork() -> dict:
    """Загружает селекторы Kwork из config/selectors_kwork.json."""
    return load_selectors_json(SELECTORS_KWORK_PATH, DEFAULT_SELECTORS_KWORK, "селекторы Kwork")


def load_system_prompt() -> str:
    """Читает системный промпт из config/system_prompt.txt."""
    try:
        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning("Файл системного промпта не найден: %s", SYSTEM_PROMPT_PATH)
        return "Ты — опытный Python-разработчик. Пиши краткое сопроводительное письмо к отклику на заказ. Стиль: конкретный, технический, без воды."
