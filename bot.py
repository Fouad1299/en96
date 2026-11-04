
import os
import json
import time
import logging
import threading
import re

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote

import telebot

from telebot.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)

from supabase import create_client
from en96_accounts import ensure_profile


# ==========================================
# EN96 ICE BEAR KINGDOM
# Telegram Mining and Withdrawal Bot
# Stellar Mainnet
# ==========================================

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

ROYAL_APP_URL = (
    "https://fouad1299.github.io/"
    "en96/en96-royal.html"
)

BOT_USERNAME = "EN96_IceDragon_2026_Bot"

TIKTOK_URL = (
    "https://www.tiktok.com/@en96mining"
)

YOUTUBE_URL = (
    "https://www.youtube.com/@EN96_Gold_Miner_bot"
)

# NEW OFFICIAL TELEGRAM CHANNEL
TELEGRAM_CHANNEL_URL = (
    "https://t.me/EN96_IceBear_Kingdom"
)

LOBSTR_URL = "https://lobstr.co/"

HORIZON_URL = "https://horizon.stellar.org"

EN96_ISSUER = (
    "GCUGIICUGBFC3KBPIFYAMPNA7OVJHGY277TNYTZUSG7EVVUCVACH3OGB"
)

EN96_ASSET = "EN96"

MINING_RATE = 0.001
MINING_DURATION = 86400

MIN_WITHDRAWAL = Decimal("500")
MAX_WITHDRAWAL = Decimal("1000000000000")
EN96_STEP = Decimal("0.0000001")

EN96_PAYOUT_SOURCE = (
    "GBWLEH67H6HCH264IWJFL66CJYF34B7WEC4GSZQJZPDM23WVC6UKB7SJ"
)

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

WITHDRAWAL_STATES = {}
WITHDRAWAL_LOCK = threading.RLock()

ADMIN_CANCEL_CONFIRM = {}
ADMIN_PROCESS_CONFIRM = {}
ADMIN_PAY_HASH = {}



# ==========================================
# FOUR-LANGUAGE INTERFACE
# Arabic / English / Russian / Spanish
# ==========================================

LANGUAGES = {
    "ar": "العربية",
    "en": "English",
    "ru": "Русский",
    "es": "Español",
}

BUTTONS = {
    '⛏️ بدء التعدين': ['⛏️ بدء التعدين', '⛏️ Start mining', '⛏️ Начать майнинг', '⛏️ Iniciar minería'],
    '💰 محفظتي': ['💰 محفظتي', '💰 My wallet', '💰 Мой кошелёк', '💰 Mi billetera'],
    '💸 سحب EN96': ['💸 سحب EN96', '💸 Withdraw EN96', '💸 Вывод EN96', '💸 Retirar EN96'],
    '📋 طلبات السحب': ['📋 طلبات السحب', '📋 Withdrawals', '📋 Запросы на вывод', '📋 Retiros'],
    '⚡ ترقية المنجم': ['⚡ ترقية المنجم', '⚡ Upgrade mine', '⚡ Улучшить шахту', '⚡ Mejorar mina'],
    '🏆 المكافآت': ['🏆 المكافآت', '🏆 Rewards', '🏆 Награды', '🏆 Recompensas'],
    '📺 مشاهدة الفيديوهات': ['📺 مشاهدة الفيديوهات', '📺 Watch videos', '📺 Смотреть видео', '📺 Ver vídeos'],
    '🎁 استلام الهدية': ['🎁 استلام الهدية', '🎁 Redeem video code', '🎁 Ввести код подарка', '🎁 Canjear código'],
    '🎁 هدية 5 EN96': ['🎁 هدية 5 EN96', '🎁 5 EN96 gift', '🎁 Подарок 5 EN96', '🎁 Regalo de 5 EN96'],
    '🐻 أعضاء القبيلة': ['🐻 أعضاء القبيلة', '🐻 Tribe', '🐻 Племя', '🐻 Tribu'],
    'ℹ️ معلومات EN96': ['ℹ️ معلومات EN96', 'ℹ️ About EN96', 'ℹ️ Об EN96', 'ℹ️ Acerca de EN96'],
    '🎵 TikTok EN96': ['🎵 TikTok EN96', '🎵 TikTok EN96', '🎵 TikTok EN96', '🎵 TikTok EN96'],
    '▶️ YouTube EN96': ['▶️ YouTube EN96', '▶️ YouTube EN96', '▶️ YouTube EN96', '▶️ YouTube EN96'],
    '📢 قناة EN96 الرسمية': ['📢 قناة EN96 الرسمية', '📢 EN96 official channel', '📢 Канал EN96', '📢 Canal oficial EN96'],
    '🌐 فتح تطبيق EN96': ['🌐 فتح تطبيق EN96', '🌐 Open EN96 app', '🌐 Открыть EN96', '🌐 Abrir app EN96'],
    '🌐 تغيير اللغة': ['🌐 تغيير اللغة', '🌐 Change language', '🌐 Сменить язык', '🌐 Cambiar idioma'],
    '🛠️ إدارة الهدايا': ['🛠️ إدارة الهدايا', '🛠️ Manage gifts', '🛠️ Управление подарками', '🛠️ Administrar regalos'],
    '⭐ رصيد Stars للإدارة': ['⭐ رصيد Stars للإدارة', '⭐ Admin Stars', '⭐ Stars администратора', '⭐ Stars de administrador'],
    '👑 إدارة السحوبات': ['👑 إدارة السحوبات', '👑 Manage withdrawals', '👑 Управление выводами', '👑 Gestionar retiros'],
    '➕ إنشاء كود هدية': ['➕ إنشاء كود هدية', '➕ Create gift code', '➕ Создать код', '➕ Crear código'],
    '📋 أكواد الهدايا': ['📋 أكواد الهدايا', '📋 Gift codes', '📋 Коды подарков', '📋 Códigos de regalo'],
    '⛔ تعطيل كود': ['⛔ تعطيل كود', '⛔ Disable code', '⛔ Отключить код', '⛔ Desactivar código'],
    '✅ تفعيل كود': ['✅ تفعيل كود', '✅ Enable code', '✅ Включить код', '✅ Activar código'],
    '🔙 القائمة الرئيسية': ['🔙 القائمة الرئيسية', '🔙 Main menu', '🔙 Главное меню', '🔙 Menú principal'],
}

LANG_ORDER = tuple(LANGUAGES)
BUTTON_CANONICAL = {translated: original for original, variants in BUTTONS.items() for translated in variants}
LANG_CACHE = {}

MESSAGES = {
    'welcome': ['🐻 مرحبًا بك في EN96 Mining!', '🐻 Welcome to EN96 Mining!', '🐻 Добро пожаловать в EN96 Mining!', '🐻 ¡Bienvenido a EN96 Mining!'],
    'choose': ['اختر زرًا من قائمة EN96.', 'Choose an EN96 menu button.', 'Выберите кнопку меню EN96.', 'Elige una opción del menú EN96.'],
    'language': ['🌐 اختر لغتك:', '🌐 Choose your language:', '🌐 Выберите язык:', '🌐 Elige tu idioma:'],
    'saved': ['✅ تم حفظ اللغة.', '✅ Language saved.', '✅ Язык сохранён.', '✅ Idioma guardado.'],
    'mining_future': ['⚡ ترقيات المنجم لم تُفعّل بعد.', '⚡ Mine upgrades are not available yet.', '⚡ Улучшения пока недоступны.', '⚡ Las mejoras aún no están disponibles.'],
    'enter_code': ['🎁 أرسل كود هدية الفيديو.', '🎁 Send the video gift code.', '🎁 Отправьте код подарка из видео.', '🎁 Envía el código de regalo del vídeo.'],
}


EXTRA_MESSAGES = {
    "rewards": {
        "ar": "🏆 مكافآت EN96 الافتراضية.\nيمكنك جمع هدايا الفيديو ومكافآت القبيلة المؤهلة.",
        "en": "🏆 EN96 virtual rewards.\nYou can collect video gifts and eligible tribe rewards.",
        "ru": "🏆 Виртуальные награды EN96.\nПолучайте видеоподарки и доступные награды племени.",
        "es": "🏆 Recompensas virtuales EN96.\nPuedes obtener regalos de vídeos y recompensas de la tribu.",
    },
    "about": {
        "ar": "🐻 EN96 Ice Bear Kingdom\n\n⛏️ تعدين افتراضي، وليس تعدين أجهزة حقيقيًا.\n⚡ 0.001 EN96 في الثانية.\n⏱️ الجلسة: 24 ساعة (86.4 EN96).\n🎁 الدعوة المؤهلة: 50 EN96.\n👥 عمولة تعدين الأصدقاء: 5%.\n💸 الحد الأدنى للسحب: 500 EN96.\n🌐 Stellar Mainnet.\n⚠️ السحب يحتاج مراجعة يدوية.",
        "en": "🐻 EN96 Ice Bear Kingdom\n\n⛏️ Virtual mining, not hardware or blockchain mining.\n⚡ 0.001 EN96 per second.\n⏱️ Session: 24 hours (86.4 EN96).\n🎁 Eligible referral: 50 EN96.\n👥 Friends' mining bonus: 5%.\n💸 Minimum withdrawal: 500 EN96.\n🌐 Stellar Mainnet.\n⚠️ Withdrawals require manual review.",
        "ru": "🐻 EN96 Ice Bear Kingdom\n\n⛏️ Виртуальный майнинг, не реальная добыча криптовалюты.\n⚡ 0,001 EN96 в секунду.\n⏱️ Сессия: 24 часа (86,4 EN96).\n🎁 За подходящее приглашение: 50 EN96.\n👥 Бонус за майнинг друзей: 5%.\n💸 Минимальный вывод: 500 EN96.\n🌐 Stellar Mainnet.\n⚠️ Вывод проверяется вручную.",
        "es": "🐻 EN96 Ice Bear Kingdom\n\n⛏️ Minería virtual, no minería real de blockchain.\n⚡ 0,001 EN96 por segundo.\n⏱️ Sesión: 24 horas (86,4 EN96).\n🎁 Invitación válida: 50 EN96.\n👥 Bono por minería de amigos: 5%.\n💸 Retiro mínimo: 500 EN96.\n🌐 Stellar Mainnet.\n⚠️ Los retiros requieren revisión manual.",
    },
}

def extra_text(key, user_id):
    return EXTRA_MESSAGES[key][get_language(user_id)]

def normalized_language(value):
    code = str(value or "").lower().split("-")[0].split("_")[0]
    return code if code in LANGUAGES else "en"

def get_language(user_id, telegram_language=None):
    uid = str(user_id)
    if uid in LANG_CACHE:
        return LANG_CACHE[uid]
    default = normalized_language(telegram_language)
    try:
        rows = (db.table("en96_user_languages")
                .select("language_code")
                .eq("telegram_id", uid).limit(1).execute().data or [])
        if rows:
            lang = normalized_language(rows[0]["language_code"])
            LANG_CACHE[uid] = lang
            return lang
    except Exception:
        log.exception("Failed to load EN96 language")
    LANG_CACHE[uid] = default
    return default

def save_language(user_id, language):
    lang = normalized_language(language)
    uid = str(user_id)
    db.table("en96_user_languages").upsert({
        "telegram_id": uid,
        "language_code": lang,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }, on_conflict="telegram_id").execute()
    LANG_CACHE[uid] = lang
    return lang

def local_text(key, user_id):
    lang = get_language(user_id)
    return MESSAGES[key][LANG_ORDER.index(lang)]

def local_button(original, user_id):
    choices = BUTTONS.get(original)
    return choices[LANG_ORDER.index(get_language(user_id))] if choices else original

def language_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    items = [InlineKeyboardButton(name, callback_data="lang:" + code)
             for code, name in LANGUAGES.items()]
    kb.add(*items)
    return kb

def choose_language(chat_id, user_id):
    bot.send_message(chat_id, local_text("language", user_id),
                     reply_markup=language_keyboard())


