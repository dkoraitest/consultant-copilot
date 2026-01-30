"""
Интеграция с Fireflies.ai
"""
import httpx

from src.config import get_settings


class FirefliesClient:
    """Клиент для Fireflies GraphQL API"""

    API_URL = "https://api.fireflies.ai/graphql"

    def __init__(self):
        settings = get_settings()
        self.api_key = settings.fireflies_api_key

    async def get_transcript(self, meeting_id: str) -> dict:
        """Получить полный транскрипт встречи"""
        query = """
        query GetTranscript($id: String!) {
            transcript(id: $id) {
                id
                title
                date
                duration
                sentences {
                    speaker_name
                    text
                    start_time
                    end_time
                }
                summary {
                    overview
                    action_items
                }
            }
        }
        """

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.API_URL,
                json={
                    "query": query,
                    "variables": {"id": meeting_id}
                },
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            response.raise_for_status()
            return response.json()["data"]["transcript"]

    def format_transcript(self, transcript_data: dict) -> str:
        """Форматировать транскрипт в текст"""
        sentences = transcript_data.get("sentences", [])
        lines = []

        for sentence in sentences:
            speaker = sentence.get("speaker_name", "Unknown")
            text = sentence.get("text", "")
            lines.append(f"{speaker}: {text}")

        return "\n".join(lines)
