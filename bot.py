
import os
import json
import logging
import threading
import time

import telebot
from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from supabase import create_client
from en96_accounts import RegistrationError, ensure_profile

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

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase configuration missing")

bot = telebot.TeleBot(BOT_TOKEN)
db = create_client(SUPABASE_URL, SUPABASE_KEY)

WAITING_GIFT = set()
WAITING_ADMIN_CODE = set()
WAITING_ADMIN_VIDEO = set()
WAITING_ADMIN_REWARD = set()
ADMIN_ACTION = {}
PENDING = {}

MINING_RATE = 0.001
MINING_DURATION = 86400

MINING_COUNTERS = {}
MINING_LOCK = threading.Lock()


def is_admin(user_id):
    return str(user_id) == ADMIN_ID


# =========================
# EN96 MAIN MENU
# =========================

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


# =========================
# TELEGRAM LOGIN
# =========================

def app_button(chat_id):
    """
    زر تسجيل دخول موثق عبر Telegram Mini App.
    يعمل في المحادثات الخاصة.
    """

    if not APP_URL.startswith("https://"):
        bot.send_message(
            chat_id,
            "رابط تطبيق EN96 غير مضبوط على Render."
        )
        return

    buttons = InlineKeyboardMarkup()

    buttons.add(
        InlineKeyboardButton(
            "🔐 دخول EN96 عبر تيليغرام 🐻",
            web_app=WebAppInfo(url=APP_URL)
        )
    )

    bot.send_message(
        chat_id,
        "🐻❄️ مرحبًا بك في مملكة EN96!\n\n"
        "اضغط الزر الموجود أسفل هذه الرسالة "
        "لدخول تطبيق التعدين.\n\n"
        "✅ تسجيل الدخول باستخدام حساب تيليغرام.\n"
        "✅ لا تحتاج إلى بريد إلكتروني.\n"
        "✅ لا تحتاج إلى كلمة مرور.\n"
        "✅ لا تكتب Telegram ID يدويًا.",
        reply_markup=buttons
    )


def register_member(telegram_id):
    """
    إنشاء حساب جديد عند الحاجة فقط.
    لا يتم تصفير الرصيد القديم.
    """

    try:
        ensure_profile(db, telegram_id)
        return True

    except RegistrationError:
        log.exception(
            "EN96 registration failed for %s",
            telegram_id
        )
        return False


def send_menu(
    chat_id,
    text="🐻 مرحبًا بك في EN96 Mining!\n"
         "أهلًا بك في مملكة الدب الجليدي.",
    user_id=None
):
    bot.send_message(
        chat_id,
        text,
        reply_markup=menu(user_id)
    )

    if (
        user_id is not None
        and int(chat_id) == int(user_id)
    ):
        app_button(chat_id)


# =========================
# DATABASE FUNCTIONS
# =========================

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
    result = (
        db.table("profiles")
        .select("id,telegram_id,stellar_public_address")
        .eq("telegram_id", str(telegram_id))
        .limit(1)
        .execute()
    )

    return result.data[0] if result.data else None


# =========================
# EN96 WALLET
# =========================

def wallet(chat_id, telegram_id):
    try:
        profile = profile_for(telegram_id)

        if not profile:
            bot.send_message(
                chat_id,
                "لم أجد حسابك.\n"
                "أرسل /start لتسجيل حساب EN96 أولًا."
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
                "لم يُعثر على سجل رصيدك."
            )
            return

        row = result.data[0]

        bot.send_message(
            chat_id,
            "💎 محفظة EN96\n\n"
            f"🟢 الرصيد المتاح: "
            f"{float(row.get('available') or 0):.7f} EN96\n"
            f"🟡 الرصيد المحجوز: "
            f"{float(row.get('reserved') or 0):.7f} EN96\n\n"
            "💸 الحد الأدنى للسحب: 500 EN96\n"
            "السحب يُراجع يدويًا.\n\n"
            "⚠️ هذا رصيد التطبيق، وليس إثباتًا "
            "لتحويل عملات على شبكة Stellar."
        )

    except Exception:
        log.exception("EN96 wallet error")

        bot.send_message(
            chat_id,
            "تعذّر جلب المحفظة الآن."
        )


# =========================
# MINING COUNTER
# =========================

def mining_keyboard():
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🔄 تحديث حالة التعدين",
            callback_data="en96_mining_refresh"
        )
    )

    return kb