# ==========================================
# LOCALIZATION OF LEGACY REPLIES
# All existing Telegram callbacks and Supabase RPCs remain unchanged.
# ==========================================
LOCALE_PHRASES = {'🐻\u200d❄️👑 محفظة EN96': ('🐻\u200d❄️👑 EN96 Wallet', '🐻\u200d❄️👑 Кошелёк EN96', '🐻\u200d❄️👑 Billetera EN96'),
 '🟢 الرصيد المتاح:': ('🟢 Available balance:', '🟢 Доступно:', '🟢 Saldo disponible:'),
 '🟡 الرصيد المحجوز:': ('🟡 Reserved balance:', '🟡 Зарезервировано:', '🟡 Saldo reservado:'),
 '💸 الحد الأدنى للسحب:': ('💸 Minimum withdrawal:', '💸 Минимальный вывод:', '💸 Retiro mínimo:'),
 '🔗 عنوان Stellar:': ('🔗 Stellar address:', '🔗 Адрес Stellar:', '🔗 Dirección Stellar:'),
 'غير مربوط': ('Not linked', 'Не привязан', 'No vinculada'),
 '📌 السحب إلى شبكة Stellar Mainnet.': ('📌 Withdrawals use Stellar Mainnet.',
                                       '📌 Вывод в сети Stellar Mainnet.',
                                       '📌 Los retiros usan Stellar Mainnet.'),
 '📌 إرسال العملات يتم يدويًا بعد المراجعة.': ('📌 Coins are sent manually after review.',
                                              '📌 Отправка монет вручную после проверки.',
                                              '📌 Las monedas se envían manualmente tras la revisión.'),
 '⚠️ الرصيد داخل البوت ليس رصيد Stellar.': ('⚠️ In-bot balance is not a Stellar balance.',
                                            '⚠️ Баланс бота не является балансом Stellar.',
                                            '⚠️ El saldo del bot no es saldo en Stellar.'),
 '💸 طلب سحب EN96': ('💸 Request EN96 withdrawal', '💸 Запросить вывод EN96', '💸 Solicitar retiro de EN96'),
 '🔗 ربط عنوان G': ('🔗 Link G address', '🔗 Привязать G-адрес', '🔗 Vincular dirección G'),
 '🛡️ فحص خط الثقة': ('🛡️ Check trustline', '🛡️ Проверить trustline', '🛡️ Comprobar trustline'),
 '🪙 إنشاء محفظة LOBSTR': ('🪙 Create LOBSTR wallet', '🪙 Создать кошелёк LOBSTR', '🪙 Crear billetera LOBSTR'),
 '🔄 تحديث التعدين': ('🔄 Refresh mining', '🔄 Обновить майнинг', '🔄 Actualizar minería'),
 '🐻👑 منجم EN96': ('🐻👑 EN96 Mine', '🐻👑 Шахта EN96', '🐻👑 Mina EN96'),
 '⛏️ التعدين الافتراضي نشط.': ('⛏️ Virtual mining is active.',
                               '⛏️ Виртуальный майнинг активен.',
                               '⛏️ La minería virtual está activa.'),
 '⛏️ التعدين الافتراضي نشط': ('⛏️ Virtual mining is active',
                              '⛏️ Виртуальный майнинг активен',
                              '⛏️ La minería virtual está activa'),
 '⚡ 0.001 EN96/ثانية': ('⚡ 0.001 EN96/second', '⚡ 0,001 EN96/секунду', '⚡ 0,001 EN96/segundo'),
 '⏱️ الجلسة: 24 ساعة': ('⏱️ Session: 24 hours', '⏱️ Сессия: 24 часа', '⏱️ Sesión: 24 horas'),
 'العداد تقديري والرصيد تحدده Supabase.': ('The counter is an estimate; Supabase determines the balance.',
                                           'Счётчик приблизительный; баланс определяет Supabase.',
                                           'El contador es estimado; Supabase determina el saldo.'),
 '💎 المكافأة التقديرية:': ('💎 Estimated reward:', '💎 Примерная награда:', '💎 Recompensa estimada:'),
 '⏱️ الوقت:': ('⏱️ Time:', '⏱️ Время:', '⏱️ Tiempo:'),
 '⚠️ الرصيد الفعلي محفوظ في Supabase.': ('⚠️ The actual balance is stored in Supabase.',
                                         '⚠️ Фактический баланс хранится в Supabase.',
                                         '⚠️ El saldo real se guarda en Supabase.'),
 '✅ تم إضافة مكافأة الجلسة السابقة وبدء جلسة جديدة.': ('✅ Previous session reward credited; new session started.',
                                                       '✅ Награда за прошлую сессию начислена; начата новая.',
                                                       '✅ Recompensa anterior acreditada; nueva sesión iniciada.'),
 'بدأت جلسة جديدة.': ('A new session has started.', 'Началась новая сессия.', 'Ha comenzado una nueva sesión.'),
 '⚠️ لم يتم تأكيد المكافأة.': ('⚠️ Reward not confirmed.',
                               '⚠️ Награда не подтверждена.',
                               '⚠️ Recompensa no confirmada.'),
 'اضغط بدء التعدين للتحقق.': ('Tap Start mining to check.',
                              'Нажмите Начать майнинг для проверки.',
                              'Pulsa Iniciar minería para comprobar.'),
 '⚠️ لم تؤكد Supabase عملية التعدين.': ('⚠️ Supabase did not confirm mining.',
                                        '⚠️ Supabase не подтвердил майнинг.',
                                        '⚠️ Supabase no confirmó la minería.'),
 'الحالة:': ('Status:', 'Статус:', 'Estado:'),
 'غير معروفة': ('Unknown', 'Неизвестно', 'Desconocido'),
 'تعذر تشغيل التعدين الآن.': ('Mining is temporarily unavailable.',
                              'Майнинг временно недоступен.',
                              'La minería no está disponible ahora.'),
 '🐻👑 قبيلة EN96': ('🐻👑 EN96 Tribe', '🐻👑 Племя EN96', '🐻👑 Tribu EN96'),
 '👥 عدد الأصدقاء:': ('👥 Friends:', '👥 Друзей:', '👥 Amigos:'),
 '🎁 مكافآت الدعوات:': ('🎁 Referral rewards:', '🎁 Награды за приглашения:', '🎁 Recompensas por invitaciones:'),
 '⛏️ عمولات تعدين الأصدقاء 5%:': ('⛏️ Friends mining bonus 5%:',
                                  '⛏️ Бонус за майнинг друзей 5%:',
                                  '⛏️ Bono por minería de amigos 5%:'),
 '💎 مجموع مكافآت القبيلة:': ('💎 Total tribe rewards:',
                             '💎 Всего наград племени:',
                             '💎 Total de recompensas de la tribu:'),
 '🔗 رابط دعوتك:': ('🔗 Your invite link:', '🔗 Ваша ссылка-приглашение:', '🔗 Tu enlace de invitación:'),
 'تعذر تحميل الإحصائيات الآن.': ('Could not load stats.',
                                 'Не удалось загрузить статистику.',
                                 'No se pudieron cargar las estadísticas.'),
 'رابط دعوتك:': ('Your invite link:', 'Ваша ссылка-приглашение:', 'Tu enlace de invitación:'),
 'لا يمكنك دعوة نفسك.': ('You cannot refer yourself.',
                         'Нельзя пригласить самого себя.',
                         'No puedes invitarte a ti mismo.'),
 '🎉 تم تسجيل دعوتك في قبيلة EN96!': ('🎉 Your referral was registered in the EN96 tribe!',
                                     '🎉 Ваше приглашение зарегистрировано в племени EN96!',
                                     '🎉 ¡Tu invitación quedó registrada en la tribu EN96!'),
 'لم أجد حسابك. أرسل /start أولًا.': ('Account not found. Send /start first.',
                                      'Аккаунт не найден. Сначала отправьте /start.',
                                      'Cuenta no encontrada. Envía /start primero.'),
 'لم أجد حسابك. أرسل /start.': ('Account not found. Send /start.',
                                'Аккаунт не найден. Отправьте /start.',
                                'Cuenta no encontrada. Envía /start.'),
 'لم أجد حسابك.': ('Account not found.', 'Аккаунт не найден.', 'Cuenta no encontrada.'),
 'أرسل /start أولًا.': ('Send /start first.', 'Сначала отправьте /start.', 'Envía /start primero.'),
 'لم أجد سجل رصيدك.': ('Balance record not found.',
                       'Запись баланса не найдена.',
                       'No se encontró el registro de saldo.'),
 'تعذر عرض المحفظة الآن.': ('Could not display wallet now.',
                            'Не удалось открыть кошелёк.',
                            'No se pudo mostrar la billetera.'),
 '🔗 ربط محفظة Stellar': ('🔗 Link Stellar wallet', '🔗 Привязать кошелёк Stellar', '🔗 Vincular billetera Stellar'),
 'أرسل عنوان Stellar عامًا صحيحًا أو أرسل /cancel.': ('Send a valid public Stellar address or /cancel.',
                                                      'Отправьте корректный публичный адрес Stellar или /cancel.',
                                                      'Envía una dirección pública de Stellar válida o /cancel.'),
 '❌ عنوان G غير صالح.': ('❌ Invalid G address.', '❌ Неверный G-адрес.', '❌ Dirección G no válida.'),
 'عنوان Stellar غير صالح.': ('Invalid Stellar address.', 'Неверный адрес Stellar.', 'Dirección Stellar no válida.'),
 '✅ تم حفظ عنوان Stellar في حساب EN96.': ('✅ Stellar address saved to your EN96 account.',
                                          '✅ Адрес Stellar сохранён в аккаунте EN96.',
                                          '✅ Dirección Stellar guardada en tu cuenta EN96.'),
 '🛡️ افحص خط الثقة قبل طلب السحب.': ('🛡️ Check the trustline before withdrawing.',
                                     '🛡️ Проверьте trustline перед выводом.',
                                     '🛡️ Comprueba la trustline antes de retirar.'),
 '⚠️ حفظ عنوان G لا يعني إثبات ملكية المحفظة.': ('⚠️ Saving a G-address does not prove ownership.',
                                                 '⚠️ Сохранение G-адреса не доказывает владение.',
                                                 '⚠️ Guardar una dirección G no demuestra propiedad.'),
 '⚠️ لديك طلب سحب معلق بالفعل.': ('⚠️ You already have a pending withdrawal.',
                                  '⚠️ У вас уже есть запрос на вывод.',
                                  '⚠️ Ya tienes un retiro pendiente.'),
 '⏳ لديك طلب سحب معلق بالفعل.': ('⏳ You already have a pending withdrawal.',
                                 '⏳ У вас уже есть запрос на вывод.',
                                 '⏳ Ya tienes un retiro pendiente.'),
 '⏳ لديك طلب سحب معلق.': ('⏳ You have a pending withdrawal.',
                          '⏳ У вас есть запрос на вывод.',
                          '⏳ Tienes un retiro pendiente.'),
 'لا يمكن تغيير عنوان الاستلام أثناء مراجعة الطلب.': ('You cannot change the receiving address during review.',
                                                      'Нельзя изменить адрес во время проверки.',
                                                      'No puedes cambiar la dirección durante la revisión.'),
 'تعذر حفظ العنوان الآن.': ('Could not save the address now.',
                            'Не удалось сохранить адрес.',
                            'No se pudo guardar la dirección.'),
 '⚠️ لم تربط عنوان G بعد.': ('⚠️ No G-address linked yet.',
                             '⚠️ G-адрес ещё не привязан.',
                             '⚠️ Aún no hay una dirección G vinculada.'),
 'افتح المحفظة واضغط ربط عنوان G.': ('Open Wallet and tap Link G address.',
                                     'Откройте кошелёк и выберите Привязать G-адрес.',
                                     'Abre la billetera y pulsa Vincular dirección G.'),
 '✅ تم العثور على خط ثقة EN96!': ('✅ EN96 trustline found!',
                                  '✅ Trustline EN96 найдена!',
                                  '✅ ¡Trustline EN96 encontrada!'),
 '💎 رصيد المحفظة على Stellar:': ('💎 Wallet balance on Stellar:',
                                 '💎 Баланс кошелька Stellar:',
                                 '💎 Saldo de billetera en Stellar:'),
 '⚠️ هذا فحص عام، وليس إثبات ملكية.': ('⚠️ This is a public check, not proof of ownership.',
                                       '⚠️ Это публичная проверка, не доказательство владения.',
                                       '⚠️ Es una consulta pública, no prueba de propiedad.'),
 'تعذر فحص خط الثقة.': ('Could not check trustline.',
                        'Не удалось проверить trustline.',
                        'No se pudo comprobar la trustline.'),
 '❌ الرصيد المتاح غير كافٍ.': ('❌ Insufficient available balance.',
                               '❌ Недостаточно доступного баланса.',
                               '❌ Saldo disponible insuficiente.'),
 'رصيدك:': ('Your balance:', 'Ваш баланс:', 'Tu saldo:'),
 'الحد الأدنى:': ('Minimum:', 'Минимум:', 'Mínimo:'),
 '🟡 الحد الأدنى:': ('🟡 Minimum:', '🟡 Минимум:', '🟡 Mínimo:'),
 'افتح «📋 طلبات السحب» لمتابعة الطلب.': ('Open Withdrawals to track it.',
                                         'Откройте Запросы на вывод для отслеживания.',
                                         'Abre Retiros para seguir la solicitud.'),
 '⚠️ لا يمكن بدء السحب.': ('⚠️ Cannot start withdrawal.',
                           '⚠️ Нельзя начать вывод.',
                           '⚠️ No se puede iniciar el retiro.'),
 '⚠️ يجب إضافة خط ثقة EN96 إلى محفظتك أولًا.': ('⚠️ Add EN96 trustline to your wallet first.',
                                                '⚠️ Сначала добавьте trustline EN96 в кошелёк.',
                                                '⚠️ Agrega primero la trustline EN96 a tu billetera.'),
 'المُصدر:': ('Issuer:', 'Эмитент:', 'Emisor:'),
 '🔗 عنوان الاستلام:': ('🔗 Receiving address:', '🔗 Адрес получателя:', '🔗 Dirección de recepción:'),
 '✅ خط الثقة موجود.': ('✅ Trustline present.', '✅ Trustline есть.', '✅ Trustline disponible.'),
 'اكتب مبلغ السحب الآن.': ('Enter the withdrawal amount now.',
                           'Введите сумму вывода.',
                           'Escribe el importe del retiro.'),
 'مثال:': ('Example:', 'Пример:', 'Ejemplo:'),
 '⚠️ تأكد أن هذا عنوان محفظتك.': ('⚠️ Make sure this is your wallet address.',
                                  '⚠️ Убедитесь, что это ваш адрес кошелька.',
                                  '⚠️ Verifica que sea tu dirección de billetera.'),
 'تعذر العثور على رصيدك.': ('Could not find your balance.', 'Не удалось найти баланс.', 'No se encontró tu saldo.'),
 'تعذر بدء طلب السحب.': ('Could not start withdrawal.', 'Не удалось начать вывод.', 'No se pudo iniciar el retiro.'),
 'لم يتم حجز رصيد جديد.': ('No new balance was reserved.',
                           'Новые средства не резервировались.',
                           'No se reservó saldo nuevo.'),
 '❌ مبلغ غير صالح.': ('❌ Invalid amount.', '❌ Неверная сумма.', '❌ Importe no válido.'),
 'أقصى دقة: 7 أرقام عشرية.': ('Maximum precision: 7 decimal places.',
                              'Точность: до 7 знаков после запятой.',
                              'Máximo 7 decimales.'),
 'أرسل المبلغ مجددًا أو /cancel.': ('Send amount again or /cancel.',
                                    'Отправьте сумму снова или /cancel.',
                                    'Envía otra vez el importe o /cancel.'),
 '👑 تأكيد سحب EN96': ('👑 Confirm EN96 withdrawal', '👑 Подтверждение вывода EN96', '👑 Confirmar retiro de EN96'),
 '💎 المبلغ:': ('💎 Amount:', '💎 Сумма:', '💎 Importe:'),
 '🔗 المحفظة:': ('🔗 Wallet:', '🔗 Кошелёк:', '🔗 Billetera:'),
 'عند التأكيد سيُنقل المبلغ من المتاح إلى المحجوز.': ('Confirming moves the amount from available to reserved.',
                                                      'После подтверждения сумма перейдёт из доступных средств в '
                                                      'резерв.',
                                                      'Al confirmar, el importe pasará de disponible a reservado.'),
 '⚠️ لن تُرسل العملات فورًا.': ('⚠️ Coins are not sent immediately.',
                                '⚠️ Монеты отправляются не сразу.',
                                '⚠️ Las monedas no se envían de inmediato.'),
 '✅ تم تسجيل طلب السحب!': ('✅ Withdrawal request submitted!',
                           '✅ Запрос на вывод отправлен!',
                           '✅ ¡Solicitud de retiro enviada!'),
 '🟡 الحالة: قيد المراجعة': ('🟡 Status: under review', '🟡 Статус: на проверке', '🟡 Estado: en revisión'),
 '🔒 تم حجز المبلغ في Supabase.': ('🔒 Amount reserved in Supabase.',
                                  '🔒 Сумма зарезервирована в Supabase.',
                                  '🔒 Importe reservado en Supabase.'),
 '🆔 رقم الطلب:': ('🆔 Request ID:', '🆔 ID запроса:', '🆔 ID de solicitud:'),
 'لا يوجد طلب جاهز للتأكيد.': ('No withdrawal ready to confirm.',
                               'Нет вывода для подтверждения.',
                               'No hay retiro listo para confirmar.'),
 '📋 لا توجد طلبات سحب حتى الآن.': ('📋 No withdrawal requests yet.',
                                   '📋 Пока нет запросов на вывод.',
                                   '📋 Aún no hay solicitudes de retiro.'),
 'تعذر تحميل طلبات السحب.': ('Could not load withdrawals.',
                             'Не удалось загрузить выводы.',
                             'No se pudieron cargar los retiros.'),
 '✅ تراجعت عن طلب السحب.': ('✅ Withdrawal canceled before submission.',
                            '✅ Запрос на вывод отменён до отправки.',
                            '✅ Retiro cancelado antes del envío.'),
 'لم يتم حجز مبلغ جديد.': ('No new amount reserved.',
                           'Новая сумма не резервировалась.',
                           'No se reservó importe nuevo.'),
 '🎁 مبروك! أضفنا 5 EN96 إلى رصيدك المتاح في Supabase.': ('🎁 Congratulations! 5 EN96 was added to your available '
                                                         'balance in Supabase.',
                                                         '🎁 Поздравляем! 5 EN96 добавлено к доступному балансу в '
                                                         'Supabase.',
                                                         '🎁 ¡Enhorabuena! Se añadieron 5 EN96 a tu saldo disponible en '
                                                         'Supabase.'),
 'يمكنك رؤية الرصيد من زر 💰 محفظتي.': ('Check it using My wallet.',
                                       'Проверьте баланс через Мой кошелёк.',
                                       'Consúltalo en Mi billetera.'),
 '✅ لقد استلمت هدية 5 EN96 سابقًا. الهدية مرة واحدة لكل حساب.': ('✅ You have already claimed the one-time 5 EN96 gift.',
                                                                 '✅ Вы уже получили разовый подарок 5 EN96.',
                                                                 '✅ Ya reclamaste el regalo único de 5 EN96.'),
 '🎁 تم استلام': ('🎁 Received', '🎁 Получено', '🎁 Recibido'),
 'بنجاح!': ('successfully!', 'успешно!', 'correctamente!'),
 'تعذر التحقق من كود الهدية.': ('Could not verify gift code.',
                                'Не удалось проверить подарочный код.',
                                'No se pudo verificar el código de regalo.'),
 'لا توجد فيديوهات هدايا حاليًا.': ('No gift videos currently available.',
                                    'Сейчас нет видео с подарками.',
                                    'Actualmente no hay vídeos con regalos.'),
 'تعذر تحميل الفيديوهات.': ('Could not load videos.',
                            'Не удалось загрузить видео.',
                            'No se pudieron cargar los vídeos.'),
 '⚠️ فشل تسجيل الهدية مؤقتًا. حاول لاحقًا ولا تكرر الضغط بسرعة.': ('⚠️ Gift registration failed temporarily. Try '
                                                                   'later; avoid repeated taps.',
                                                                   '⚠️ Временная ошибка подарка. Попробуйте позже; не '
                                                                   'нажимайте часто.',
                                                                   '⚠️ Error temporal al reclamar el regalo. Inténtalo '
                                                                   'después; no pulses repetidamente.'),
 '⚠️ تعذر المطالبة الآن. لم تتم إضافة مكافأة جديدة.': ('⚠️ Claim unavailable. No new reward was added.',
                                                       '⚠️ Получение недоступно. Новая награда не начислена.',
                                                       '⚠️ No se pudo reclamar. No se añadió una recompensa nueva.'),
 '⚠️ لم نجد حسابك. أرسل /start أولًا.': ('⚠️ Account not found. Send /start first.',
                                         '⚠️ Аккаунт не найден. Сначала отправьте /start.',
                                         '⚠️ Cuenta no encontrada. Envía /start primero.'),
 '⚠️ تعذر تسجيل حسابك. أرسل /start لاحقًا.': ('⚠️ Could not register your account. Try /start later.',
                                              '⚠️ Не удалось создать аккаунт. Попробуйте /start позже.',
                                              '⚠️ No se pudo registrar tu cuenta. Prueba /start después.'),
 '🎵 TikTok الرسمي لمشروع EN96': ('🎵 Official EN96 TikTok', '🎵 Официальный TikTok EN96', '🎵 TikTok oficial de EN96'),
 '▶️ قناة YouTube الرسمية لـ EN96': ('▶️ Official EN96 YouTube channel',
                                     '▶️ Официальный канал EN96 на YouTube',
                                     '▶️ Canal oficial de YouTube de EN96'),
 '📢 تابع أخبار المملكة الرسمية.': ('📢 Follow official kingdom news.',
                                   '📢 Следите за официальными новостями королевства.',
                                   '📢 Sigue las noticias oficiales del reino.'),
 '🎁 تعرف على الهدايا والمكافآت.': ('🎁 Discover gifts and rewards.',
                                   '🎁 Узнавайте о подарках и наградах.',
                                   '🎁 Descubre regalos y recompensas.'),
 '🌍 تابع تطور مشروع EN96.': ('🌍 Follow EN96 project progress.',
                             '🌍 Следите за развитием проекта EN96.',
                             '🌍 Sigue la evolución del proyecto EN96.'),
 'اضغط الزر أدناه لفتح القناة.': ('Tap below to open the channel.',
                                  'Нажмите кнопку ниже, чтобы открыть канал.',
                                  'Pulsa abajo para abrir el canal.'),
 'افتح EN96 في محادثة خاصة.': ('Open EN96 in a private chat.',
                               'Откройте EN96 в личном чате.',
                               'Abre EN96 en un chat privado.'),
 '⚠️ تعذر تأكيد حسابك.': ('⚠️ Could not verify your account.',
                          '⚠️ Не удалось подтвердить аккаунт.',
                          '⚠️ No se pudo verificar tu cuenta.'),
 'حاول لاحقًا.': ('Try later.', 'Попробуйте позже.', 'Inténtalo más tarde.'),
 '✅ تم إلغاء الإدخال الجاري.': ('✅ Current input canceled.', '✅ Текущий ввод отменён.', '✅ Entrada actual cancelada.'),
 '⚠️ تعذر تنفيذ الأمر الآن.': ('⚠️ Could not perform this action.',
                               '⚠️ Не удалось выполнить действие.',
                               '⚠️ No se pudo completar esta acción.')}

