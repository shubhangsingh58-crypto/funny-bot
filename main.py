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

try:
    cursor.execute("ALTER TABLE users ADD COLUMN referrals INTEGER DEFAULT 0")
    conn.commit()
except sqlite3.OperationalError:
    pass

try:
    cursor.execute("ALTER TABLE users ADD COLUMN invite_code TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

conn.close()


def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def add_xp(user_id, amount=5):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT xp FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        if not row:
            return

        xp = (row[0] or 0) + amount
        level = (xp // 100) + 1

        cursor.execute(
            "UPDATE users SET xp=?, level=? WHERE user_id=?",
            (xp, level, user_id)
        )
        db.commit()
    except Exception as e:
        logging.error(f"Error in add_xp: {e}")
    finally:
        db.close()


def add_referral_direct(db, invite_code, new_user_id):
    cursor = db.cursor()
    cursor.execute("SELECT user_id FROM users WHERE invite_code=?", (invite_code,))
    inviter = cursor.fetchone()
    if not inviter:
        return

    inviter_id = inviter[0]
    if inviter_id == new_user_id:
        return

    cursor.execute("SELECT invited_by FROM users WHERE user_id=?", (new_user_id,))
    row = cursor.fetchone()
    if row and row[0]:
        return

    cursor.execute("UPDATE users SET invited_by=? WHERE user_id=?", (invite_code, new_user_id))
    cursor.execute("UPDATE users SET referrals = COALESCE(referrals, 0) + 1 WHERE user_id=?", (inviter_id,))
    db.commit()


def register_user(user, context=None):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        cursor.execute("SELECT invite_code FROM users WHERE user_id=?", (user.id,))
        row = cursor.fetchone()
        
        if not row:
            invite_code = generate_invite_code()
            cursor.execute("""
                INSERT INTO users (user_id, username, invite_code, referrals, xp, level)
                VALUES (?, ?, ?, 0, 0, 1)
            """, (user.id, user.username, invite_code))
            db.commit()
        elif not row[0]:
            invite_code = generate_invite_code()
            cursor.execute("UPDATE users SET invite_code=? WHERE user_id=?", (invite_code, user.id))
            db.commit()

        if context and context.args:
            add_referral_direct(db, context.args[0], user.id)
    except Exception as e:
        logging.error(f"Registration error: {e}")
    finally:
        db.close()


# =========================
# MEMORY / STATE
# =========================
user_memories = defaultdict(lambda: deque(maxlen=8))   
user_modes = defaultdict(lambda: "normal")             
last_message_time = {}                                 

BOT_NAME_HINTS = ["funny bot", "funnybot"]

    
# =========================
# TRUTH & DARE QUESTIONS
# =========================
TRUTH_QUESTIONS = [
    "Teri life ka sabse bada aur embarassing secret kya hai? 👀",
    "Tu kabhi kisi pe line maarte hue pakda gaya hai? 😂",
    "Agar tujhe mauka mile toh tu is group mein kisko block karega? 😏",
    "Sabse aakhri jhoot tune kisse aur kya bola tha? 🤫",
    "Kya tune kabhi bina nahaye 3-4 din nikale hain? 😷",
    "Teri life ka wo kaun sa sach hai jo tere gharwale jaante hain toh teri dhunai pakki hai? 💀",
    "Kisi aisi cheez ka naam bata jo tune chori ki ho, chahe wo dosto ki canteen ka samosa hi kyun na ho! 🥐",
    "Agar tu ek din ke liye ladki ban jaye, toh sabse pehle kya karega? 💅",
    "Tera abhi tak ka sabse bura crush kaun raha hai aur kyun? 🤫",
    "Kya tune kabhi apne dost ki bandi/bande par line maarne ki sochi hai? 🧐"
]

DARE_TASKS = [
    "Apni gallery ka sabse purana aur ajeeb photo group mein bhejo abhi ke abhi! 📸",
    "Kisi bhi random dost ko message karo 'Mujhe tumse ek baat chhupani thi...' aur uska reply aane par block kar do! 😜",
    "Apne status par likho 'Main thoda pagal hoon' aur use 15 minute tak mat hatana. 📱",
    "Ek voice note bhejo jismein tum kisi heroine ya hero ki kharab acting kar rahe ho! 🎙️",
    "Apne baap ko text karo 'Papa shaadi karni hai' aur jo reply aaye uska screenshot yahan bhejo! 💀",
    "Agli 5 lines tak har message ke end mein 'Main toh ghadha hoon' likhna padega. 🐴",
    "Apne dosto ke group mein apna ek ajeeb sa selfie khinch kar bhejo bina filter ke! 🤳",
    "Kisi aisi ladki/ladke ko text karo jisse sadiyon se baat nahi hui, aur likho 'Tumhari yaad aa rahi thi' aur screenshot bhejo. 💀"
]

# =========================
# TEXTS
# =========================
HELP_TEXT = """
😏 Commands sun lo bhai:
/profile - apni profile dekho 😎

/start - game shuru karein
/help - menu check karo
/about - mere baare me jaano
/ping - check kar main zinda hoon ya nahi
/mode normal - thoda theek thaak behave karunga
/mode savage - ekdum tabaahi roasty replies 🔥
/mode emotional - dard dukh baantne ke liye
/mode flirty - thoda maze lene ke liye 😉
/game truth - Sach bolna padega beta 🤔
/game dare - Himmat hai toh task poora kar 🔥
/invite - dosto ko bulao aur rewards jeeto 👥
/reset - purani baatein bhool jao (clear memory)
"""

ABOUT_TEXT = """
😏 Main koi robotic AI ya bot nahi hoon. Ek seedha saadha ladka hoon jo mast bakchodi karta hai dosto ke sath. Shubhang ne mujhe dimaag diya hai taaki tum logo ke maze le sakoon! 😎
"""

INTRO_TEXT = (
    "Abe bataya toh, main ek seedha saadha ladka hoon! 😎\n"
    "Random baatein, savage roasting, dukh-dard bhulana aur thodi bohot flirty vibes — sab on point hai.\n"
    "Aur haan, mujhe Shubhang ne banaya hai 😏🔥"
)

# =========================
# PERSONALITY / SYSTEM PROMPT
# =========================
BASE_SYSTEM_PROMPT = """
You are NOT an AI, robot, or a chatbot. Never call yourself a bot, AI, or language model. 
Aap ek seedhe saade, mast-maula ladke ho jise Shubhang ne banaya hai.

Core identity:
- If someone asks who you are, say you are a simple, fun-loving guy (seedha saadha ladka), not an AI bot.
- Developer/Creator ka naam hamesha Shubhang batana hai ekdum natural style mein.
- Example vibe: "Mujhe Shubhang ne banaya hai bhai, ekdum kadak ladka hoon main! 😎🔥"

General vibe:
- Talk like a savage, smart, human online friend. 
- Use casual Hinglish naturally, like friends chatting on WhatsApp/Telegram.
- Keep replies witty, funny, sharp, and slightly roasty (savage). Don't give boring gyaan.
- Keep answers short and crisp.
- If the user talks about being sad, comfort them like a true brother/friend, not a therapist.
"""

MODE_PROMPTS = {
    "normal": """
Current mode: NORMAL
- Friendly, smart, balanced but funny.
""",
    "savage": """
Current mode: SAVAGE
- Highly savage, roasty, cheeky, and full of bakchodi. 
- Take things playfully, tease the user sharply but keep it fun.
""",
    "emotional": """
Current mode: EMOTIONAL
- Warm, caring, loyal brother vibe. Listen to their problems naturally.
""",
    "flirty": """
Current mode: FLIRTY
- Playful, charming, witty banter. Keep it fun and completely safe.
"""
}

OWNER_KEYWORDS = [
    "owner", "developer", "creator", "who made you", "who created you",
    "kisne banaya", "tumhara owner", "tumhara developer", "made you",
    "dev name", "creator name"
]

INTRO_KEYWORDS = [
    "tu kaun hai", "tum kaun ho", "who are you", "apne baare me bata",
    "about yourself", "what can you do", "what are you", "introduce yourself"
]

ABUSE_WORDS = [
    "madarchod", "bhenchod", "mc", "bc", "chutiya", "gandu", "randi", "lund"
]

# =========================
# HELPERS
# =========================
def build_system_prompt(mode: str, memory_text: str = "") -> str:
    mode_prompt = MODE_PROMPTS.get(mode, MODE_PROMPTS["normal"])
    prompt = BASE_SYSTEM_PROMPT + "\n\n" + mode_prompt

    if memory_text.strip():
        prompt += f"\n\nRecent conversation context:\n{memory_text}"
    return prompt


def format_memory(user_id: int) -> str:
    turns = list(user_memories[user_id])
    if not turns:
        return ""
    return "\n".join(turns[-8:])


def contains_owner_question(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in OWNER_KEYWORDS)


def contains_intro_question(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in INTRO_KEYWORDS)


def contains_abuse(text: str) -> bool:
    t = text.lower()
    return any(word in t for word in ABUSE_WORDS)


def should_reply_in_group(update: Update, bot_username: str) -> bool:
    if not update.message or not update.message.text:
        return False
    text = update.message.text.lower()
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        if update.message.reply_to_message.from_user.is_bot:
            return True
    if bot_username and f"@{bot_username.lower()}" in text:
        return True
    if any(name in text for name in BOT_NAME_HINTS):
        return True
    return False


def get_ai_reply(user_id: int, user_message: str) -> str:
    memory_text = format_memory(user_id)
    mode = user_modes[user_id]
    system_prompt = build_system_prompt(mode, memory_text)

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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        data = response.json()
        if response.status_code != 200:
            return "Aaj thoda dimag buffering pe chal raha hai 😵‍💫 thodi der me fir bolna."
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return "Reply dene gaya tha, raste me thoda system latak gaya 😭 thodi der baad try kar."


# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user, context)
    text = (
        "Yo! 😎 Main koi bot nahi, ek seedha saadha ladka hoon.\n"
        "Savage bakchodi, roast ya game khelna ho toh batao. Seedha baatein shuru karo ya /help dekh lo!"
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_TEXT)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Mast online baitha hoon bhai 😎")


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_memories[user_id].clear()
    await update.message.reply_text("Done 😌 purani baatein bhool gaya main!")


async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        current = user_modes[user_id]
        await update.message.reply_text(
            f"Abhi main {current} mood mein hoon.\nBadalne ke liye use karo:\n/mode normal\n/mode savage\n/mode emotional\n/mode flirty"
        )
        return

    mode = context.args[0].lower().strip()
    if mode not in ["normal", "savage", "emotional", "flirty"]:
        await update.message.reply_text("Valid moods: normal, savage, emotional, flirty")
        return

    user_modes[user_id] = mode
    await update.message.reply_text(f"Mood switched to *{mode}* bhaiya! 😎", parse_mode="Markdown")


async def truth_or_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Abe sahi se bolo na bhai! 😏\n"
            "Chunno jaldi:\n"
            "/game truth - Sach bolne ki himmat hai?\n"
            "/game dare - Dum hai toh task kar! 🔥"
        )
        return

    choice = context.args[0].lower().strip()
    
    if choice == "truth":
        question = random.choice(TRUTH_QUESTIONS)
        await update.message.reply_text(f"Ab sach bolna padega beta... 🤔\n\n*Sawaal:* {question}", parse_mode="Markdown")
    elif choice == "dare":
        task = random.choice(DARE_TASKS)
        await update.message.reply_text(f"Dum hai toh poora kar ke dikha! 🔥\n\n*Task:* {task}", parse_mode="Markdown")
    else:
        await update.message.reply_text("Ya toh 'truth' chunno ya 'dare'.. ye teesra dimag mat lagao! 🤦‍♂️")


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        user_id = update.effective_user.id

        cursor.execute(
            "SELECT invite_code, referrals FROM users WHERE user_id=?",
            (user_id,)
        )
        row = cursor.fetchone()

        if row is None:
            db.close()
            register_user(update.effective_user)
            db = get_db_connection()
            cursor = db.cursor()
            cursor.execute(
                "SELECT invite_code, referrals FROM users WHERE user_id=?",
                (user_id,)
            )
            row = cursor.fetchone()

        invite_code = row[0] if (row and row[0]) else generate_invite_code()
        referrals = row[1] if (row and row[1]) else 0

        if row and not row[0]:
            cursor.execute("UPDATE users SET invite_code=? WHERE user_id=?", (invite_code, user_id))
            db.commit()

        try:
            bot_username = (await context.bot.get_me()).username
        except Exception:
            bot_username = context.bot.username or "YourBotUsername"

        invite_link = f"https://t.me/{bot_username}?start={invite_code}"

        text = (
            "👥 *Invite Friends & Earn Rewards*\n\n"
            f"🔗 {invite_link}\n\n"
            f"👥 Referrals: {referrals}/5\n\n"
            "🎁 *Rewards:*\n"
            "🔥 Premium Roast\n"
            "⚡ 100 Daily Messages\n"
            "😎 Baklol Badge"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Error in invite command: {e}")
    finally:
        db.close()

    
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db_connection()
    cursor = db.cursor()
    try:
        user_id = update.effective_user.id

        cursor.execute("""
            SELECT username, referrals, badge, premium, xp, level
            FROM users
            WHERE user_id=?
        """, (user_id,))

        row = cursor.fetchone()
        if not row:
            await update.message.reply_text("Pehle /start kar bhai 😎")
            return

        username, referrals, badge, premium, xp, level = row
        premium_text = "✅ Yes" if premium else "❌ No"

        text = f"""
👤 @{username or 'User'}

🏅 Badge : {badge}

⭐ Level : {level}
✨ XP : {xp}

👥 Referrals : {referrals}

💎 Premium : {premium_text}
"""
        await update.message.reply_text(text)
    except Exception as e:
        logging.error(f"Error in profile command: {e}")
    finally:
        db.close()


# =========================
# MAIN CHAT HANDLER
# =========================
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    chat_obj = update.effective_chat
    user_id = user.id
    raw_text = update.message.text.strip()
    text = raw_text.lower()

    now = time.time()
    last_time = last_message_time.get(user_id, 0)
    if now - last_time < 1.5:
        return
    last_message_time[user_id] = now

    bot_username = None
    if context.bot.username:
        bot_username = context.bot.username

    if chat_obj.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        if not should_reply_in_group(update, bot_username):
            return

    if contains_owner_question(text):
        await update.message.reply_text(
            "Mujhe Shubhang ne banaya hai bhai! Ekdum kadak ladka hoon main. 😎🔥"
        )
        return

    if contains_intro_question(text):
        await update.message.reply_text(INTRO_TEXT)
        return

    if contains_abuse(text):
        await update.message.reply_text("Abe shaant gusse par control rakh thoda! 😭")
        return

    await update.message.chat.send_action(action=ChatAction.TYPING)
    
    # Global add_xp function perfectly called here
    add_xp(user_id)

    reply = get_ai_reply(user_id, raw_text)

    user_memories[user_id].append(f"User: {raw_text}")
    user_memories[user_id].append(f"Bot: {reply}")

    await update.message.reply_text(reply)


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
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("mode", mode_command))
    app.add_handler(CommandHandler("game", truth_or_dare))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(CommandHandler("profile", profile))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    app.add_error_handler(error_handler)

    print("Funny Bot V2 Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