def mining_counter(
    chat_id,
    telegram_id,
    elapsed_before=0
):
    """
    عداد مرئي تقديري فقط.
    Supabase هي المسؤولة عن المكافأة الفعلية.
    """

    key = (chat_id, str(telegram_id))

    with MINING_LOCK:
        old_event = MINING_COUNTERS.get(key)

        if old_event:
            old_event.set()

        stop_event = threading.Event()
        MINING_COUNTERS[key] = stop_event

    elapsed_before = max(
        0,
        min(int(elapsed_before), MINING_DURATION)
    )

    start_time = time.time() - elapsed_before

    try:
        msg = bot.send_message(
            chat_id,
            "🐻❄️ منجم EN96 الجليدي\n\n"
            "⛏️ التعدين الافتراضي نشط\n"
            "💎 المكافأة التقديرية: 0.0000000 EN96\n"
            "⏱️ الوقت: 00:00:00 / 24:00:00\n\n"
            "⚡ المعدل: 0.001 EN96/ثانية\n"
            "⚠️ العداد للعرض فقط، "
            "والرصيد الفعلي تحدده Supabase.",
            reply_markup=mining_keyboard()
        )

    except Exception:
        log.exception("Could not send mining counter")

        with MINING_LOCK:
            if MINING_COUNTERS.get(key) is stop_event:
                MINING_COUNTERS.pop(key, None)
        return

    def update_counter():
        nonlocal start_time

        try:
            while not stop_event.is_set():

                elapsed = min(
                    max(0, int(time.time() - start_time)),
                    MINING_DURATION
                )

                reward_estimate = elapsed * MINING_RATE

                hours, remainder = divmod(elapsed, 3600)
                minutes, seconds = divmod(remainder, 60)

                counter_text = (
                    "🐻❄️ منجم EN96 الجليدي\n\n"
                    "⛏️ التعدين الافتراضي نشط\n"
                    f"💎 المكافأة التقديرية: "
                    f"{reward_estimate:.7f} EN96\n"
                    f"⏱️ الوقت: "
                    f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    " / 24:00:00\n\n"
                    "⚡ المعدل: 0.001 EN96/ثانية\n"
                    "⚠️ المكافأة المعروضة تقديرية؛ "
                    "الرصيد الفعلي تحدده قاعدة البيانات."
                )

                try:
                    bot.edit_message_text(
                        counter_text,
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
                            "Mining counter update: %s",
                            exc
                        )

                if elapsed >= MINING_DURATION:

                    try:
                        result = rpc_data(
                            db.rpc(
                                "en96_mining_action",
                                {
                                    "p_telegram_id":
                                        str(telegram_id)
                                }
                            ).execute()
                        )

                        status = result.get("status")

                        if status == "rewarded_and_started":

                            reward = result.get(
                                "reward",
                                86.4
                            )

                            bot.send_message(
                                chat_id,
                                "✅ أكدت Supabase انتهاء الجلسة "
                                f"وإضافة {reward} EN96.\n"
                                "بدأت جلسة جديدة."
                            )

                            start_time = time.time()
                            continue

                        if status == "active":
                            remaining = max(
                                1,
                                int(
                                    result.get(
                                        "remaining_seconds",
                                        1
                                    )
                                )
                            )

                            start_time = (
                                time.time()
                                - (
                                    MINING_DURATION
                                    - remaining
                                )
                            )
                            continue

                        bot.send_message(
                            chat_id,
                            "⚠️ انتهى العداد، لكن Supabase "
                            "لم تؤكد إضافة المكافأة.\n"
                            "اضغط بدء التعدين للتحقق."
                        )
                        break

                    except Exception:
                        log.exception(
                            "Mining settlement failed"
                        )

                        bot.send_message(
                            chat_id,
                            "⚠️ تعذّر التحقق من المكافأة "
                            "بعد انتهاء الجلسة."
                        )
                        break

                if stop_event.wait(5):
                    break

        finally:
            with MINING_LOCK:
                if MINING_COUNTERS.get(key) is stop_event:
                    MINING_COUNTERS.pop(key, None)

    threading.Thread(
        target=update_counter,
        daemon=True
    ).start()


def mining(chat_id, telegram_id):
    try:
        if not profile_for(telegram_id):
            bot.send_message(
                chat_id,
                "لم أجد حسابك.\n"
                "أرسل /start أولًا."
            )
            return

        data = rpc_data(
            db.rpc(
                "en96_mining_action",
                {
                    "p_telegram_id": str(telegram_id)
                }
            ).execute()
        )

        status = (
            data.get("status")
            or data.get("reason")
            or data.get("message")
        )

        if status == "started":
            mining_counter(
                chat_id,
                telegram_id,
                0
            )

        elif status == "rewarded_and_started":
            bot.send_message(
                chat_id,
                "✅ مكافأة مؤكدة من Supabase: "
                f"{data.get('reward', 86.4)} EN96\n"
                "بدأت جلسة جديدة."
            )

            mining_counter(
                chat_id,
                telegram_id,
                0
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
                    MINING_DURATION
                )
            )

            mining_counter(
                chat_id,
                telegram_id,
                MINING_DURATION - remaining
            )

        elif status == "profile_missing":
            bot.send_message(
                chat_id,
                "لم أجد حسابك في قاعدة البيانات."
            )

        elif status == "balance_missing":
            bot.send_message(
                chat_id,
                "لم أجد سجل رصيدك."
            )

        else:
            log.warning(
                "Unexpected mining response: %r",
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
            "حدث خطأ في التعدين. حاول لاحقًا."
        )


