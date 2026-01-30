"""
Интеграция с Todoist
"""
from todoist_api_python import TodoistAPI

from src.config import get_settings


class TodoistIntegration:
    """Работа с задачами в Todoist"""

    def __init__(self):
        settings = get_settings()
        self.api = TodoistAPI(settings.todoist_api_token)
        self.default_project_id = settings.todoist_default_project_id

    def create_task(
        self,
        content: str,
        due_date: str | None = None,
        project_id: str | None = None,
        labels: list | None = None
    ) -> dict:
        """Создать задачу"""
        task = self.api.add_task(
            content=content,
            due_string=due_date,
            project_id=project_id or self.default_project_id,
            labels=labels or []
        )
        return {
            "id": task.id,
            "content": task.content,
            "url": task.url
        }

    def list_tasks(self, project_id: str | None = None) -> list:
        """Получить незавершённые задачи"""
        tasks = self.api.get_tasks(project_id=project_id)
        return [
            {
                "id": t.id,
                "content": t.content,
                "due": t.due.string if t.due else None,
                "url": t.url
            }
            for t in tasks
        ]

    def complete_task(self, task_id: str) -> bool:
        """Завершить задачу"""
        return self.api.close_task(task_id)

    def get_task(self, task_id: str) -> dict | None:
        """Получить задачу по ID"""
        try:
            task = self.api.get_task(task_id)
            return {
                "id": task.id,
                "content": task.content,
                "due": task.due.string if task.due else None
            }
        except Exception:
            return None
