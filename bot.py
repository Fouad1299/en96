
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

# Backend address - keep unchanged
APP_URL = os.getenv(
    "APP_URL",
    "https://en96.onrender.com"
)

# NEW ROYAL EN96 INTERFACE
ROYAL_APP_URL = (
    "https://fouad1299.github.io/"
    "en96/en96-royal.html"
)

BOT_USERNAME = "EN96_IceDragon_2026_Bot"

TIKTOK_URL = (
    "https://www.tiktok.com/@en96mining"
)

MINING_RATE = 0.001
MINING_DURATION = 86400

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Supabase configuration missing"
    )

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
            "Registration failed: %s",
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
# TIKTOK
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
        "🎁 ابحث عن أكواد الهدايا.\n\n"
        "حسابنا الرسمي:\n"
        "@en96mining\n\n"
        "💎 عد إلى البوت لاستبدال "
        "أكواد الهدايا الصالحة.\n\n"
        "⚠️ المكافآت تخضع للتحقق "
        "وقواعد نظام EN96.",
        reply_markup=kb,
        disable_web_page_preview=True,
    )


@bot.message_handler(commands=["tiktok"])
def tiktok_command(message):
    show_tiktok(message.chat.id)


# =====================================
# TELEGRAM ROYAL WEB APP
# =====================================

def app_button(chat_id):
    if not ROYAL_APP_URL.startswith("https://"):
        bot.send_message(
            chat_id,
            "رابط تطبيق EN96 غير مضبوط."
        )
        return

    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "👑 افتح مملكة EN96 الملكية 🐻",
            web_app=WebAppInfo(
                url=ROYAL_APP_URL
            ),
        )
    )

    bot.send_message(
        chat_id,
        "👑🐻 مرحبًا بك في مملكة EN96!\n\n"
        "✨ الواجهة الملكية الذهبية جاهزة.\n"
        "⛏️ التعدين الافتراضي.\n"
        "💎 المحفظة والمكافآت.\n"
        "🎁 الهدايا وأعضاء القبيلة.\n\n"
        "اضغط الزر للدخول إلى الواجهة.\n\n"
        "⚠️ النقر داخل الواجهة تجريبي "
        "ولا يضيف عملات حقيقية حاليًا.",
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
            bot.send_message(
                chat_id,
                "لم أجد حسابك. أرسل /start أولًا."
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
            bot.send_message(
                chat_id,
                "لم أجد سجل رصيدك."
            )
            return

        balance = result.data[0]

        bot.send_message(
            chat_id,
            "💎 محفظة EN96\n\n"
            "🟢 الرصيد المتاح:\n"
            f"{en96_number(balance.get('available'))} "
            "EN96\n\n"
            "🟡 الرصيد المحجوز:\n"
            f"{en96_number(balance.get('reserved'))} "
            "EN96\n\n"
            "💸 الحد الأدنى للسحب: 500 EN96\n"
            "السحب يُراجع يدويًا.\n\n"
            "⚠️ الرصيد داخل التطبيق، "
            "وليس إثبات تحويل على Stellar.",
        )

    except Exception:
        log.exception("EN96 wallet error")
        bot.send_message(
            chat_id,
            "تعذّر عرض المحفظة الآن."
        )


# =====================================
# MINING
# =====================================

def mining_keyboard():
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🔄 تحديث التعدين",
            callback_data="mining_refresh",
        )
    )

    return kb


