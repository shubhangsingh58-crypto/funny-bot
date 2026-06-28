import os
import logging
import requests
import time
import random
import re
from collections import defaultdict, deque
import sqlite3
import string
from datetime import datetime
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

def init_db():
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
        coins INTEGER DEFAULT 100,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        streak_count INTEGER DEFAULT 0,
        last_streak_date TEXT
    )
    """)
    conn.commit()

    # Column upgrades handled safely step-by-step
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN referrals INTEGER DEFAULT 0")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN coins INTEGER DEFAULT 100")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN invite_code TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE users ADD COLUMN streak_count INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN last_streak_date TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    
    conn.close()

init_db()

def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))


def check_and_update_streak(user_id):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT streak_count, last_streak_date FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        db.close()
        return None

    streak_count, last_date_str = row
    streak_count = streak_count or 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    streak_msg = ""
    
    if not last_date_str:
        cursor.execute("UPDATE users SET streak_count=1, last_streak_date=?, coins=COALESCE(coins, 100)+50 WHERE user_id=?", (today_str, user_id))
        db.commit()
        streak_msg = "🔥 <b>Daily Streak Started!</b> You got +50 Bonus Coins!"
    else:
        try:
            last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            delta = (today - last_date).days
            
            if delta == 1:
                new_streak = streak_count + 1
                cursor.execute("UPDATE users SET streak_count=?, last_streak_date=?, coins=COALESCE(coins, 100)+50 WHERE user_id=?", (new_streak, today_str, user_id))
                db.commit()
                streak_msg = f"🔥 <b>Daily Streak Maintained!</b> Day {new_streak}! You got +50 Bonus Coins!"
            elif delta > 1:
                cursor.execute("UPDATE users SET streak_count=1, last_streak_date=?, coins=COALESCE(coins, 100)+50 WHERE user_id=?", (today_str, user_id))
                db.commit()
                streak_msg = "💔 <b>Streak Broken!</b> Starting fresh today. You got +50 Bonus Coins!"
        except Exception:
            pass
            
    db.close()
    return streak_msg


def add_xp(user_id, amount=5):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT xp FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        db.close()
        return

    xp = (row[0] or 0) + amount
    level = (xp // 100) + 1

    cursor.execute(
        "UPDATE users SET xp=?, level=?, coins=COALESCE(coins, 100)+2 WHERE user_id=?",
        (xp, level, user_id)
    )
    db.commit()
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
                INSERT INTO users (user_id, username, invite_code, referrals, coins, streak_count)
                VALUES (?, ?, ?, 0, 100, 0)
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
# MEMORY / STATE / GAMES DATA
# =========================
user_memories = defaultdict(lambda: deque(maxlen=8))   
user_modes = defaultdict(lambda: "normal")             
last_message_time = {}                                 
game_sessions = {}  # Format: {user_id: {"type": "guess", "number": 5, "quiz_ans": "a"}}

BOT_NAME_HINTS = ["funny bot", "funnybot"]

QUIZ_BANK = [
    {"q": "India ki capital kya hai?\n\nA) Mumbai\nB) Delhi\nC) Kolkata\nD) Chennai", "a": "b"},
    {"q": "Thala kis player ko bola jata hai? 😂\n\nA) Virat Kohli\nB) Rohit Sharma\nC) MS Dhoni\nD) Hardik Pandya", "a": "c"},
    {"q": "Free Fire aur BGMI me se sabse zyada lag kis me hota hai? (Just for fun!)\n\nA) BGMI\nB) Free Fire\nC) Dono bekar hain\nD) Mera device hi kharab hai 💀", "a": "d"},
    {"q": "Internet par sabse bada search engine kaun sa hai?\n\nA) Bing\nB) Yahoo\nC) Google\nD) DuckDuckGo", "a": "c"}
]

MEME_LIST = [
    "Dost: Bhai breakup ho gaya hai, bohot bura lag raha hai.\nMe: Ro mat bhai, chal rank push karte hain! 🎮💀",
    "Gharwale: Humara ladka ek din bada hokar naam roshan karega.\nMe: Subah 4 baje tak reels scroll karte hue... 👁️👄👁️",
    "Ex to Me: Tumhe mere se acchi koi nahi milegi.\nMe: Abe wahi toh chahiye, tere jaisi se toh dushman bhi bache! 😏👋",
    "Backbenchers during exams: Bhai bas aage wale ka sir thoda left ho jaye, poora question paper chhap dunga. 📝🔥",
    "Engineer dosto ki life: Degree haath me hai, par dimaag me sirf bakchodi bhari hai! 😎"
]
    
# =========================
# TRUTH & DARE QUESTIONS
# =========================
TRUTH_QUESTIONS = [
    "Teri life ka sabse bada aur embarassing secret kya hai? 👀",
    "Tu kabhi kisi pe line maarte hue pakda gaya hai? 😂",
    "Agar tujhe mauka mile toh tu is group mein kisko block karega? 😏"
]

DARE_TASKS = [
    "Apni gallery ka sabse purana aur ajeeb photo group mein bhejo abhi ke abhi! 📸",
    "Apne status par likho 'Main thoda pagal hoon' aur use 15 minute tak mat hatana. 📱"
]

# =========================
# TEXTS
# =========================
HELP_TEXT = """
😏 <b>Commands sun lo bhai:</b>
━━━━━━━━━━━━━━━━━━━━
/profile - apni profile dekho 😎
/leaderboard - top ameer baklolon ki list 🏆
/meme - ek mast instant meme joke suno 😂
/guess - number guessing game shuru karo 🎮
/quiz - quiz khel kar coins jeeto 🧠
/start - game shuru karein
/help - menu check karo
/about - mere baare me jaano
/ping - check kar main zinda hoon ya nahi
/mode [normal/savage/emotional/flirty] - mood badlo
/game [truth/dare] - game khelo
/invite - dosto ko bulao aur rewards jeeto 👥
/reset - purani baatein bhool jao
━━━━━━━━━━━━━━━━━━━━
"""

ABOUT_TEXT = """
😏 Main koi robotic AI ya bot nahi hoon. Ek seedha saadha ladka hoon jo mast bakchodi karta hai dosto ke sath. Shubhang ne mujhe dimaag diya hai! 😎
"""

INTRO_TEXT = (
    "Abe bataya toh, main ek seedha saadha ladka hoon! 😎\n"
    "Random baatein, savage roasting aur games sab on point hai.\n"
    "Aur haan, mujhe Shubhang ne banaya hai 😏🔥"
)

# =========================
# PERSONALITY / SYSTEM PROMPT
# =========================
BASE_SYSTEM_PROMPT = """
You are NOT an AI, robot, or a chatbot. Never call yourself a bot, AI, or language model. 
Aap ek seedhe saade, mast-maula ladke ho jise Shubhang ne banaya hai.
"""

MODE_PROMPTS = {
    "normal": "\nCurrent mode: NORMAL\n- Friendly, smart, balanced but funny.\n",
    "savage": "\nCurrent mode: SAVAGE\n- Highly savage, roasty, cheeky, and full of bakchodi.\n",
    "emotional": "\nCurrent mode: EMOTIONAL\n- Warm, caring, loyal brother vibe.\n",
    "flirty": "\nCurrent mode: FLIRTY\n- Playful, charming, witty banter.\n"
}

OWNER_KEYWORDS = ["owner", "developer", "creator", "who made you", "kisne banaya"]
INTRO_KEYWORDS = ["tu kaun hai", "tum kaun ho", "who are you", "introduce yourself"]
ABUSE_WORDS = ["madarchod", "bhenchod", "mc", "bc", "chutiya", "gandu"]

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
    return any(k in text.lower() for k in OWNER_KEYWORDS)

def contains_intro_question(text: str) -> bool:
    return any(k in text.lower() for k in INTRO_KEYWORDS)

def contains_abuse(text: str) -> bool:
    return any(word in text.lower() for word in ABUSE_WORDS)

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
        if response.status_code != 200:
            return "Aaj thoda dimag buffering pe chal raha hai 😵‍💫 thodi der me fir bolna."
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return "Reply dene gaya tha, raste me thoda system latak gaya 😭"

# =========================
# COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    register_user(update.effective_user, context)
    await update.message.reply_text("Yo! 😎 Main koi bot nahi, ek seedha saadha ladka hoon. /help dekh lo!")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="HTML")

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_TEXT)

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Mast online baitha hoon bhai 😎")

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_memories[update.effective_user.id].clear()
    await update.message.reply_text("Done 😌 purani baatein bhool gaya main!")

async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text(f"Abhi main {user_modes[user_id]} mood mein hoon.")
        return
    mode = context.args[0].lower().strip()
    if mode in ["normal", "savage", "emotional", "flirty"]:
        user_modes[user_id] = mode
        await update.message.reply_text(f"Mood switched to <b>{mode}</b> bhaiya! 😎", parse_mode="HTML")
    else:
        await update.message.reply_text("Valid moods: normal, savage, emotional, flirty")

async def truth_or_dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("/game truth ya /game dare likho bhai!")
        return
    choice = context.args[0].lower().strip()
    if choice == "truth":
        await update.message.reply_text(f"🤔 <b>Sawaal:</b> {random.choice(TRUTH_QUESTIONS)}", parse_mode="HTML")
    elif choice == "dare":
        await update.message.reply_text(f"🔥 <b>Task:</b> {random.choice(DARE_TASKS)}", parse_mode="HTML")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db_connection()
    cursor = db.cursor()
    user_id = update.effective_user.id
    cursor.execute("SELECT invite_code, referrals FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    db.close()
    if not row:
        return
    bot_username = (await context.bot.get_me()).username or "Bot"
    text = f"👥 <b>Invite Friends</b>\n\n🔗 https://t.me/{bot_username}?start={row[0]}\n\n👥 <b>Referrals:</b> {row[1]}/5"
    await update.message.reply_text(text, parse_mode="HTML")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT username, coins FROM users WHERE coins IS NOT NULL ORDER BY coins DESC LIMIT 10")
    rows = cursor.fetchall()
    db.close()
    if not rows:
        await update.message.reply_text("Abhi tak leaderboard khali hai bhai! 😲")
        return
    text = "🏆 <b>TOP BAKLOL LEADERBOARD</b> 🏆\n━━━━━━━━━━━━━━━━━━━━\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for idx, row in enumerate(rows):
        display_name = f"@{row[0]}" if row[0] else "Unknown Baklol"
        text += f"{medals[idx]} {display_name} — <b>{row[1]} 💰</b>\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = get_db_connection()
    cursor = db.cursor()
    cursor.execute("SELECT username, referrals, badge, premium, xp, level, coins, streak_count FROM users WHERE user_id=?", (update.effective_user.id,))
    row = cursor.fetchone()
    db.close()
    if not row:
        await update.message.reply_text("Pehle /start kar bhai 😎")
        return
    text = f"👤 <b>@{row[0] or 'User'}</b>\n\n🏅 <b>Badge :</b> {row[2]}\n🔥 <b>Daily Streak :</b> {row[7] or 0} Days\n⭐ <b>Level :</b> {row[5]}\n✨ <b>XP :</b> {row[4]}\n💰 <b>Coins :</b> {row[6] or 100}"
    await update.message.reply_text(text, parse_mode="HTML")

# =========================
# NEW NEW NEW FEATURES
# =========================
async def meme_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a random witty text-based pop joke."""
    await update.message.reply_text(f"😂 <b>Baklol Joke:</b>\n\n{random.choice(MEME_LIST)}", parse_mode="HTML")