@bot.callback_query_handler(
    func=lambda call:
        call.data == "en96_mining_refresh"
)
def mining_refresh_callback(call):
    try:
        bot.answer_callback_query(
            call.id,
            "جارٍ تحديث التعدين…"
        )

        mining(
            call.message.chat.id,
            call.from_user.id
        )

    except Exception:
        log.exception("Mining refresh error")

        try:
            bot.answer_callback_query(
                call.id,
                "تعذّر التحديث."
            )
        except Exception:
            pass


# =========================
# VIDEO GIFT REDEMPTION
# =========================

def redeem_gift(message):
    user_id = message.from_user.id
    chat_id = message.chat.id

    code = (message.text or "").strip()

    WAITING_GIFT.discard(user_id)

    try:
        data = rpc_data(
            db.rpc(
                "redeem_en96_video_gift",
                {
                    "p_telegram_id": int(user_id),
                    "p_code": code
                }
            ).execute()
        )

        if data.get("ok") is True:
            bot.send_message(
                chat_id,
                "🎁 تم استلام "
                f"{data.get('reward', 1)} EN96 بنجاح!"
            )
            return

        reason = (
            data.get("reason")
            or data.get("status")
            or data.get("message")
            or "unknown"
        )

        errors = {
            "invalid_input":
                "الكود غير صالح.",
            "profile_not_found":
                "لم أجد حسابك؛ أرسل /start أولًا.",
            "invalid_or_inactive_code":
                "الكود غير موجود أو غير مفعّل.",
            "already_claimed":
                "لقد استعملت هذا الكود من قبل.",
            "cooldown_2_hours":
                "انتظر ساعتين قبل استلام هدية أخرى.",
            "balance_not_found":
                "لم أجد سجل رصيدك."
        }

        bot.send_message(
            chat_id,
            errors.get(
                reason,
                f"تعذّر استلام الهدية: {reason}"
            )
        )

    except Exception:
        log.exception("Gift redemption error")

        bot.send_message(
            chat_id,
            "تعذّر التحقق من كود الهدية."
        )


# =========================
# ADMIN GIFT MANAGEMENT
# =========================

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
        "أرسل رابط فيديو YouTube الآن."
    )


