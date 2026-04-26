import os
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)
from agents import run_agents

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PROFILES_DIR = Path("profiles")
DOCS_DIR = Path("documents")
PROFILES_DIR.mkdir(exist_ok=True)
DOCS_DIR.mkdir(exist_ok=True)

OWNER_ID = 535542320

ONBOARDING, CHATTING = range(2)

QUESTIONS = [
    ("name",          "Как тебя зовут?"),
    ("business",      "Чем ты занимаешься сейчас? (бизнес, проект, идея)"),
    ("experience",    "Какой у тебя опыт в бизнесе? (сколько лет, какие сферы)"),
    ("goal",          "Какая главная цель на ближайший год?"),
    ("strengths",     "Что тебе легче всего даётся в работе?"),
    ("challenges",    "Что для тебя самое сложное в бизнесе?"),
    ("adhd",          "Есть ли у тебя СДВГ или другие нейроотличия? Как это влияет на работу?"),
    ("education",     "Какое у тебя образование или специализация?"),
    ("budget",        "Какой бюджет готова вложить в новый проект?"),
    ("ai_motivation", "Почему хочешь работать в AI для бизнеса? Что тебя туда тянет?"),
]


def load_profile(user_id: int) -> dict:
    path = PROFILES_DIR / f"{user_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_profile(user_id: int, profile: dict):
    path = PROFILES_DIR / f"{user_id}.json"
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def format_profile(profile: dict) -> str:
    labels = {
        "name":          "Имя",
        "business":      "Деятельность",
        "experience":    "Опыт в бизнесе",
        "goal":          "Цель на год",
        "strengths":     "Сильные стороны",
        "challenges":    "Сложности",
        "adhd":          "СДВГ / нейроотличия",
        "education":     "Образование",
        "budget":        "Бюджет",
        "ai_motivation": "Мотивация в AI",
    }
    lines = [f"{label}: {profile[key]}" for key, label in labels.items() if key in profile]
    return "\n".join(lines) if lines else "Профиль не заполнен."


def read_docx(path: str) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        return

    doc = update.message.document
    file_name = doc.file_name or "document"
    ext = Path(file_name).suffix.lower()

    if ext not in [".docx", ".txt"]:
        await update.message.reply_text(f"Формат {ext} не поддерживается. Пришли .docx или .txt")
        return

    await update.message.reply_text(f"Читаю «{file_name}»...")

    tg_file = await doc.get_file()
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_path = tmp.name

    await tg_file.download_to_drive(tmp_path)

    try:
        if ext == ".docx":
            text = read_docx(tmp_path)
        else:
            text = Path(tmp_path).read_text(encoding="utf-8", errors="ignore")

        text = text[:50000]
        save_path = DOCS_DIR / f"{Path(file_name).stem}.txt"
        save_path.write_text(text, encoding="utf-8")

        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=512,
            system="Отвечай только на русском языке.",
            messages=[{"role": "user", "content": f"Кратко (5 предложений) — о чём этот документ?\n\n{text[:8000]}"}]
        )
        summary = response.content[0].text

        await update.message.reply_text(
            f"Документ «{file_name}» сохранён.\n\n*Краткое содержание:*\n{summary}",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка при чтении: {str(e)}")
    finally:
        os.unlink(tmp_path)

    return CHATTING


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Этот бот личный и недоступен для посторонних.")
        return ConversationHandler.END

    profile = load_profile(user_id)

    if profile.get("onboarding_done"):
        await update.message.reply_text(
            f"С возвращением, {profile.get('name', 'друг')}!\n\n"
            "Система агентов готова. Можешь:\n"
            "— Задать вопрос про рынок, нишу или стратегию\n"
            "— Прислать документ (.docx или .txt) для изучения\n"
            "— Попросить написать текст, пост или письмо"
        )
        return CHATTING

    context.user_data["profile"] = {}
    context.user_data["question_index"] = 0

    await update.message.reply_text(
        "Привет! Я Максим — твой бизнес-ментор и система AI-агентов.\n\n"
        "Умею искать информацию в интернете, анализировать рынки, читать документы и писать тексты.\n\n"
        "Сначала познакомимся. Отвечай честно.\n\n"
        f"*{QUESTIONS[0][1]}*",
        parse_mode="Markdown"
    )
    return ONBOARDING


async def onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("question_index", 0)
    profile = context.user_data.get("profile", {})

    key, _ = QUESTIONS[idx]
    profile[key] = update.message.text
    context.user_data["profile"] = profile

    next_idx = idx + 1
    context.user_data["question_index"] = next_idx

    if next_idx < len(QUESTIONS):
        await update.message.reply_text(f"*{QUESTIONS[next_idx][1]}*", parse_mode="Markdown")
        return ONBOARDING

    profile["onboarding_done"] = True
    save_profile(update.effective_user.id, profile)

    await update.message.reply_text(
        f"Отлично, {profile.get('name', '')}. Теперь я знаю тебя.\n\n"
        "Система агентов активирована. Задай первый вопрос!\n"
        "_Например: «Проанализируй рынок AI-инструментов для малого бизнеса в России»_",
        parse_mode="Markdown"
    )
    return CHATTING


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = load_profile(user_id)
    history = context.user_data.get("history", [])

    await update.message.chat.send_action("typing")

    reply = await run_agents(
        user_message=update.message.text,
        profile=format_profile(profile),
        history=history
    )

    history.append({"role": "user", "content": update.message.text})
    history.append({"role": "assistant", "content": reply})
    if len(history) > 20:
        history = history[-20:]
    context.user_data["history"] = history

    # Telegram лимит 4096 символов — делим длинные ответы
    if len(reply) <= 4096:
        await update.message.reply_text(reply)
    else:
        for i in range(0, len(reply), 4096):
            await update.message.reply_text(reply[i:i+4096])

    return CHATTING


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    path = PROFILES_DIR / f"{update.effective_user.id}.json"
    if path.exists():
        path.unlink()
    context.user_data.clear()
    await update.message.reply_text("Профиль удалён. Напиши /start чтобы начать заново.")
    return ConversationHandler.END


def main():
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ONBOARDING: [MessageHandler(filters.TEXT & ~filters.COMMAND, onboarding)],
            CHATTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat),
                MessageHandler(filters.Document.ALL, handle_document),
            ],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    app.add_handler(conv)
    print("Бот с агентами запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
