"""
Движок суммаризации встреч
"""
import yaml
from pathlib import Path
from dataclasses import dataclass

import anthropic

from src.config import get_settings


@dataclass
class SummaryResult:
    """Результат суммаризации"""
    text: str
    meeting_type: str
    json_data: dict | None = None
    tasks: list | None = None


class SummarizerEngine:
    """Движок суммаризации на базе Claude"""

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Загрузить конфигурацию типов встреч"""
        config_path = Path(__file__).parent.parent.parent / "config" / "meeting_types.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    def _load_prompt(self, meeting_type: str) -> tuple[str, str]:
        """Загрузить промпт для типа встречи"""
        prompts_dir = Path(__file__).parent / "prompts"
        prompt_file = prompts_dir / f"{meeting_type}.md"

        if not prompt_file.exists():
            raise ValueError(f"Промпт для типа '{meeting_type}' не найден")

        content = prompt_file.read_text()

        # Парсим system и user промпты из файла
        # Формат: ## System Prompt\n```\n...\n```\n## User Prompt\n```\n...\n```
        system_prompt = ""
        user_prompt = ""

        # Простой парсинг (можно улучшить)
        if "## System Prompt" in content:
            parts = content.split("## User Prompt")
            system_part = parts[0].split("## System Prompt")[1]
            system_prompt = system_part.strip().strip("```").strip()

            if len(parts) > 1:
                user_prompt = parts[1].strip().strip("```").strip()

        return system_prompt, user_prompt

    async def summarize(
        self,
        transcript: str,
        meeting_type: str
    ) -> SummaryResult:
        """Создать саммари встречи"""
        type_config = self.config["meeting_types"].get(meeting_type)
        if not type_config:
            raise ValueError(f"Неизвестный тип встречи: {meeting_type}")

        system_prompt, user_prompt_template = self._load_prompt(meeting_type)

        # Подставляем транскрипт
        user_prompt = user_prompt_template.replace("{transcript}", transcript)

        # Вызов Claude
        defaults = self.config.get("defaults", {})
        message = self.client.messages.create(
            model=defaults.get("model", "claude-3-5-sonnet-20241022"),
            max_tokens=defaults.get("max_tokens", 4096),
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )

        result_text = message.content[0].text

        # Проверка лимита символов
        char_limit = type_config.get("char_limit")
        if char_limit and len(result_text) > char_limit:
            # TODO: Повторный запрос с просьбой сократить
            pass

        return SummaryResult(
            text=result_text,
            meeting_type=meeting_type,
            json_data=None,  # TODO: Парсить структурированные данные
            tasks=None       # TODO: Извлекать задачи
        )