_ORIGINAL_SEND_MESSAGE = bot.send_message
_ORIGINAL_EDIT_MESSAGE_TEXT = bot.edit_message_text
_ORIGINAL_REPLY_TO = bot.reply_to

def translate_legacy(text_value, user_id):
    if not isinstance(text_value, str) or not any('\u0600' <= c <= '\u06ff' for c in text_value):
        return text_value
    language = get_language(user_id)
    if language == 'ar':
        return text_value
    column = {'en': 0, 'ru': 1, 'es': 2}.get(language, 0)
    result = text_value
    for arabic in sorted(LOCALE_PHRASES, key=len, reverse=True):
        if arabic in result:
            result = result.replace(arabic, LOCALE_PHRASES[arabic][column])
    return result

def translate_inline_keyboard(markup, user_id):
    if isinstance(markup, InlineKeyboardMarkup):
        for line in markup.keyboard:
            for key in line:
                if getattr(key, 'text', None):
                    key.text = translate_legacy(key.text, user_id)
    return markup

def localized_send_message(chat_id, text, *args, **kwargs):
    if 'reply_markup' in kwargs:
        kwargs['reply_markup'] = translate_inline_keyboard(kwargs['reply_markup'], chat_id)
    return _ORIGINAL_SEND_MESSAGE(chat_id, translate_legacy(text, chat_id), *args, **kwargs)

def localized_edit_message_text(text, *args, **kwargs):
    chat_id = kwargs.get('chat_id')
    if chat_id is None and args:
        chat_id = args[0]
    if chat_id is not None:
        text = translate_legacy(text, chat_id)
        if 'reply_markup' in kwargs:
            kwargs['reply_markup'] = translate_inline_keyboard(kwargs['reply_markup'], chat_id)
    return _ORIGINAL_EDIT_MESSAGE_TEXT(text, *args, **kwargs)

def localized_reply_to(message, text, *args, **kwargs):
    uid = message.from_user.id if getattr(message, 'from_user', None) else message.chat.id
    return _ORIGINAL_REPLY_TO(message, translate_legacy(text, uid), *args, **kwargs)

bot.send_message = localized_send_message
bot.edit_message_text = localized_edit_message_text
bot.reply_to = localized_reply_to


# Extra localized replies for legacy workflows
LOCALE_PHRASES.update({'افتح LOBSTR واختر Receive، ثم انسخ عنوانك العام الذي يبدأ بحرف G.': ('Open LOBSTR, choose Receive, and copy your public address starting with G.', 'Откройте LOBSTR, выберите Receive и скопируйте публичный адрес, начинающийся с G.', 'Abre LOBSTR, elige Receive y copia tu dirección pública que empieza con G.'), 'أرسله هنا لحفظ عنوان الاستلام.': ('Send it here to save your receiving address.', 'Отправьте его сюда, чтобы сохранить адрес получения.', 'Envíala aquí para guardar tu dirección de recepción.'), '⚠️ لا ترسل المفتاح السري أو كلمات الاسترداد.': ('⚠️ Never send your secret key or recovery phrase.', '⚠️ Не отправляйте секретный ключ или фразу восстановления.', '⚠️ Nunca envíes la clave secreta ni la frase de recuperación.'), '⚠️ لديك طلب سحب معلق.': ('⚠️ You have a pending withdrawal.', '⚠️ У вас есть ожидающий вывод.', '⚠️ Tienes un retiro pendiente.'), '⚠️ لم يكتمل تأكيد طلب السحب.': ('⚠️ Withdrawal confirmation was not completed.', '⚠️ Подтверждение вывода не завершено.', '⚠️ La confirmación del retiro no se completó.'), 'افتح «📋 طلبات السحب» وتحقق من وجود طلب معلق قبل المحاولة مجددًا.': ('Open Withdrawals and check pending requests before trying again.', 'Откройте «Запросы на вывод» и проверьте заявки перед повтором.', 'Abre Retiros y revisa las solicitudes pendientes antes de reintentar.'), 'لم يتم إرسال أي عملات Stellar.': ('No Stellar assets were sent.', 'Активы Stellar не отправлялись.', 'No se enviaron activos Stellar.'), 'لم يتم إلغاء أي طلب سحب مسجل في Supabase.': ('No withdrawal request stored in Supabase was canceled.', 'Ни одна заявка на вывод в Supabase не была отменена.', 'No se canceló ninguna solicitud de retiro guardada en Supabase.'), 'اضغط زر تأكيد السحب أو تراجع من الرسالة السابقة.': ('Use the confirmation or back button in the previous message.', 'Нажмите подтверждение или отмену в предыдущем сообщении.', 'Usa el botón de confirmación o volver del mensaje anterior.'), '⏳ طلبك قيد المعالجة.': ('⏳ Your request is being processed.', '⏳ Ваш запрос обрабатывается.', '⏳ Tu solicitud se está procesando.'), 'تحقق من طلبات السحب.': ('Check your withdrawals.', 'Проверьте запросы на вывод.', 'Consulta tus retiros.'), '✅ تراجعت. لم يتغير الطلب.': ('✅ Canceled the action; the request is unchanged.', '✅ Действие отменено, заявка не изменена.', '✅ Acción cancelada; la solicitud no cambió.'), '✅ لم يتم إلغاء الطلب.': ('✅ The request was not canceled.', '✅ Заявка не была отменена.', '✅ No se canceló la solicitud.'), 'هذا الأمر مخصص للمسؤول.': ('This command is for administrators only.', 'Эта команда доступна только администратору.', 'Este comando es solo para administradores.'), '🔒 هذا القسم خاص بإدارة EN96.': ('🔒 This area is for EN96 administrators only.', '🔒 Раздел доступен только администрации EN96.', '🔒 Esta sección es solo para administradores de EN96.'), 'تعذر الحصول على رصيد Stars.': ('Could not retrieve Stars balance.', 'Не удалось получить баланс Stars.', 'No se pudo obtener el saldo de Stars.'), 'تحقق من Render وحاول مجددًا.': ('Check Render and try again.', 'Проверьте Render и повторите попытку.', 'Comprueba Render e inténtalo de nuevo.'), 'تعذر فتح تأكيد الدفع.': ('Could not open payment confirmation.', 'Не удалось открыть подтверждение оплаты.', 'No se pudo abrir la confirmación de pago.'), 'تعذر فتح تأكيد المعالجة.': ('Could not open processing confirmation.', 'Не удалось открыть подтверждение обработки.', 'No se pudo abrir la confirmación de procesamiento.'), 'تعذر فتح تأكيد الإلغاء.': ('Could not open cancellation confirmation.', 'Не удалось открыть подтверждение отмены.', 'No se pudo abrir la confirmación de cancelación.'), 'الطلب غير موجود.': ('Request not found.', 'Заявка не найдена.', 'Solicitud no encontrada.'), 'تعذر فحص المحفظة.': ('Could not check the wallet.', 'Не удалось проверить кошелёк.', 'No se pudo comprobar la billetera.'), 'لا يمكن إلغاء هذا الطلب.': ('This request cannot be canceled.', 'Эту заявку нельзя отменить.', 'Esta solicitud no se puede cancelar.'), 'تعذر تأكيد الإلغاء.': ('Could not confirm cancellation.', 'Не удалось подтвердить отмену.', 'No se pudo confirmar la cancelación.'), 'تعذر تأكيد نتيجة المعالجة.': ('Could not confirm processing result.', 'Не удалось подтвердить результат обработки.', 'No se pudo confirmar el resultado del procesamiento.'), 'تحقق من Supabase قبل إعادة المحاولة.': ('Check Supabase before trying again.', 'Проверьте Supabase перед повторной попыткой.', 'Revisa Supabase antes de reintentar.'), 'انتهت صلاحية زر التأكيد؛ افتح الطلب مجددًا.': ('Confirmation expired; open the request again.', 'Подтверждение устарело; откройте заявку снова.', 'La confirmación caducó; abre la solicitud de nuevo.'), 'انتهى تأكيد الإلغاء.': ('Cancellation confirmation expired.', 'Срок подтверждения отмены истёк.', 'La confirmación de cancelación caducó.'), 'تم التراجع دون تغيير الطلب.': ('Went back without changing the request.', 'Возврат без изменения заявки.', 'Se volvió sin cambiar la solicitud.'), 'أرسل رابط فيديو الهدية.': ('Send the gift video URL.', 'Отправьте ссылку на видео с подарком.', 'Envía el enlace del vídeo de regalo.'), 'أرسل مقدار المكافأة، مثل 1.': ('Send the reward amount, for example 1.', 'Отправьте размер награды, например 1.', 'Envía el importe de la recompensa, por ejemplo 1.'), 'أرسل كود الهدية الجديد.': ('Send the new gift code.', 'Отправьте новый подарочный код.', 'Envía el nuevo código de regalo.'), 'أرسل الكود المطلوب.': ('Send the relevant code.', 'Отправьте нужный код.', 'Envía el código correspondiente.'), 'الكود غير صالح.': ('Invalid code.', 'Неверный код.', 'Código no válido.'), 'رابط الفيديو غير صالح.': ('Invalid video link.', 'Неверная ссылка на видео.', 'Enlace de vídeo no válido.'), 'بيانات الهدية ناقصة.': ('Gift details are incomplete.', 'Данные подарка неполные.', 'Faltan datos del regalo.'), 'أرسل رقمًا موجبًا.': ('Send a positive number.', 'Отправьте положительное число.', 'Envía un número positivo.'), 'تعذر إنشاء كود الهدية.': ('Could not create gift code.', 'Не удалось создать подарочный код.', 'No se pudo crear el código de regalo.'), 'لا توجد أكواد هدايا.': ('There are no gift codes.', 'Подарочных кодов нет.', 'No hay códigos de regalo.'), 'تعذر عرض الأكواد.': ('Could not display gift codes.', 'Не удалось показать подарочные коды.', 'No se pudieron mostrar los códigos.'), '✅ تم تغيير حالة الكود.': ('✅ Code status updated.', '✅ Статус кода изменён.', '✅ Estado del código actualizado.'), 'لم أجد هذا الكود.': ('Code not found.', 'Код не найден.', 'No se encontró el código.'), 'تعذر تغيير حالة الكود.': ('Could not update code status.', 'Не удалось изменить статус кода.', 'No se pudo cambiar el estado del código.'), '👑 لوحة سحوبات EN96': ('👑 EN96 withdrawal dashboard', '👑 Панель выводов EN96', '👑 Panel de retiros EN96'), 'لا تُرسل العملات مرتين. راجع كل طلب ورقم المعاملة.': ('Do not send coins twice. Verify each request and transaction ID.', 'Не отправляйте монеты дважды. Проверяйте заявки и хеши транзакций.', 'No envíes monedas dos veces. Verifica solicitudes e identificadores de transacción.'), '⚠️ تعذر تحميل لوحة السحوبات.': ('⚠️ Could not load withdrawal dashboard.', '⚠️ Не удалось загрузить панель выводов.', '⚠️ No se pudo cargar el panel de retiros.'), '⚠️ الطلب ليس قيد المعالجة.': ('⚠️ Request is not being processed.', '⚠️ Заявка не находится в обработке.', '⚠️ La solicitud no está en procesamiento.'), '⚠️ الطلب غير موجود أو لم يعد معلّقًا.': ('⚠️ Request not found or no longer pending.', '⚠️ Заявка не найдена или уже не ожидает.', '⚠️ La solicitud no existe o ya no está pendiente.'), '🛠️ إدارة الهدايا': ('🛠️ Manage gifts', '🛠️ Управление подарками', '🛠️ Administrar regalos')})

