import os
import requests
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


def tavily_search(query: str, search_depth: str = "basic", max_results: int = 5) -> dict:
    response = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": TAVILY_API_KEY, "query": query, "search_depth": search_depth, "max_results": max_results},
        timeout=15
    )
    return response.json() if response.ok else {"results": []}

DOCS_DIR = Path("documents")
DOCS_DIR.mkdir(exist_ok=True)

TOOLS = [
    {
        "name": "search_web",
        "description": "Поиск актуальной информации в интернете. Используй для исследования рынка, конкурентов, трендов, макроэкономики РФ, мирового кризиса, AI-технологий для бизнеса.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос"},
                "depth": {"type": "string", "enum": ["basic", "advanced"], "description": "basic — быстрый, advanced — глубокий"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "analyze_niche",
        "description": "Глубокий анализ AI-ниши для бизнеса: спрос, конкуренты, потенциал рынка в РФ и мире.",
        "input_schema": {
            "type": "object",
            "properties": {
                "niche": {"type": "string", "description": "Описание ниши для анализа"}
            },
            "required": ["niche"]
        }
    },
    {
        "name": "psychology_insight",
        "description": "Анализ с точки зрения поведенческой психологии, психологии собственника бизнеса и нейроотличных предпринимателей.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Тема для психологического анализа"}
            },
            "required": ["topic"]
        }
    },
    {
        "name": "read_documents",
        "description": "Читает загруженные пользователем книги и документы.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Что найти в документах"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "write_content",
        "description": "Создаёт тексты: посты, письма, питчи, КП, отчёты.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content_type": {"type": "string", "description": "Тип: пост, письмо, питч, отчёт, КП"},
                "topic": {"type": "string", "description": "Тема"},
                "context": {"type": "string", "description": "Дополнительный контекст"}
            },
            "required": ["content_type", "topic"]
        }
    }
]


def execute_tool(name: str, inputs: dict) -> str:
    try:
        if name == "search_web":
            depth = inputs.get("depth", "basic")
            results = tavily_search(query=inputs["query"], search_depth=depth, max_results=5)
            items = []
            for r in results.get("results", []):
                items.append(f"**{r.get('title', '')}**\n{r.get('content', '')[:600]}\nИсточник: {r.get('url', '')}")
            return "\n\n".join(items) or "Результатов не найдено."

        elif name == "analyze_niche":
            niche = inputs["niche"]
            queries = [
                f"{niche} рынок Россия 2025 спрос",
                f"{niche} AI SaaS конкуренты стартапы",
                f"{niche} B2B бизнес тренды"
            ]
            all_results = []
            for q in queries:
                r = tavily_search(query=q, search_depth="advanced", max_results=3)
                for item in r.get("results", []):
                    all_results.append(f"{item.get('title', '')}: {item.get('content', '')[:400]}")
            return "\n\n".join(all_results) or "Данных не найдено."

        elif name == "psychology_insight":
            queries = [
                f"поведенческая психология бизнес {inputs['topic']}",
                f"психология собственника {inputs['topic']}",
                f"СДВГ предпринимательство {inputs['topic']}"
            ]
            all_results = []
            for q in queries:
                r = tavily_search(query=q, search_depth="basic", max_results=2)
                for item in r.get("results", []):
                    all_results.append(item.get("content", "")[:400])
            return "\n\n".join(all_results) or "Данных не найдено."

        elif name == "read_documents":
            docs = list(DOCS_DIR.glob("*.txt"))
            if not docs:
                return "Документы не загружены. Пришли файл в Telegram."
            query_words = inputs["query"].lower().split()
            results = []
            for doc in docs:
                text = doc.read_text(encoding="utf-8", errors="ignore")
                paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
                relevant = [p for p in paragraphs if any(w in p.lower() for w in query_words)]
                if relevant:
                    results.append(f"Из «{doc.stem}»:\n" + "\n".join(relevant[:8]))
            return "\n\n".join(results) or "Релевантных данных не найдено."

        elif name == "write_content":
            return (
                f"Задание: создать {inputs['content_type']} на тему «{inputs['topic']}». "
                f"Контекст: {inputs.get('context', 'не указан')}. Напиши текст."
            )

    except Exception as e:
        return f"Ошибка {name}: {str(e)}"

    return "Инструмент не найден."


ORCHESTRATOR_PROMPT = """Ты — система AI-агентов для бизнес-стратегии. Инструменты:
- search_web: поиск в интернете (рынок, тренды, конкуренты, макроэкономика РФ, мировой кризис)
- analyze_niche: анализ AI-ниши для B2B
- psychology_insight: поведенческая психология, психология собственника, нейроотличия
- read_documents: чтение книг и материалов пользователя
- write_content: тексты, посты, письма, питчи, отчёты

Профиль пользователя:
{profile}

Правила:
- Для сложных запросов используй несколько инструментов
- Структурируй ответы: заголовки, списки, выводы
- Давай конкретные рекомендации
- Отвечай только на русском языке"""


async def run_agents(user_message: str, profile: str, history: list) -> str:
    system = ORCHESTRATOR_PROMPT.format(profile=profile)
    messages = history[-10:] + [{"role": "user", "content": user_message}]

    for _ in range(6):
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            break

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = execute_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })

        if not tool_results:
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            break

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    return "Не удалось получить ответ. Попробуй переформулировать запрос."
