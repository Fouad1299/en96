import os
import json
import logging

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from supabase import create_client

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("EN96")

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_KEY")
ADMIN_ID = str(os.getenv("ADMIN_TELEGRAM_ID", "8721009110"))
APP_URL = os.getenv("APP_URL", "https://en96.onrender.com")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_SECRET_KEY is missing")

bot = telebot.TeleBot(BOT_TOKEN)
db = create_client(SUPABASE_URL, SUPABASE_KEY)

WAITING_GIFT = set()
WAITING_ADMIN_CODE = set()
WAITING_ADMIN_VIDEO = set()
WAITING_ADMIN_REWARD = set()
ADMIN_ACTION = {}
PENDING = {}


def is_admin(user_id):
    return str(user_id) == ADMIN_ID


def menu(user_id=None):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("⛏️ بدء التعدين"), KeyboardButton("💰 محفظتي"))
    kb.row(KeyboardButton("⚡ ترقية المنجم"), KeyboardButton("🏆 المكافآت"))
    kb.row(KeyboardButton("📺 مشاهدة الفيديوهات"), KeyboardButton("🎁 استلام الهدية"))
    kb.row(KeyboardButton("🐉 أعضاء القبيلة"), KeyboardButton("ℹ️ معلومات EN96"))
    if APP_URL.startswith("https://"):
        kb.row(KeyboardButton("🌐 فتح تطبيق EN96", web_app=WebAppInfo(url=APP_URL)))
    if user_id is not None and is_admin(user_id):
        kb.row(KeyboardButton("🛠️ إدارة الهدايا"))
    return kb


def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton("➕ إنشاء كود هدية"), KeyboardButton("📋 أكواد الهدايا"))
    kb.row(KeyboardButton("⛔ تعطيل كود"), KeyboardButton("✅ تفعيل كود"))
    kb.row(KeyboardButton("🔙 القائمة الرئيسية"))
    return kb


def send_menu(chat_id, text="🐉 مرحبًا بك في EN96 Mining!\nأهلًا بك في مملكة التنين الجليدي.", user_id=None):
    bot.send_message(chat_id, text, reply_markup=menu(user_id))


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


def profile_for(telegram_id):
    result = db.table("profiles").select("id,telegram_id,stellar_public_address").eq(
        "telegram_id", str(telegram_id)
    ).limit(1).execute()
    return result.data[0] if result.data else None


def wallet(chat_id, telegram_id):
    try:
        profile = profile_for(telegram_id)
        if not profile:
            bot.send_message(chat_id, "لم أجد ملفك في قاعدة البيانات. افتح تطبيق EN96 وسجّل الدخول أولًا.")
            return
        result = db.table("balances").select("available,reserved").eq(
            "user_id", profile["id"]
        ).limit(1).execute()
        if not result.data:
            bot.send_message(chat_id, "لم يُعثر على سجل رصيدك.")
            return
        row = result.data[0]
        bot.send_message(
            chat_id,
            "💰 محفظة EN96\n\n"
            f"🟢 المتاح: {float(row.get('available') or 0):.7f} EN96\n"
            f"🟡 المحجوز: {float(row.get('reserved') or 0):.7f} EN96\n\n"
            "الرصيد هنا داخل التطبيق؛ هذا العرض لا يعني حدوث تحويل على Stellar."
        )
    except Exception:
        log.exception("wallet error")
        bot.send_message(chat_id, "تعذّر جلب المحفظة الآن. حاول لاحقًا.")


def mining(chat_id, telegram_id):
    try:
        if not profile_for(telegram_id):
            bot.send_message(chat_id, "لم أجد ملفك. افتح تطبيق EN96 وسجّل الدخول أولًا.")
            return
        data = rpc_data(db.rpc("en96_mining_action", {"p_telegram_id": str(telegram_id)}).execute())
        status = data.get("status") or data.get("reason") or data.get("message")
        if status in ("started", "rewarded_and_started"):
            bot.send_message(chat_id, "⛏️ بدأ التعدين الافتراضي!\nالمعدل: 0.001 EN96/ثانية.\nمدة الجلسة: 24 ساعة.\nالمجموع النظري خلال 24 ساعة: 86.4 EN96.\n\nهذا نظام مكافآت افتراضي وليس تعدينًا حقيقيًا.")
        elif status == "active":
            bot.send_message(chat_id, "⛏️ جلسة التعدين نشطة بالفعل.")
        elif status == "profile_missing":
            bot.send_message(chat_id, "لم أجد ملفك في قاعدة البيانات.")
        elif status == "balance_missing":
            bot.send_message(chat_id, "لم أجد سجل رصيدك.")
        elif data.get("ok") is True:
            bot.send_message(chat_id, "تم تنفيذ طلب التعدين: " + json.dumps(data, ensure_ascii=False))
        else:
            log.warning("Unexpected mining response: %r", data)
            bot.send_message(chat_id, "لم أتمكن من تأكيد حالة التعدين. راجع سجلات Render.")
    except Exception:
        log.exception("mining error")
        bot.send_message(chat_id, "حدث خطأ في التعدين. حاول لاحقًا.")


