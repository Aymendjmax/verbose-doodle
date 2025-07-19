import os
import json
import logging
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode
from flask import Flask, jsonify
import threading
import time

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# متغيرات البيئة
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
DEVELOPER_USERNAME = os.getenv('DEVELOPER_USERNAME')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')
PORT = int(os.getenv('PORT', 5000))
AI_API_URL = "https://chatgpt5free.com/wp-admin/admin-ajax.php"

# تحويل CHANNEL_ID إلى عدد صحيح
if CHANNEL_ID:
    CHANNEL_ID = int(CHANNEL_ID)
else:
    logger.error("يجب تعيين CHANNEL_ID في المتغيرات البيئية")
    exit(1)

# Quran API من alquran.vip
BASE_URL = "https://api.alquran.cloud/v1"

# API الصوتيات الجديد
AUDIO_API_URL = "https://www.mp3quran.net/api/v3/reciters?language=ar"

# API الجديد لصور المصحف
QURAN_IMAGE_API = "https://alquran.vip/APIs/quranPagesImage"

# Flask app للـ ping
app = Flask(__name__)

@app.route('/')
def ping():
    return jsonify({"status": "البوت يعمل بنجاح! 🕊️", "bot": "سُطورٌ من السَّماء ☁️"})

@app.route('/health')
def health():
    return jsonify({"health": "ok", "timestamp": time.time()})

# تشغيل Flask في thread منفصل
def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# بدء Flask server
flask_thread = threading.Thread(target=run_flask)
flask_thread.daemon = True
flask_thread.start()

# الذاكرة المؤقتة للبيانات
cache = {
    'surah_info': None,
    'juz_info': None,
    'surah_data': {},
    'reciters': None,
    'search_results': {},
    'quran_pages': None,  # تخزين بيانات صفحات المصحف
    'surah_page_map': {}  # خريطة السور للصفحات
}

async def fetch_json(url, headers=None):
    """جلب بيانات JSON من URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"خطأ في جلب البيانات من {url}: {response.status}")
                    return None
    except asyncio.TimeoutError:
        logger.error(f"انتهت المهلة أثناء جلب {url}")
        return None
    except Exception as e:
        logger.error(f"خطأ في الاتصال بـ {url}: {e}")
        return None

async def post_json(url, data, headers=None):
    """إرسال طلب POST والحصول على JSON"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"خطأ في إرسال البيانات إلى {url}: {response.status}")
                    return None
    except asyncio.TimeoutError:
        logger.error(f"انتهت المهلة أثناء إرسال البيانات إلى {url}")
        return None
    except Exception as e:
        logger.error(f"خطأ في الاتصال بـ {url}: {e}")
        return None

async def load_surah_info():
    """تحميل معلومات السور"""
    if cache['surah_info'] is None:
        url = f"{BASE_URL}/surah"
        data = await fetch_json(url)
        if data and data.get('code') == 200 and 'data' in data:
            cache['surah_info'] = data['data']
        else:
            logger.error("فشل في تحميل معلومات السور")
    return cache['surah_info']

async def load_juz_info():
    """تحميل معلومات الأجزاء"""
    if cache['juz_info'] is None:
        juzs = []
        for i in range(1, 31):
            juzs.append({
                "number": i,
                "name_arabic": f"الجزء {i}",
            })
        cache['juz_info'] = juzs
    return cache['juz_info']

async def load_surah_data(surah_number):
    """تحميل بيانات سورة معينة"""
    if surah_number not in cache['surah_data']:
        url = f"{BASE_URL}/surah/{surah_number}/ar.alafasy"
        data = await fetch_json(url)
        if data and data.get('code') == 200 and 'data' in data:
            verses = {}
            surah_data = data['data']
            for ayah in surah_data['ayahs']:
                verse_number = ayah['numberInSurah']
                verses[verse_number] = ayah['text']
            cache['surah_data'][surah_number] = {
                'verses': verses,
                'name': surah_data['englishName'],
                'name_arabic': surah_data['name'],
                'revelation_type': surah_data['revelationType'],
                'ayahs_count': surah_data['numberOfAyahs']
            }
        else:
            logger.error(f"فشل في تحميل بيانات سورة {surah_number}")
            return None
    return cache['surah_data'].get(surah_number)

async def load_reciters():
    """تحميل قائمة القراء من API الجديد"""
    if cache['reciters'] is None:
        data = await fetch_json(AUDIO_API_URL)
        if data and 'reciters' in data:
            cache['reciters'] = data['reciters']
        else:
            logger.error("فشل في تحميل قائمة القراء")
    return cache['reciters']

