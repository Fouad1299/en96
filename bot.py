import os
import json
import time
import logging
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from supabase import create_client
from en96_accounts import ensure_profile


# =====================================
# EN96 CONFIGURATION
# =====================================

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("EN96")

BOT_TOKEN = os.getenv("BOT_TOKEN")

SUPABASE_URL = os.getenv("SUPABASE_URL")

SUPABASE_KEY = (
    os.getenv("SUPABASE_SECRET_KEY")
    or os.getenv("SUPABASE_KEY")
)

ADMIN_ID = str(
    os.getenv("ADMIN_TELEGRAM_ID", "8721009110")
)

APP_URL = os.getenv(
    "APP_URL",
    "https://en96.onrender.com"
)

BOT_USERNAME = "EN96_IceDragon_2026_Bot"

# Official EN96 TikTok
TIKTOK_URL = "https://www.tiktok.com/@en96mining"

# Virtual mining settings
MINING_RATE = 0.001
MINING_DURATION = 86400

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing")

bot = telebot.TeleBot(BOT_TOKEN)

db = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

MINING_COUNTERS = {}
MINING_LOCK = threading.Lock()

WAITING_GIFT = set()
WAITING_ADMIN_CODE = set()
WAITING_ADMIN_VIDEO = set()
WAITING_ADMIN_REWARD = set()

ADMIN_ACTION = {}
PENDING = {}


# =====================================
# HELPERS
# =====================================

def is_admin(user_id):
    return str(user_id) == ADMIN_ID


def rpc_data(result):
    data = result.data

    if isinstance(data, list):
        data = data[0] if data else {}

    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {"message": data}

    return data or {}


def register_member(user_id):
    try:
        ensure_profile(db, user_id)
        return True

    except Exception:
        log.exception(
            "EN96 registration failed: %s",
            user_id
        )
        return False


def profile_for(user_id):
    result = (
        db.table("profiles")
        .select(
            "id,telegram_id,stellar_public_address"
        )
        .eq("telegram_id", str(user_id))
        .limit(1)
        .execute()
    )

    return result.data[0] if result.data else None


def en96_number(value):
    try:
        return f"{float(value or 0):,.7f}"
    except (TypeError, ValueError):
        return "0.0000000"


# =====================================
# MAIN MENU
# =====================================

def menu(user_id=None):
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    kb.row(
        KeyboardButton("⛏️ بدء التعدين"),
        KeyboardButton("💰 محفظتي"),
    )

    kb.row(
        KeyboardButton("⚡ ترقية المنجم"),
        KeyboardButton("🏆 المكافآت"),
    )

    kb.row(
        KeyboardButton("📺 مشاهدة الفيديوهات"),
        KeyboardButton("🎁 استلام الهدية"),
    )

    kb.row(
        KeyboardButton("🐻 أعضاء القبيلة"),
        KeyboardButton("ℹ️ معلومات EN96"),
    )

    # NEW: Official TikTok button
    kb.row(
        KeyboardButton("🎵 TikTok EN96"),
        KeyboardButton("🌐 فتح تطبيق EN96"),
    )

    if user_id is not None and is_admin(user_id):
        kb.row(
            KeyboardButton("🛠️ إدارة الهدايا"),
            KeyboardButton("⭐ رصيد Stars للإدارة"),
        )

    return kb


def admin_menu():
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    kb.row(
        KeyboardButton("➕ إنشاء كود هدية"),
        KeyboardButton("📋 أكواد الهدايا"),
    )

    kb.row(
        KeyboardButton("⛔ تعطيل كود"),
        KeyboardButton("✅ تفعيل كود"),
    )

    kb.row(
        KeyboardButton("🔙 القائمة الرئيسية")
    )

    return kb


# =====================================
# NEW: TIKTOK EN96
# =====================================

def show_tiktok(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🎵 افتح TikTok الرسمي لـ EN96",
            url=TIKTOK_URL,
        )
    )

    bot.send_message(
        chat_id,
        "🐻👑 TikTok الرسمي لمملكة EN96\n"
        "━━━━━━━━━━━━━━\n\n"
        "🎵 تابع أخبار EN96 الجديدة.\n"
        "🎬 شاهد فيديوهات الدب الملك.\n"
        "🎁 ابحث عن أكواد الهدايا في الفيديوهات.\n\n"
        "اضغط على الزر بالأسفل لزيارة حسابنا:\n\n"
        "@en96mining\n\n"
        "💎 يمكنك العودة إلى هذا البوت "
        "لاستبدال أكواد الهدايا المتاحة.\n\n"
        "⚠️ تُضاف المكافآت فقط عند إدخال "
        "كود صحيح وقبول الطلب في نظام EN96.",
        reply_markup=kb,
        disable_web_page_preview=True,
    )


@bot.message_handler(commands=["tiktok"])
def tiktok_command(message):
    show_tiktok(message.chat.id)


# =====================================
# TELEGRAM APP LOGIN
# =====================================

def app_button(chat_id):
    if not APP_URL.startswith("https://"):
        bot.send_message(
            chat_id,
            "رابط تطبيق EN96 غير مضبوط."
        )
        return

    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🔐 دخول EN96 عبر تيليغرام 🐻",
            web_app=WebAppInfo(url=APP_URL),
        )
    )

    bot.send_message(
        chat_id,
        "🐻❄️ مرحبًا بك في EN96!\n\n"
        "اضغط الزر أسفل الرسالة للدخول "
        "بحساب تيليغرام.\n\n"
        "✅ لا تحتاج إلى بريد إلكتروني.\n"
        "✅ لا تحتاج إلى كلمة مرور.",
        reply_markup=kb,
    )


def send_menu(
    chat_id,
    text="🐻 مرحبًا بك في EN96 Mining!",
    user_id=None,
):
    bot.send_message(
        chat_id,
        text,
        reply_markup=menu(user_id)
    )

    if (
        user_id is not None
        and str(chat_id) == str(user_id)
    ):
        app_button(chat_id)


# =====================================
# WALLET
# =====================================

def wallet(chat_id, user_id):
    try:
        profile = profile_for(user_id)

        if not profile:

