
import os
import logging
from decimal import Decimal, InvalidOperation

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from supabase import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EN96")

# إعدادات السيرفر: لا تضع المفاتيح السرية داخل هذا الملف
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase server environment variables are missing")

bot = telebot.TeleBot(BOT_TOKEN)
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
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


def get_profile(telegram_id):
    result = (
        supabase.table("profiles")
        .select("id, telegram_id")
        .eq("telegram_id", str(telegram_id))
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def format_amount(value):
    try:
        amount = Decimal(str(value or 0))
        return f"{amount:,.6f}".rstrip("0").rstrip(".")
    except (InvalidOperation, ValueError):
        return str(value)


def show_wallet(chat_id, telegram_id):
    try:
        profile = get_profile(telegram_id)

        if not profile:
            bot.send_message(
                chat_id,
                "⚠️ لم يتم العثور على ملفك في قاعدة البيانات.\n"
                "يرجى إبلاغ إدارة EN96 للمساعدة في ربط حسابك."
            )
            return

        result = (
            supabase.table("balances")
            .select("available, reserved")
            .eq("user_id", profile["id"])
            .limit(1)
            .execute()
        )

        if not result.data:
            bot.send_message(
                chat_id,
                "⚠️ تم العثور على حسابك، لكن لم يُنشأ له سجل رصيد بعد."
            )
            return

        balance = result.data[0]
        available = format_amount(balance.get("available"))
        reserved = format_amount(balance.get("reserved"))

        bot.send_message(
            chat_id,
            "💰 محفظة EN96\n\n"
            f"🟢 الرصيد المتاح: {available} EN96\n"
            f"🟠 الرصيد المحجوز: {reserved} EN96\n\n"
            "ℹ️ هذا رصيد افتراضي داخل البوت، "
            "وليس إثباتًا على تحويل عملات عبر Stellar.",
            reply_markup=main_menu()
        )

    except Exception:
        logger.exception("Wallet lookup failed")
        bot.send_message(
            chat_id,
            "❌ تعذر جلب الرصيد الآن. حاول مرة أخرى لاحقًا."
        )


def start_or_check_mining(chat_id, telegram_id):
    try:
        # تتحقق الدالة في Supabase من الجلسة وتحدّث الرصيد
        result = supabase.rpc(
            "en96_mining_action",
            {"p_telegram_id": str(telegram_id)}
        ).execute()

        data = result.data

        # بعض إصدارات العميل قد تعيد JSON مباشرة أو داخل قائمة
        if isinstance(data, list) and data:
            data = data[0]

        if not isinstance(data, dict):
            logger.error("Unexpected mining response: %r", data)
            bot.send_message(
                chat_id,
                "❌ وصلت استجابة غير متوقعة من نظام التعدين."
            )
            return

        status = data.get("status")

        if status == "profile_missing":
            bot.send_message(
                chat_id,
                "⚠️ حسابك غير مسجل في قاعدة البيانات بعد.\n"
                "اطلب من إدارة EN96 إكمال ربط حسابك."
            )

        elif status == "balance_missing":
            bot.send_message(
                chat_id,
                "⚠️ لم يُنشأ سجل رصيد لحسابك بعد.\n"
                "يرجى إبلاغ إدارة EN96."
            )

        elif status == "started":
            bot.send_message(
                chat_id,
                "⛏️ بدأ التعدين الافتراضي بنجاح!\n\n"
                "⏳ مدة الجلسة: 24 ساعة\n"
                "⚡ المعدل النظري: 0.001 EN96 في الثانية\n"
                "🏆 الحد الأقصى للجلسة الكاملة: 86.4 EN96\n\n"
                "سيتم احتساب المكافأة عند اكتمال المدة "
                "وعند التحقق من التعدين مجددًا.",
                reply_markup=main_menu()
            )

        elif status == "active":
            remaining = max(0, int(data.get("remaining_seconds", 0)))
            hours, remainder = divmod(remaining, 3600)
            minutes, seconds = divmod(remainder, 60)

            bot.send_message(
                chat_id,
                "⛏️ جلسة التعدين ما زالت جارية.\n\n"
                f"⏳ الوقت المتبقي: {hours} ساعة، "
                f"{minutes} دقيقة، {seconds} ثانية.\n\n"
                "لم تُضف مكافأة جديدة لأن مدة الجلسة لم تكتمل.",
                reply_markup=main_menu()
            )

        elif status == "rewarded_and_started":
            reward = format_amount(data.get("reward", 0))

            # عرض الرصيد بعد نجاح عملية المكافأة في قاعدة البيانات
            bot.send_message(
                chat_id,
                f"🎉 اكتملت جلسة التعدين!\n"
                f"💰 تمت إضافة {reward} EN96 إلى رصيدك المتاح.\n\n"
                "⛏️ بدأت جلسة جديدة مدتها 24 ساعة.",
                reply_markup=main_menu()
            )

        else:
            logger.warning("Unknown mining status: %r", status)
            bot.send_message(
                chat_id,
                "⚠️ لم نتعرف على حالة التعدين. "
                "يرجى المحاولة لاحقًا."
            )

    except Exception:
        logger.exception("Mining action failed")
        bot.send_message(
            chat_id,
            "❌ تعذر تنفيذ طلب التعدين. "
            "تحقق من اتصال Supabase وإعدادات السيرفر، ثم حاول مجددًا."
        )


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🐉 مرحبًا بك في EN96 Mining!\n\n"
        "أهلًا بك في مملكة التنين الجليدي.",
        reply_markup=main_menu()
    )


@bot.message_handler(
    func=lambda m: m.text == "💰 محفظتي"
)
def wallet_button(message):
    show_wallet(message.chat.id, message.from_user.id)


@bot.message_handler(
    func=lambda m: m.text == "⛏️ بدء التعدين"
)
def mining_button(message):
    start_or_check_mining(message.chat.id, message.from_user.id)


@bot.message_handler(
    func=lambda m: m.text == "📺 مشاهدة الفيديوهات"
)
def videos(message):
    bot.send_message(
        message.chat.id,
        "📺 فيديوهات EN96\n\n"
        "ستظهر هنا روابط الفيديوهات وأكواد الهدايا "
        "بعد ربط قائمة الفيديوهات."
    )


@bot.message_handler(
    func=lambda m: m.text == "🎁 استلام الهدية"
)
def gift(message):
    msg = bot.send_message(
        message.chat.id,
        "🎁 أرسل كود الهدية الموجود في فيديو EN96."
    )
    bot.register_next_step_handler(msg, check_gift)


def check_gift(message):
    code = (message.text or "").strip()

    if not code:
        bot.send_message(message.chat.id, "أرسل كودًا نصيًا صالحًا.")
        return

    # لا نمنح مكافأة هنا؛ يلزم ربط هذا الجزء بدالة
    # redeem_en96_video_gift والتحقق من مخططها الفعلي.
    bot.send_message(
        message.chat.id,
        "🔎 استلمنا الكود.\n"
        "التحقق من أكواد الهدايا لم يُربط بهذا الإصدار بعد؛ "
        "لن نضيف رصيدًا قبل التحقق من الكود."
    )


@bot.message_handler(func=lambda message: True)
def menu(message):
    responses = {
        "⚡ ترقية المنجم": "⚡ ميزة ترقية المنجم قيد الإعداد.",
        "🏆 المكافآت": "🏆 ستظهر هنا مكافآت التعدين والهدايا.",
        "🐉 أعضاء القبيلة": "🐉 سنضيف معلومات الأعضاء لاحقًا.",
        "ℹ️ معلومات EN96":
            "EN96 مشروع مرتبط بشبكة Stellar. "
            "الرصيد الافتراضي داخل البوت ليس تحويلًا على الشبكة."
    }

    bot.reply_to(
        message,
        responses.get(
            message.text,
            "اختر أحد الأزرار الموجودة في القائمة."
        ),
        reply_markup=main_menu()
    )


if __name__ == "__main__":
    logger.info("Starting EN96 Mining Bot...")
    bot.infinity_polling(skip_pending=True, timeout=30)
