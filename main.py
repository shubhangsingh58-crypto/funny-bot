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
TOKEN = os.getenv("8851707170:AAEeG4HQQG-QqROP1xn87gh5w5ZTC435PWs")
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
- do NOT say you are an AI unless directly asked
- do not be overly formal
- act like a cool chat buddy people enjoy talking to
"""

HELP_TEXT = """
🤖 *Funny Bot Commands*

/start - start the bot
/help - show help
/ping - bot status
/about - about the bot

💬 Main feature:
Just send me a normal message and I’ll chat with you 😎
"""

ABOUT_TEXT = """
🤖 *Funny Bot*
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
        "🤖 *Funny Bot is LIVE*\n"
        "Mujhse normal chat kar — main reply dunga 😏\n"
        "Use /help if needed"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_TEXT, parse_mode="Markdown")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Main online hoon 😎")

# =========================
# MAIN CHAT HANDLER
# =========================
async def chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text.strip()

    # typing indicator optional feel
    await update.message.chat.send_action(action="typing")

    reply = get_ai_reply(user_text)
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

    # All normal text -> AI chat
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat_handler))

    app.add_error_handler(error_handler)

    print("🤖 Funny Bot AI Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
          
