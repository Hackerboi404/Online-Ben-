from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = "8345687203:AAEloDRtx3ymHyuKDXbkUfjpnKvisTTbrMQ"
WEB_URL = "https://ben-tennyson.onrender.com"

async def stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Command received")  # debug

    keyboard = [
        [InlineKeyboardButton("🎬 Open Stream", url=WEB_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Click below to watch stream 👇",
        reply_markup=reply_markup
    )

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("stream", stream))

print("Bot started...")
app.run_polling()
