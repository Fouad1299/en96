import os
import logging
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing from environment secrets")

bot = telebot.TeleBot(BOT_TOKEN)


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


@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🐉 مرحبًا بك في EN96 Mining!\n\n"
        "أهلًا بك في مملكة التنين الجليدي.",
        reply_markup=main_menu()
    )


@bot.message_handler(
    func=lambda m: m.text == "📺 مشاهدة الفيديوهات"
)
def videos(message):
    bot.send_message(
        message.chat.id,
        "📺 فيديوهات EN96\n\n"
        "ستظهر هنا روابط الفيديوهات وأكواد الهدايا "
        "بعد إعداد قاعدة بيانات الهدايا."
    )


@bot.message_handler(
    func=lambda m: m.text == "🎁 استلام الهدية"
)
def gift(message):
    msg = bot.send_message(
        message.chat.id,
        "🎁 أرسل كود الهدية الموجود في فيديو EN96.\n"
        "مثال: 15642\n\n"
        "لن يُضاف أي رصيد حتى نربط التحقق بقاعدة البيانات."
    )
    bot.register_next_step_handler(msg, check_gift)


def check_gift(message):
    code = (message.text or "").strip()
    if not code:
        bot.send_message(
            message.chat.id,
            "أرسل كودًا نصيًا صالحًا من فيديو EN96."
        )
        return

    bot.send_message(
        message.chat.id,
        "🔎 استلمت الكود: " + code + "\n\n"
        "الخطوة التالية هي التحقق من الكود في قاعدة البيانات "
        "ومنع تكرار المطالبة قبل منح 1 EN96 افتراضية."
    )


@bot.message_handler(func=lambda message: True)
def menu(message):
    responses = {
        "⛏️ بدء التعدين":
            "⛏️ سنربط التعدين الافتراضي وحفظ المكافآت بقاعدة البيانات.",
        "💰 محفظتي":
            "💰 سنعرض رصيدك المحفوظ بعد ربط قاعدة البيانات.",
        "⚡ ترقية المنجم":
            "⚡ ميزة ترقية المنجم قيد الإعداد.",
        "🏆 المكافآت":
            "🏆 ستظهر هنا مكافآت التعدين والهدايا.",
        "🐉 أعضاء القبيلة":
            "🐉 سنضيف معلومات الأعضاء لاحقًا.",
        "ℹ️ معلومات EN96":
            "EN96 مشروع مرتبط بشبكة Stellar. الرصيد الافتراضي داخل البوت ليس تحويلًا على الشبكة."
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
    logging.info("Starting EN96 Mining Bot...")
    bot.infinity_polling(skip_pending=True, timeout=30)
