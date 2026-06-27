import os
import logging
import requests
import time
import random
import re
from collections import defaultdict, deque
import sqlite3
import string
import secrets

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
    raise ValueError("TELEGRAM_TOKEN environment variable missing!")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY environment variable missing!")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================
# DATABASE SETUP
# =========================
def get_db_connection():
    return sqlite3.connect("baklol_v2.db", check_same_thread=False)

conn = get_db_connection()
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    invite_code TEXT UNIQUE,
    invited_by TEXT,
    referrals INTEGER DEFAULT 0,
    badge TEXT DEFAULT 'Newbie',
    premium INTEGER DEFAULT 0,
    daily_messages INTEGER DEFAULT 50,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1
)
""")

conn.commit()
conn.close()


def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


# =========================
# MEMORY / STATE
# =========================
user_memories = defaultdict(lambda: deque(maxlen=8))
user_modes = defaultdict(lambda: "normal")
last_message_time = {}

BOT_NAME_HINTS = ["funny bot", "funnybot"]

# =========================
# XP SYSTEM (FIXED)
# =========================
def add_xp(user_id, amount=5):
    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("SELECT xp FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if not row:
        db.close()
        return

    xp = row[0] + amount
    level = (xp // 100) + 1

    cursor.execute(
        "UPDATE users SET xp=?, level=? WHERE user_id=?",
        (xp, level, user_id)
    )

    db.commit()
    db.close()


# =========================
# REFERRAL FIXED
# =========================
def add_referral_direct(db, invite_code, new_user_id):
    cursor = db.cursor()

    cursor.execute("SELECT user_id FROM users WHERE invite_code=?", (invite_code,))
    inviter = cursor.fetchone()

    if not inviter:
        return

    inviter_id = inviter[0]

    if inviter_id == new_user_id:
        return

    cursor.execute(
        "UPDATE users SET referrals = COALESCE(referrals, 0) + 1 WHERE user_id=?",
        (inviter_id,)
    )

    db.commit()


# =========================
# REGISTER USER (FIXED ONLY)
# =========================
def register_user(user, context=None):
    db = get_db_connection()
    cursor = db.cursor()

    try:
        cursor.execute("SELECT invite_code FROM users WHERE user_id=?", (user.id,))
        row = cursor.fetchone()

        if not row:
            invite_code = generate_invite_code()
            cursor.execute("""
                INSERT INTO users (user_id, username, invite_code, referrals)
                VALUES (?, ?, ?, 0)
            """, (user.id, user.username, invite_code))
            db.commit()

        elif not row[0]:
            invite_code = generate_invite_code()
            cursor.execute(
                "UPDATE users SET invite_code=? WHERE user_id=?",
                (invite_code, user.id)
            )
            db.commit()

        if context and context.args:
            add_referral_direct(db, context.args[0], user.id)

    except Exception as e:
        logging.error(f"Registration error: {e}")

    finally:
        db.close()


# =========================
# TRUTH & DARE (UNCHANGED)
# =========================
TRUTH_QUESTIONS = [
    "Teri life ka sabse bada aur embarassing secret kya hai? 👀",
    "Tu kabhi kisi pe line maarte hue pakda gaya hai? 😂",
    "Agar tujhe mauka mile toh tu is group mein kisko block karega? 😏",
]

DARE_TASKS = [
    "Apni gallery ka sabse purana photo bhejo 📸",
    "Kisi ko weird msg karo 😜",
    "Status pe 'Main pagal hoon' likho 📱",
]

# =========================
# TEXTS (UNCHANGED)
# =========================
HELP_TEXT = """
😏 Commands:
/start
/help
/about
/ping
/mode normal|savage|emotional|flirty
/game truth|dare
/invite
/profile
/reset
"""

ABOUT_TEXT = "Main ek fun Hinglish chat bot hoon 😎"

INTRO_TEXT = "Main ek mast-maula ladka hoon 😏"

# =========================
# SYSTEM PROMPT (UNCHANGED)
# =========================
BASE_SYSTEM_PROMPT = """
You are NOT an AI or bot.
You are a fun Hinglish chatting friend.
"""

MODE_PROMPTS = {
    "normal": "Friendly mode",
    "savage": "Savage roast mode",
    "emotional": "Caring mode",
    "flirty": "Playful mode"
}

# =========================
# HELPERS
# =========================
def format_memory(user_id):
    return "\n".join(user_memories[user_id])


def build_prompt(mode):
    return BASE_SYSTEM_PROMPT + "\n" + MODE_PROMPTS.get(mode, "normal")


# =========================
# AI (FIXED SAFE)
# =========================
def get_ai_reply(user_id, text):
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": build_prompt(user_modes[user_id])},
            {"role": "user", "content": text}
        ]
    }

    try:
        r = requests.post(url, json=payload, timeout=60)
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except:
        return "Server thoda busy hai 😅"


# =========================
# COMMANDS (UNCHANGED)
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user, context)
    await update.message.reply_text("Yo 😎 Bot ready!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_TEXT)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong!")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_memories[update.effective_user.id].clear()
    await update.message.reply_text("Memory cleared 😌")

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not context.args:
        await update.message.reply_text(user_modes[uid])
        return

    user_modes[uid] = context.args[0]
    await update.message.reply_text(f"Mode: {context.args[0]} 😎")


async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/game truth or dare")
        return

    if context.args[0] == "truth":
        await update.message.reply_text(random.choice(TRUTH_QUESTIONS))
    elif context.args[0] == "dare":
        await update.message.reply_text(random.choice(DARE_TASKS))


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db_connection()
    cursor = db.cursor()

    uid = update.effective_user.id

    cursor.execute("SELECT invite_code, referrals FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text("Start first /start")
        return

    code, ref = row
    link = f"https://t.me/{context.bot.username}?start={code}"

    await update.message.reply_text(f"{link}\nReferrals: {ref}")


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db_connection()
    cursor = db.cursor()

    uid = update.effective_user.id

    cursor.execute("SELECT xp, level, referrals FROM users WHERE user_id=?", (uid,))
    row = cursor.fetchone()

    if not row:
        await update.message.reply_text("Start first /start")
        return

    xp, level, ref = row

    await update.message.reply_text(
        f"⭐ Level: {level}\n✨ XP: {xp}\n👥 Ref: {ref}"
    )


# =========================
# CHAT HANDLER
# =========================
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    now = time.time()
    if now - last_message_time.get(user.id, 0) < 1.5:
        return
    last_message_time[user.id] = now

    add_xp(user.id)

    reply = get_ai_reply(user.id, text)

    user_memories[user.id].append(text)
    user_memories[user.id].append(reply)

    await update.message.reply_text(reply)


# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("game", game))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(CommandHandler("profile", profile))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    print("Funny Bot V2 Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
  