async def get_reciter_audio(reciter_id, surah_number):
    """الحصول على رابط الصوت للقارئ والسورة"""
    reciters = await load_reciters()
    if not reciters:
        return None
    
    reciter = next((r for r in reciters if r['id'] == reciter_id), None)
    if not reciter:
        return None
    
    # البحث عن الروابط في الموشافات المتاحة
    for moshaf in reciter.get('moshaf', []):
        if 'surah_list' in moshaf:
            # تحويل قائمة السور إلى قائمة أرقام
            surah_list = moshaf['surah_list'].split(',')
            if str(surah_number) in surah_list:
                server = moshaf.get('server')
                if server:
                    # تنسيق رقم السورة (001, 002, ... 114)
                    surah_str = str(surah_number).zfill(3)
                    return f"{server}{surah_str}.mp3"
    
    # إذا لم نجد الرابط بالطريقة العادية، نبحث عن طريقة بديلة
    for moshaf in reciter.get('moshaf', []):
        if 'surah_list' in moshaf and str(surah_number) in moshaf['surah_list']:
            server = moshaf.get('server')
            if server:
                # تجربة تنسيقات مختلفة
                formats = [
                    f"{server}{str(surah_number).zfill(3)}.mp3",
                    f"{server}{surah_number}.mp3",
                    f"{server}surah{surah_number}.mp3",
                    f"{server}{surah_number:03d}.mp3"
                ]
                
                # التحقق من وجود الملف في أحد التنسيقات
                async with aiohttp.ClientSession() as session:
                    for format in formats:
                        try:
                            async with session.head(format, timeout=10) as response:
                                if response.status == 200:
                                    return format
                        except:
                            continue
    
    return None

async def load_quran_pages():
    """تحميل بيانات صفحات المصحف من API الجديد"""
    if cache['quran_pages'] is None:
        data = await fetch_json(QURAN_IMAGE_API)
        if data and isinstance(data, list):
            cache['quran_pages'] = data
            # إنشاء خريطة السور للصفحات
            surah_page_map = {}
            for page in data:
                # افترض أن كل صفحة تحتوي على سورة واحدة فقط
                # (هذا افتراض قد يحتاج للتعديل حسب بيانات API الفعلية)
                surah_page_map[page['page_number']] = {
                    'surah_number': page.get('surah_number', 1),
                    'surah_name': page.get('surah_name', 'الفاتحة')
                }
            cache['surah_page_map'] = surah_page_map
        else:
            logger.error("فشل في تحميل بيانات صفحات المصحف")
    return cache['quran_pages']

def get_page_url(page_number):
    """الحصول على رابط الصورة لصفحة معينة"""
    pages = cache.get('quran_pages')
    if not pages:
        return None
    
    page = next((p for p in pages if p['page_number'] == page_number), None)
    if page:
        return page['page_url']
    return None

def get_surah_for_page(page_number):
    """الحصول على معلومات السورة لصفحة معينة"""
    page_map = cache.get('surah_page_map')
    if not page_map:
        return {'surah_number': 1, 'surah_name': 'الفاتحة'}
    
    return page_map.get(page_number, {'surah_number': 1, 'surah_name': 'الفاتحة'})