# ==========================================
# COMMON HELPERS
# ==========================================

def is_admin(user_id):
    return str(user_id) == ADMIN_ID


def is_private(message):
    return (
        message.chat.type == "private"
        and str(message.chat.id)
        == str(message.from_user.id)
    )


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
        log.exception("Registration error")
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

    return (
        result.data[0]
        if result.data
        else None
    )


def balance_for(profile_id):
    result = (
        db.table("balances")
        .select("available,reserved")
        .eq("user_id", profile_id)
        .limit(1)
        .execute()
    )

    return (
        result.data[0]
        if result.data
        else None
    )


def en96_number(value):
    try:
        return (
            f"{Decimal(str(value or 0)):,.7f}"
        )
    except Exception:
        return "0.0000000"


def valid_stellar_address(value):
    if not isinstance(value, str):
        return False

    return bool(
        re.fullmatch(
            r"G[A-Z2-7]{55}",
            value.strip().upper()
        )
    )


def parse_amount(value):
    try:
        value = (
            str(value)
            .strip()
            .replace(",", ".")
        )

        amount = Decimal(value)

        if not amount.is_finite():
            return None

        if amount < MIN_WITHDRAWAL:
            return None

        if amount > MAX_WITHDRAWAL:
            return None

        if amount != amount.quantize(EN96_STEP):
            return None

        return amount

    except (
        InvalidOperation,
        ValueError,
        TypeError
    ):
        return None


def clear_withdrawal_state(user_id):
    with WITHDRAWAL_LOCK:
        WITHDRAWAL_STATES.pop(
            str(user_id),
            None
        )


def get_withdrawal_state(user_id):
    with WITHDRAWAL_LOCK:
        return WITHDRAWAL_STATES.get(
            str(user_id)
        )


def set_withdrawal_state(user_id, state):
    with WITHDRAWAL_LOCK:
        WITHDRAWAL_STATES[
            str(user_id)
        ] = state


def wallet_support_keyboard():
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🪙 إنشاء / فتح محفظة LOBSTR",
            url=LOBSTR_URL
        )
    )

    return kb


# ==========================================
# ROYAL WEB APP
# ==========================================

def app_button(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "👑 افتح مملكة EN96 الملكية 🐻",
            web_app=WebAppInfo(
                url=ROYAL_APP_URL
            )
        )
    )

    bot.send_message(
        chat_id,
        "👑🐻 مرحبًا بك في EN96!\n\n"
        "⛏️ التعدين الافتراضي\n"
        "💰 المحفظة\n"
        "💸 طلبات السحب\n"
        "🎁 الهدايا والقبيلة\n"
        "📢 القناة الرسمية\n\n"
        "اضغط الزر للدخول.\n\n"
        "⚠️ النقر التجريبي على الدب "
        "لا يضيف رصيدًا حقيقيًا.",
        reply_markup=kb
    )


# ==========================================
# MAIN MENU
# ==========================================

def menu(user_id=None):
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    kb.row(
        KeyboardButton(local_button("⛏️ بدء التعدين", user_id)),
        KeyboardButton(local_button("💰 محفظتي", user_id))
    )

    kb.row(
        KeyboardButton(local_button("💸 سحب EN96", user_id)),
        KeyboardButton(local_button("📋 طلبات السحب", user_id))
    )

    kb.row(
        KeyboardButton(local_button("⚡ ترقية المنجم", user_id)),
        KeyboardButton(local_button("🏆 المكافآت", user_id))
    )

    kb.row(
        KeyboardButton(local_button("📺 مشاهدة الفيديوهات", user_id)),
        KeyboardButton(local_button("🎁 استلام الهدية", user_id))
    )

    kb.row(
        KeyboardButton(local_button("🎁 هدية 5 EN96", user_id))
    )

    kb.row(
        KeyboardButton(local_button("🐻 أعضاء القبيلة", user_id)),
        KeyboardButton(local_button("ℹ️ معلومات EN96", user_id))
    )

    kb.row(
        KeyboardButton(local_button("🎵 TikTok EN96", user_id)),
        KeyboardButton(local_button("▶️ YouTube EN96", user_id))
    )

    kb.row(KeyboardButton(local_button("🌐 تغيير اللغة", user_id)))

    # NEW CHANNEL BUTTON
    kb.row(
        KeyboardButton(local_button("📢 قناة EN96 الرسمية", user_id))
    )

    kb.row(
        KeyboardButton(local_button("🌐 فتح تطبيق EN96", user_id))
    )

    if (
        user_id is not None
        and is_admin(user_id)
    ):
        kb.row(
            KeyboardButton(local_button("🛠️ إدارة الهدايا", user_id)),
            KeyboardButton(
                local_button("⭐ رصيد Stars للإدارة", user_id)
            )
        )

        kb.row(
            KeyboardButton(local_button("👑 إدارة السحوبات", user_id))
        )

    return kb


def send_menu(
    chat_id,
    text="🐻 مرحبًا بك في EN96 Mining!",
    user_id=None
):
    if user_id is not None and text == MESSAGES["welcome"][0]:
        text = local_text("welcome", user_id)
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


def admin_menu(user_id=None):
    kb = ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    kb.row(
        KeyboardButton(local_button("➕ إنشاء كود هدية", user_id)),
        KeyboardButton(local_button("📋 أكواد الهدايا", user_id))
    )

    kb.row(
        KeyboardButton(local_button("⛔ تعطيل كود", user_id)),
        KeyboardButton(local_button("✅ تفعيل كود", user_id))
    )

    kb.row(
        KeyboardButton(local_button("🔙 القائمة الرئيسية", user_id))
    )

    return kb


# ==========================================
# STELLAR ACCOUNT VERIFICATION
# ==========================================

def stellar_account_info(address):
    """
    Public account lookup only.
    Does not sign transactions.
    Does not prove wallet ownership.
    """

    if not valid_stellar_address(address):
        return {
            "ok": False,
            "reason": "invalid_address"
        }

    endpoint = (
        f"{HORIZON_URL}/accounts/"
        f"{address.upper()}"
    )

    request = Request(
        endpoint,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96Bot/1.0"
        }
    )

    try:
        with urlopen(
            request,
            timeout=12
        ) as response:
            account = json.loads(
                response.read().decode("utf-8")
            )

    except HTTPError as exc:
        if exc.code == 404:
            return {
                "ok": False,
                "reason": "account_not_found"
            }

        log.warning(
            "Stellar HTTP error: %s",
            exc.code
        )

        return {
            "ok": False,
            "reason": "network_error"
        }

    except Exception:
        log.exception(
            "Stellar account lookup failed"
        )

        return {
            "ok": False,
            "reason": "network_error"
        }

    asset = None

    for item in account.get("balances", []):
        if (
            item.get("asset_code")
            == EN96_ASSET
            and item.get("asset_issuer")
            == EN96_ISSUER
        ):
            asset = item
            break

    return {
        "ok": True,
        "trustline": asset is not None,
        "asset_balance": (
            asset.get("balance")
            if asset
            else None
        )
    }


def stellar_error_text(reason):
    errors = {
        "invalid_address":
            "عنوان Stellar غير صالح.",

        "account_not_found":
            "الحساب غير مفعّل على Stellar Mainnet.",

        "network_error":
            "تعذر الاتصال بشبكة Stellar الآن."
    }

    return errors.get(
        reason,
        "تعذر التحقق من المحفظة."
    )


# ==========================================
# EN96 WALLET
# ==========================================

def wallet(chat_id, user_id):
    try:
        profile = profile_for(user_id)

        if not profile:
            bot.send_message(
                chat_id,
                "لم أجد حسابك. أرسل /start أولًا."
            )
            return

        balance = balance_for(
            profile["id"]
        )

        if not balance:
            bot.send_message(
                chat_id,
                "لم أجد سجل رصيدك."
            )
            return

        address = (
            profile.get(
                "stellar_public_address"
            ) or ""
        )

        kb = InlineKeyboardMarkup()

        kb.row(
            InlineKeyboardButton(
                "💸 طلب سحب EN96",
                callback_data="withdraw_start"
            ),
            InlineKeyboardButton(
                "🔗 ربط عنوان G",
                callback_data="wallet_link"
            )
        )

        kb.row(
            InlineKeyboardButton(
                "🛡️ فحص خط الثقة",
                callback_data="wallet_trustline"
            )
        )

        kb.row(
            InlineKeyboardButton(
                "🪙 إنشاء محفظة LOBSTR",
                url=LOBSTR_URL
            )
        )

        bot.send_message(
            chat_id,
            "🐻‍❄️👑 محفظة EN96\n"
            "━━━━━━━━━━━━━━\n\n"

            "🟢 الرصيد المتاح:\n"
            f"{en96_number(balance.get('available'))} EN96\n\n"

            "🟡 الرصيد المحجوز:\n"
            f"{en96_number(balance.get('reserved'))} EN96\n\n"

            "💸 الحد الأدنى للسحب: 500 EN96\n\n"

            "🔗 عنوان Stellar:\n"
            f"{address if address else 'غير مربوط'}\n\n"

            "📌 السحب إلى شبكة Stellar Mainnet.\n"
            "📌 إرسال العملات يتم يدويًا بعد المراجعة.\n"
            "⚠️ الرصيد داخل البوت ليس رصيد Stellar.",
            reply_markup=kb
        )

    except Exception:
        log.exception("Wallet error")

        bot.send_message(
            chat_id,
            "تعذر عرض المحفظة الآن."
        )


def start_wallet_link(chat_id, user_id):
    set_withdrawal_state(
        user_id,
        {"step": "link_address"}
    )

    bot.send_message(
        chat_id,
        "🔗 ربط محفظة Stellar\n\n"
        "افتح LOBSTR واختر Receive، "
        "ثم انسخ عنوانك العام الذي يبدأ بحرف G.\n\n"
        "أرسله هنا لحفظ عنوان الاستلام.\n\n"
        "⚠️ لا ترسل المفتاح السري أو كلمات الاسترداد.\n"
        "⚠️ حفظ العنوان لا يثبت ملكيته.",
        reply_markup=wallet_support_keyboard()
    )


def save_wallet_address(
    chat_id,
    user_id,
    address
):
    address = address.strip().upper()

    if not valid_stellar_address(address):
        bot.send_message(
            chat_id,
            "❌ عنوان G غير صالح.\n"
            "أرسل عنوان Stellar عامًا صحيحًا "
            "أو أرسل /cancel."
        )
        return

    try:
        profile = profile_for(user_id)

        if not profile:
            clear_withdrawal_state(user_id)

            bot.send_message(
                chat_id,
                "لم أجد حسابك. أرسل /start."
            )
            return

        existing = (
            db.table("withdrawal_requests")
            .select("id")
            .eq("user_id", profile["id"])
            .eq("status", "pending")
            .limit(1)
            .execute()
            .data or []
        )

        if existing:
            clear_withdrawal_state(user_id)

            bot.send_message(
                chat_id,
                "⚠️ لديك طلب سحب معلق.\n"
                "لا يمكن تغيير عنوان الاستلام "
                "أثناء مراجعة الطلب."
            )
            return

        db.table("profiles").update(
            {
                "stellar_public_address": address
            }
        ).eq(
            "id",
            profile["id"]
        ).execute()

        clear_withdrawal_state(user_id)

        bot.send_message(
            chat_id,
            "✅ تم حفظ عنوان Stellar في حساب EN96.\n\n"
            f"{address}\n\n"
            "🛡️ افحص خط الثقة قبل طلب السحب.\n\n"
            "⚠️ حفظ عنوان G لا يعني إثبات "
            "ملكية المحفظة.",
            reply_markup=menu(user_id)
        )

    except Exception:
        log.exception(
            "Save Stellar address error"
        )

        bot.send_message(
            chat_id,
            "تعذر حفظ العنوان الآن."
        )


def check_wallet_trustline(
    chat_id,
    user_id
):
    try:
        profile = profile_for(user_id)

        if not profile:
            bot.send_message(
                chat_id,
                "أرسل /start أولًا."
            )
            return

        address = (
            profile.get(
                "stellar_public_address"
            ) or ""
        )

        if not valid_stellar_address(address):
            bot.send_message(
                chat_id,
                "⚠️ لم تربط عنوان G بعد.\n"
                "افتح المحفظة واضغط ربط عنوان G.",
                reply_markup=wallet_support_keyboard()
            )
            return

        result = stellar_account_info(
            address
        )

        if not result["ok"]:
            bot.send_message(
                chat_id,
                "⚠️ " + stellar_error_text(
                    result["reason"]
                ),
                reply_markup=wallet_support_keyboard()
            )
            return

        if result["trustline"]:
            bot.send_message(
                chat_id,
                "✅ تم العثور على خط ثقة EN96!\n\n"
                "🌐 Stellar Mainnet\n"
                f"🪙 الأصل: {EN96_ASSET}\n\n"
                "💎 رصيد المحفظة على Stellar:\n"
                f"{result['asset_balance']} EN96\n\n"
                "⚠️ هذا فحص عام، وليس إثبات ملكية."
            )

        else:
            bot.send_message(
                chat_id,
                "⚠️ حساب Stellar موجود، "
                "لكن خط ثقة EN96 غير موجود.\n\n"
                "افتح LOBSTR ثم Add Asset.\n"
                "ابحث عن EN96 بالمُصدر:\n\n"
                f"{EN96_ISSUER}\n\n"
                "وافق على إضافة الأصل من المحفظة.",
                reply_markup=wallet_support_keyboard()
            )

    except Exception:
        log.exception(
            "Trustline check error"
        )

        bot.send_message(
            chat_id,
            "تعذر فحص خط الثقة."
        )


# ==========================================
# WITHDRAWAL - MEMBER
# ==========================================

def start_withdrawal(
    chat_id,
    user_id
):
    try:
        profile = profile_for(user_id)

        if not profile:
            bot.send_message(
                chat_id,
                "لم أجد حسابك.\nأرسل /start أولًا."
            )
            return

        balance = balance_for(
            profile["id"]
        )

        if not balance:
            bot.send_message(
                chat_id,
                "تعذر العثور على رصيدك."
            )
            return

        available = Decimal(
            str(
                balance.get("available")
                or 0
            )
        )

        address = (
            profile.get(
                "stellar_public_address"
            ) or ""
        )

        if available < MIN_WITHDRAWAL:
            bot.send_message(
                chat_id,
                "❌ الرصيد المتاح غير كافٍ.\n\n"
                f"رصيدك: {en96_number(available)} EN96\n"
                "الحد الأدنى: 500 EN96."
            )
            return

        existing = (
            db.table("withdrawal_requests")
            .select("id")
            .eq("user_id", profile["id"])
            .eq("status", "pending")
            .limit(1)
            .execute()
            .data or []
        )

        if existing:
            bot.send_message(
                chat_id,
                "⏳ لديك طلب سحب معلق بالفعل.\n"
                "افتح «📋 طلبات السحب» "
                "لمتابعة الطلب."
            )
            return

        if not valid_stellar_address(address):
            start_wallet_link(
                chat_id,
                user_id
            )
            return

        result = stellar_account_info(
            address
        )

        if not result["ok"]:
            bot.send_message(
                chat_id,
                "⚠️ لا يمكن بدء السحب.\n"
                + stellar_error_text(
                    result["reason"]
                )
            )
            return

        if not result["trustline"]:
            bot.send_message(
                chat_id,
                "⚠️ يجب إضافة خط ثقة EN96 "
                "إلى محفظتك أولًا.\n\n"
                f"المُصدر:\n{EN96_ISSUER}",
                reply_markup=wallet_support_keyboard()
            )
            return

        set_withdrawal_state(
            user_id,
            {
                "step": "amount",
                "address": address
            }
        )

        bot.send_message(
            chat_id,
            "💸 طلب سحب EN96\n"
            "━━━━━━━━━━━━━━\n\n"

            "🟢 الرصيد المتاح:\n"
            f"{en96_number(available)} EN96\n\n"

            "🟡 الحد الأدنى: 500 EN96\n\n"

            "🔗 عنوان الاستلام:\n"
            f"{address}\n\n"

            "✅ خط الثقة موجود.\n\n"

            "اكتب مبلغ السحب الآن.\n"
            "مثال: 500\n\n"

            "⚠️ تأكد أن هذا عنوان محفظتك."
        )

    except Exception:
        log.exception(
            "Start withdrawal error"
        )

        bot.send_message(
            chat_id,
            "تعذر بدء طلب السحب.\n"
            "لم يتم حجز رصيد جديد."
        )


def withdrawal_amount_input(
    chat_id,
    user_id,
    value
):
    amount = parse_amount(value)

    if amount is None:
        bot.send_message(
            chat_id,
            "❌ مبلغ غير صالح.\n\n"
            "الحد الأدنى: 500 EN96.\n"
            "أقصى دقة: 7 أرقام عشرية.\n\n"
            "أرسل المبلغ مجددًا أو /cancel."
        )
        return

    state = get_withdrawal_state(
        user_id
    )

    if (
        not state
        or state.get("step") != "amount"
    ):
        return

    address = state.get(
        "address",
        ""
    )

    if not valid_stellar_address(address):
        clear_withdrawal_state(user_id)

        bot.send_message(
            chat_id,
            "عنوان Stellar غير صالح."
        )
        return

    set_withdrawal_state(
        user_id,
        {
            "step": "confirm",
            "amount": str(amount),
            "address": address
        }
    )

    kb = InlineKeyboardMarkup()

    kb.row(
        InlineKeyboardButton(
            "✅ تأكيد طلب السحب",
            callback_data="withdraw_confirm"
        ),
        InlineKeyboardButton(
            "❌ تراجع",
            callback_data="withdraw_abort"
        )
    )

    bot.send_message(
        chat_id,
        "👑 تأكيد سحب EN96\n"
        "━━━━━━━━━━━━━━\n\n"

        f"💎 المبلغ: {en96_number(amount)} EN96\n\n"
        f"🔗 المحفظة:\n{address}\n\n"

        "عند التأكيد سيُنقل المبلغ "
        "من المتاح إلى المحجوز.\n\n"

        "⚠️ لن تُرسل العملات فورًا.\n"
        "سيُراجع الطلب قبل الإرسال اليدوي.\n\n"

        "تأكد من صحة العنوان.",
        reply_markup=kb
    )


def confirm_withdrawal(
    chat_id,
    user_id
):
    with WITHDRAWAL_LOCK:
        state = WITHDRAWAL_STATES.get(
            str(user_id)
        )

        if (
            not state
            or state.get("step") != "confirm"
        ):
            bot.send_message(
                chat_id,
                "لا يوجد طلب جاهز للتأكيد."
            )
            return

        WITHDRAWAL_STATES[
            str(user_id)
        ] = {
            **state,
            "step": "processing"
        }

    try:
        address = state["address"]
        amount = Decimal(
            state["amount"]
        )

        profile = profile_for(user_id)

        if not profile:
            raise ValueError(
                "Account not found"
            )

        if (
            profile.get(
                "stellar_public_address"
            ) != address
        ):
            raise ValueError(
                "Destination changed"
            )

        check = stellar_account_info(
            address
        )

        if not check["ok"]:
            raise ValueError(
                "Stellar verification unavailable"
            )

        if not check["trustline"]:
            raise ValueError(
                "EN96 trustline missing"
            )

        result = db.rpc(
            "en96_request_withdrawal",
            {
                "p_telegram_id": str(user_id),
                "p_amount": str(amount),
                "p_stellar_address": address
            }
        ).execute()

        request_id = result.data

        if isinstance(
            request_id,
            list
        ):
            request_id = (
                request_id[0]
                if request_id
                else None
            )

        if not request_id:
            raise ValueError(
                "Missing withdrawal request ID"
            )

        clear_withdrawal_state(user_id)

        bot.send_message(
            chat_id,
            "✅ تم تسجيل طلب السحب!\n"
            "━━━━━━━━━━━━━━\n\n"

            f"💎 المبلغ: {en96_number(amount)} EN96\n\n"

            "🟡 الحالة: قيد المراجعة\n"
            "🔒 تم حجز المبلغ في Supabase.\n\n"

            f"🆔 رقم الطلب:\n{request_id}\n\n"

            "📌 العملات لم تُرسل بعد.\n"
            "سيتولى المسؤول مراجعة الطلب.",
            reply_markup=menu(user_id)
        )

        try:
            bot.send_message(
                int(ADMIN_ID),
                "👑 طلب سحب EN96 جديد\n\n"
                f"👤 Telegram ID: {user_id}\n"
                f"💎 المبلغ: {en96_number(amount)} EN96\n\n"
                f"🔗 عنوان الاستلام:\n{address}\n\n"
                f"🆔 الطلب:\n{request_id}\n\n"
                "⚠️ لا ترسل العملات مرتين.\n"
                "افتح لوحة إدارة السحوبات."
            )

        except Exception:
            log.exception(
                "Admin notification error"
            )

    except Exception:
        clear_withdrawal_state(
            user_id
        )

        log.exception(
            "Withdrawal request failed"
        )

        bot.send_message(
            chat_id,
            "⚠️ لم يكتمل تأكيد طلب السحب.\n"
            "افتح «📋 طلبات السحب» "
            "وتحقق من وجود طلب معلق "
            "قبل المحاولة مجددًا.\n\n"
            "لم يتم إرسال أي عملات Stellar."
        )


def member_withdrawal_history(
    chat_id,
    user_id
):
    try:
        profile = profile_for(user_id)

        if not profile:
            bot.send_message(
                chat_id,
                "أرسل /start أولًا."
            )
            return

        rows = (
            db.table("withdrawal_requests")
            .select(
                "id,amount,status,"
                "stellar_public_address"
            )
            .eq("user_id", profile["id"])
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
                "📋 لا توجد طلبات سحب حتى الآن."
            )
            return

        labels = {
            "pending":
                "⏳ قيد المراجعة",

            "paid":
                "✅ مدفوع",

            "cancelled":
                "❌ ملغى",

            "processing":
                "🔄 قيد المعالجة"
        }

        lines = [
            "🐻‍❄️ طلبات سحب EN96",
            "━━━━━━━━━━━━━━"
        ]

        for row in rows:
            status = row.get(
                "status",
                "unknown"
            )

            lines.append(
                "\n"
                f"🆔 {row.get('id')}\n"
                f"💎 {en96_number(row.get('amount'))} EN96\n"
                f"{labels.get(status, status)}"
            )

        bot.send_message(
            chat_id,
            "\n".join(lines)
        )

    except Exception:
        log.exception(
            "Withdrawal history error"
        )

        bot.send_message(
            chat_id,
            "تعذر تحميل طلبات السحب."
        )


# ==========================================
# ADMIN WITHDRAWALS
# ==========================================

def admin_withdrawals(
    chat_id,
    user_id
):
    if (
        not is_admin(user_id)
        or str(chat_id) != str(user_id)
    ):
        return

    try:
        headings = (
            (
                "pending",
                "⏳ طلبات تنتظر المراجعة"
            ),
            (
                "processing",
                "🔄 طلبات تنتظر التحويل أو التأكيد"
            ),
            (
                "paid",
                "✅ آخر عمليات السحب المدفوعة"
            ),
        )

        bot.send_message(
            chat_id,
            "👑 لوحة سحوبات EN96\n"
            "الحد الأدنى: 500 EN96\n"
            "لا تُرسل العملات مرتين. "
            "راجع كل طلب ورقم المعاملة."
        )

        for status, heading in headings:
            rows = (
                db.table("withdrawal_requests")
                .select(
                    "id,user_id,amount,status,"
                    "transaction_hash,"
                    "stellar_public_address,created_at"
                )
                .eq("status", status)
                .order(
                    "created_at",
                    desc=(status == "paid")
                )
                .limit(10)
                .execute()
                .data or []
            )

            bot.send_message(
                chat_id,
                f"{heading}: {len(rows)}"
            )

            for item in rows:
                request_id = str(
                    item["id"]
                )

                members = (
                    db.table("profiles")
                    .select("telegram_id")
                    .eq(
                        "id",
                        item["user_id"]
                    )
                    .limit(1)
                    .execute()
                    .data or []
                )

                telegram_id = (
                    str(
                        members[0].get(
                            "telegram_id"
                        )
                    )
                    if members
                    else "غير معروف"
                )

                kb = InlineKeyboardMarkup()

                if status == "pending":
                    kb.add(
                        InlineKeyboardButton(
                            "👑 بدء معالجة السحب",
                            callback_data=(
                                "admin_proc:"
                                + request_id
                            )
                        )
                    )

                    kb.add(
                        InlineKeyboardButton(
                            "↩️ إلغاء قبل الدفع",
                            callback_data=(
                                "admin_cancel:"
                                + request_id
                            )
                        )
                    )

                if status == "processing":
                    kb.add(
                        InlineKeyboardButton(
                            "🔐 التحقق من الدفع برقم المعاملة",
                            callback_data=(
                                "admin_pay:"
                                + request_id
                            )
                        )
                    )

                if status != "paid":
                    kb.add(
                        InlineKeyboardButton(
                            "🔍 فحص محفظة المستلم",
                            callback_data=(
                                "admin_check:"
                                + request_id
                            )
                        )
                    )

                suffix = (
                    "\n🔗 معاملة Stellar: "
                    + item["transaction_hash"]
                    if item.get(
                        "transaction_hash"
                    )
                    else ""
                )

                bot.send_message(
                    chat_id,
                    f"👤 Telegram ID: {telegram_id}\n"
                    f"💎 {en96_number(item['amount'])} EN96\n"
                    f"📌 الحالة: {status}\n"
                    f"🏦 العنوان: "
                    f"{item['stellar_public_address']}\n"
                    f"🆔 الطلب: {request_id}{suffix}",
                    reply_markup=(
                        kb
                        if kb.keyboard
                        else None
                    )
                )

    except Exception:
        log.exception(
            "Admin withdrawals error"
        )

        bot.send_message(
            chat_id,
            "⚠️ تعذر تحميل لوحة السحوبات."
        )


# ==========================================
# STELLAR TRANSACTION VERIFICATION
# ==========================================

