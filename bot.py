import os
import logging
import json

import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
)
from supabase import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EN96")

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase environment variables are missing")

bot = telebot.TeleBot(BOT_TOKEN)
db = create_client(SUPABASE_URL, SUPABASE_KEY)

APP_URL = "https://en96.onrender.com"


def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)

    # فتح تطبيق EN96 داخل تيليغرام
    keyboard.row(
        KeyboardButton(
            "🚀 فتح تطبيق EN96",
            web_app=WebAppInfo(url=APP_URL)
        )
    )

    keyboard.row(
        KeyboardButton("⛏️ بدء التعدين"),
        KeyboardButton("💰 محفظتي")
    )
    keyboard.row(
        KeyboardButton("⚡ ترقية المنجم"),
        KeyboardButton("🏆 المكافآت")
    )
    keyboard.row(
        KeyboardButton("📺 مشاهدة الفيديوهات"),
        KeyboardButton("🎁 استلام الهدية")
    )
    keyboard.row(
        KeyboardButton("🐉 أعضاء القبيلة"),
        KeyboardButton("ℹ️ معلومات EN96")
    )

    return keyboard


def send_menu(chat_id, text):
    bot.send_message(chat_id, text, reply_markup=main_menu())


def get_profile(telegram_id):
    result = (
        db.table("profiles")
        .select("id,telegram_id")
        .eq("telegram_id", str(telegram_id))
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def wallet(chat_id, telegram_id):
    try:
        profile = get_profile(telegram_id)

        if not profile:
            send_menu(
                chat_id,
                "⚠️ حسابك غير مربوط بقاعدة البيانات بعد."
            )
            return

        result = (
            db.table("balances")
            .select("available,reserved")
            .eq("user_id", profile["id"])
            .limit(1)
            .execute()
        )

        if not result.data:
            send_menu(chat_id, "⚠️ سجل رصيدك غير موجود.")
            return

        row = result.data[0]
        send_menu(
            chat_id,
            "💰 محفظة EN96\n\n"
            f"🟢 الرصيد المتاح: {row.get('available', 0)} EN96\n"
            f"🟠 الرصيد المحجوز: {row.get('reserved', 0)} EN96\n\n"
            "ℹ️ هذا رصيد افتراضي داخل البوت."
        )

    except Exception:
        logger.exception("Wallet error")
        send_menu(
            chat_id,
            "❌ تعذرت قراءة المحفظة. يرجى مراجعة سجلات Render."
        )


def mining(chat_id, telegram_id):
    try:
        result = db.rpc(
            "en96_mining_action",
            {"p_telegram_id": str(telegram_id)}
        ).execute()

        data = result.data
        if isinstance(data, list) and data:
            data = data[0]

        if not isinstance(data, dict):
            send_menu(
                chat_id,
                "❌ استجابة غير متوقعة من قاعدة البيانات."
            )
            return

        status = data.get("status")

        if status == "profile_missing":
            message = "⚠️ حسابك غير مربوط في profiles."
        elif status == "balance_missing":
            message = "⚠️ سجل رصيدك غير موجود في balances."
        elif status == "started":
            message = (
                "⛏️ بدأ التعدين الافتراضي!\n\n"
                "⏳ المدة: 24 ساعة\n"
                "⚡ المعدل: 0.001 EN96/ثانية\n"
                "🏆 مكافأة الجلسة الكاملة: 86.4 EN96"
            )
        elif status == "active":
            seconds = max(
                0, int(data.get("remaining_seconds", 0))
            )
            hours, remainder = divmod(seconds, 3600)
            minutes = remainder // 60
            message = (
                "⛏️ التعدين ما زال جاريًا.\n"
                f"⏳ الوقت المتبقي: {hours} ساعة و{minutes} دقيقة."
            )
        elif status == "rewarded_and_started":
            message = (
                "🎉 اكتملت جلسة التعدين!\n"
                f"💰 المكافأة المضافة: {data.get('reward', 0)} EN96\n"
                "⛏️ بدأت جلسة جديدة مدتها 24 ساعة."
            )
        else:
            message = f"⚠️ حالة التعدين: {status}"

        send_menu(chat_id, message)

    except Exception:
        logger.exception("Mining error")
        send_menu(
            chat_id,
            "❌ تعذر تنفيذ التعدين. يرجى مراجعة سجلات Render."
        )


def process_gift_code(message):
    code = (message.text or "").strip()
    chat_id = message.chat.id

    menu_buttons = {
        "🚀 فتح تطبيق EN96",
        "⛏️ بدء التعدين",
        "💰 محفظتي",
        "⚡ ترقية المنجم",
        "🏆 المكافآت",
        "📺 مشاهدة الفيديوهات",
        "🎁 استلام الهدية",
        "🐉 أعضاء القبيلة",
        "ℹ️ معلومات EN96",
    }

    if not code or code in menu_buttons or code.startswith("/"):
        send_menu(
            chat_id,
            "تم إلغاء إدخال الكود. اضغط 🎁 استلام الهدية للمحاولة مجددًا."
        )
        return

    try:
        result = db.rpc(
            "redeem_en96_video_gift",
            {
                "p_telegram_id": message.from_user.id,
                "p_code": code,
            }
        ).execute()

        data = result.data

        if isinstance(data, list) and data:
            data = data[0]

        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (ValueError, TypeError):
                data = None

        if not isinstance(data, dict):
            logger.error(
                "Unexpected gift response type: %s",
                type(data).__name__
            )
            send_menu(
                chat_id,
                "❌ وصل رد غير متوقع من قاعدة البيانات."
            )
            return

        if data.get("ok") is True:
            reward = data.get("reward", 0)
            available = data.get("available")

            response = (
                "🎉 تم استلام الهدية بنجاح!\n\n"
                f"🎁 المكافأة: {reward} EN96\n"
            )

            if available is not None:
                response += (
                    f"💰 الرصيد المتاح الآن: {available} EN96\n"
                )

            response += "\n✅ تم حفظ المكافأة في قاعدة البيانات."

        else:
            reason = data.get(
                "reason",
                data.get("status", data.get("error", "unknown"))
            )

            messages = {
                "invalid_input": "⚠️ بيانات المطالبة غير مكتملة.",
                "profile_not_found": "⚠️ حسابك غير مربوط في profiles.",
                "invalid_or_inactive_code": "❌ الكود غير صحيح أو غير نشط.",
                "already_claimed": "⚠️ سبق لك استلام هذه الهدية.",
                "cooldown_2_hours": "⏳ انتظر ساعتين قبل طلب هدية أخرى.",
                "balance_not_found": "⚠️ سجل رصيدك غير موجود في balances.",
            }

            response = messages.get(
                reason,
                f"⚠️ تعذر استلام الهدية. السبب: {reason}"
            )

        send_menu(chat_id, response)

    except Exception:
        logger.exception("Gift redemption error")
        send_menu(
            chat_id,
            "❌ حدث خطأ أثناء التحقق من الكود. "
            "يرجى مراجعة سجلات Render."
        )


# بدء البوت
@bot.message_handler(commands=["start"])
def start(message):
    send_menu(
        message.chat.id,
        "🐉 مرحبًا بك في EN96 Mining!\n"
        "أهلًا بك في مملكة التنين الجليدي.\n\n"
        "🚀 اضغط على زر فتح تطبيق EN96 للدخول إلى التطبيق."
    )


# أوامر تيليغرام المباشرة
@bot.message_handler(commands=["wallet"])
def wallet_command(message):
    wallet(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["mining"])
def mining_command(message):
    mining(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["rewards"])
def rewards_command(message):
    send_menu(
        message.chat.id,
        "🏆 مكافآت EN96\n\n"
        "⚡ معدل التعدين الافتراضي: 0.001 EN96 في الثانية.\n"
        "⏳ مدة الجلسة: 24 ساعة.\n"
        "ℹ️ المكافآت افتراضية داخل البوت."
    )


@bot.message_handler(commands=["videos"])
def videos_command(message):
    send_menu(
        message.chat.id,
        "📺 قائمة الفيديوهات قيد الإعداد."
    )


@bot.message_handler(commands=["tribe"])
def tribe_command(message):
    send_menu(
        message.chat.id,
        "🐉 معلومات أعضاء القبيلة قيد الإعداد."
    )


@bot.message_handler(commands=["info"])
def info_command(message):
    send_menu(
        message.chat.id,
        "ℹ️ معلومات EN96\n\n"
        "EN96 مشروع مرتبط بشبكة Stellar.\n"
        "الرصيد الافتراضي داخل البوت ليس تحويلًا على الشبكة."
    )


# أزرار القائمة
@bot.message_handler(func=lambda m: m.text == "💰 محفظتي")
def wallet_button(message):
    wallet(message.chat.id, message.from_user.id)


@bot.message_handler(func=lambda m: m.text == "⛏️ بدء التعدين")
def mining_button(message):
    mining(message.chat.id, message.from_user.id)


@bot.message_handler(func=lambda m: m.text == "🎁 استلام الهدية")
def gift_button(message):
    prompt = bot.send_message(
        message.chat.id,
        "🎁 أرسل كود الهدية الذي حصلت عليه من الفيديو:"
    )
    bot.register_next_step_handler(prompt, process_gift_code)


@bot.message_handler(func=lambda m: m.text == "📺 مشاهدة الفيديوهات")
def videos_button(message):
    send_menu(
        message.chat.id,
        "📺 قائمة الفيديوهات قيد الإعداد."
    )


@bot.message_handler(func=lambda m: m.text == "🏆 المكافآت")
def rewards_button(message):
    rewards_command(message)


@bot.message_handler(func=lambda m: m.text == "🐉 أعضاء القبيلة")
def tribe_button(message):
    tribe_command(message)


@bot.message_handler(func=lambda m: m.text == "ℹ️ معلومات EN96")
def info_button(message):
    info_command(message)


@bot.message_handler(func=lambda m: m.text == "⚡ ترقية المنجم")
def upgrade_button(message):
    send_menu(
        message.chat.id,
        "⚡ ميزة ترقية المنجم قيد الإعداد."
    )


@bot.message_handler(func=lambda m: m.text == "🚀 فتح تطبيق EN96")
def open_app_button(message):
    send_menu(
        message.chat.id,
        "🚀 اضغط على زر فتح تطبيق EN96 في القائمة لفتحه."
    )


@bot.message_handler(func=lambda m: True)
def other_messages(message):
    send_menu(
        message.chat.id,
        "اختر أمرًا أو زرًا من قائمة EN96."
    )


if __name__ == "__main__":
    logger.info("Starting EN96 bot")
    bot.infinity_polling(skip_pending=True, timeout=30)
```