async def guess_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts a number guessing mini-game."""
    user_id = update.effective_user.id
    secret_num = random.randint(1, 10)
    game_sessions[user_id] = {"type": "guess", "number": secret_num}
    await update.message.reply_text("🎮 <b>Guess the Number Game!</b>\n\nMaine 1 se 10 ke beech ek number socha hai. Guess karo aur direct chat me answer send karo! (e.g. 5)")

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggers a quick trivia game."""
    user_id = update.effective_user.id
    quiz = random.choice(QUIZ_BANK)
    game_sessions[user_id] = {"type": "quiz", "answer": quiz["a"]}
    await update.message.reply_text(f"🧠  <b>Instant Baklol Quiz!</b>\n\n{quiz['q']}\n\n👉 Apne answer ke option ka letter (A, B, C, D) direct reply me likho!")


# =========================
# MAIN CHAT HANDLER
# =========================
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    user_id = update.effective_user.id
    raw_text = update.message.text.strip()
    text_clean = raw_text.lower()
    
    now = time.time()
    if now - last_message_time.get(user_id, 0) < 1.5:
        return
    last_message_time[user_id] = now

    # Intercept for Mini-Games Answers
    if user_id in game_sessions:
        session = game_sessions[user_id]
        
        if session["type"] == "guess":
            if raw_text.isdigit():
                guessed = int(raw_text)
                correct = session["number"]
                if guessed == correct:
                    db = get_db_connection()
                    db.cursor().execute("UPDATE users SET coins=COALESCE(coins,100)+30 WHERE user_id=?", (user_id,))
                    db.commit()
                    db.close()
                    del game_sessions[user_id]
                    await update.message.reply_text(f"🎉 <b>Arrebaah Sahi Jawab!</b> Maine {correct} hi socha tha! You won <b>+30 Coins 💰</b>!", parse_mode="HTML")
                    return
                else:
                    del game_sessions[user_id]
                    await update.message.reply_text(f"❌ <b>Galat Jawab!</b> Maine {correct} socha tha. Dobara /guess karke try kar!")
                    return
                    
        elif session["type"] == "quiz":
            if text_clean in ["a", "b", "c", "d"]:
                correct = session["answer"]
                if text_clean == correct:
                    db = get_db_connection()
                    db.cursor().execute("UPDATE users SET coins=COALESCE(coins,100)+40 WHERE user_id=?", (user_id,))
                    db.commit()
                    db.close()
                    del game_sessions[user_id]
                    await update.message.reply_text("🎉 <b>Ekdum Perfect!</b> Sahi option chuna tune. You won <b>+40 Coins 💰</b>!", parse_mode="HTML")
                    return
                else:
                    del game_sessions[user_id]
                    await update.message.reply_text(f"❌ <b>Dhat Teri Ki!</b> Galat jawab. Correct answer option '{correct.upper()}' tha. Agli baar dhyan dena!")
                    return

    if update.effective_chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]:
        if not should_reply_in_group(update, context.bot.username):
            return

    if contains_owner_question(raw_text):
        await update.message.reply_text("Mujhe Shubhang ne banaya hai bhai! 😎🔥")
        return
    if contains_intro_question(raw_text):
        await update.message.reply_text(INTRO_TEXT)
        return
    if contains_abuse(raw_text):
        await update.message.reply_text("Abe shaant gusse par control rakh thoda! 😭")
        return

    streak_alert = check_and_update_streak(user_id)
    if streak_alert:
        await update.message.reply_text(streak_alert, parse_mode="HTML")

    await update.message.chat.send_action(action=ChatAction.TYPING)
    add_xp(user_id)
    reply = get_ai_reply(user_id, raw_text)
    await update.message.reply_text(reply)

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
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    
    # NEW HANDLERS REGISTERED Safely
    app.add_handler(CommandHandler("meme", meme_command))
    app.add_handler(CommandHandler("guess", guess_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    print("Funny Bot V4 With Mini-Games & Memes Running Smoothly...")
    app.run_polling()

if __name__ == "__main__":
    main()