def en96_horizon_json(path):
    request = Request(
        HORIZON_URL.rstrip("/") + path,
        headers={
            "Accept": "application/json",
            "User-Agent": "EN96Bot/2.0"
        }
    )

    with urlopen(
        request,
        timeout=18
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def verify_en96_payment(
    tx_hash,
    order
):
    tx_hash = (
        str(tx_hash)
        .strip()
        .lower()
    )

    if not re.fullmatch(
        r"[0-9a-f]{64}",
        tx_hash
    ):
        raise ValueError(
            "رقم المعاملة يجب أن يكون "
            "64 حرفًا سداسيًا."
        )

    tx = en96_horizon_json(
        "/transactions/" + quote(
            tx_hash
        )
    )

    if (
        tx.get("hash", "").lower()
        != tx_hash
        or tx.get("successful")
        is not True
    ):
        raise ValueError(
            "المعاملة غير ناجحة "
            "أو لا تطابق الرقم."
        )

    if not tx.get("ledger"):
        raise ValueError(
            "لم تُؤكد المعاملة "
            "في دفتر Stellar."
        )

    operations = en96_horizon_json(
        "/transactions/"
        + quote(tx_hash)
        + "/operations?limit=200"
    )

    records = operations.get(
        "_embedded",
        {}
    ).get(
        "records",
        []
    )

    if (
        int(
            tx.get("operation_count")
            or 0
        ) != 1
        or len(records) != 1
    ):
        raise ValueError(
            "المعاملة تحتوي عمليات متعددة؛ "
            "تتطلب مراجعة يدوية."
        )

    op = records[0]

    if (
        op.get("type") != "payment"
        or op.get("transaction_successful")
        is not True
    ):
        raise ValueError(
            "المعاملة ليست تحويل "
            "EN96 عاديًا ناجحًا."
        )

    if (
        op.get("from")
        != EN96_PAYOUT_SOURCE
    ):
        raise ValueError(
            "حساب الإرسال غير معتمد "
            "في إعدادات EN96."
        )

    if (
        op.get("to")
        != order["stellar_public_address"]
    ):
        raise ValueError(
            "عنوان المستلم لا يطابق طلب السحب."
        )

    if (
        op.get("asset_code")
        != EN96_ASSET
        or op.get("asset_issuer")
        != EN96_ISSUER
    ):
        raise ValueError(
            "رمز EN96 أو عنوان المُصدر غير صحيح."
        )

    if (
        Decimal(
            str(
                op.get("amount", "0")
            )
        )
        != Decimal(
            str(order["amount"])
        )
    ):
        raise ValueError(
            "مبلغ المعاملة مختلف عن طلب السحب."
        )

    if (
        op.get(
            "transaction_hash",
            ""
        ).lower() != tx_hash
    ):
        raise ValueError(
            "عملية الدفع لا تطابق المعاملة المطلوبة."
        )

    return True


def admin_pay_prompt(
    chat_id,
    user_id,
    request_id
):
    if (
        not is_admin(user_id)
        or str(chat_id) != str(user_id)
    ):
        return

    try:
        orders = (
            db.table("withdrawal_requests")
            .select(
                "id,amount,status,"
                "stellar_public_address,"
                "transaction_hash"
            )
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data or []
        )

        if (
            not orders
            or orders[0]["status"]
            != "processing"
        ):
            bot.send_message(
                chat_id,
                "⚠️ الطلب ليس قيد المعالجة."
            )
            return

        ADMIN_PAY_HASH[
            str(user_id)
        ] = request_id

        bot.send_message(
            chat_id,
            "🔐 تأكيد دفع EN96\n\n"
            f"💎 المبلغ: "
            f"{en96_number(orders[0]['amount'])} EN96\n"
            f"🔗 المستلم: "
            f"{orders[0]['stellar_public_address']}\n"
            f"🆔 الطلب: {request_id}\n\n"
            "إذا كنت أرسلت العملات بالفعل "
            "من محفظة المخزون المعتمدة، "
            "أرسل رقم المعاملة "
            "Transaction Hash (64 حرفًا).\n"
            "للخروج أرسل /cancel. "
            "لا ترسل عملات مرة أخرى."
        )

    except Exception:
        log.exception(
            "Admin pay prompt error"
        )

        bot.send_message(
            chat_id,
            "تعذر فتح تأكيد الدفع."
        )


def admin_pay_input(message):
    uid = message.from_user.id

    if (
        not is_admin(uid)
        or not is_private(message)
    ):
        return

    request_id = ADMIN_PAY_HASH.pop(
        str(uid),
        None
    )

    if not request_id:
        return

    tx_hash = (
        message.text or ""
    ).strip().lower()

    if tx_hash == "/cancel":
        bot.send_message(
            message.chat.id,
            "تم التراجع دون تغيير الطلب."
        )
        return

    try:
        orders = (
            db.table("withdrawal_requests")
            .select(
                "id,amount,status,"
                "stellar_public_address,"
                "transaction_hash"
            )
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data or []
        )

        if (
            not orders
            or orders[0]["status"]
            != "processing"
        ):
            raise ValueError(
                "الطلب لم يعد قيد المعالجة."
            )

        if orders[0].get(
            "transaction_hash"
        ):
            raise ValueError(
                "هذا الطلب لديه رقم معاملة سابق."
            )

        verify_en96_payment(
            tx_hash,
            orders[0]
        )

        result = db.rpc(
            "en96_finalize_paid",
            {
                "p_request_id": request_id,
                "p_transaction_hash": tx_hash
            }
        ).execute()

        if result.data != "paid":
            raise RuntimeError(
                "نتيجة تسوية غير متوقعة."
            )

        bot.send_message(
            message.chat.id,
            "✅ تم التحقق من Stellar "
            "وتسجيل الطلب مدفوعًا.\n"
            f"🆔 {request_id}\n"
            f"🔗 {tx_hash}\n"
            "تم خصم المبلغ المحجوز مرة واحدة "
            "داخل Supabase."
        )

    except Exception as exc:
        log.exception(
            "Admin payment verification error"
        )

        bot.send_message(
            message.chat.id,
            f"⚠️ لم يتم تسجيل الدفع: "
            f"{str(exc)[:220]}\n"
            "تحقق من بيانات الطلب في Supabase "
            "قبل أي محاولة أخرى. "
            "لا ترسل العملات مرتين."
        )


def admin_check_withdrawal(
    chat_id,
    user_id,
    request_id
):
    if not is_admin(user_id):
        return

    try:
        rows = (
            db.table("withdrawal_requests")
            .select(
                "id,status,amount,"
                "stellar_public_address"
            )
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "الطلب غير موجود."
            )
            return

        item = rows[0]

        address = item[
            "stellar_public_address"
        ]

        result = stellar_account_info(
            address
        )

        if not result["ok"]:
            bot.send_message(
                chat_id,
                "⚠️ " + stellar_error_text(
                    result["reason"]
                )
            )
            return

        bot.send_message(
            chat_id,
            "🔍 فحص محفظة المستلم\n\n"
            f"🆔 الطلب: {request_id}\n"
            f"💎 المبلغ: "
            f"{en96_number(item['amount'])}\n\n"
            "🛡️ خط الثقة:\n"
            + (
                "✅ موجود"
                if result["trustline"]
                else "❌ غير موجود"
            )
            + "\n\n"
            "⚠️ فحص خط الثقة لا يثبت ملكية "
            "المحفظة أو اكتمال الدفع."
        )

    except Exception:
        log.exception(
            "Admin check withdrawal"
        )

        bot.send_message(
            chat_id,
            "تعذر فحص المحفظة."
        )


def admin_begin_processing_prompt(
    chat_id,
    user_id,
    request_id
):
    if (
        not is_admin(user_id)
        or str(chat_id) != str(user_id)
    ):
        return

    try:
        rows = (
            db.table("withdrawal_requests")
            .select(
                "id,amount,status,"
                "stellar_public_address"
            )
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data or []
        )

        if (
            not rows
            or rows[0]["status"]
            != "pending"
        ):
            bot.send_message(
                chat_id,
                "⚠️ الطلب غير موجود "
                "أو لم يعد معلّقًا."
            )
            return

        order = rows[0]

        ADMIN_PROCESS_CONFIRM[
            str(user_id)
        ] = str(order["id"])

        kb = InlineKeyboardMarkup()

        kb.row(
            InlineKeyboardButton(
                "✅ تأكيد بدء المعالجة",
                callback_data=(
                    "admin_proc_yes:"
                    + str(order["id"])
                )
            ),
            InlineKeyboardButton(
                "❌ تراجع",
                callback_data="admin_proc_no"
            )
        )

        bot.send_message(
            chat_id,
            "👑 مراجعة بدء معالجة السحب\n\n"
            f"🆔 الطلب: {order['id']}\n"
            f"💎 المبلغ: "
            f"{en96_number(order['amount'])} EN96\n\n"
            f"🔗 العنوان:\n"
            f"{order['stellar_public_address']}\n\n"
            "سيُحوّل الطلب إلى processing "
            "ويظل الرصيد محجوزًا.\n"
            "لن تُرسل عملات Stellar بهذا الزر.",
            reply_markup=kb
        )

    except Exception:
        log.exception(
            "Admin begin processing prompt error"
        )

        bot.send_message(
            chat_id,
            "تعذر فتح تأكيد المعالجة."
        )


def admin_begin_processing_execute(
    chat_id,
    user_id,
    request_id
):
    if (
        not is_admin(user_id)
        or str(chat_id) != str(user_id)
    ):
        return

    if (
        ADMIN_PROCESS_CONFIRM.pop(
            str(user_id),
            None
        ) != request_id
    ):
        bot.send_message(
            chat_id,
            "انتهت صلاحية زر التأكيد؛ "
            "افتح الطلب مجددًا."
        )
        return

    try:
        result = db.rpc(
            "en96_begin_withdrawal_processing",
            {
                "p_request_id": request_id
            }
        ).execute()

        if result.data != "processing":
            raise RuntimeError(
                "Unexpected processing RPC response"
            )

        bot.send_message(
            chat_id,
            "✅ بدأت معالجة طلب السحب.\n\n"
            f"🆔 {request_id}\n"
            "🔒 الحالة: processing\n"
            "💎 الرصيد ما زال محجوزًا.\n"
            "🪙 لم تُرسل أي عملات."
        )

    except Exception:
        log.exception(
            "Admin begin processing execute error"
        )

        bot.send_message(
            chat_id,
            "⚠️ تعذر تأكيد نتيجة المعالجة. "
            "تحقق من Supabase "
            "قبل إعادة المحاولة."
        )


def admin_cancel_prompt(
    chat_id,
    user_id,
    request_id
):
    if not is_admin(user_id):
        return

    try:
        rows = (
            db.table("withdrawal_requests")
            .select(
                "id,status,amount"
            )
            .eq("id", request_id)
            .limit(1)
            .execute()
            .data or []
        )

        if (
            not rows
            or rows[0]["status"]
            != "pending"
        ):
            bot.send_message(
                chat_id,
                "لا يمكن إلغاء هذا الطلب."
            )
            return

        ADMIN_CANCEL_CONFIRM[
            str(user_id)
        ] = request_id

        kb = InlineKeyboardMarkup()

        kb.row(
            InlineKeyboardButton(
                "✅ لم أرسل العملات، ألغِ الطلب",
                callback_data="admin_cancel_yes"
            ),
            InlineKeyboardButton(
                "❌ تراجع",
                callback_data="admin_cancel_no"
            )
        )

        bot.send_message(
            chat_id,
            "⚠️ تأكيد إلغاء سحب EN96\n\n"
            f"🆔 {request_id}\n"
            f"💎 {en96_number(rows[0]['amount'])} EN96\n\n"
            "لا توافق إلا إذا تأكدت أنك "
            "لم ترسل العملات ولم تبدأ "
            "عملية تحويل قد تكتمل لاحقًا.\n\n"
            "سيعود المبلغ إلى رصيد العضو المتاح.",
            reply_markup=kb
        )

    except Exception:
        log.exception(
            "Admin cancel prompt error"
        )

        bot.send_message(
            chat_id,
            "تعذر فتح تأكيد الإلغاء."
        )


def admin_cancel_execute(
    chat_id,
    user_id
):
    if not is_admin(user_id):
        return

    request_id = ADMIN_CANCEL_CONFIRM.pop(
        str(user_id),
        None
    )

    if not request_id:
        bot.send_message(
            chat_id,
            "انتهى تأكيد الإلغاء."
        )
        return

    try:
        result = db.rpc(
            "en96_cancel_withdrawal",
            {
                "p_request_id": request_id
            }
        ).execute()

        if result.data != "cancelled":
            raise ValueError(
                "Unexpected cancellation response"
            )

        bot.send_message(
            chat_id,
            "✅ أُلغي طلب السحب.\n"
            "✅ أعادت Supabase المبلغ "
            "من المحجوز إلى المتاح.\n\n"
            f"🆔 {request_id}"
        )

    except Exception:
        log.exception(
            "Cancel withdrawal failed"
        )

        bot.send_message(
            chat_id,
            "⚠️ تعذر تأكيد الإلغاء.\n"
            "تحقق من حالة الطلب في Supabase."
        )


# ==========================================
# MINING
# ==========================================

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
    key = (
        chat_id,
        str(user_id)
    )

    with MINING_LOCK:
        previous = MINING_COUNTERS.get(
            key
        )

        if previous:
            previous.set()

        stop_event = threading.Event()

        MINING_COUNTERS[
            key
        ] = stop_event

    elapsed_before = max(
        0,
        min(
            int(elapsed_before),
            MINING_DURATION
        )
    )

    started = (
        time.time()
        - elapsed_before
    )

    try:
        msg = bot.send_message(
            chat_id,
            "🐻👑 منجم EN96\n\n"
            "⛏️ التعدين الافتراضي نشط.\n"
            "⚡ 0.001 EN96/ثانية\n"
            "⏱️ الجلسة: 24 ساعة\n\n"
            "العداد تقديري "
            "والرصيد تحدده Supabase.",
            reply_markup=mining_keyboard()
        )

    except Exception:
        log.exception(
            "Counter send error"
        )

        with MINING_LOCK:
            if (
                MINING_COUNTERS.get(key)
                is stop_event
            ):
                MINING_COUNTERS.pop(
                    key,
                    None
                )

        return

    def update():
        nonlocal started

        try:
            while not stop_event.is_set():
                elapsed = min(
                    max(
                        0,
                        int(
                            time.time()
                            - started
                        )
                    ),
                    MINING_DURATION
                )

                estimate = (
                    elapsed * MINING_RATE
                )

                hours, rest = divmod(
                    elapsed,
                    3600
                )

                minutes, seconds = divmod(
                    rest,
                    60
                )

                content = (
                    "🐻👑 منجم EN96\n\n"
                    "⛏️ التعدين الافتراضي نشط\n\n"

                    "💎 المكافأة التقديرية:\n"
                    f"{estimate:.7f} EN96\n\n"

                    "⏱️ الوقت:\n"
                    f"{hours:02d}:"
                    f"{minutes:02d}:"
                    f"{seconds:02d} / 24:00:00\n\n"

                    "⚡ 0.001 EN96/ثانية\n\n"

                    "⚠️ الرصيد الفعلي "
                    "محفوظ في Supabase."
                )

                try:
                    bot.edit_message_text(
                        content,
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
                        data = rpc_data(
                            db.rpc(
                                "en96_mining_action",
                                {
                                    "p_telegram_id":
                                        str(user_id)
                                }
                            ).execute()
                        )

                        status = data.get(
                            "status"
                        )

                        if (
                            status
                            == "rewarded_and_started"
                        ):
                            bot.send_message(
                                chat_id,
                                "✅ أكدت Supabase إضافة "
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
                            "⚠️ لم يتم تأكيد المكافأة.\n"
                            "اضغط بدء التعدين للتحقق."
                        )

                        break

                    except Exception:
                        log.exception(
                            "Mining settlement error"
                        )

                        break

                if stop_event.wait(5):
                    break

        finally:
            with MINING_LOCK:
                if (
                    MINING_COUNTERS.get(key)
                    is stop_event
                ):
                    MINING_COUNTERS.pop(
                        key,
                        None
                    )

    threading.Thread(
        target=update,
        daemon=True
    ).start()


def mining(
    chat_id,
    user_id
):
    try:
        if not profile_for(user_id):
            bot.send_message(
                chat_id,
                "لم أجد حسابك. "
                "أرسل /start أولًا."
            )

            return

        data = rpc_data(
            db.rpc(
                "en96_mining_action",
                {
                    "p_telegram_id":
                        str(user_id)
                }
            ).execute()
        )

        status = data.get(
            "status"
        )

        if status in (
            "started",
            "rewarded_and_started"
        ):
            if (
                status
                == "rewarded_and_started"
            ):
                bot.send_message(
                    chat_id,
                    "✅ تم إضافة مكافأة "
                    "الجلسة السابقة وبدء جلسة جديدة."
                )

            mining_counter(
                chat_id,
                user_id,
                elapsed_before=0
            )

            return

        if status == "active":
            remaining = int(
                data.get(
                    "remaining_seconds",
                    MINING_DURATION
                )
            )

            elapsed = max(
                0,
                MINING_DURATION - remaining
            )

            mining_counter(
                chat_id,
                user_id,
                elapsed_before=elapsed
            )

            return

        bot.send_message(
            chat_id,
            "⚠️ لم تؤكد Supabase "
            "عملية التعدين.\n"
            f"الحالة: "
            f"{status or 'غير معروفة'}"
        )

    except Exception:
        log.exception(
            "Mining error"
        )

        bot.send_message(
            chat_id,
            "تعذر تشغيل التعدين الآن."
        )


# ==========================================
# REFERRALS AND TRIBE
# ==========================================

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

    if (
        parts[0].split("@")[0]
        != "/start"
    ):
        return

    payload = parts[1].strip()

    if not payload.startswith("ref_"):
        return

    referrer = payload[4:]

    new_user = str(
        message.from_user.id
    )

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
                "p_referrer_telegram_id":
                    referrer
            }
        ).execute()

        data = rpc_data(result)

        if (
            data.get("status")
            == "registered"
        ):
            bot.send_message(
                message.chat.id,
                "🎉 تم تسجيل دعوتك في قبيلة EN96!"
            )

    except Exception:
        log.exception(
            "Referral error"
        )


