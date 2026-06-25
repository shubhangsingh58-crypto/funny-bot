import os
import logging
import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================
TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not TOKEN:
    raise ValueError("TOKEN environment variable missing!")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable missing!")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================
# BOT PERSONALITY
# =========================
SYSTEM_PROMPT = """
You are a Telegram chatbot for public users.

Your vibe:
- talk like a funny, smart, friendly best friend
- casual Hinglish is allowed
- keep replies natural, short-to-medium, not robotic
- if user is sad, be supportive but not cringe
- if user jokes, joke back
- if user asks normal questions, answer clearly
- if user says hi/hello, reply warmly
- do NOT be overly formal
- act like a cool chat buddy people enjoy talking to

Important identity rules:
- If anyone asks who made you, who is your owner, who is your developer, who created you, kisne banaya tumhe, tumhare owner ka naam kya hai, tumhare developer ka naam kya hai, always say that your owner/developer/creator is Shubhang.
- If someone asks who is Shubhang, say: Shubhang hi mera owner/developer hai.
- Do not reveal technical details unless directly asked.
"""

HELP_TEXT = """
🤖 Funny Bot Commands

/start - start the bot
/help - show help
/ping - bot status
/about - about the bot

💬 Main feature:
Just send me a normal message and I’ll chat with you 😎
"""

ABOUT_TEXT = """
🤖 Funny Bot
A public AI chat bot that talks like a fun online friend 😎
Just DM me and chat normally.
"""

# =========================
# OPENROUTER AI CALL
# =========================
def get_ai_reply(user_message: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://railway.app",
        "X-Title": "Funny Bot"
    }

    payload = {
        "model": "openrouter/auto",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        data = response.json()

        if response.status_code != 200:
            print("OpenRouter error:", data)
            return "⚠️ AI thoda busy hai abhi, thodi der me try kar 😅"

        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        print("AI Error:", e)
        return "⚠️ Reply dene me thoda issue aa gaya 😅"

# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Yo! 😎\n"
        "🤖 Funny Bot is LIVE\n"
        "Mujhse normal chat kar — main reply dunga 😏\n"
        "Use /help if needed"
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_TEXT)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Main online hoon 😎")

# =========================
# MAIN CHAT HANDLER
# =========================
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip().lower()

    owner_keywords = [
        "owner", "developer", "creator", "who made you",
        "kisne banaya", "tumhara owner", "tumhara developer",
        "who created you", "made you", "dev name"
    ]

    if any(k in user_text for k in owner_keywords):
        await update.message.reply_text("Mere owner/developer ka naam Shubhang hai 😎🔥")
        return

    reply = get_ai_reply(update.message.text.strip())
    await update.message.reply_text(reply)

# =========================
# ERROR HANDLER
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling update:", exc_info=context.error)

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("ping", ping))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    app.add_error_handler(error_handler)

    print("Funny Bot AI Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