def redeem_gift(message):
    user_id = message.from_user.id
    code = (message.text or "").strip()
    WAITING_GIFT.discard(user_id)
    try:
        data = rpc_data(db.rpc("redeem_en96_video_gift", {
            "p_telegram_id": int(user_id), "p_code": code
        }).execute())
        if data.get("ok") is True:
            bot.send_message(message.chat.id, f"🎁 تم استلام {data.get('reward', 1)} EN96 بنجاح!")
            return
        reason = data.get("reason") or data.get("status") or data.get("message") or "unknown"
        errors = {
            "invalid_input": "الكود غير صالح.",
            "profile_not_found": "لم أجد ملفك؛ افتح التطبيق وسجّل الدخول.",
            "invalid_or_inactive_code": "الكود غير موجود أو غير مفعّل.",
            "already_claimed": "لقد استعملت هذا الكود من قبل.",
            "cooldown_2_hours": "انتظر ساعتين قبل استلام هدية أخرى.",
            "balance_not_found": "لم أجد سجل رصيدك.",
        }
        bot.send_message(message.chat.id, errors.get(reason, f"تعذّر استلام الهدية: {reason}"))
    except Exception:
        log.exception("gift redeem error")
        bot.send_message(message.chat.id, "تعذّر التحقق من الكود الآن.")


def admin_create_code(message):
    uid = message.from_user.id
    code = (message.text or "").strip()
    WAITING_ADMIN_CODE.discard(uid)
    if not code or len(code) > 120:
        bot.send_message(message.chat.id, "الكود غير صالح.")
        return
    PENDING[uid] = {"code": code}
    WAITING_ADMIN_VIDEO.add(uid)
    bot.send_message(message.chat.id, "أرسل رابط الفيديو الآن.")


def admin_video(message):
    uid = message.from_user.id
    url = (message.text or "").strip()
    if not url.startswith(("https://", "http://")):
        bot.send_message(message.chat.id, "أرسل رابطًا يبدأ بـ https:// أو http://.")
        return
    PENDING.setdefault(uid, {})["video_url"] = url
    WAITING_ADMIN_VIDEO.discard(uid)
    WAITING_ADMIN_REWARD.add(uid)
    bot.send_message(message.chat.id, "أرسل مقدار المكافأة، مثل 1.")


def admin_reward(message):
    uid = message.from_user.id
    try:
        reward = float((message.text or "").strip().replace(",", "."))
        if reward <= 0:
            raise ValueError
    except ValueError:
        bot.send_message(message.chat.id, "أرسل رقمًا موجبًا، مثل 1.")
        return
    item = PENDING.get(uid, {})
    if not item.get("code") or not item.get("video_url"):
        WAITING_ADMIN_REWARD.discard(uid)
        bot.send_message(message.chat.id, "بيانات الهدية ناقصة؛ ابدأ من جديد.")
        return
    try:
        db.table("video_gift_codes").insert({
            "code": item["code"], "video_url": item["video_url"],
            "reward": reward, "active": True,
            "description": "Created by EN96 admin bot"
        }).execute()
        bot.send_message(message.chat.id, f"✅ تم إنشاء الكود {item['code']} بمكافأة {reward:g} EN96.")
    except Exception:
        log.exception("admin create code error")
        bot.send_message(message.chat.id, "تعذّر إنشاء الكود. تحقق من عدم تكراره وصلاحيات المفتاح.")
    finally:
        WAITING_ADMIN_REWARD.discard(uid)
        PENDING.pop(uid, None)


def list_gifts(chat_id):
    try:
        rows = db.table("video_gift_codes").select(
            "id,code,reward,active,created_at"
        ).order("created_at", desc=True).limit(20).execute().data or []
        if not rows:
            bot.send_message(chat_id, "لا توجد أكواد هدايا.")
            return
        lines = ["📋 أكواد الهدايا:"]
        for row in rows:
            lines.append(f"ID {row.get('id')} | {row.get('code')} | {row.get('reward')} EN96 | {'مفعّل' if row.get('active') else 'معطّل'}")
        bot.send_message(chat_id, "\n".join(lines))
    except Exception:
        log.exception("list gifts error")
        bot.send_message(chat_id, "تعذّر عرض الأكواد.")


def set_gift_active(message, active):
    code = (message.text or "").strip()
    try:
        result = db.table("video_gift_codes").update({"active": active}).eq("code", code).execute()
        if result.data:
            bot.send_message(message.chat.id, f"تم {'تفعيل' if active else 'تعطيل'} الكود {code}.")
        else:
            bot.send_message(message.chat.id, "لم أعثر على هذا الكود.")
    except Exception:
        log.exception("toggle gift error")
        bot.send_message(message.chat.id, "تعذّر تغيير حالة الكود.")


@bot.message_handler(commands=["start", "menu"])
def start(message):
    send_menu(message.chat.id, user_id=message.from_user.id)


@bot.message_handler(commands=["wallet"])
def wallet_command(message):
    wallet(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["mining"])
def mining_command(message):
    mining(message.chat.id, message.from_user.id)


