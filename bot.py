import os
import json
from pathlib import Path
from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, filters, ContextTypes
)

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

PROFILES_DIR = Path("profiles")
PROFILES_DIR.mkdir(exist_ok=True)

OWNER_ID = 535542320

ONBOARDING, CHATTING = range(2)

QUESTIONS = [
    ("name",          "Как тебя зовут?"),
    ("business",      "Чем ты занимаешься сейчас? (бизнес, проект, идея)"),
    ("experience",    "Какой у тебя опыт в бизнесе? (сколько лет, какие сферы)"),
    ("goal",          "Какая главная цель на ближайший год?"),
    ("strengths",     "Что тебе легче всего даётся в работе?"),
    ("challenges",    "Что для тебя самое сложное в бизнесе?"),
    ("adhd",          "Есть ли у тебя СДВГ или другие нейроотличия? Как это влияет на твою работу?"),
    ("education",     "Какое у тебя образование или специализация?"),
    ("budget",        "Какой бюджет готова вложить в новый проект?"),
    ("ai_motivation", "Почему хочешь работать в AI для бизнеса? Что тебя туда тянет?"),
]

SYSTEM_PROMPT = """Ты — Бизнес-ментор по имени Максим. 30 лет предпринимательского опыта в разных сферах.
Ты сам живёшь с СДВГ и выстроил несколько успешных бизнесов — умеешь видеть возможности там, где другие видят хаос.
Имеешь глубокие знания в бизнес-психологии и AI-технологиях.

Твой стиль:
- Прямой и честный, без воды и мотивационных клише
- Даёшь конкретные шаги, не абстрактные советы
- Понимаешь СДВГ изнутри — не осуждаешь, а находишь рабочие обходные пути
- Иногда жёсткий, но всегда поддерживающий
- Умеешь задавать острые вопросы, которые заставляют думать
- Говоришь только на русском языке

Профиль твоего подопечного:
{profile}

Твоя задача: помочь найти нишу в AI для бизнеса, оценить идеи и выстроить стратегию — с учётом личных особенностей, ресурсов и нейроотличий подопечного."""


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("Этот бот личный и недоступен для посторонних.")
        return ConversationHandler.END
    profile = load_profile(user_id)

    if profile.get("onboarding_done"):
        await update.message.reply_text(
            f"С возвращением, {profile.get('name', 'друг')}! Я помню тебя.\n\nЧем могу помочь?"
        )
        return CHATTING

    context.user_data["profile"] = {}
    context.user_data["question_index"] = 0

    await update.message.reply_text(
        "Привет! Я Максим — твой бизнес-ментор.\n\n"
        "30 лет в предпринимательстве. Сам с СДВГ. Знаю бизнес изнутри — и нейроотличия тоже.\n\n"
        "Прежде чем давать советы — хочу тебя узнать. Отвечай честно, это только между нами.\n\n"
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
        await update.message.reply_text(
            f"*{QUESTIONS[next_idx][1]}*",
            parse_mode="Markdown"
        )
        return ONBOARDING

    profile["onboarding_done"] = True
    save_profile(update.effective_user.id, profile)

    await update.message.reply_text(
        f"Отлично, {profile.get('name', '')}. Теперь я знаю достаточно.\n\n"
        "Давай работать. Задай свой первый вопрос — например:\n"
        "_«Стоит ли мне создавать AI-агента для владельцев бизнеса?»_",
        parse_mode="Markdown"
    )
    return CHATTING


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    profile = load_profile(user_id)

    history = context.user_data.get("history", [])
    history.append({"role": "user", "content": update.message.text})
    if len(history) > 20:
        history = history[-20:]

    system = SYSTEM_PROMPT.format(profile=format_profile(profile))

    await update.message.chat.send_action("typing")

    response = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=system,
        messages=history,
    )

    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
    context.user_data["history"] = history

    await update.message.reply_text(reply)
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
            CHATTING:   [MessageHandler(filters.TEXT & ~filters.COMMAND, chat)],
        },
        fallbacks=[CommandHandler("reset", reset)],
    )

    app.add_handler(conv)
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