def mining_counter(
    chat_id,
    user_id,
    elapsed_before=0
):
    key = (chat_id, str(user_id))

    with MINING_LOCK:
        previous = MINING_COUNTERS.get(key)

        if previous:
            previous.set()

        stop_event = threading.Event()
        MINING_COUNTERS[key] = stop_event

    elapsed_before = max(
        0,
        min(
            int(elapsed_before),
            MINING_DURATION
        )
    )

    started = time.time() - elapsed_before

    try:
        msg = bot.send_message(
            chat_id,
            "🐻❄️ منجم EN96\n\n"
            "⛏️ التعدين الافتراضي نشط\n"
            "💎 جارٍ حساب المكافأة...\n\n"
            "⚡ 0.001 EN96/ثانية\n"
            "⏱️ مدة الجلسة 24 ساعة\n\n"
            "العداد تقديري؛ "
            "الرصيد الفعلي تحدده Supabase.",
            reply_markup=mining_keyboard(),
        )

    except Exception:
        log.exception("Counter send error")

        with MINING_LOCK:
            if MINING_COUNTERS.get(key) is stop_event:
                MINING_COUNTERS.pop(key, None)

        return

    def update():
        nonlocal started

        try:
            while not stop_event.is_set():
                elapsed = min(
                    max(
                        0,
                        int(time.time() - started)
                    ),
                    MINING_DURATION,
                )

                estimate = elapsed * MINING_RATE

                hours, rest = divmod(
                    elapsed,
                    3600
                )

                minutes, seconds = divmod(
                    rest,
                    60
                )

                counter_text = (
                    "🐻👑 منجم EN96\n\n"
                    "⛏️ التعدين الافتراضي نشط\n\n"
                    "💎 المكافأة التقديرية:\n"
                    f"{estimate:.7f} EN96\n\n"
                    "⏱️ الوقت:\n"
                    f"{hours:02d}:"
                    f"{minutes:02d}:"
                    f"{seconds:02d}"
                    " / 24:00:00\n\n"
                    "⚡ 0.001 EN96/ثانية\n\n"
                    "⚠️ الرصيد الفعلي "
                    "محفوظ في Supabase."
                )

                try:
                    bot.edit_message_text(
                        counter_text,
                        chat_id=chat_id,
                        message_id=msg.message_id,
                        reply_markup=mining_keyboard(),
                    )

                except Exception as exc:
                    if (
                        "message is not modified"
                        not in str(exc).lower()
                    ):
                        log.warning(
                            "Counter update error: %s",
                            exc
                        )

                if elapsed >= MINING_DURATION:
                    try:
                        data = rpc_data(
                            db.rpc(
                                "en96_mining_action",
                                {
                                    "p_telegram_id":
                                    str(user_id)
                                },
                            ).execute()
                        )

                        status = data.get("status")

                        if status == "rewarded_and_started":
                            bot.send_message(
                                chat_id,
                                "✅ أكدت Supabase إضافة "
                                f"{data.get('reward', 86.4)} "
                                "EN96.\n\n"
                                "بدأت جلسة تعدين جديدة.",
                            )

                            started = time.time()
                            continue

                        if status == "active":
                            remaining = max(
                                1,
                                int(
                                    data.get(
                                        "remaining_seconds",
                                        1
                                    )
                                ),
                            )

                            started = (
                                time.time()
                                - MINING_DURATION
                                + remaining
                            )

                            continue

                        bot.send_message(
                            chat_id,
                            "⚠️ لم يتم تأكيد مكافأة "
                            "الجلسة.\n"
                            "اضغط بدء التعدين للتحقق.",
                        )

                        break

                    except Exception:
                        log.exception(
                            "Mining settlement error"
                        )

                        bot.send_message(
                            chat_id,
                            "تعذّر التحقق "
                            "من مكافأة التعدين.",
                        )

                        break

                if stop_event.wait(5):
                    break

        finally:
            with MINING_LOCK:
                if MINING_COUNTERS.get(key) is stop_event:
                    MINING_COUNTERS.pop(key, None)

    threading.Thread(
        target=update,
        daemon=True
    ).start()


def mining(chat_id, user_id):
    try:
        if not profile_for(user_id):
            bot.send_message(
                chat_id,
                "لم أجد حسابك. أرسل /start أولًا."
            )
            return

        data = rpc_data(
            db.rpc(
                "en96_mining_action",
                {
                    "p_telegram_id":
                    str(user_id)
                },
            ).execute()
        )

        status = data.get("status")

        if status == "started":
            mining_counter(
                chat_id,
                user_id
            )

        elif status == "rewarded_and_started":
            bot.send_message(
                chat_id,
                "✅ تمت إضافة "
                f"{data.get('reward', 86.4)} "
                "EN96 وبدأت جلسة جديدة.",
            )

            mining_counter(
                chat_id,
                user_id
            )

        elif status == "active":
            remaining = max(
                0,
                min(
                    int(
                        data.get(
                            "remaining_seconds",
                            MINING_DURATION
                        )
                    ),
                    MINING_DURATION,
                ),
            )

            mining_counter(
                chat_id,
                user_id,
                MINING_DURATION - remaining,
            )

        elif status == "profile_missing":
            bot.send_message(
                chat_id,
                "ملفك غير موجود في قاعدة البيانات."
            )

        elif status == "balance_missing":
            bot.send_message(
                chat_id,
                "سجل رصيدك غير موجود."
            )

        else:
            log.warning(
                "Unexpected mining response: %s",
                data
            )

            bot.send_message(
                chat_id,
                "تعذّر تأكيد حالة التعدين."
            )

    except Exception:
        log.exception("Mining error")
        bot.send_message(
            chat_id,
            "حدث خطأ في التعدين."
        )


@bot.callback_query_handler(
    func=lambda call: call.data == "mining_refresh"
)
def mining_refresh(call):
    try:
        bot.answer_callback_query(call.id)

        mining(
            call.message.chat.id,
            call.from_user.id,
        )

    except Exception:
        log.exception("Mining refresh error")


# =====================================
# REFERRALS
# =====================================

def referral_link(user_id):
    return (
        f"https://t.me/{BOT_USERNAME}"
        f"?start=ref_{user_id}"
    )


def record_referral(message):
    parts = (
        (message.text or "")
        .strip()
        .split(maxsplit=1)
    )

    if len(parts) != 2:
        return

    command = parts[0].split("@")[0]

    if command != "/start":
        return

    payload = parts[1].strip()

    if not payload.startswith("ref_"):
        return

    referrer = payload[4:]
    new_user = str(message.from_user.id)

    if (
        not referrer.isascii()
        or not referrer.isdigit()
    ):
        return

    if referrer == new_user:
        bot.send_message(
            message.chat.id,
            "لا يمكنك دعوة نفسك."
        )
        return

    try:
        result = db.rpc(
            "en96_record_referral",
            {
                "p_telegram_id": new_user,
                "p_referrer_telegram_id": referrer,
            },
        ).execute()

        data = rpc_data(result)
        status = data.get("status")

        if status == "registered":
            bot.send_message(
                message.chat.id,
                "🎉 تم تسجيل دعوتك "
                "في قبيلة EN96!",
            )

        elif status:
            log.info(
                "Referral status: %s",
                status
            )

    except Exception:
        log.exception(
            "Referral registration error"
        )


# =====================================
# TRIBE
# =====================================

def tribe(chat_id, user_id):
    link = referral_link(user_id)

    try:
        result = db.rpc(
            "en96_tribe_stats",
            {
                "p_telegram_id":
                str(user_id)
            },
        ).execute()

        data = rpc_data(result)

        if data.get("status") == "profile_missing":
            bot.send_message(
                chat_id,
                "لم أجد حسابك.\n"
                "أرسل /start أولًا.",
            )
            return

        if data.get("status") != "ok":
            log.warning(
                "Unexpected tribe data: %s",
                data
            )

            raise ValueError(
                "Unexpected tribe stats response"
            )

        friends = int(
            data.get("friends") or 0
        )

        invitation_bonus = en96_number(
            data.get("invitation_bonus")
        )

        commission = en96_number(
            data.get("mining_commission")
        )

        total = en96_number(
            data.get("total")
        )

        bot.send_message(
            chat_id,
            "🐻👑 قبيلة EN96 الجليدية\n"
            "━━━━━━━━━━━━━━\n\n"
            f"👥 عدد الأصدقاء: {friends}\n\n"
            "🎁 مكافآت دعوة الأصدقاء:\n"
            f"{invitation_bonus} EN96\n\n"
            "⛏️ عمولات تعدين الأصدقاء 5%:\n"
            f"{commission} EN96\n\n"
            "💎 مجموع مكافآت القبيلة:\n"
            f"{total} EN96\n\n"
            "━━━━━━━━━━━━━━\n"
            "🔗 رابط دعوتك الخاص:\n"
            f"{link}\n\n"
            "🎁 50 EN96 عند اكتمال "
            "أول جلسة مؤهلة للصديق.\n"
            "⛏️ 5% من مكافآت تعدين "
            "أصدقائك المباشرين المؤكدة.\n\n"
            "⚠️ الأرقام تعرض المكافآت "
            "المسجلة في Supabase.",
            disable_web_page_preview=True,
        )

    except Exception:
        log.exception(
            "EN96 tribe statistics error"
        )

        bot.send_message(
            chat_id,
            "🐻👑 قبيلة EN96\n\n"
            "تعذّر تحميل الإحصائيات الآن.\n"
            "يمكنك استخدام رابط دعوتك:\n"
            f"{link}",
            disable_web_page_preview=True,
        )


# =====================================
# VIDEO GIFTS
# =====================================

def redeem_gift(message):
    uid = message.from_user.id
    code = (message.text or "").strip()

    WAITING_GIFT.discard(uid)

    try:
        data = rpc_data(
            db.rpc(
                "redeem_en96_video_gift",
                {
                    "p_telegram_id": int(uid),
                    "p_code": code,
                },
            ).execute()
        )

        if data.get("ok") is True:
            bot.send_message(
                message.chat.id,
                "🎁 تم استلام "
                f"{data.get('reward', 1)} "
                "EN96 بنجاح!",
            )
            return

        reason = (
            data.get("reason")
            or data.get("status")
            or "unknown"
        )

        errors = {
            "invalid_input":
                "الكود غير صالح.",
            "profile_not_found":
                "أرسل /start أولًا.",
            "invalid_or_inactive_code":
                "الكود غير موجود أو غير مفعّل.",
            "already_claimed":
                "استعملت هذا الكود من قبل.",
            "cooldown_2_hours":
                "انتظر ساعتين قبل استلام "
                "هدية أخرى.",
            "balance_not_found":
                "لم أجد سجل رصيدك.",
        }

        bot.send_message(
            message.chat.id,
            errors.get(
                reason,
                f"تعذّر استلام الهدية: {reason}",
            ),
        )

    except Exception:
        log.exception("Gift error")

        bot.send_message(
            message.chat.id,
            "تعذّر التحقق من كود الهدية.",
        )


def show_videos(chat_id):
    try:
        rows = (
            db.table("video_gift_codes")
            .select(
                "video_url,reward,description"
            )
            .eq("active", True)
            .order(
                "created_at",
                desc=True
            )
            .limit(10)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "لا توجد فيديوهات هدايا حاليًا.",
            )
            return

        lines = []

        for row in rows:
            lines.append(
                f"📺 {row.get('description') or 'EN96'}\n"
                f"🎁 {row.get('reward')} EN96\n"
                f"{row.get('video_url')}"
            )

        bot.send_message(
            chat_id,
            "\n\n".join(lines),
            disable_web_page_preview=True,
        )

    except Exception:
        log.exception("Videos error")

        bot.send_message(
            chat_id,
            "تعذّر تحميل الفيديوهات.",
        )


# =====================================
# ADMIN GIFTS
# =====================================

def admin_create_code(message):
    uid = message.from_user.id
    code = (message.text