@bot.message_handler(commands=["admin"])
def admin_command(message):
    if is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "🛠️ إدارة هدايا EN96", reply_markup=admin_menu())
    else:
        bot.send_message(message.chat.id, "هذا الأمر مخصص للمدير.")


# Pending input handlers are registered before the general text handler.
@bot.message_handler(func=lambda m: m.from_user.id in WAITING_GIFT, content_types=["text"])
def gift_input(message):
    redeem_gift(message)


@bot.message_handler(func=lambda m: m.from_user.id in WAITING_ADMIN_CODE and ADMIN_ACTION.get(m.from_user.id) in ("enable", "disable"), content_types=["text"])
def admin_toggle_input(message):
    uid = message.from_user.id
    action = ADMIN_ACTION.pop(uid)
    WAITING_ADMIN_CODE.discard(uid)
    set_gift_active(message, active=(action == "enable"))


@bot.message_handler(func=lambda m: m.from_user.id in WAITING_ADMIN_CODE, content_types=["text"])
def admin_code_input(message):
    if is_admin(message.from_user.id):
        admin_create_code(message)
    else:
        WAITING_ADMIN_CODE.discard(message.from_user.id)


@bot.message_handler(func=lambda m: m.from_user.id in WAITING_ADMIN_VIDEO, content_types=["text"])
def admin_video_input(message):
    if is_admin(message.from_user.id):
        admin_video(message)
    else:
        WAITING_ADMIN_VIDEO.discard(message.from_user.id)


@bot.message_handler(func=lambda m: m.from_user.id in WAITING_ADMIN_REWARD, content_types=["text"])
def admin_reward_input(message):
    if is_admin(message.from_user.id):
        admin_reward(message)
    else:
        WAITING_ADMIN_REWARD.discard(message.from_user.id)


@bot.message_handler(content_types=["text"])
def menu_handler(message):
    text = (message.text or "").strip()
    uid, chat_id = message.from_user.id, message.chat.id

    if text == "⛏️ بدء التعدين":
        mining(chat_id, uid)
    elif text == "💰 محفظتي":
        wallet(chat_id, uid)
    elif text == "⚡ ترقية المنجم":
        bot.send_message(chat_id, "ترقيات المنجم لم تُفعّل بعد. لا ترسل أموالًا عبر هذا الزر.")
    elif text == "🏆 المكافآت":
        bot.send_message(chat_id, "المكافآت داخل التطبيق افتراضية. استخدم استلام الهدية لإدخال كود فيديو.")
    elif text == "📺 مشاهدة الفيديوهات":
        try:
            rows = db.table("video_gift_codes").select(
                "video_url,reward,description"
            ).eq("active", True).order("created_at", desc=True).limit(10).execute().data or []
            if not rows:
                bot.send_message(chat_id, "لا توجد فيديوهات هدايا متاحة حاليًا.")
            else:
                bot.send_message(chat_id, "\n\n".join(
                    f"{r.get('description') or 'فيديو EN96'} — {r.get('reward')} EN96\n{r.get('video_url')}"
                    for r in rows
                ), disable_web_page_preview=True)
        except Exception:
            log.exception("videos error")
            bot.send_message(chat_id, "تعذّر جلب الفيديوهات.")
    elif text == "🎁 استلام الهدية":
        WAITING_GIFT.add(uid)
        bot.send_message(chat_id, "أرسل كود الهدية الذي حصلت عليه من الفيديو.")
    elif text == "🐉 أعضاء القبيلة":
        bot.send_message(chat_id, "نظام القبيلة سيُضاف لاحقًا.")
    elif text == "ℹ️ معلومات EN96":
        bot.send_message(chat_id, "🐉 EN96 — مملكة التنين الجليدي\nالتعدين افتراضي بمعدل 0.001 EN96/ثانية، أي 86.4 EN96 نظريًا خلال 24 ساعة. ليس تعدينًا حقيقيًا. السحب يُراجع يدويًا.")
    elif text == "🛠️ إدارة الهدايا" and is_admin(uid):
        bot.send_message(chat_id, "🛠️ إدارة الهدايا", reply_markup=admin_menu())
    elif text == "➕ إنشاء كود هدية" and is_admin(uid):
        WAITING_ADMIN_CODE.add(uid)
        bot.send_message(chat_id, "أرسل كود الهدية الجديد.")
    elif text == "📋 أكواد الهدايا" and is_admin(uid):
        list_gifts(chat_id)
    elif text in ("⛔ تعطيل كود", "✅ تفعيل كود") and is_admin(uid):
        ADMIN_ACTION[uid] = "disable" if text == "⛔ تعطيل كود" else "enable"
        WAITING_ADMIN_CODE.add(uid)
        bot.send_message(chat_id, "أرسل الكود الذي تريد تغييره.")
    elif text == "🔙 القائمة الرئيسية":
        send_menu(chat_id, user_id=uid)
    elif text == "🌐 فتح تطبيق EN96":
        bot.send_message(chat_id, APP_URL)
    else:
        send_menu(chat_id, "اختر أحد أزرار قائمة EN96.", user_id=uid)


if __name__ == "__main__":
    log.info("Starting EN96 Telegram bot")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