async def check_user_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من اشتراك المستخدم في القناة"""
    try:
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

async def subscription_required(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من الاشتراك الإجباري"""
    user_id = update.effective_user.id
    
    if not await check_user_subscription(user_id, context):
        keyboard = [
            [InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🌟 *مرحباً بك في سُطورٌ من السَّماء* ☁️\n\n"
            "📖 للاستفادة من خدمات البوت، يرجى الاشتراك في قناتنا أولاً:\n\n"
            "💎 ستجد في القناة:\n"
            "• آيات قرآنية يومية 🌅\n"
            "• تفسيرات مختارة 📚\n"
            "• أدعية وأذكار 🤲\n"
            "• محتوى إسلامي مميز ✨\n\n"
            "🤲 بارك الله فيك وجعل هذا البوت سبباً في رضاك",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية"""
    if not await subscription_required(update, context):
        return
    
    user_name = update.effective_user.first_name
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف", callback_data="browse_quran")],
        [InlineKeyboardButton("🔍 البحث في القرآن", callback_data="search_quran")],
        [InlineKeyboardButton("📚 تصفح الأجزاء", callback_data="browse_juz")],
        [InlineKeyboardButton("🎵 الاستماع للتلاوات", callback_data="audio_menu")],
        [InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = f"""
🌟 *أهلاً وسهلاً {user_name}* 🌟

 *سُطورٌ من السَّماء* ☁️

🕊️ *بوت شامل للقرآن الكريم*

✨ *الخدمات المتاحة:*
• 📖 تصفح المصحف الكامل مع التلاوة
• 🔍 البحث في الآيات بذكاء
• 📚 تصفح الأجزاء والأحزاب بسهولة
• 🎵 الاستماع للتلاوات بصوت أشهر القراء
• 📝 معلومات تفصيلية عن السور

🤲 *بارك الله فيك وجعل القرآن ربيع قلبك ونور صدرك*
    """
    
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من الاشتراك عند الضغط على الزر"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if await check_user_subscription(user_id, context):
        await query.edit_message_text(
            "✅ *تم التحقق بنجاح!*\n\n"
            "🌟 أهلًا بك في رحلة القرآن الكريم ☁️\n\n"
            "استخدم الأزرار أدناه لاستكشاف كنوز القرآن:",
            parse_mode=ParseMode.MARKDOWN
        )
        # إعادة توجيه للقائمة الرئيسية
        await asyncio.sleep(1)
        await start_from_callback(query, context)
    else:
        await query.edit_message_text(
            "❌ *لم يتم العثور على اشتراكك*\n\n"
            "🔔 يرجى الاشتراك في القناة أولاً ثم اضغط على 'تحقق من الاشتراك'",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")],
                [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]
            ])
        )

async def start_from_callback(query, context):
    """بدء القائمة الرئيسية من callback"""
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف", callback_data="browse_quran")],
        [InlineKeyboardButton("🔍 البحث في القرآن", callback_data="search_quran")],
        [InlineKeyboardButton("📚 تصفح الأجزاء", callback_data="browse_juz")],
        [InlineKeyboardButton("🎵 الاستماع للتلاوات", callback_data="audio_menu")],
        [InlineKeyboardButton("👨‍💻 المطور", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        " *سُطورٌ من السَّماء* ☁️\n\n"
        "📖 *اختر الخدمة التي تريدها:*\n\n"
        "✨ استكشف عالم القرآن الكريم بلمسة زر",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_quran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح المصحف (اختيار بين نصي وصوري)"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 مصحف نصي", callback_data="browse_quran_text")],
        [InlineKeyboardButton("🖼️ مصحف بالصور", callback_data="browse_quran_images")],
        [InlineKeyboardButton("🔙 العودة", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📖 *اختر طريقة تصفح المصحف:*\n\n"
        "• *المصحف النصي*: قراءة الآيات كتابة\n"
        "• *المصحف المصور*: تصفح صفحات المصحف كصور",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_quran_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح المصحف نصي"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السور")
        return
    
    # تقسيم السور إلى صفحات
    surahs_per_page = 10
    total_pages = (len(surah_info) + surahs_per_page - 1) // surahs_per_page
    
    # الصفحة الأولى
    page = 0
    start_idx = page * surahs_per_page
    end_idx = min(start_idx + surahs_per_page, len(surah_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        surah = surah_info[i]
        button_text = f"{surah['number']}. {surah['name']} ({surah['numberOfAyahs']} آية)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"surah_{surah['number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"quran_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"quran_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📖 *المصحف الشريف (نصي)*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n"
        f"🔢 السور {start_idx + 1} - {end_idx}\n\n"
        f"اختر السورة التي تريد قراءتها:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_quran_images(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح المصحف بالصور"""
    query = update.callback_query
    await query.answer()
    
    # تحميل بيانات الصفحات
    pages_data = await load_quran_pages()
    if not pages_data:
        await query.edit_message_text("❌ خطأ في تحميل بيانات صفحات المصحف")
        return
    
    # تقسيم الصفحات إلى مجموعات
    pages_per_page = 10
    total_pages = (len(pages_data) + pages_per_page - 1) // pages_per_page
    
    # الصفحة الأولى
    page = 0
    start_idx = page * pages_per_page
    end_idx = min(start_idx + pages_per_page, len(pages_data))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        page_data = pages_data[i]
        button_text = f"الصفحة {page_data['page_number']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"quran_page_image_{page_data['page_number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"quran_image_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"quran_image_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📖 *المصحف الشريف (صوري)*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n"
        f"🔢 الصفحات {start_idx + 1} - {end_idx}\n\n"
        f"اختر الصفحة التي تريد تصفحها:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من السور (نصي)"""
    query = update.callback_query
    await query.answer()
    
    page = int(query.data.split('_')[2])
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السور")
        return
    
    surahs_per_page = 10
    total_pages = (len(surah_info) + surahs_per_page - 1) // surahs_per_page
    
    start_idx = page * surahs_per_page
    end_idx = min(start_idx + surahs_per_page, len(surah_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        surah = surah_info[i]
        button_text = f"{surah['number']}. {surah['name']} ({surah['numberOfAyahs']} آية)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"surah_{surah['number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"quran_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"quran_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📖 *المصحف الشريف (نصي)*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n"
        f"🔢 السور {start_idx + 1} - {end_idx}\n\n"
        f"اختر السورة التي تريد قراءتها:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_image_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من الصفحات (صوري)"""
    query = update.callback_query
    await query.answer()
    
    page = int(query.data.split('_')[3])
    
    pages_data = await load_quran_pages()
    if not pages_data:
        await query.edit_message_text("❌ خطأ في تحميل بيانات صفحات المصحف")
        return
    
    pages_per_page = 10
    total_pages = (len(pages_data) + pages_per_page - 1) // pages_per_page
    
    start_idx = page * pages_per_page
    end_idx = min(start_idx + pages_per_page, len(pages_data))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        page_data = pages_data[i]
        button_text = f"الصفحة {page_data['page_number']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"quran_page_image_{page_data['page_number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"quran_image_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"quran_image_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📖 *المصحف الشريف (صوري)*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n"
        f"🔢 الصفحات {start_idx + 1} - {end_idx}\n\n"
        f"اختر الصفحة التي تريد تصفحها:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def show_page_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض صفحة مصورة من المصحف"""
    query = update.callback_query
    await query.answer()
    
    page_number = int(query.data.split('_')[3])
    
    # جلب رابط الصورة
    page_url = get_page_url(page_number)
    if not page_url:
        await query.edit_message_text("❌ تعذر العثور على الصفحة المطلوبة")
        return
    
    # الحصول على معلومات السورة للصفحة
    surah_info = get_surah_for_page(page_number)
    
    keyboard = [
        [
            InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"prev_page_{page_number}"),
            InlineKeyboardButton("➡️ الصفحة التالية", callback_data=f"next_page_{page_number}")
        ],
        [InlineKeyboardButton("🔙 العودة للمصحف", callback_data="browse_quran_images")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
📖 *الصفحة {page_number} من المصحف الشريف*

📝 *السورة:* {surah_info['surah_name']} (رقم {surah_info['surah_number']})

✨ استمر في التصفح باستخدام الأزرار أدناه
    """
    
    try:
        # إرسال الصورة مع النص
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=page_url,
            caption=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        # حذف الرسالة القديمة
        await query.message.delete()
    except Exception as e:
        logger.error(f"خطأ في إرسال الصورة: {e}")
        await query.edit_message_text("❌ تعذر تحميل صورة الصفحة. يرجى المحاولة لاحقًا.")

async def navigate_page(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    """التنقل بين الصفحات"""
    query = update.callback_query
    await query.answer()
    
    current_page = int(query.data.split('_')[2])
    
    if direction == "next":
        new_page = current_page + 1
    else:
        new_page = current_page - 1
    
    # التحقق من حدود الصفحات
    pages_data = await load_quran_pages()
    if not pages_data:
        await query.edit_message_text("❌ خطأ في تحميل بيانات صفحات المصحف")
        return
    
    min_page = min(p['page_number'] for p in pages_data)
    max_page = max(p['page_number'] for p in pages_data)
    
    if new_page < min_page:
        new_page = min_page
    elif new_page > max_page:
        new_page = max_page
    
    # جلب رابط الصورة الجديدة
    page_url = get_page_url(new_page)
    if not page_url:
        await query.edit_message_text("❌ تعذر العثور على الصفحة المطلوبة")
        return
    
    # الحصول على معلومات السورة للصفحة
    surah_info = get_surah_for_page(new_page)
    
    keyboard = []
    
    # إضافة أزرار التنقل إذا كانت هناك صفحات قبل أو بعد
    buttons = []
    if new_page > min_page:
        buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"prev_page_{new_page}"))
    if new_page < max_page:
        buttons.append(InlineKeyboardButton("➡️ الصفحة التالية", callback_data=f"next_page_{new_page}"))
    
    if buttons:
        keyboard.append(buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 العودة للمصحف", callback_data="browse_quran_images")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
📖 *الصفحة {new_page} من المصحف الشريف*

📝 *السورة:* {surah_info['surah_name']} (رقم {surah_info['surah_number']})

✨ استمر في التصفح باستخدام الأزرار أدناه
    """
    
    try:
        # إرسال الصورة الجديدة
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=page_url,
            caption=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        # حذف الرسالة القديمة
        await query.message.delete()
    except Exception as e:
        logger.error(f"خطأ في إرسال الصورة: {e}")
        await query.edit_message_text("❌ تعذر تحميل صورة الصفحة. يرجى المحاولة لاحقًا.")

async def next_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الصفحة التالية"""
    await navigate_page(update, context, "next")

async def prev_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الصفحة السابقة"""
    await navigate_page(update, context, "prev")

async def show_surah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سورة معينة (نصي)"""
    query = update.callback_query
    await query.answer()
    
    surah_number = int(query.data.split('_')[1])
    
    # تحميل بيانات السورة
    surah_data = await load_surah_data(surah_number)
    
    if not surah_data:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السورة")
        return
    
    keyboard = [
        [InlineKeyboardButton("📖 قراءة السورة", callback_data=f"read_surah_{surah_number}")],
        [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_surah_{surah_number}")],
        [InlineKeyboardButton("🔙 العودة للمصحف", callback_data="browse_quran_text")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
📖 *{surah_data['name_arabic']}*

🔢 *رقم السورة:* {surah_number}
📍 *نوع النزول:* {surah_data['revelation_type']}
📝 *عدد الآيات:* {surah_data['ayahs_count']}

🌟 *اختر ما تريد:*
    """
    
    await query.edit_message_text(
        message_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def read_surah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قراءة السورة كاملة (نصي)"""
    query = update.callback_query
    await query.answer()
    
    surah_number = int(query.data.split('_')[2])
    
    # تحميل بيانات السورة
    surah_data = await load_surah_data(surah_number)
    
    if not surah_data:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السورة")
        return
    
    # إنشاء نص السورة
    surah_text = f"📖 *{surah_data['name_arabic']}*\n\n"
    
    # إضافة البسملة للسور (عدا التوبة)
    if surah_number != 9:
        surah_text += "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ\n\n"
    
    verses = surah_data['verses']
    sorted_verses = sorted(verses.items(), key=lambda x: int(x[0]))
    
    for verse_number, verse_text in sorted_verses:
        surah_text += f"{verse_text} ﴿{verse_number}﴾\n\n"
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(surah_text) > 3000:
            keyboard = [
                [InlineKeyboardButton("⬇️ المتابعة", callback_data=f"continue_surah_{surah_number}_{verse_number}")],
                [InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                surah_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    # إضافة أزرار التنقل
    keyboard = [
        [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_surah_{surah_number}")],
        [InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        surah_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def continue_reading(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """متابعة قراءة السورة من حيث توقفت"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    surah_number = int(data[2])
    start_verse = int(data[3])
    
    # تحميل بيانات السورة
    surah_data = await load_surah_data(surah_number)
    
    if not surah_data:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السورة")
        return
    
    # إنشاء نص السورة من الآية المحددة
    surah_text = f"📖 *{surah_data['name_arabic']}*\n\n"
    
    # فرز الآيات حسب أرقامها
    verses = surah_data['verses']
    sorted_verses = sorted(verses.items(), key=lambda x: int(x[0]))
    
    # بدء من الآية المحددة
    found_start = False
    for verse_number, verse_text in sorted_verses:
        verse_num = int(verse_number)
        if verse_num < start_verse:
            continue
        if not found_start:
            found_start = True
            # إضافة البسملة إذا بدأنا من الآية الأولى
            if verse_num == 1 and surah_number != 9:
                surah_text += "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ\n\n"
            
        surah_text += f"{verse_text} ﴿{verse_number}﴾\n\n"
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(surah_text) > 3000:
            keyboard = [
                [InlineKeyboardButton("⬇️ المتابعة", callback_data=f"continue_surah_{surah_number}_{verse_number}")],
                [InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                surah_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    # إضافة أزرار التنقل
    keyboard = [
        [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_surah_{surah_number}")],
        [InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        surah_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_juz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح الأجزاء"""
    query = update.callback_query
    await query.answer()
    
    juz_info = await load_juz_info()
    if not juz_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات الأجزاء")
        return
    
    # تقسيم الأجزاء إلى صفحات
    juzs_per_page = 10
    total_pages = (len(juz_info) + juzs_per_page - 1) // juzs_per_page
    
    # الصفحة الأولى
    page = 0
    start_idx = page * juzs_per_page
    end_idx = min(start_idx + juzs_per_page, len(juz_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        juz = juz_info[i]
        button_text = f"الجزء {juz['number']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"juz_{juz['number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"juz_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"juz_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📚 *أجزاء القرآن الكريم*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n"
        f"اختر الجزء الذي تريد قراءته:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_juz_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من الأجزاء"""
    query = update.callback_query
    await query.answer()
    
    page = int(query.data.split('_')[2])
    
    juz_info = await load_juz_info()
    if not juz_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات الأجزاء")
        return
    
    juzs_per_page = 10
    total_pages = (len(juz_info) + juzs_per_page - 1) // juzs_per_page
    
    start_idx = page * juzs_per_page
    end_idx = min(start_idx + juzs_per_page, len(juz_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        juz = juz_info[i]
        button_text = f"الجزء {juz['number']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"juz_{juz['number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"juz_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"juz_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📚 *أجزاء القرآن الكريم*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n"
        f"اختر الجزء الذي تريد قراءته:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def show_juz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات الجزء"""
    query = update.callback_query
    await query.answer()
    
    juz_number = int(query.data.split('_')[1])
    
    keyboard = [
        [InlineKeyboardButton("📖 قراءة الجزء", callback_data=f"read_juz_{juz_number}")],
        [InlineKeyboardButton("🔙 العودة للأجزاء", callback_data="browse_juz")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
📚 *الجزء {juz_number}*

🌟 *اختر ما تريد:*
    """
    
    await query.edit_message_text(
        message_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def audio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الصوتيات"""
    query = update.callback_query
    await query.answer()
    
    await browse_quran_for_audio(update, context)

async def browse_quran_for_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح المصحف لاختيار سورة للتلاوة"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السور")
        return
    
    # تقسيم السور إلى صفحات
    surahs_per_page = 10
    total_pages = (len(surah_info) + surahs_per_page - 1) // surahs_per_page
    
    # الصفحة الأولى
    page = 0
    start_idx = page * surahs_per_page
    end_idx = min(start_idx + surahs_per_page, len(surah_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        surah = surah_info[i]
        button_text = f"{surah['number']}. {surah['name']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"audio_surah_{surah['number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"audio_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"audio_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎵 *اختر سورة للاستماع إليها*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n\n"
        "✨ اختر سورة لتستمع إلى تلاوتها بأصوات أشهر القراء",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def audio_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من السور للصوتيات"""
    query = update.callback_query
    await query.answer()
    
    page = int(query.data.split('_')[2])
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السور")
        return
    
    surahs_per_page = 10
    total_pages = (len(surah_info) + surahs_per_page - 1) // surahs_per_page
    
    start_idx = page * surahs_per_page
    end_idx = min(start_idx + surahs_per_page, len(surah_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        surah = surah_info[i]
        button_text = f"{surah['number']}. {surah['name']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"audio_surah_{surah['number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"audio_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"audio_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎵 *اختر سورة للاستماع إليها*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n\n"
        "✨ اختر سورة لتستمع إلى تلاوتها بأصوات أشهر القراء",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def show_reciters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة القراء لسورة محددة"""
    query = update.callback_query
    await query.answer()
    
    # استخراج رقم السورة من بيانات الـ callback
    callback_data = query.data
    if callback_data.startswith("audio_surah_"):
        surah_number = int(callback_data.split('_')[2])
    elif callback_data.startswith("reciters_"):
        surah_number = int(callback_data.split('_')[1])
    else:
        await query.edit_message_text("❌ لم يتم تحديد السورة")
        return
    
    # جلب القُراء المتاحين
    reciters = await load_reciters()
    if not reciters:
        await query.edit_message_text("❌ لا يوجد قُراء متاحين حالياً، يرجى المحاولة لاحقاً")
        return
    
    # تقسيم القراء إلى صفحات
    reciters_per_page = 10
    total_pages = (len(reciters) + reciters_per_page - 1) // reciters_per_page
    
    # الصفحة الأولى
    page = 0
    start_idx = page * reciters_per_page
    end_idx = min(start_idx + reciters_per_page, len(reciters))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        reciter = reciters[i]
        # التحقق من توفر السورة لهذا القارئ
        audio_url = await get_reciter_audio(reciter['id'], surah_number)
        if audio_url:
            keyboard.append([InlineKeyboardButton(f"🎧 {reciter['name']}", callback_data=f"play_audio_{reciter['id']}_{surah_number}")])
    
    if not keyboard:
        await query.edit_message_text("❌ لا يوجد قُراء متاحين لهذه السورة حالياً")
        return
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"reciters_page_{surah_number}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"reciters_page_{surah_number}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([
        InlineKeyboardButton("🔙 العودة للسور", callback_data="audio_menu"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # جلب اسم السورة
    surah_info = await load_surah_info()
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    surah_name = surah_data['name'] if surah_data else f"سورة {surah_number}"
    
    await query.edit_message_text(
        f"🎵 *اختر قارئاً للاستماع لسورة {surah_name}:*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n\n"
        "✨ اختر قارئاً لتستمع إلى تلاوة عذبة تلامس القلب",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def reciters_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من القراء"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    surah_number = int(data[2])
    page = int(data[3])
    
    # جلب القُراء المتاحين
    reciters = await load_reciters()
    if not reciters:
        await query.edit_message_text("❌ لا يوجد قُراء متاحين حالياً، يرجى المحاولة لاحقاً")
        return
    
    # تقسيم القراء إلى صفحات
    reciters_per_page = 10
    total_pages = (len(reciters) + reciters_per_page - 1) // reciters_per_page
    
    start_idx = page * reciters_per_page
    end_idx = min(start_idx + reciters_per_page, len(reciters))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        reciter = reciters[i]
        # التحقق من توفر السورة لهذا القارئ
        audio_url = await get_reciter_audio(reciter['id'], surah_number)
        if audio_url:
            keyboard.append([InlineKeyboardButton(f"🎧 {reciter['name']}", callback_data=f"play_audio_{reciter['id']}_{surah_number}")])
    
    if not keyboard:
        await query.edit_message_text("❌ لا يوجد قُراء متاحين لهذه السورة حالياً")
        return
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"reciters_page_{surah_number}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"reciters_page_{surah_number}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([
        InlineKeyboardButton("🔙 العودة للسور", callback_data="audio_menu"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # جلب اسم السورة
    surah_info = await load_surah_info()
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    surah_name = surah_data['name'] if surah_data else f"سورة {surah_number}"
    
    await query.edit_message_text(
        f"🎵 *اختر قارئاً للاستماع لسورة {surah_name}:*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n\n"
        "✨ اختر قارئاً لتستمع إلى تلاوة عذبة تلامس القلب",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def play_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل تلاوة السورة"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    reciter_id = int(data[2])
    surah_number = int(data[3])
    
    surah_info = await load_surah_info()
    if not surah_info or surah_number < 1 or surah_number > len(surah_info):
        await query.edit_message_text("❌ رقم السورة غير صحيح")
        return
    
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    if not surah_data:
        await query.edit_message_text("❌ لم يتم العثور على معلومات السورة")
        return
    
    surah_name = surah_data['name']
    
    # جلب معلومات القارئ
    reciters = await load_reciters()
    reciter = next((r for r in reciters if r['id'] == reciter_id), None)
    if not reciter:
        await query.edit_message_text("❌ لم يتم العثور على معلومات القارئ")
        return
    
    reciter_name = reciter['name']
    
    # إعلام المستخدم بأن التحميل جارٍ
    await query.edit_message_text(f"⏳ جاري تحميل تلاوة سورة {surah_name} بصوت {reciter_name}...")
    
    # جلب رابط الصوت
    audio_url = await get_reciter_audio(reciter_id, surah_number)
    
    if not audio_url:
        await query.edit_message_text("❌ تعذر العثور على التلاوة المطلوبة")
        return
    
    # إرسال ملف الصوت بدون أي نص أو أزرار
    try:
        # الرسالة الأولى: الملف الصوتي فقط
        audio_msg = await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=audio_url,
            read_timeout=90,
            write_timeout=90,
            connect_timeout=90,
            pool_timeout=90
        )
        
        # الرسالة الثانية: النص والأزرار
        message_text = f"""
🌟 *تم إرسال تلاوة سورة {surah_name}*

🎧 *القارئ:* {reciter_name}
📖 *السورة:* {surah_name} ({surah_number})
🕋 *عدد آياتها:* {surah_data['numberOfAyahs']}

✨ *هل تود الاستماع إلى تلاوات أخرى؟*
        """
        
        keyboard = [
            [InlineKeyboardButton("🎵 تلاوات أخرى", callback_data=f"reciters_{surah_number}")],
            [InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        # حذف رسالة "جاري التحميل"
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
    except Exception as e:
        logger.error(f"خطأ في إرسال الصوت: {e}")
        
        # رسالة تفاعلية مع شرح للمشكلة
        message = f"""
⚠️ *تعذر إرسال الملف الصوتي مباشرةً*

🎧 **لكن يمكنك الاستماع للتلاوة من الرابط بعد الضغط على الزر**

📖 سورة *{surah_name}* بصوت *{reciter_name}*

👨‍💻 **ملاحظة من المطور:**
عذرا 🫠 ... لكن حقًا المشكلة ليست بيدي 🤷🏼‍♂️
ببساطة، بعض السور الكبيرة لا يمكن إرسالها مباشرة بسبب قيود النظام 😐💔
لكن لو جربت سورًا قصيرة ستجد أن البوت يرسلها بشكل طبيعي 😁🤝
لا تستهن بخبرتي كمطور محترف 😌✨️
        """
        
        # إرسال الرسالة مع الزر
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎧 استمع الآن", url=audio_url)],
                [InlineKeyboardButton("🔙 العودة للقارئين", callback_data=f"reciters_{surah_number}")]
            ])
        )
        
        # حذف رسالة "جاري التحميل"
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)

async def search_quran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية البحث"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔍 *البحث في القرآن الكريم*\n\n"
        "اكتب الكلمة أو الجملة التي تريد البحث عنها:\n\n"
        "✨ سيتم البحث في آيات القرآن الكريم وإعادتها لك مع تفسير مختصر",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data['search_mode'] = True

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ البحث في القرآن باستخدام ChatGPT API"""
    search_text = update.message.text.strip()
    
    if len(search_text) < 3:
        await update.message.reply_text("🔍 يرجى إدخال كلمة مكونة من 3 أحرف على الأقل")
        return
    
    # مسح حالة البحث
    context.user_data.pop('search_mode', None)
    
    # إعلام المستخدم بأن البحث جاري
    msg = await update.message.reply_text("🔍 جاري البحث في القرآن الكريم...\n\n✨ سيتم إرسال النتائج قريباً")
    
    # إعداد بيانات الطلب لـ ChatGPT API
    payload = {
        'action': 'ai_chat',
        'message': f"ابحث في القرآن الكريم عن: {search_text}"
    }
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # إرسال طلب البحث
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(AI_API_URL, data=payload, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    ai_reply = data.get('data', '') if data else None
                else:
                    ai_reply = None
    except Exception as e:
        logger.error(f"خطأ في الاتصال بـ API البحث: {e}")
        ai_reply = None
    
    if not ai_reply:
        await msg.edit_text("❌ لم أتمكن من العثور على نتائج لبحثك. يرجى المحاولة مرة أخرى.")
        return
    
    # استخراج الرسالة من الرد
    if isinstance(ai_reply, dict) and 'message' in ai_reply:
        ai_reply = ai_reply['message']
    
    # حفظ النتائج في الذاكرة المؤقتة
    cache['search_results'][update.message.chat_id] = {
        'results': ai_reply,
        'query': search_text
    }
    
    # عرض النتائج
    await show_search_results(update, context, msg.message_id)

async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id=None):
    """عرض نتائج البحث"""
    if update.callback_query:
        chat_id = update.callback_query.message.chat_id
        message_id = update.callback_query.message.message_id
    else:
        chat_id = update.message.chat_id
    
    search_data = cache['search_results'].get(chat_id)
    
    if not search_data:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ لم يتم العثور على بيانات البحث")
        else:
            await update.message.reply_text("❌ لم يتم العثور على بيانات البحث")
        return
    
    results = search_data['results']
    query = search_data['query']
    
    # تنظيف النتائج من الرموز غير المرغوبة
    if results.startswith('{'):
        try:
            data = json.loads(results)
            if 'message' in data:
                results = data['message']
        except:
            pass
    
    # إضافة أزرار البحث من جديد والعودة
    keyboard = [
        [InlineKeyboardButton("🔍 بحث جديد", callback_data="search_quran")],
        [InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # تقسيم النتائج إذا كانت طويلة
    if len(results) > 4000:
        parts = [results[i:i+4000] for i in range(0, len(results), 4000)]
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                # في الجزء الأخير نضيف الأزرار
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔍 *نتائج البحث عن: \"{query}\"*\n\n{part}\n\n"
                         "🌟 *هل تود البحث عن شيء آخر؟*",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔍 *نتائج البحث عن: \"{query}\"*\n\n{part}",
                    parse_mode=ParseMode.MARKDOWN
                )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔍 *نتائج البحث عن: \"{query}\"*\n\n{results}\n\n"
                 "🌟 *هل تود البحث عن شيء آخر؟*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    
    # حذف رسالة "جاري البحث"
    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    await start_from_callback(query, context)

async def read_juz(update: Update, context: ContextTypes.DEFAULT_TYPE, juz_number: int):
    """قراءة الجزء كاملاً"""
    query = update.callback_query
    await query.answer()
    
    # إعلام المستخدم بأن التحميل جارٍ
    await query.edit_message_text(f"⏳ جاري تحميل الجزء {juz_number}...")
    
    # جلب بيانات الجزء
    url = f"{BASE_URL}/juz/{juz_number}/ar.alafasy"
    data = await fetch_json(url)
    
    if not data or data.get('code') != 200 or 'data' not in data:
        await query.edit_message_text("❌ خطأ في جلب بيانات الجزء")
        return
    
    juz_data = data['data']
    if not juz_data or 'ayahs' not in juz_data:
        await query.edit_message_text("❌ لا توجد آيات في هذا الجزء")
        return
    
    # إنشاء نص الجزء
    juz_text = f"📖 *الجزء {juz_number}*\n\n"
    
    # تجميع الآيات مع ذكر اسم السورة عند تغييرها
    current_surah = None
    for ayah in juz_data['ayahs']:
        surah_id = ayah['surah']['number']
        verse_number = ayah['numberInSurah']
        verse_text = ayah['text']
        
        # إذا تغيرت السورة، نكتب اسم السورة الجديدة
        if surah_id != current_surah:
            surah_info = await load_surah_info()
            surah_name = next((s['name'] for s in surah_info if s['number'] == surah_id), f"سورة {surah_id}")
            juz_text += f"\n*{surah_name}*\n\n"
            current_surah = surah_id
            
        juz_text += f"{verse_text} ﴿{verse_number}﴾ "
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(juz_text) > 3000:
            keyboard = [
                [InlineKeyboardButton("⬇️ المتابعة", callback_data=f"continue_juz_{juz_number}_{surah_id}_{verse_number}")],
                [InlineKeyboardButton("🔙 العودة للجزء", callback_data=f"juz_{juz_number}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                juz_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    # إضافة أزرار التنقل
    keyboard = [
        [InlineKeyboardButton("🔙 العودة للجزء", callback_data=f"juz_{juz_number}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        juz_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def continue_juz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """متابعة قراءة الجزء"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    juz_number = int(data[2])
    surah_id = int(data[3])
    verse_number = int(data[4])
    
    # جلب بيانات الجزء
    url = f"{BASE_URL}/juz/{juz_number}/ar.alafasy"
    data = await fetch_json(url)
    
    if not data or data.get('code') != 200 or 'data' not in data:
        await query.edit_message_text("❌ خطأ في جلب بيانات الجزء")
        return
    
    juz_data = data['data']
    if not juz_data or 'ayahs' not in juz_data:
        await query.edit_message_text("❌ لا توجد آيات في هذا الجزء")
        return
    
    # إنشاء نص الجزء
    juz_text = f"📖 *الجزء {juz_number}*\n\n"
    
    # تجميع الآيات مع ذكر اسم السورة عند تغييرها
    current_surah = None
    found_start = False
    
    for ayah in juz_data['ayahs']:
        surah_num = ayah['surah']['number']
        verse_num = ayah['numberInSurah']
        verse_text = ayah['text']
        
        # تخطي الآيات حتى نصل إلى نقطة المتابعة
        if not found_start:
            if surah_num == surah_id and verse_num == verse_number:
                found_start = True
            else:
                continue
        
        # إذا تغيرت السورة، نكتب اسم السورة الجديدة
        if surah_num != current_surah:
            surah_info = await load_surah_info()
            surah_name = next((s['name'] for s in surah_info if s['number'] == surah_num), f"سورة {surah_num}")
            juz_text += f"\n*{surah_name}*\n\n"
            current_surah = surah_num
            
        juz_text += f"{verse_text} ﴿{verse_num}﴾ "
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(juz_text) > 3000:
            keyboard = [
                [InlineKeyboardButton("⬇️ المتابعة", callback_data=f"continue_juz_{juz_number}_{surah_num}_{verse_num}")],
                [InlineKeyboardButton("🔙 العودة للجزء", callback_data=f"juz_{juz_number}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                juz_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    # إضافة أزرار التنقل
    keyboard = [
        [InlineKeyboardButton("🔙 العودة للجزء", callback_data=f"juz_{juz_number}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        juz_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل العادية"""
    if not await subscription_required(update, context):
        return
    
    # التحقق من وضع البحث
    if context.user_data.get('search_mode'):
        await perform_search(update, context)
        return
    
    await update.message.reply_text(
        " مرحباً بك في *سُطورٌ من السَّماء* ☁️\n\n"
        "📖 استخدم الأزرار أدناه للتنقل بين الخدمات\n\n"
        "💡 /start للعودة للقائمة الرئيسية\n\n"
        "✨ استكشف عالم القرآن الكريم بلمسة زر",
        parse_mode=ParseMode.MARKDOWN
    )

def main():
    """الدالة الرئيسية"""
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # تشغيل البوت
    logger.info("🚀 بدء تشغيل البوت...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()