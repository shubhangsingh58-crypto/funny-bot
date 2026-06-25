import os
import random
import logging
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
TOKEN ="8851707170:AAEeG4HQQG-QqROP1xn87gh5w5ZTC435PWs"

if not TOKEN:
    raise ValueError("TOKEN environment variable missing!")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# =========================
# DATA
# =========================
JOKES = [
    "Why don’t skeletons fight each other? They don’t have the guts 😆",
    "I told my computer I needed a break… now it won’t stop sending me KitKats 🍫",
    "Parallel lines have so much in common… it’s a shame they’ll never meet 😭",
    "Why was the math book sad? It had too many problems 📚",
    "My Wi-Fi and I have a special connection… until someone moves the router 😤",
    "I asked the dog what’s two minus two. He said nothing 🐶",
]

ROASTS = [
    "You’re not useless… you can always be used as a bad example 😏",
    "You have something on your chin… no, the third one.",
    "You bring everyone so much joy… when you leave the chat 😌",
    "Your secrets are always safe with me. I never even listen when you tell me 😴",
    "You’re proof that even Google doesn’t have all the answers.",
]

MEMES = [
    "When you say ‘I’ll sleep early today’ and suddenly it’s 3:07 AM 🤡",
    "Me: just one reel.\nAlso me 2 hours later: 🫠",
    "POV: you opened the fridge for no reason and still expected a miracle 🍕",
    "When teacher says ‘it’s easy’ and the whole class goes silent 💀",
    "That one friend who says ‘5 min’ and arrives after 2 business days 🐢",
]

QUOTES = [
    "I’m not lazy. I’m on energy-saving mode 😌",
    "Confidence level: screenshotting my own jokes.",
    "Life is short. Smile while you still have teeth 😁",
    "If stress burned calories, I’d be a model by now.",
    "Be yourself. Unless you can be a potato. Potatoes are great 🥔",
]

TRUTHS = [
    "What’s the most embarrassing thing you’ve searched recently? 👀",
    "Who was your first crush? 😏",
    "What’s one secret habit nobody knows about? 🤫",
    "Have you ever lied to get out of trouble? 😶",
    "What’s the dumbest thing you’ve done because of a dare? 😂",
]

DARES = [
    "Send a voice note saying ‘I am the king/queen of nonsense’ 🎤",
    "Change your bio/status to ‘Professional overthinker’ for 10 minutes 😎",
    "Type with only emojis for the next 5 messages 😂",
    "Compliment the last person you texted ✨",
    "Do 10 squats right now. No excuses 😤",
]

HI_REPLIES = [
    "Yo 😎 kya haal?",
    "Hello ji 😄",
    "Haan bhai bol 😏",
    "Hi hi 👋",
    "Kya scene hai 😌",
]

BAD_WORDS = {
    # Basic examples. Add/remove as you like.
    "bc", "mc", "bkl", "chutiya", "gandu", "madarchod", "behenchod"
}

# In-memory warning counts (resets on restart)
user_warnings = {}

# =========================
# HELP TEXT
# =========================
HELP_TEXT = """
🤖 *Funny Bot Commands*

*/start* - Start the bot
*/help* - Show all commands
*/joke* - Random joke 😂
*/roast* - Savage roast 😈
*/meme* - Meme-style line 🎭
*/quote* - Funny quote 😎
*/truth* - Random truth question 👀
*/dare* - Random dare challenge 🔥
*/ship name1 name2* - Fun compatibility %
*/rate your text* - Rate anything out of 10
*/ping* - Bot status check 🟢
*/about* - About the bot

💬 Normal chat:
Say *hi*, *hello*, *hey* and I’ll reply 😄
"""

ABOUT_TEXT = """
🤖 *Free Funny Bot*
Your 24/7 fun partner for jokes, memes, roasts and chaos 😎

Made with Python + Telegram Bot API
Hosted online so it stays active ⚡
"""

# =========================
# COMMAND HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Yo! 😎\n"
        "🤖 *Free Funny Bot is LIVE 24/7*\n"
        "Use /help to see commands"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(ABOUT_TEXT, parse_mode="Markdown")

async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Bot is online and chilling 😎")

async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(JOKES))

async def roast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(ROASTS))

async def meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(MEMES))

async def quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(QUOTES))

async def truth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🫣 Truth:\n" + random.choice(TRUTHS))

async def dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 Dare:\n" + random.choice(DARES))

async def ship(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /ship name1 name2")
        return

    name1 = args[0]
    name2 = args[1]
    percent = random.randint(1, 100)

    if percent >= 85:
        vibe = "Soulmate energy 💘"
    elif percent >= 60:
        vibe = "Pretty solid match 😏"
    elif percent >= 35:
        vibe = "Could work… maybe 👀"
    else:
        vibe = "Bas dosti hi theek hai 😭"

    await update.message.reply_text(
        f"💞 *Ship Result*\n{name1} ❤️ {name2}\nCompatibility: *{percent}%*\n{vibe}",
        parse_mode="Markdown"
    )

async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /rate something")
        return

    thing = " ".join(context.args)
    score = random.randint(1, 10)
    comments = {
        1: "Certified disaster 💀",
        2: "Nahh bhai, weak 😭",
        3: "Needs serious improvement 😶",
        4: "Thoda theek, thoda nahi 😬",
        5: "Average-ish 😐",
        6: "Not bad 👌",
        7: "Pretty good 😎",
        8: "Solid stuff 🔥",
        9: "Damn, impressive 😮",
        10: "Absolute masterpiece 👑",
    }
    await update.message.reply_text(
        f"📊 *Rating*\n{thing}\nScore: *{score}/10*\n{comments[score]}",
        parse_mode="Markdown"
    )

# =========================
# GROUP / CHAT MODERATION
# =========================
def contains_bad_word(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in BAD_WORDS)

async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles normal text: hi/hello replies + bad word warnings."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip().lower()
    user = update.effective_user

    # Basic moderation
    if contains_bad_word(text):
        user_id = user.id
        user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
        count = user_warnings[user_id]

        await update.message.reply_text(
            f"⚠️ {user.first_name}, thoda language control 😅\nWarning: {count}/3"
        )

        # Optional: after 3 warnings, send stronger message
        if count >= 3:
            await update.message.reply_text(
                f"🚫 {user.first_name}, next time thoda tameez se 😤"
            )
        return

    # Friendly replies
    greetings = {"hi", "hello", "hey", "yo", "hii", "heyy"}
    if text in greetings:
        await update.message.reply_text(random.choice(HI_REPLIES))
        return

# =========================
# NEW MEMBER WELCOME
# =========================
async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            await update.message.reply_text(
                f"🎉 Welcome {member.first_name}!\n"
                f"Main Funny Bot hoon 😎\n"
                f"Use /help and let the chaos begin 🔥"
            )

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

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("joke", joke))
    app.add_handler(CommandHandler("roast", roast))
    app.add_handler(CommandHandler("meme", meme))
    app.add_handler(CommandHandler("quote", quote))
    app.add_handler(CommandHandler("truth", truth))
    app.add_handler(CommandHandler("dare", dare))
    app.add_handler(CommandHandler("ship", ship))
    app.add_handler(CommandHandler("rate", rate))

    # Group welcome
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_members))

    # Text / moderation / hi-hello
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, moderate_message))

    # Error logging
    app.add_error_handler(error_handler)

    print("🤖 Free Funny Bot Running 24/7...")
    app.run_polling()

if __name__ == "__main__":
    main()
          
