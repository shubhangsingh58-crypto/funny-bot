import os
import logging
import requests
import time
import random
import sqlite3
import string
from collections import defaultdict, deque

from telegram import Update
from telegram.constants import ChatAction, ChatType
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
    raise ValueError("Missing TELEGRAM_TOKEN")
if not OPENROUTER_API_KEY:
    raise ValueError("Missing OPENROUTER_API_KEY")

logging.basicConfig(level=logging.INFO)

# =========================
# DB
# =========================
def get_db():
    return sqlite3.connect("bot.db", check_same_thread=False)

conn = get_db()
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    invite_code TEXT UNIQUE,
    invited_by TEXT,
    referrals INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1
)
""")
conn.commit()
conn.close()


def generate_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# =========================
# MEMORY
# =========================
memory = defaultdict(lambda: deque(maxlen=8))
modes = defaultdict(lambda: "normal")
last_msg = {}

# =========================
# XP SYSTEM (FIXED)
# =========================
def add_xp(user_id: int, amount: int = 5):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT xp, level FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()

    if not row:
        db.close()
        return

    xp = row[0] + amount
    level = (xp // 100) + 1

    c.execute(
        "UPDATE users SET xp=?, level=? WHERE user_id=?",
        (xp, level, user_id)
    )

    db.commit()
    db.close()


# =========================
# REGISTER USER (FIXED)
# =========================
def register_user(user, invite=None):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT invite_code FROM users WHERE user_id=?", (user.id,))
    row = c.fetchone()

    if not row:
        code = generate_code()
        c.execute("""
            INSERT INTO users (user_id, username, invite_code, referrals)
            VALUES (?, ?, ?, 0)
        """, (user.id, user.username, code))
    elif not row[0]:
        code = generate_code()
        c.execute("UPDATE users SET invite_code=? WHERE user_id=?", (code, user.id))

    db.commit()
    db.close()


def add_referral(invite_code, new_user_id):
    db = get_db()
    c = db.cursor()

    c.execute("SELECT user_id FROM users WHERE invite_code=?", (invite_code,))
    row = c.fetchone()
    if not row:
        db.close()
        return

    inviter = row[0]
    if inviter == new_user_id:
        db.close()
        return

    c.execute("UPDATE users SET referrals = referrals + 1 WHERE user_id=?", (inviter,))
    db.commit()
    db.close()


# =========================
# AI RESPONSE
# =========================
def ai_reply(user_id, text):
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a funny Hinglish chat buddy."},
            {"role": "user", "content": text}
        ]
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except:
        return "System thoda busy hai 😅 try again later"


# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    invite = context.args[0] if context.args else None
    register_user(user, invite)

    if invite:
        add_referral(invite, user.id)

    await update.message.reply_text("Yo 😎 Bot ready hai!")


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")


# =========================
# CHAT HANDLER
# =========================
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    text = update.message.text

    now = time.time()
    if now - last_msg.get(user.id, 0) < 1.5:
        return
    last_msg[user.id] = now

    if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        if not update.message.reply_to_message:
            return

    await update.message.chat.send_action(ChatAction.TYPING)

    add_xp(user.id)

    reply = ai_reply(user.id, text)

    memory[user.id].append(f"User: {text}")
    memory[user.id].append(f"Bot: {reply}")

    await update.message.reply_text(reply)


# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()

