from flask import Flask
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ===== CONFIG =====
BOT_TOKEN = "8345687203:AAEloDRtx3ymHyuKDXbkUfjpnKvisTTbrMQ"
WEB_URL = "https://ben-tennyson.onrender.com"

# ===== FLASK =====
app = Flask(__name__)

@app.route("/")
def home():
    return "<h1>🔥 Stream is Live</h1>"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

# ===== BOT =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is alive & working!")

async def stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Open Stream", url=WEB_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Click below to watch stream 👇",
        reply_markup=reply_markup
    )

# ===== MAIN =====
if __name__ == "__main__":
    # Flask background me
    threading.Thread(target=run_flask).start()

    # Bot MAIN THREAD me (IMPORTANT 🔥)
    app_bot = ApplicationBuilder().token(BOT_TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(CommandHandler("stream", stream))

    print("🤖 Bot started...")

    app_bot.run_polling()
