"""
Сервис разбиения текста на чанки для эмбеддинга
"""
from langchain.text_splitter import RecursiveCharacterTextSplitter


def chunk_transcript(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> list[str]:
    """
    Разбить транскрипт на чанки для эмбеддинга.

    Args:
        text: Текст транскрипта
        chunk_size: Размер чанка в символах
        chunk_overlap: Перекрытие между чанками

    Returns:
        Список чанков текста
    """
    if not text or not text.strip():
        return []

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", "! ", "? ", ", ", " ", ""]
    )

    chunks = splitter.split_text(text)
    return chunks


def chunk_transcript_with_metadata(
    text: str,
    meeting_title: str = "",
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> list[dict]:
    """
    Разбить транскрипт с метаданными для каждого чанка.

    Returns:
        Список словарей с chunk_text и metadata
    """
    chunks = chunk_transcript(text, chunk_size, chunk_overlap)

    return [
        {
            "chunk_text": chunk,
            "chunk_index": i,
            "metadata": {
                "meeting_title": meeting_title,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
        }
        for i, chunk in enumerate(chunks)
    ]