def admin_video(message):
    uid = message.from_user.id
    url = (message.text or "").strip()

    if not url.startswith(("https://", "http://")):
        bot.send_message(
            message.chat.id,
            "أرسل رابطًا صالحًا يبدأ بـ https://."
        )
        return

    PENDING.setdefault(uid, {})["video_url"] = url

    WAITING_ADMIN_VIDEO.discard(uid)
    WAITING_ADMIN_REWARD.add(uid)

    bot.send_message(
        message.chat.id,
        "أرسل مقدار المكافأة، مثل 1."
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
            "أرسل رقمًا موجبًا، مثل 1."
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
            "بيانات الهدية ناقصة؛ ابدأ من جديد."
        )
        return

    try:
        db.table("video_gift_codes").insert({
            "code": item["code"],
            "video_url": item["video_url"],
            "reward": reward,
            "active": True,
            "description": "Created by EN96 admin bot"
        }).execute()

        bot.send_message(
            message.chat.id,
            f"✅ تم إنشاء الكود {item['code']} "
            f"بمكافأة {reward:g} EN96."
        )

    except Exception:
        log.exception("Admin create gift error")

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
            .select("id,code,reward,active,created_at")
            .order("created_at", desc=True)
            .limit(20)
            .execute().data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "لا توجد أكواد هدايا."
            )
            return

        lines = ["📋 أكواد هدايا EN96:"]

        for row in rows:
            state = (
                "مفعّل"
                if row.get("active")
                else "معطّل"
            )

            lines.append(
                f"ID {row.get('id')} | "
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
            "تعذّر عرض أكواد الهدايا."
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
            state = (
                "تفعيل"
                if active
                else "تعطيل"
            )

            bot.send_message(
                message.chat.id,
                f"تم {state} الكود {code}."
            )

        else:
            bot.send_message(
                message.chat.id,
                "لم أعثر على الكود."
            )

    except Exception:
        log.exception("Gift status error")

        bot.send_message(
            message.chat.id,
            "تعذّر تغيير حالة الكود."
        )


# =========================
# TELEGRAM COMMANDS
# =========================

@bot.message_handler(commands=["start", "menu"])
def start(message):
    if message.chat.type != "private":
        bot.reply_to(
            message,
            "افتح بوت EN96 في محادثة خاصة "
            "لتسجيل حسابك."
        )
        return

    registered = register_member(
        message.from_user.id
    )

    if not registered:
        bot.send_message(
            message.chat.id,
            "⚠️ لم أتمكن من تأكيد إنشاء حسابك "
            "في Supabase حاليًا.\n"
            "يمكنك تجربة زر الدخول، "
            "ثم إعادة إرسال /start إذا لزم الأمر."
        )

    # روابط الدعوات لا تضيف مكافآت تلقائيًا
    # حتى يُفعّل نظام التحقق في Supabase.
    send_menu(
        message.chat.id,
        user_id=message.from_user.id
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
    else:
        bot.send_message(
            message.chat.id,
            "هذا الأمر مخصص للمسؤول."
        )


# =========================
# INPUT HANDLERS
# =========================

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
        and ADMIN_ACTION.get(
            m.from_user.id
        ) in ("enable", "disable"),
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
    else:
        WAITING_ADMIN_CODE.discard(
            message.from_user.id
        )


@bot.message_handler(
    func=lambda m:
        m.from_user.id in WAITING_ADMIN_VIDEO,
    content_types=["text"]
)
def admin_video_input(message):
    if is_admin(message.from_user.id):
        admin_video(message)
    else:
        WAITING_ADMIN_VIDEO.discard(
            message.from_user.id
        )


@bot.message_handler(
    func=lambda m:
        m.from_user.id in WAITING_ADMIN_REWARD,
    content_types=["text"]
)
def admin_reward_input(message):
    if is_admin(message.from_user.id):
        admin_reward(message)
    else:
        WAITING_ADMIN_REWARD.discard(
            message.from_user.id
        )


# =========================
# ALL MENU BUTTONS
# =========================

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
            "⚡ ترقيات المنجم لم تُفعّل بعد.\n"
            "لن يتم خصم أي رصيد."
        )

    elif text == "🏆 المكافآت":
        bot.send_message(
            chat_id,
            "🏆 مكافآت EN96 الافتراضية.\n"
            "يمكنك استخدام أكواد هدايا الفيديو."
        )

    elif text == "📺 مشاهدة الفيديوهات":
        bot.send_message(
            chat_id,
            "📺 مكتبة فيديوهات EN96 داخل التطبيق.\n"
            "افتح التطبيق واختر قسم الهدايا "
            "لمشاهدة الفيديوهات."
        )

        if message.chat.type == "private":
            app_button(chat_id)

    elif text == "🎁 استلام الهدية":
        WAITING_GIFT.add(uid)

        bot.send_message(
            chat_id,
            "🎁 أرسل كود الهدية الموجود "
            "في فيديو YouTube."
        )

    elif text in (
        "🐻 أعضاء القبيلة",
        "🐉 أعضاء القبيلة"
    ):
        bot.send_message(
            chat_id,
            "👥 مجتمع EN96 الجليدي.\n"
            "روابط الدعوات متاحة داخل التطبيق.\n"
            "مكافآت الدعوات لم تُفعّل بعد."
        )

        if message.chat.type == "private":
            app_button(chat_id)

    elif text == "ℹ️ معلومات EN96":
        bot.send_message(
            chat_id,
            "🐻❄️ EN96 Ice Bear Mining\n\n"
            "⚡ معدل التعدين: 0.001 EN96/ثانية\n"
            "⏱️ مدة الجلسة: 24 ساعة\n"
            "💎 المكافأة النظرية: 86.4 EN96\n\n"
            "⚠️ هذا تعدين افتراضي، "
            "وليس تعدين أجهزة حقيقيًا."
        )

    elif text == "🛠️ إدارة الهدايا" and is_admin(uid):
        bot.send_message(
            chat_id,
            "🛠️ إدارة الهدايا",
            reply_markup=admin_menu()
        )

    elif text == "➕ إنشاء كود هدية" and is_admin(uid):
        WAITING_ADMIN_CODE.add(uid)

        bot.send_message(
            chat_id,
            "أرسل كود الهدية الجديد."
        )

    elif text == "📋 أكواد الهدايا" and is_admin(uid):
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
            "أرسل الكود الذي تريد تغيير حالته."
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
            bot.send_message(
                chat_id,
                "افتح بوت EN96 في محادثة خاصة."
            )

    else:
        send_menu(
            chat_id,
            "اختر أحد أزرار EN96.",
            user_id=uid
        )


if __name__ == "__main__":
    log.info("Starting EN96 Telegram bot")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