def tribe(
    chat_id,
    user_id
):
    link = referral_link(user_id)

    try:
        data = rpc_data(
            db.rpc(
                "en96_tribe_stats",
                {
                    "p_telegram_id":
                        str(user_id)
                }
            ).execute()
        )

        if (
            data.get("status")
            == "profile_missing"
        ):
            bot.send_message(
                chat_id,
                "لم أجد حسابك. "
                "أرسل /start أولًا."
            )
            return

        if data.get("status") != "ok":
            raise ValueError(
                "Unexpected tribe response"
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
            "🐻👑 قبيلة EN96\n"
            "━━━━━━━━━━━━━━\n\n"

            f"👥 عدد الأصدقاء: {friends}\n\n"

            "🎁 مكافآت الدعوات:\n"
            f"{invitation_bonus} EN96\n\n"

            "⛏️ عمولات تعدين الأصدقاء 5%:\n"
            f"{commission} EN96\n\n"

            "💎 مجموع مكافآت القبيلة:\n"
            f"{total} EN96\n\n"

            "🔗 رابط دعوتك:\n"
            f"{link}\n\n"

            "🎁 50 EN96 عند اكتمال "
            "أول جلسة مؤهلة للصديق.\n"

            "⛏️ 5% من مكافآت تعدين "
            "الأصدقاء المباشرين المؤكدة.\n\n"

            "⚠️ المكافآت حسب سجلات Supabase.",
            disable_web_page_preview=True
        )

    except Exception:
        log.exception(
            "Tribe stats error"
        )

        bot.send_message(
            chat_id,
            "🐻👑 قبيلة EN96\n\n"
            "تعذر تحميل الإحصائيات الآن.\n"
            f"رابط دعوتك:\n{link}",
            disable_web_page_preview=True
        )


# ==========================================
# ONE-TIME 5 EN96 GIFT
# ==========================================

def claim_gift5(
    chat_id,
    user_id
):
    if (
        str(chat_id)
        != str(user_id)
    ):
        return

    if not register_member(user_id):
        bot.send_message(
            chat_id,
            "⚠️ تعذر تسجيل حسابك. "
            "أرسل /start لاحقًا."
        )

        return

    try:
        data = rpc_data(
            db.rpc(
                "en96_claim_gift5",
                {
                    "p_telegram_id":
                        str(user_id)
                }
            ).execute()
        )

        state = data.get("status")

        if state == "claimed":
            bot.send_message(
                chat_id,
                "🎁 مبروك! أضفنا 5 EN96 "
                "إلى رصيدك المتاح في Supabase.\n"
                "يمكنك رؤية الرصيد "
                "من زر 💰 محفظتي."
            )

        elif state == "already_claimed":
            bot.send_message(
                chat_id,
                "✅ لقد استلمت هدية 5 EN96 سابقًا. "
                "الهدية مرة واحدة لكل حساب."
            )

        elif state == "profile_missing":
            bot.send_message(
                chat_id,
                "⚠️ لم نجد حسابك. "
                "أرسل /start أولًا."
            )

        else:
            bot.send_message(
                chat_id,
                "⚠️ تعذر المطالبة الآن. "
                "لم تتم إضافة مكافأة جديدة."
            )

    except Exception:
        log.exception(
            "Claim EN96 gift5 failed"
        )

        bot.send_message(
            chat_id,
            "⚠️ فشل تسجيل الهدية مؤقتًا. "
            "حاول لاحقًا ولا تكرر الضغط بسرعة."
        )


# ==========================================
# VIDEO GIFTS
# ==========================================

