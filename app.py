import os
import time
import threading
import sqlite3
import requests
import re
from datetime import datetime
from flask import Flask, jsonify

# ==========================================
# ⚙️ CONFIGURATION & CONSTANTS
# ==========================================
app = Flask(__name__)

# Get these from environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = list(map(int, os.environ.get("ADMIN_IDS", "123456789").split(",")))

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
DB_NAME = "guardian_bot.db"

# ==========================================
# 💾 DATABASE SYSTEM (SQLite)
# ==========================================
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, blacklisted INTEGER DEFAULT 0, reason TEXT, timestamp TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, group_id INTEGER, message TEXT, action TEXT, timestamp TEXT
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY, value TEXT
        )''')
        conn.commit()

def db_execute(query, params=(), fetch=False):
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        if fetch: return cursor.fetchall()
        return None

def is_blacklisted(user_id):
    res = db_execute("SELECT blacklisted FROM users WHERE user_id = ?", (user_id,), fetch=True)
    return res and res[0][0] == 1

def add_blacklist(user_id, username, reason):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_execute("INSERT OR REPLACE INTO users (user_id, username, blacklisted, reason, timestamp) VALUES (?, ?, 1, ?, ?)",
               (user_id, username, reason, now))

def remove_blacklist(user_id):
    db_execute("UPDATE users SET blacklisted = 0, reason = NULL WHERE user_id = ?", (user_id))

def get_blacklist():
    return db_execute("SELECT user_id, username, reason FROM users WHERE blacklisted = 1", fetch=True)

def save_log(user_id, group_id, message, action):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_execute("INSERT INTO logs (user_id, group_id, message, action, timestamp) VALUES (?, ?, ?, ?, ?)",
               (user_id, group_id, message, action, now))

def get_setting(key):
    res = db_execute("SELECT value FROM settings WHERE key = ?", (key,), fetch=True)
    return res[0][0] if res else None

def set_setting(key, value):
    db_execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

init_db()

# ==========================================
# 🧠 DETECTION ENGINE (UPDATED KEYWORDS)
# ==========================================
SCAM_KEYWORDS = [
    # Money & Investment
    "earn", "income", "profit", "investment", "crypto", "bitcoin", "trading", 
    "forex", "binary", "betting", "casino", "loan", "spam", "click here", 
    "join now", "daily income", "guaranteed", "work from home", "make money",
    "paisa", "kamaye", "rozana", "rupay", 
    "ربح", "استثمار", 
    "பணம்", "வருமானம்",
    # Job / Paid Spam
    "job", "internship", "salary", "part time", "work from home", "earn daily",
    "paid", "paid promotion", "paid service", "paid ugc", "paid promo",
    "job alert", "hiring", "vacancy", "recruitment"
]

# 🚫 ADULT / PAID SERVICE / BAD WORDS FILTER
BAD_CONTENT_KEYWORDS = [
    # Adult / Paid Services
    "sex", "porn", "xxx", "nude", "naked", "nsfw", "hentai", "onlyfans",
    "call girl", "callgirl", "escort", "massage", "night service", "dating",
    "service available", "full night", "fun available", "enjoy", "hookup",
    
    # Specific Requests (like 8inc)
    "8inc", "dick pic", "cock", "pussy", "boobs", "ass", "fuck", 
    "chut", "lund", "gand", "muth", "madarchod", "behenchod", "randi",
    
    # Inappropriate / Abuse
    "rape", "kill", "death", "suicide", "bomb", "terrorist"
]

def calculate_score(text):
    if not text: return 0
    text_lower = text.lower()
    score = 0

    # 1. Scam / Money / Job Keywords (+5)
    for kw in SCAM_KEYWORDS:
        if kw in text_lower:
            score += 5
            break 

    # 2. ADULT / BAD WORDS / PAID SERVICES (+8)
    for kw in BAD_CONTENT_KEYWORDS:
        if kw in text_lower:
            score += 8
            break 

    # 3. Group Invite Link (+10)
    if re.search(r't\.me/\+|t\.me/joinchat', text):
        score += 10

    # 4. Emoji Spam / Distortion (+3)
    if len(re.findall(r'[^\w\s]', text)) > 10: 
        score += 3
    if re.search(r'(.)\1{4,}', text): 
        score += 3

    return score

def send_log(user_id, group_id, msg_text, reason, action):
    save_log(user_id, group_id, msg_text, f"{action} | {reason}")
    log_channel_id = get_setting("log_channel")
    
    if log_channel_id:
        log_msg = (
            f"🚨 **Guardian Filter Log**\n"
            f"👤 User: `{user_id}`\n"
            f"🗑 Action: {action}\n"
            f"📝 Reason: {reason}\n"
            f"💬 Message: `{msg_text[:100]}...`\n"
            f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}"
        )
        try:
            requests.post(f"{API_URL}/sendMessage", data={
                "chat_id": log_channel_id, "text": log_msg, "parse_mode": "Markdown"
            })
        except Exception as e:
            print(f"Log failed: {e}")

def telegram_request(method, data):
    try:
        requests.post(f"{API_URL}/{method}", data=data)
    except Exception as e:
        print(f"API Error: {e}")

# ==========================================
# 🚀 POLLING LOOP
# ==========================================
offset = 0
def run_bot():
    global offset
    print("🤖 Guardian Bot Started...")
    
    while True:
        try:
            resp = requests.get(f"{API_URL}/getUpdates", params={"timeout": 30, "offset": offset})
            data = resp.json()
            
            if not data["ok"]:
                time.sleep(5)
                continue

            for update in data["result"]:
                offset = update["update_id"] + 1
                
                # Handle Group Join (Auto-Ban Blacklisters, No Welcome Msg)
                if "new_chat_members" in update.get("message", {}):
                    message = update["message"]
                    chat = message["chat"]
                    user = message["new_chat_members"][0] 
                    chat_id = chat["id"]
                    user_id = user["id"]
                    
                    # If blacklisted, ban them immediately
                    if is_blacklisted(user_id):
                        telegram_request("banChatMember", {"chat_id": chat_id, "user_id": user_id})
                        send_log(user_id, chat_id, "User Joined", "Auto-Banned (Blacklisted)", "Banned")
                    continue

                message = update.get("message")
                if not message: continue

                user = message.get("from")
                chat = message.get("chat")
                text = message.get("text", "")
                msg_id = message.get("message_id")
                
                user_id = user["id"]
                username = user.get("username", "Unknown")
                chat_id = chat["id"]
                chat_type = chat.get("type", "private")
                is_admin = user_id in ADMIN_IDS

                # --- DM COMMAND: /start (Neon Welcome) ---
                if chat_type == "private" and text == "/start":
                    first_name = user.get("first_name", "Friend")
                    
                    # Neon Style Welcome Message
                    welcome_msg = (
                        f"💠 𝗪𝗲𝗹𝗰𝗼𝗺𝗲 𝘁𝗼 𝗚𝘂𝗮𝗿𝗱𝗶𝗮𝗻 𝗙𝗶𝗹𝘁𝗲𝗿, {first_name}! 💠\n\n"
                        f"🛡️ 𝗔𝗱𝘃𝗮𝗻𝗰𝗲𝗱 𝗦𝗽𝗮𝗺 𝗣𝗿𝗼𝘁𝗲𝗰𝘁𝗶𝗼𝗻\n"
                        f"⚡ 𝗠𝘂𝗹𝘁𝗶-𝗹𝗶𝗻𝗴𝘂𝗮𝗹 𝗔𝗜 𝗗𝗲𝘁𝗲𝗰𝘁𝗶𝗼𝗻\n"
                        f"🚫 𝗔𝘂𝘁𝗼-𝗕𝗹𝗮𝗰𝗸𝗹𝗶𝘀𝘁 𝗦𝘆𝘀𝘁𝗲𝗺\n"
                        f"📊 𝗥𝗲𝗮𝗹-𝘁𝗶𝗺𝗲 𝗟𝗼𝗴𝗴𝗶𝗻𝗴\n\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"✨ 𝗙𝗲𝗮𝘁𝘂𝗿𝗲𝘀:\n"
                        f"• 𝗦𝗰𝗮𝗺 & 𝗖𝗿𝘆𝗽𝘁𝗼 𝗙𝗶𝗹𝘁𝗲𝗿\n"
                        f"• 𝗔𝗱𝘂𝗹𝘁 & 𝗕𝗮𝗱 𝗪𝗼𝗿𝗱 𝗙𝗶𝗹𝘁𝗲𝗿\n"
                        f"• 𝗣𝗮𝗶𝗱 𝗦𝗲𝗿𝘃𝗶𝗰𝗲 𝗕𝗹𝗼𝗰𝗸𝗲𝗿\n"
                        f"• 𝗝𝗼𝗯/𝗦𝗽𝗮𝗺 𝗗𝗲𝘁𝗲𝗰𝘁𝗼𝗿\n"
                        f"━━━━━━━━━━━━━━━\n"
                        f"🤖 𝗔𝗱𝗱 𝗺𝗲 𝘁𝗼 𝘆𝗼𝘂𝗿 𝗴𝗿𝗼𝘂𝗽 𝘁𝗼 𝗴𝗲𝘁 𝘀𝘁𝗮𝗿𝘁𝗲𝗱!"
                    )
                    
                    telegram_request("sendMessage", {
                        "chat_id": chat_id, 
                        "text": welcome_msg
                    })
                    continue

                # --- ADMIN COMMANDS ---
                if is_admin and text.startswith("/"):
                    if text == "/blacklist list":
                        blist = get_blacklist()
                        reply = "🚫 **Blacklist:**\n" + "\n".join([f"• `{u[0]}` ({u[1]})" for u in blist])
                        telegram_request("sendMessage", {"chat_id": chat_id, "text": reply, "parse_mode": "Markdown"})
                    elif text.startswith("/unblacklist"):
                        try:
                            target_id = int(text.split(" ")[1])
                            remove_blacklist(target_id)
                            telegram_request("sendMessage", {"chat_id": chat_id, "text": f"✅ Unblacklisted {target_id}"})
                        except: pass
                    elif text.startswith("/log set"):
                        set_setting("log_channel", str(chat_id))
                        telegram_request("sendMessage", {"chat_id": chat_id, "text": "✅ Log channel set!"})
                    elif text == "/stats":
                        logs = db_execute("SELECT COUNT(*) FROM logs", fetch=True)[0][0]
                        users = db_execute("SELECT COUNT(*) FROM users", fetch=True)[0][0]
                        telegram_request("sendMessage", {"chat_id": chat_id, "text": f"📊 Logs: {logs}\n👥 Users: {users}"})
                    continue

                # --- MODERATION (Groups Only) ---
                if chat_type in ["group", "supergroup"]:
                    
                    if is_blacklisted(user_id):
                        telegram_request("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
                        send_log(user_id, chat_id, text, "User Blacklisted", "Deleted")
                        continue

                    score = calculate_score(text)

                    # Score 8+ Delete + Ban
                    if score >= 8:
                        telegram_request("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
                        telegram_request("banChatMember", {"chat_id": chat_id, "user_id": user_id}) 
                        add_blacklist(user_id, username, f"Severe Violation (Score {score})")
                        send_log(user_id, chat_id, text, f"Severe (Score {score})", "Banned + Deleted")
                    
                    # Score 5+ Delete Only
                    elif score >= 5:
                        telegram_request("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
                        send_log(user_id, chat_id, text, f"Moderate (Score {score})", "Deleted")

        except Exception as e:
            print(f"Polling Error: {e}")
            time.sleep(5)

# ==========================================
# 🌐 FLASK ENDPOINTS
# ==========================================
@app.route('/')
def index():
    neon_html = """
    <div style='background-color:#0d0d0d; color:#00ffcc; font-family:monospace; padding:20px; text-align:center;'>
        <h1>💠 𝗚𝘂𝗮𝗿𝗱𝗶𝗮𝗻 𝗙𝗶𝗹𝘁𝗲𝗿 𝗕𝗼𝘁 💠</h1>
        <p>🚫 Spam/Scam: <b>ACTIVE</b></p>
        <p>🔞 Adult/Bad Words: <b>BLOCKED</b></p>
        <p>💸 Paid Services: <b>BLOCKED</b></p>
        <p>🧠 AI Detection: <b>RUNNING</b></p>
    </div>
    """
    return neon_html

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    t = threading.Thread(target=run_bot)
    t.daemon = True
    t.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=5000)
