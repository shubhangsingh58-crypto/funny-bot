import os
import random

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction

from PIL import Image, ImageDraw


# 🔐 ENV
TOKEN = "8851707170:AAEeG4HQQG-QqROP1xn87gh5w5ZTC435PWs"


# 🧠 MEMORY
user_memory = {}
game_state = {}
user_mode = {}

ADMIN_ID = 123456789  # change this


# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_memory[user.id] = user.first_name
    user_mode[user.id] = "normal"

    await update.message.reply_text(
        "👋 Yo!\n🤖 Free Funny Bot is LIVE 24/7\nUse /help"
    )


# ---------------- HELP ----------------
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start\n/help\n/game\n/mode\n/meme\n/joke\n/roast"
    )


# ---------------- MODE ----------------
async def mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user_mode[uid] = "savage" if user_mode.get(uid, "normal") == "normal" else "normal"
    await update.message.reply_text(f"😎 Mode: {user_mode[uid]}")


# ---------------- GAME ----------------
async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    game_state[uid] = random.randint(1, 5)
    await update.message.reply_text("🎮 Guess number (1-5)")


# ---------------- MEME ----------------
async def meme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = " ".join(context.args)

    if not text:
        await update.message.reply_text("Use: /meme text")
        return

    img = Image.new("RGB", (500, 500), "black")
    draw = ImageDraw.Draw(img)
    draw.text((50, 200), text, fill="white")

    path = "meme.png"
    img.save(path)

    await update.message.reply_photo(photo=open(path, "rb"))
    os.remove(path)


# ---------------- JOKE ----------------
jokes = [
    "😂 Tu padhaai karta hai ya WiFi se rishta hai?",
    "😆 Tera code dekh ke compiler bhi ro deta hai",
    "🤣 Tu genius hai... bas subject change karle",
    "😜 Error tera friend ban gaya hai"
]

async def joke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(jokes))


# ---------------- ROAST ----------------
roasts = [
    "😈 Tu itna slow hai ki snail bhi overtake kar jaye",
    "😂 Tere ideas Google bhi reject kar de",
    "🤣 Tu silent mode pe bhi loud lagta hai",
    "😏 Brain loading... 99% forever"
]

async def roast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(random.choice(roasts))


# ---------------- CHAT (NO AI) ----------------
async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = update.message.text.lower()

    # GAME check
    if uid in game_state and text.isdigit():
        guess = int(text)
        correct = game_state[uid]

        if guess == correct:
            await update.message.reply_text("🎉 Correct!")
        else:
            await update.message.reply_text(f"❌ Wrong! It was {correct}")

        del game_state[uid]
        return

    # simple auto replies
    responses = {
        "hi": "👋 Yo bro!",
        "hello": "😄 Hello hello!",
        "how are you": "🤖 I am just code but I am fine 😎",
        "bye": "👋 Bye bye!"
    }

    reply_text = responses.get(text, random.choice([
        "😂 Kya bol raha hai tu?",
        "😎 Interesting...",
        "🤣 Samajh nahi aaya par theek hai",
        "🤖 Main free bot hoon bro 😄"
    ]))

    await update.message.reply_text(reply_text)


# ---------------- APP ----------------
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(CommandHandler("mode", mode))
app.add_handler(CommandHandler("game", game))
app.add_handler(CommandHandler("meme", meme))
app.add_handler(CommandHandler("joke", joke))
app.add_handler(CommandHandler("roast", roast))

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))

print("🤖 Free Funny Bot Running 24/7...")
app.run_polling()