def redeem_gift(message):
    uid = message.from_user.id

    code = (
        message.text or ""
    ).strip()

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
                "🎁 تم استلام "
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
                "استعملت هذا الكود من قبل.",

            "cooldown_2_hours":
                "انتظر ساعتين قبل هدية أخرى.",

            "balance_not_found":
                "لم أجد سجل رصيدك."
        }

        bot.send_message(
            message.chat.id,
            errors.get(
                reason,
                f"تعذر استلام الهدية: "
                f"{reason}"
            )
        )

    except Exception:
        log.exception(
            "Redeem gift error"
        )

        bot.send_message(
            message.chat.id,
            "تعذر التحقق من كود الهدية."
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
                "لا توجد فيديوهات هدايا حاليًا."
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
        log.exception(
            "Show videos error"
        )

        bot.send_message(
            chat_id,
            "تعذر تحميل الفيديوهات."
        )


# ==========================================
# ADMIN GIFTS
# ==========================================

def admin_create_code(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    code = (
        message.text or ""
    ).strip()

    WAITING_ADMIN_CODE.discard(uid)

    if (
        not code
        or len(code) > 120
    ):
        bot.send_message(
            message.chat.id,
            "الكود غير صالح."
        )

        return

    PENDING[uid] = {
        "code": code
    }

    WAITING_ADMIN_VIDEO.add(uid)

    bot.send_message(
        message.chat.id,
        "أرسل رابط فيديو الهدية."
    )


def admin_video(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    url = (
        message.text or ""
    ).strip()

    if not url.startswith(
        ("https://", "http://")
    ):
        bot.send_message(
            message.chat.id,
            "رابط الفيديو غير صالح."
        )

        return

    PENDING.setdefault(
        uid,
        {}
    )["video_url"] = url

    WAITING_ADMIN_VIDEO.discard(uid)
    WAITING_ADMIN_REWARD.add(uid)

    bot.send_message(
        message.chat.id,
        "أرسل مقدار المكافأة، مثل 1."
    )


def admin_reward(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

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

    item = PENDING.get(
        uid,
        {}
    )

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
        db.table(
            "video_gift_codes"
        ).insert(
            {
                "code": item["code"],
                "video_url": item["video_url"],
                "reward": reward,
                "active": True,
                "description":
                    "EN96 admin gift"
            }
        ).execute()

        bot.send_message(
            message.chat.id,
            "✅ تم إنشاء الكود "
            f"{item['code']} "
            f"بمكافأة {reward:g} EN96."
        )

    except Exception:
        log.exception(
            "Create gift error"
        )

        bot.send_message(
            message.chat.id,
            "تعذر إنشاء كود الهدية."
        )

    finally:
        WAITING_ADMIN_REWARD.discard(uid)
        PENDING.pop(uid, None)


def list_gifts(chat_id):
    try:
        rows = (
            db.table("video_gift_codes")
            .select(
                "id,code,reward,active"
            )
            .order(
                "created_at",
                desc=True
            )
            .limit(20)
            .execute()
            .data or []
        )

        if not rows:
            bot.send_message(
                chat_id,
                "لا توجد أكواد هدايا."
            )
            return

        lines = [
            "📋 أكواد هدايا EN96:"
        ]

        for row in rows:
            status = (
                "مفعل"
                if row.get("active")
                else "معطل"
            )

            lines.append(
                f"{row.get('code')} | "
                f"{row.get('reward')} EN96 | "
                f"{status}"
            )

        bot.send_message(
            chat_id,
            "\n".join(lines)
        )

    except Exception:
        log.exception(
            "List gifts error"
        )

        bot.send_message(
            chat_id,
            "تعذر عرض الأكواد."
        )


def set_gift_active(
    message,
    active
):
    if not is_admin(
        message.from_user.id
    ):
        return

    code = (
        message.text or ""
    ).strip()

    try:
        result = (
            db.table("video_gift_codes")
            .update({
                "active": active
            })
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
        log.exception(
            "Gift toggle error"
        )

        bot.send_message(
            message.chat.id,
            "تعذر تغيير حالة الكود."
        )


# ==========================================
# SOCIAL LINKS
# ==========================================

def show_social(chat_id):
    kb = InlineKeyboardMarkup()

    kb.row(
        InlineKeyboardButton(
            "▶️ YouTube EN96",
            url=YOUTUBE_URL
        ),
        InlineKeyboardButton(
            "🎵 TikTok EN96",
            url=TIKTOK_URL
        )
    )

    kb.add(
        InlineKeyboardButton(
            "📢 قناة EN96 الرسمية",
            url=TELEGRAM_CHANNEL_URL
        )
    )

    bot.send_message(
        chat_id,
        "🐻👑 مجتمع EN96 الرسمي\n\n"

        "▶️ شاهد فيديوهات YouTube.\n"
        "🎵 تابع فيديوهات TikTok.\n"
        "📢 تابع أخبار المملكة عبر Telegram.\n"
        "🎁 ابحث عن أكواد الهدايا.\n\n"

        "يمكنك إدخال الأكواد الصحيحة "
        "داخل بوت EN96.",
        reply_markup=kb
    )


def show_tiktok(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "🎵 فتح TikTok الرسمي",
            url=TIKTOK_URL
        )
    )

    bot.send_message(
        chat_id,
        "🎵 TikTok الرسمي لمشروع EN96\n\n"
        "@en96mining",
        reply_markup=kb
    )


def show_youtube(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "▶️ فتح قناة YouTube",
            url=YOUTUBE_URL
        )
    )

    bot.send_message(
        chat_id,
        "▶️ قناة YouTube الرسمية لـ EN96\n\n"
        "@EN96_Gold_Miner_bot",
        reply_markup=kb
    )


# ==========================================
# OFFICIAL TELEGRAM CHANNEL - NEW
# ==========================================

def show_telegram_channel(chat_id):
    kb = InlineKeyboardMarkup()

    kb.add(
        InlineKeyboardButton(
            "📢 افتح قناة EN96 الرسمية",
            url=TELEGRAM_CHANNEL_URL
        )
    )

    bot.send_message(
        chat_id,
        "🐻‍❄️👑 قناة EN96 Ice Bear Kingdom\n"
        "━━━━━━━━━━━━━━\n\n"

        "📢 تابع أخبار المملكة الرسمية.\n"
        "🎁 تعرف على الهدايا والمكافآت.\n"
        "🌍 تابع تطور مشروع EN96.\n\n"

        "اضغط الزر أدناه لفتح القناة.\n\n"
        f"{TELEGRAM_CHANNEL_URL}",
        reply_markup=kb,
        disable_web_page_preview=True
    )


# ==========================================
# TELEGRAM STARS - ADMIN ONLY
# ==========================================

def admin_stars_balance(
    chat_id,
    user_id,
    chat_type="private"
):
    if (
        not is_admin(user_id)
        or chat_type != "private"
        or str(chat_id) != str(user_id)
    ):
        bot.send_message(
            chat_id,
            "🔒 هذا القسم خاص بإدارة EN96."
        )
        return

    try:
        endpoint = (
            "https://api.telegram.org/"
            f"bot{BOT_TOKEN}/getMyStarBalance"
        )

        request = Request(
            endpoint,
            data=b"{}",
            headers={
                "Content-Type":
                    "application/json"
            },
            method="POST"
        )

        with urlopen(
            request,
            timeout=15
        ) as response:
            payload = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        if not payload.get("ok"):
            raise RuntimeError(
                "Telegram rejected getMyStarBalance"
            )

        result = payload.get(
            "result"
        ) or {}

        whole = int(
            result.get("amount", 0)
        )

        nano = int(
            result.get(
                "nanostar_amount",
                0
            )
        )

        amount = (
            whole
            + nano / 1_000_000_000
        )

        bot.send_message(
            chat_id,
            "👑 إدارة مملكة EN96\n"
            "━━━━━━━━━━━━━━\n\n"

            "⭐ رصيد نجوم البوت\n\n"

            f"💎 {amount:,.9f} Stars\n\n"

            "ℹ️ هذا رصيد Stars الخاص بالبوت، "
            "وليس رصيد حسابك الشخصي.\n\n"

            "⚠️ الرصيد لا يضمن أهلية السحب "
            "عبر Fragment."
        )

    except Exception:
        log.exception(
            "Stars balance error"
        )

        bot.send_message(
            chat_id,
            "⚠️ تعذر الحصول على رصيد Stars.\n"
            "تحقق من Render وحاول مجددًا."
        )


# ==========================================
# BOT COMMANDS
# ==========================================

@bot.message_handler(
    commands=["start", "menu"]
)
def start(message):
    if not is_private(message):
        bot.reply_to(
            message,
            "افتح EN96 في محادثة خاصة."
        )
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    get_language(uid, getattr(message.from_user, "language_code", None))
    clear_withdrawal_state(uid)

    if not register_member(uid):
        bot.send_message(
            chat_id,
            "⚠️ تعذر تأكيد حسابك.\n"
            "حاول لاحقًا."
        )
        return

    parts = (
        (message.text or "")
        .strip()
        .split(maxsplit=1)
    )

    command = (
        parts[0].split("@")[0]
        if parts
        else ""
    )

    payload = (
        parts[1].strip()
        if len(parts) == 2
        else ""
    )

    if (
        command == "/start"
        and payload == "mining"
    ):
        mining(
            chat_id,
            uid
        )
        return

    if (
        command == "/start"
        and payload.startswith("ref_")
    ):
        record_referral(message)

    send_menu(
        chat_id,
        local_text("welcome", uid),
        user_id=uid
    )


@bot.message_handler(
    commands=["cancel"]
)
def cancel_command(message):
    if not is_private(message):
        return

    uid = message.from_user.id

    clear_withdrawal_state(uid)

    WAITING_GIFT.discard(uid)
    WAITING_ADMIN_CODE.discard(uid)
    WAITING_ADMIN_VIDEO.discard(uid)
    WAITING_ADMIN_REWARD.discard(uid)

    ADMIN_ACTION.pop(uid, None)
    PENDING.pop(uid, None)

    ADMIN_PAY_HASH.pop(
        str(uid),
        None
    )

    ADMIN_PROCESS_CONFIRM.pop(
        str(uid),
        None
    )

    ADMIN_CANCEL_CONFIRM.pop(
        str(uid),
        None
    )

    bot.send_message(
        message.chat.id,
        "✅ تم إلغاء الإدخال الجاري.\n"
        "لم يتم إلغاء أي طلب سحب "
        "مسجل في Supabase.",
        reply_markup=menu(uid)
    )


@bot.message_handler(
    commands=["wallet"]
)
def wallet_command(message):
    if is_private(message):
        wallet(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(
    commands=["withdraw"]
)
def withdraw_command(message):
    if is_private(message):
        start_withdrawal(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(
    commands=["withdrawals"]
)
def withdrawals_command(message):
    if is_private(message):
        member_withdrawal_history(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(
    commands=["mining"]
)
def mining_command(message):
    if is_private(message):
        mining(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(
    commands=["tribe"]
)
def tribe_command(message):
    if is_private(message):
        tribe(
            message.chat.id,
            message.from_user.id
        )


@bot.message_handler(
    commands=["stars"]
)
def stars_command(message):
    admin_stars_balance(
        message.chat.id,
        message.from_user.id,
        message.chat.type
    )


@bot.message_handler(
    commands=["tiktok"]
)
def tiktok_command(message):
    if is_private(message):
        show_tiktok(
            message.chat.id
        )


@bot.message_handler(
    commands=["youtube"]
)
def youtube_command(message):
    if is_private(message):
        show_youtube(
            message.chat.id
        )


# NEW CHANNEL COMMAND
@bot.message_handler(
    commands=["channel"]
)
def channel_command(message):
    if is_private(message):
        show_telegram_channel(
            message.chat.id
        )


@bot.message_handler(commands=["language", "lang"])
def language_command(message):
    if is_private(message):
        choose_language(message.chat.id, message.from_user.id)


@bot.message_handler(
    commands=["admin"]
)
def admin_command(message):
    if (
        is_private(message)
        and is_admin(
            message.from_user.id
        )
    ):
        admin_withdrawals(
            message.chat.id,
            message.from_user.id
        )
    else:
        bot.send_message(
            message.chat.id,
            "هذا الأمر مخصص للمسؤول."
        )


# ==========================================
# INLINE BUTTON HANDLER
# ==========================================

@bot.callback_query_handler(
    func=lambda call: True
)
def callback_handler(call):
    uid = call.from_user.id

    if (
        not call.message
        or call.message.chat.type
        != "private"
    ):
        return

    chat_id = call.message.chat.id
    data = call.data or ""

    try:
        bot.answer_callback_query(
            call.id
        )
    except Exception:
        pass

    if (
        str(chat_id)
        != str(uid)
    ):
        return

    try:
        if data.startswith("lang:"):
            new_lang = data.split(":", 1)[1]
            if new_lang not in LANGUAGES:
                return
            try:
                save_language(uid, new_lang)
            except Exception:
                log.exception("EN96 language update failed")
                bot.send_message(chat_id, "⚠️ Could not save language. Try again.")
                return
            send_menu(chat_id, local_text("saved", uid), user_id=uid)

        elif data == "mining_refresh":
            mining(
                chat_id,
                uid
            )

        elif data == "gift5_claim":
            claim_gift5(
                chat_id,
                uid
            )

        elif data == "withdraw_start":
            start_withdrawal(
                chat_id,
                uid
            )

        elif data == "wallet_link":
            start_wallet_link(
                chat_id,
                uid
            )

        elif data == "wallet_trustline":
            check_wallet_trustline(
                chat_id,
                uid
            )

        elif data == "withdraw_abort":
            clear_withdrawal_state(uid)

            bot.send_message(
                chat_id,
                "✅ تراجعت عن طلب السحب.\n"
                "لم يتم حجز مبلغ جديد."
            )

        elif data == "withdraw_confirm":
            confirm_withdrawal(
                chat_id,
                uid
            )

        elif (
            data.startswith("admin_pay:")
            and is_admin(uid)
        ):
            admin_pay_prompt(
                chat_id,
                uid,
                data.split(":", 1)[1]
            )

        elif (
            data.startswith("admin_proc:")
            and is_admin(uid)
        ):
            admin_begin_processing_prompt(
                chat_id,
                uid,
                data.split(":", 1)[1]
            )

        elif (
            data.startswith("admin_proc_yes:")
            and is_admin(uid)
        ):
            admin_begin_processing_execute(
                chat_id,
                uid,
                data.split(":", 1)[1]
            )

        elif (
            data == "admin_proc_no"
            and is_admin(uid)
        ):
            ADMIN_PROCESS_CONFIRM.pop(
                str(uid),
                None
            )

            bot.send_message(
                chat_id,
                "✅ تراجعت. لم يتغير الطلب."
            )

        elif (
            data.startswith("admin_check:")
            and is_admin(uid)
        ):
            admin_check_withdrawal(
                chat_id,
                uid,
                data.split(":", 1)[1]
            )

        elif (
            data.startswith("admin_cancel:")
            and is_admin(uid)
        ):
            admin_cancel_prompt(
                chat_id,
                uid,
                data.split(":", 1)[1]
            )

        elif (
            data == "admin_cancel_yes"
            and is_admin(uid)
        ):
            admin_cancel_execute(
                chat_id,
                uid
            )

        elif (
            data == "admin_cancel_no"
            and is_admin(uid)
        ):
            ADMIN_CANCEL_CONFIRM.pop(
                str(uid),
                None
            )

            bot.send_message(
                chat_id,
                "✅ لم يتم إلغاء الطلب."
            )

    except Exception:
        log.exception(
            "Callback handler error"
        )

        bot.send_message(
            chat_id,
            "⚠️ تعذر تنفيذ الأمر الآن."
        )


# ==========================================
# INPUT HANDLERS
# ==========================================

@bot.message_handler(
    func=lambda m: (
        is_private(m) and
        BUTTON_CANONICAL.get((m.text or "").strip()) == "🌐 تغيير اللغة"
    ),
    content_types=["text"]
)
def language_button_handler(message):
    choose_language(message.chat.id, message.from_user.id)



@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id
        in WAITING_GIFT
    ),
    content_types=["text"]
)
def gift_input(message):
    redeem_gift(message)


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id
        in WAITING_ADMIN_CODE
        and ADMIN_ACTION.get(
            m.from_user.id
        ) in ("enable", "disable")
    ),
    content_types=["text"]
)
def admin_toggle_input(message):
    uid = message.from_user.id

    if not is_admin(uid):
        return

    action = ADMIN_ACTION.pop(
        uid,
        None
    )

    WAITING_ADMIN_CODE.discard(uid)

    set_gift_active(
        message,
        active=(action == "enable")
    )


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id
        in WAITING_ADMIN_CODE
    ),
    content_types=["text"]
)
def admin_code_input(message):
    if is_admin(
        message.from_user.id
    ):
        admin_create_code(message)


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id
        in WAITING_ADMIN_VIDEO
    ),
    content_types=["text"]
)
def admin_video_input(message):
    if is_admin(
        message.from_user.id
    ):
        admin_video(message)


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and m.from_user.id
        in WAITING_ADMIN_REWARD
    ),
    content_types=["text"]
)
def admin_reward_input(message):
    if is_admin(
        message.from_user.id
    ):
        admin_reward(message)


@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and is_admin(m.from_user.id)
        and str(m.from_user.id)
        in ADMIN_PAY_HASH
    ),
    content_types=["text"]
)
def admin_payment_hash_handler(message):
    admin_pay_input(message)


# ==========================================
# WITHDRAWAL TEXT INPUT
# ==========================================

@bot.message_handler(
    func=lambda m: (
        is_private(m)
        and get_withdrawal_state(
            m.from_user.id
        ) is not None
    ),
    content_types=["text"]
)
def withdrawal_input(message):
    uid = message.from_user.id
    chat_id = message.chat.id

    state = get_withdrawal_state(uid)

    if not state:
        return

    step = state.get("step")

    text_value = (
        message.text or ""
    ).strip()

    if step == "link_address":
        save_wallet_address(
            chat_id,
            uid,
            text_value
        )

    elif step == "amount":
        withdrawal_amount_input(
            chat_id,
            uid,
            text_value
        )

    elif step == "confirm":
        bot.send_message(
            chat_id,
            "اضغط زر تأكيد السحب "
            "أو تراجع من الرسالة السابقة."
        )

    elif step == "processing":
        bot.send_message(
            chat_id,
            "⏳ طلبك قيد المعالجة.\n"
            "تحقق من طلبات السحب."
        )


# ==========================================
# MAIN MENU HANDLER
# ==========================================

@bot.message_handler(
    content_types=["text"]
)
def menu_handler(message):
    if not is_private(message):
        return

    text_value = (
        message.text or ""
    ).strip()

    uid = message.from_user.id
    chat_id = message.chat.id
    text_value = BUTTON_CANONICAL.get(text_value, text_value)

    if text_value == "🌐 تغيير اللغة":
        choose_language(chat_id, uid)

    elif text_value == "⛏️ بدء التعدين":
        mining(
            chat_id,
            uid
        )

    elif text_value == "🎁 هدية 5 EN96":
        claim_gift5(
            chat_id,
            uid
        )

    elif text_value == "💰 محفظتي":
        wallet(
            chat_id,
            uid
        )

    elif text_value == "💸 سحب EN96":
        start_withdrawal(
            chat_id,
            uid
        )

    elif text_value == "📋 طلبات السحب":
        member_withdrawal_history(
            chat_id,
            uid
        )

    elif (
        text_value == "👑 إدارة السحوبات"
        and is_admin(uid)
    ):
        admin_withdrawals(
            chat_id,
            uid
        )

    elif (
        text_value == "⭐ رصيد Stars للإدارة"
        and is_admin(uid)
    ):
        admin_stars_balance(
            chat_id,
            uid,
            message.chat.type
        )

    elif text_value == "⚡ ترقية المنجم":
        bot.send_message(
            chat_id,
            local_text("mining_future", uid)
        )

    elif text_value == "🏆 المكافآت":
        bot.send_message(chat_id, extra_text("rewards", uid))

    elif text_value == "🎵 TikTok EN96":
        show_tiktok(chat_id)

    elif text_value == "▶️ YouTube EN96":
        show_youtube(chat_id)

    # NEW TELEGRAM CHANNEL MENU HANDLER
    elif text_value == "📢 قناة EN96 الرسمية":
        show_telegram_channel(chat_id)

    elif text_value == "📺 مشاهدة الفيديوهات":
        show_videos(chat_id)

    elif text_value == "🎁 استلام الهدية":
        WAITING_GIFT.add(uid)

        bot.send_message(
            chat_id,
            local_text("enter_code", uid)
        )

    elif text_value in (
        "🐻 أعضاء القبيلة",
        "🐉 أعضاء القبيلة"
    ):
        tribe(
            chat_id,
            uid
        )

    elif text_value == "ℹ️ معلومات EN96":
        bot.send_message(
            chat_id,
            extra_text("about", uid) + "\n\n" + TELEGRAM_CHANNEL_URL,
            disable_web_page_preview=True
        )

    elif (
        text_value == "🛠️ إدارة الهدايا"
        and is_admin(uid)
    ):
        bot.send_message(
            chat_id,
            "🛠️ إدارة الهدايا",
            reply_markup=admin_menu(uid)
        )

    elif (
        text_value == "➕ إنشاء كود هدية"
        and is_admin(uid)
    ):
        WAITING_ADMIN_CODE.add(uid)

        bot.send_message(
            chat_id,
            "أرسل كود الهدية الجديد."
        )

    elif (
        text_value == "📋 أكواد الهدايا"
        and is_admin(uid)
    ):
        list_gifts(chat_id)

    elif (
        text_value in (
            "⛔ تعطيل كود",
            "✅ تفعيل كود"
        )
        and is_admin(uid)
    ):
        ADMIN_ACTION[uid] = (
            "disable"
            if text_value == "⛔ تعطيل كود"
            else "enable"
        )

        WAITING_ADMIN_CODE.add(uid)

        bot.send_message(
            chat_id,
            "أرسل الكود المطلوب."
        )

    elif text_value == "🔙 القائمة الرئيسية":
        clear_withdrawal_state(uid)

        send_menu(
            chat_id,
            user_id=uid
        )

    elif text_value == "🌐 فتح تطبيق EN96":
        app_button(chat_id)

    else:
        send_menu(
            chat_id,
            local_text("choose", uid),
            user_id=uid
        )


# ==========================================
# START BOT
# ==========================================

if __name__ == "__main__":
    log.info(
        "Starting EN96 Telegram bot"
    )

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )
