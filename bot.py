
import os
import json
import time
import logging
import threading

import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from supabase import create_client
from en96_accounts import ensure_profile

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
    "APP_URL", "https://en96.onrender.com"
)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing")

bot = telebot.TeleBot(BOT_TOKEN)
db = create_client(SUPABASE_URL, SUPABASE_KEY)

MINING_RATE = 0.001
MINING_DURATION = 86400

MINING_COUNTERS = {}
MINING_LOCK = threading.Lock()

WAITING_GIFT = set()
WAITING_ADMIN_CODE = set()
WAITING_ADMIN_VIDEO = set()
WAITING_ADMIN_REWARD = set()

ADMIN_ACTION = {}
PENDING = {}


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
        .select("id,telegram_id,stellar_public_address")
        .eq("telegram_id", str(user_id))
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ==================================
# MAIN MENU
# ==================================

def menu(user_id=None):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row(
        KeyboardButton("⛏️ بدء التعدين"),
        KeyboardButton("💰 محفظتي")
    )
    kb.row(
        KeyboardButton("⚡ ترقية المنجم"),
        KeyboardButton("🏆 المكافآت")
    )
    kb.row(
        KeyboardButton("📺 مشاهدة الفيديوهات"),
        KeyboardButton("🎁 استلام الهدية")
    )
    kb.row(
        KeyboardButton("🐻 أعضاء القبيلة"),
        KeyboardButton("ℹ️ معلومات EN96")
    )
    kb.row(
        KeyboardButton("🌐 فتح تطبيق EN96")
    )

    if user_id is not None and is_admin(user_id):
        kb.row(
            KeyboardButton("🛠️ إدارة الهدايا")
        )

    return kb


def admin_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)

    kb.row(
        KeyboardButton("➕ إنشاء كود هدية"),
        KeyboardButton("📋 أكواد الهدايا")
    )
    kb.row(
        KeyboardButton("⛔ تعطيل كود"),
        KeyboardButton("✅ تفعيل كود")
    )
    kb.row(
        KeyboardButton("🔙 القائمة الرئيسية")
    )
    return kb


# ==================================
# TELEGRAM MINI APP LOGIN
# ==================================

def app_button(chat_id):
    if not APP_URL.startswith("https://"):
        bot.send_message(
            chat_id,
            "رابط التطبيق غير مضبوط."
        )
        return

    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            "🔐 دخول EN96 عبر تيليغرام 🐻",
            web_app=WebAppInfo(url=APP_URL)
        )
    )

    bot.send_message(
        chat_id,
        "🐻❄️ مرحبًا بك في EN96!\n\n"
        "اضغط الزر أدناه للدخول "
        "باستخدام حساب تيليغرام.",
        reply_markup=kb
    )


def send_menu(
    chat_id,
    text="🐻 مرحبًا بك في EN96 Mining!",
    user_id=None
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


# ==================================
# WALLET
# ==================================

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

        available = float(
            balance.get("available") or 0
        )
        reserved = float(
            balance.get("reserved") or 0
        )

        bot.send_message(
            chat_id,
            "💎 محفظة EN96\n\n"
            f"🟢 المتاح: {available:.7f} EN96\n"
            f"🟡 المحجوز: {reserved:.7f} EN96\n\n"
            "💸 الحد الأدنى للسحب: 500 EN96\n"
            "السحب يتم بمراجعة يدوية.\n\n"
            "هذا رصيد داخل التطبيق وليس "
            "تحويلًا مؤكدًا على Stellar."
        )

    except Exception:
        log.exception("Wallet error")
        bot.send_message(
            chat_id,
            "تعذّر عرض المحفظة الآن."
        )


# ==================================
# MINING COUNTER
# ==================================

def mining_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton(
            "🔄 تحديث التعدين",
            callback_data="mining_refresh"
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
            "💎 جاري حساب المكافأة...\n"
            "⚡ المعدل: 0.001 EN96/ثانية\n\n"
            "العداد تقديري، والرصيد الفعلي "
            "تحدده Supabase.",
            reply_markup=mining_keyboard()
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
                    MINING_DURATION
                )

                estimate = elapsed * MINING_RATE

                hours, rest = divmod(elapsed, 3600)
                minutes, seconds = divmod(rest, 60)

                text = (
                    "🐻❄️ منجم EN96\n\n"
                    "⛏️ التعدين الافتراضي نشط\n"
                    f"💎 التقديري: {estimate:.7f} EN96\n"
                    f"⏱️ {hours:02d}:{minutes:02d}:"
                    f"{seconds:02d} / 24:00:00\n"
                    "⚡ 0.001 EN96/ثانية\n\n"
                    "⚠️ هذا عداد مرئي فقط؛ "
                    "الرصيد الفعلي محفوظ في Supabase."
                )

                try:
                    bot.edit_message_text(
                        text,
                        chat_id=chat_id,
                        message_id=msg.message_id,
                        reply_markup=mining_keyboard()
                    )
                except Exception as exc:
                    if (
                        "message is not modified"
                        not in str(exc).lower()
                    ):
                        log.warning(
                            "Counter edit error: %s",
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
                                }
                            ).execute()
                        )

                        status = data.get("status")

                        if status == "rewarded_and_started":
                            bot.send_message(
                                chat_id,
                                "✅ أكد النظام إضافة "
                                f"{data.get('reward', 86.4)} "
                                "EN96.\n"
                                "بدأت جلسة جديدة."
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
                                )
                            )
                            started = (
                                time.time()
                                - MINING_DURATION
                                + remaining
                            )
                            continue

                        bot.send_message(
                            chat_id,
                            "تعذّر تأكيد المكافأة. "
                            "اضغط بدء التعدين للتحقق."
                        )
                        break

                    except Exception:
                        log.exception(
                            "Mining settlement error"
                        )
                        bot.send_message(
                            chat_id,
                            "تعذّر التحقق من المكافأة."
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
                    "p_telegram_id": str(user_id)
                }
            ).execute()
        )

        status = data.get("status")

        if status == "started":
            mining_counter(chat_id, user_id)

        elif status == "rewarded_and_started":
            bot.send_message(
                chat_id,
                "✅ تمت إضافة "
                f"{data.get('reward', 86.4)} "
                "EN96 وبدأت جلسة جديدة."
            )
            mining_counter(chat_id, user_id)

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
                    MINING_DURATION
                )
            )
            mining_counter(
                chat_id,
                user_id,
                MINING_DURATION - remaining
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
    func=lambda call:
        call.data == "mining_refresh"
)
def mining_refresh(call):
    try:
        bot.answer_callback_query(call.id)
        mining(
            call.message.chat.id,
            call.from_user.id
        )
    except Exception:
        log.exception("Mining refresh error")


# ==================================
# REFERRALS
# ==================================

BOT_USERNAME = "EN96_IceDragon_2026_Bot"


def referral_link(user_id):
    return (
        f"https://t.me/{BOT_USERNAME}"
        f"?start=ref_{user_id}"
    )


def record_referral(message):
    """
    تسجيل الدعوة فقط، دون صرف العملات.
    صرف 50 EN96 و5% سيضاف لاحقًا
    إلى معاملة ذرية في Supabase.
    """

    parts = (
        (message.text or "")
        .strip()
        .split(maxsplit=1)
    )

    if len(parts) != 2:
        return

    if parts[0].split("@")[0] != "/start":
        return

    payload = parts[1].strip()

    if not payload.startswith("ref_"):
        return

    referrer = payload[4:]
    new_user = str(message.from_user.id)

    if not referrer.isascii() or not referrer.isdigit():
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
                "p_referrer_telegram_id": referrer
            }
        ).execute()

        data = rpc_data(result)
        status = data.get("status")

        if status == "registered":
            bot.send_message(
                message.chat.id,
                "🎉 تم تسجيل دعوتك في قبيلة EN96!"
            )

        elif status:
            log.info(
                "Referral status: %s",
                status
            )

        else:
            log.warning(
                "Unexpected referral response: %s",
                data
            )

    except Exception:
        log.exception("Referral registration error")


def tribe(chat_id, user_id):
    link = referral_link(user_id)

    bot.send_message(
        chat_id,
        "🐻👑 قبيلة EN96\n\n"
        "🔗 رابط الدعوة الخاص بك:\n"
        f"{link}\n\n"
        "🎁 50 EN96 لكل صديق جديد مؤهل.\n"
        "⛏️ 5% من مكافآت التعدين "
        "المؤكدة للأصدقاء المباشرين.\n\n"
        "⚠️ يتم حاليًا تسجيل الدعوات فقط؛ "
        "صرف المكافآت لم يُفعّل بعد.",
        disable_web_page_preview=True
    )


# ==================================
# VIDEO GIFTS
# ==================================

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
                    "p_code": code
                }
            ).execute()
        )

        if data.get("ok") is True:
            bot.send_message(
                message.chat.id,
                "🎁 استلمت "
                f"{data.get('reward', 1)} "
                "EN96 بنجاح!"
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
                "الكود غير موجود أو غير مفعل.",
            "already_claimed":
                "استخدمت هذا الكود سابقًا.",
            "cooldown_2_hours":
                "انتظر ساعتين قبل الهدية التالية.",
            "balance_not_found":
                "لم أجد سجل رصيدك."
        }

        bot.send_message(
            message.chat.id,
            errors.get(
                reason,
                f"تعذّر استلام الهدية: {reason}"
            )
        )

    except Exception:
        log.exception("Gift error")
        bot.send_message(
            message.chat.id,
            "تعذّر التحقق من الهدية."
        )


def show_videos(chat_id):
    try:
        rows = (
            db.table("video_gift_codes")
            .select("video_url,reward,description")
            .eq("active", True)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "لا توجد فيديوهات حاليًا."
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
            disable_web_page_preview=True
        )

    except Exception:
        log.exception("Videos error")
        bot.send_message(
            chat_id,
            "تعذّر تحميل الفيديوهات."
        )


# ==================================
# ADMIN GIFTS
# ==================================

def admin_create_code(message):
    uid = message.from_user.id
    code = (message.text or "").strip()

    WAITING_ADMIN_CODE.discard(uid)

    if not code or len(code) > 120:
        bot.send_message(
            message.chat.id,
            "الكود غير صالح."
        )
        return

    PENDING[uid] = {"code": code}
    WAITING_ADMIN_VIDEO.add(uid)

    bot.send_message(
        message.chat.id,
        "أرسل رابط الفيديو."
    )


def admin_video(message):
    uid = message.from_user.id
    url = (message.text or "").strip()

    if not url.startswith(
        ("https://", "http://")
    ):
        bot.send_message(
            message.chat.id,
            "رابط الفيديو غير صالح."
        )
        return

    PENDING.setdefault(
        uid, {}
    )["video_url"] = url

    WAITING_ADMIN_VIDEO.discard(uid)
    WAITING_ADMIN_REWARD.add(uid)

    bot.send_message(
        message.chat.id,
        "أرسل المكافأة، مثل 1."
    )


def admin_reward(message):
    uid = message.from_user.id

    try:
        reward = float(
            (message.text or "")
            .strip()
            .replace(",", ".")
        )

        if reward <= 0:
            raise ValueError

    except ValueError:
        bot.send_message(
            message.chat.id,
            "أرسل رقمًا موجبًا."
        )
        return

    item = PENDING.get(uid, {})

    if (
        not item.get("code")
        or not item.get("video_url")
    ):
        WAITING_ADMIN_REWARD.discard(uid)
        bot.send_message(
            message.chat.id,
            "بيانات الهدية ناقصة."
        )
        return

    try:
        db.table("video_gift_codes").insert({
            "code": item["code"],
            "video_url": item["video_url"],
            "reward": reward,
            "active": True,
            "description": "EN96 admin gift"
        }).execute()

        bot.send_message(
            message.chat.id,
            "✅ تم إنشاء الكود "
            f"{item['code']} "
            f"بمكافأة {reward:g} EN96."
        )

    except Exception:
        log.exception("Create gift error")
        bot.send_message(
            message.chat.id,
            "تعذّر إنشاء الكود."
        )

    finally:
        WAITING_ADMIN_REWARD.discard(uid)
        PENDING.pop(uid, None)


def list_gifts(chat_id):
    try:
        rows = (
            db.table("video_gift_codes")
            .select("id,code,reward,active")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "لا توجد أكواد."
            )
            return

        lines = ["📋 أكواد EN96:"]

        for row in rows:
            state = (
                "مفعّل"
                if row.get("active")
                else "معطّل"
            )

            lines.append(
                f"{row.get('code')} | "
                f"{row.get('reward')} EN96 | "
                f"{state}"
            )

        bot.send_message(
            chat_id,
            "\n".join(lines)
        )

    except Exception:
        log.exception("List gifts error")
        bot.send_message(
            chat_id,
            "تعذّر عرض الأكواد."
        )


def set_gift_active(message, active):
    code = (message.text or "").strip()

    try:
        result = (
            db.table("video_gift_codes")
            .update({"active": active})
            .eq("code", code)
            .execute()
        )

        if result.data:
            bot.send_message(
                message.chat.id,
                "✅ تم تغيير حالة الكود."
            )
        else:
            bot.send_message(
                message.chat.id,
                "لم أجد هذا الكود."
            )

    except Exception:
        log.exception("Gift toggle error")
        bot.send_message(
            message.chat.id,
            "تعذّر تغيير حالة الكود."
        )


# ==================================
# TELEGRAM COMMANDS
# ==================================

@bot.message_handler(commands=["start", "menu"])
def start(message):
    if message.chat.type != "private":
        bot.reply_to(
            message,
            "افتح EN96 في محادثة خاصة."
        )
        return

    uid = message.from_user.id

    registered = register_member(uid)

    if not registered:
        bot.send_message(
            message.chat.id,
            "⚠️ تعذّر تأكيد حساب EN96.\n"
            "حاول لاحقًا."
        )
        return

    record_referral(message)

    send_menu(
        message.chat.id,
        user_id=uid
    )


@bot.message_handler(commands=["wallet"])
def wallet_command(message):
    wallet(
        message.chat.id,
        message.from_user.id
    )


@bot.message_handler(commands=["mining"])
def mining_command(message):
    mining(
        message.chat.id,
        message.from_user.id
    )


@bot.message_handler(commands=["admin"])
def admin_command(message):
    if is_admin(message.from_user.id):
        bot.send_message(
            message.chat.id,
            "🛠️ إدارة هدايا EN96",
            reply_markup=admin_menu()
        )


# ==================================
# INPUT HANDLERS
# ==================================

@bot.message_handler(
    func=lambda m:
        m.from_user.id in WAITING_GIFT,
    content_types=["text"]
)
def gift_input(message):
    redeem_gift(message)


@bot.message_handler(
    func=lambda m:
        m.from_user.id in WAITING_ADMIN_CODE
        and ADMIN_ACTION.get(m.from_user.id)
        in ("enable", "disable"),
    content_types=["text"]
)
def admin_toggle_input(message):
    uid = message.from_user.id

    action = ADMIN_ACTION.pop(uid)
    WAITING_ADMIN_CODE.discard(uid)

    set_gift_active(
        message,
        active=(action == "enable")
    )


@bot.message_handler(
    func=lambda m:
        m.from_user.id in WAITING_ADMIN_CODE,
    content_types=["text"]
)
def admin_code_input(message):
    if is_admin(message.from_user.id):
        admin_create_code(message)


@bot.message_handler(
    func=lambda m:
        m.from_user.id in WAITING_ADMIN_VIDEO,
    content_types=["text"]
)
def admin_video_input(message):
    if is_admin(message.from_user.id):
        admin_video(message)


@bot.message_handler(
    func=lambda m:
        m.from_user.id in WAITING_ADMIN_REWARD,
    content_types=["text"]
)
def admin_reward_input(message):
    if is_admin(message.from_user.id):
        admin_reward(message)


# ==================================
# MAIN HANDLER
# ==================================

@bot.message_handler(content_types=["text"])
def menu_handler(message):
    text = (message.text or "").strip()
    uid = message.from_user.id
    chat_id = message.chat.id

    if text == "⛏️ بدء التعدين":
        mining(chat_id, uid)

    elif text == "💰 محفظتي":
        wallet(chat_id, uid)

    elif text == "⚡ ترقية المنجم":
        bot.send_message(
            chat_id,
            "⚡ الترقيات غير مفعلة بعد."
        )

    elif text == "🏆 المكافآت":
        bot.send_message(
            chat_id,
            "🏆 مكافآت EN96 الافتراضية."
        )

    elif text == "📺 مشاهدة الفيديوهات":
        show_videos(chat_id)

    elif text == "🎁 استلام الهدية":
        WAITING_GIFT.add(uid)

        bot.send_message(
            chat_id,
            "🎁 أرسل كود هدية الفيديو."
        )

    elif text in (
        "🐻 أعضاء القبيلة",
        "🐉 أعضاء القبيلة"
    ):
        tribe(chat_id, uid)

    elif text == "ℹ️ معلومات EN96":
        bot.send_message(
            chat_id,
            "🐻 EN96 Ice Bear Mining\n\n"
            "⛏️ تعدين افتراضي.\n"
            "⚡ 0.001 EN96 في الثانية.\n"
            "⏱️ مدة الجلسة 24 ساعة.\n"
            "💎 86.4 EN96 لكل جلسة مكتملة.\n"
            "السحب يدوي."
        )

    elif (
        text == "🛠️ إدارة الهدايا"
        and is_admin(uid)
    ):
        bot.send_message(
            chat_id,
            "🛠️ إدارة الهدايا",
            reply_markup=admin_menu()
        )

    elif (
        text == "➕ إنشاء كود هدية"
        and is_admin(uid)
    ):
        WAITING_ADMIN_CODE.add(uid)
        bot.send_message(
            chat_id,
            "أرسل الكود الجديد."
        )

    elif (
        text == "📋 أكواد الهدايا"
        and is_admin(uid)
    ):
        list_gifts(chat_id)

    elif (
        text in (
            "⛔ تعطيل كود",
            "✅ تفعيل كود"
        )
        and is_admin(uid)
    ):
        ADMIN_ACTION[uid] = (
            "disable"
            if text == "⛔ تعطيل كود"
            else "enable"
        )

        WAITING_ADMIN_CODE.add(uid)

        bot.send_message(
            chat_id,
            "أرسل الكود."
        )

    elif text == "🔙 القائمة الرئيسية":
        send_menu(
            chat_id,
            user_id=uid
        )

    elif text == "🌐 فتح تطبيق EN96":
        if message.chat.type == "private":
            app_button(chat_id)

    else:
        send_menu(
            chat_id,
            "اختر زرًا من قائمة EN96.",
            user_id=uid
        )


if __name__ == "__main__":
    log.info("Starting EN96 Telegram bot")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
