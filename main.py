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
    'search_results': {}
}

async def fetch_json(url, headers=None):
    """جلب بيانات JSON من URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=15) as response:
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
            async with session.post(url, data=data, headers=headers, timeout=15) as response:
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
        if 'surah_list' in moshaf and str(surah_number) in moshaf['surah_list']:
            server = moshaf.get('server')
            if server:
                # تنسيق رقم السورة (001, 002, ... 114)
                surah_str = str(surah_number).zfill(3)
                return f"{server}{surah_str}.mp3"
    
    return None

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
            "• آيات قرآنية يومية\n"
            "• تفسيرات مختارة\n"
            "• أدعية وأذكار\n"
            "• محتوى إسلامي مميز\n\n"
            "🤲 بارك الله فيك",
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

📖 *سُطورٌ من السَّماء* ☁️

🕊️ *بوت شامل للقرآن الكريم*

✨ *الخدمات المتاحة:*
• 📖 تصفح المصحف الكامل
• 🔍 البحث في الآيات
• 📚 تصفح الأجزاء والأحزاب
• 🎵 الاستماع للتلاوات
• 📝 معلومات تفصيلية عن السور

🤲 *بارك الله فيك وجعل القرآن ربيع قلبك*
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
            "🌟 مرحباً بك في سُطورٌ من السَّماء ☁️\n\n"
            "استخدم الأزرار أدناه للتنقل:",
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
        "🌟 *سُطورٌ من السَّماء* ☁️\n\n"
        "📖 *اختر الخدمة التي تريدها:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_quran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح المصحف"""
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
        f"📖 *المصحف الشريف*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n"
        f"🔢 السور {start_idx + 1} - {end_idx}\n\n"
        f"اختر السورة التي تريد قراءتها:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من السور"""
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
        f"📖 *المصحف الشريف*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}\n"
        f"🔢 السور {start_idx + 1} - {end_idx}\n\n"
        f"اختر السورة التي تريد قراءتها:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def show_surah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سورة معينة"""
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
        [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_menu_{surah_number}")],
        [InlineKeyboardButton("📊 معلومات السورة", callback_data=f"info_surah_{surah_number}")],
        [InlineKeyboardButton("🔙 العودة للمصحف", callback_data="browse_quran")]
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
    """قراءة السورة كاملة"""
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
        [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_menu_{surah_number}")],
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
        [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_menu_{surah_number}")],
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
    
    data = query.data.split('_')
    surah_number = int(data[2]) if len(data) > 2 else None
    
    # جلب القُراء المتاحين
    reciters = await load_reciters()
    if not reciters:
        await query.edit_message_text("❌ لا يوجد قُراء متاحين حالياً، يرجى المحاولة لاحقاً")
        return
    
    keyboard = []
    for reciter in reciters:
        # التحقق من توفر السورة إذا كان معيناً
        if surah_number:
            # التحقق من توفر السورة لهذا القارئ
            available = False
            for moshaf in reciter.get('moshaf', []):
                if 'surah_list' in moshaf and str(surah_number) in moshaf['surah_list']:
                    available = True
                    break
            if not available:
                continue
        
        reciter_id = reciter['id']
        reciter_name = reciter['name']
        callback_data = f"reciter_{reciter_id}_{surah_number}" if surah_number else f"reciter_{reciter_id}"
        keyboard.append([InlineKeyboardButton(f"🎧 {reciter_name}", callback_data=callback_data)])
    
    if not keyboard:
        await query.edit_message_text("❌ لا يوجد قُراء متاحين لهذه السورة حالياً")
        return
    
    if surah_number:
        keyboard.append([InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")])
    else:
        keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if surah_number:
        surah_info = await load_surah_info()
        surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
        surah_name = surah_data['name'] if surah_data else f"سورة {surah_number}"
        message = f"🎵 *اختر قارئاً للاستماع لسورة {surah_name}:*"
    else:
        message = "🎵 *اختر القارئ الذي تريد الاستماع إليه:*"
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def play_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل تلاوة السورة"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    reciter_id = int(data[1])
    surah_number = int(data[2]) if len(data) > 2 else None
    
    if not surah_number:
        # إذا لم يتم تحديد سورة، عرض قائمة السور
        await browse_quran_for_audio(update, context, reciter_id)
        return
    
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
    
    # إرسال ملف الصوت
    try:
        await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=audio_url,
            caption=f"🎧 سورة {surah_name} بصوت {reciter_name}",
            title=f"سورة {surah_name}",
            performer=reciter_name,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة للقارئين", callback_data=f"audio_menu_{surah_number}")]
            ])
        )
        
        # حذف رسالة "جاري التحميل"
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)
    except Exception as e:
        logger.error(f"خطأ في إرسال الصوت: {e}")
        await query.edit_message_text("❌ حدث خطأ أثناء إرسال التلاوة. يرجى المحاولة لاحقاً.")

async def browse_quran_for_audio(update: Update, context: ContextTypes.DEFAULT_TYPE, reciter_id: int):
    """تصفح المصحف لاختيار سورة للتلاوة"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السور")
        return
    
    # جلب معلومات القارئ
    reciters = await load_reciters()
    reciter = next((r for r in reciters if r['id'] == reciter_id), None)
    if not reciter:
        await query.edit_message_text("❌ لم يتم العثور على معلومات القارئ")
        return
    
    reciter_name = reciter['name']
    
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
        # التحقق من توفر السورة للقارئ
        available = False
        for moshaf in reciter.get('moshaf', []):
            if 'surah_list' in moshaf and str(surah['number']) in moshaf['surah_list']:
                available = True
                break
        
        if available:
            button_text = f"{surah['number']}. {surah['name']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"audio_surah_{reciter_id}_{surah['number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"audio_page_{reciter_id}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"audio_page_{reciter_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 العودة للقارئين", callback_data="audio_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🎵 *اختر سورة للاستماع بصوت {reciter_name}*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def audio_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من السور للصوتيات"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    reciter_id = int(data[2])
    page = int(data[3])
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السور")
        return
    
    # جلب معلومات القارئ
    reciters = await load_reciters()
    reciter = next((r for r in reciters if r['id'] == reciter_id), None)
    if not reciter:
        await query.edit_message_text("❌ لم يتم العثور على معلومات القارئ")
        return
    
    reciter_name = reciter['name']
    
    surahs_per_page = 10
    total_pages = (len(surah_info) + surahs_per_page - 1) // surahs_per_page
    
    start_idx = page * surahs_per_page
    end_idx = min(start_idx + surahs_per_page, len(surah_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        surah = surah_info[i]
        # التحقق من توفر السورة للقارئ
        available = False
        for moshaf in reciter.get('moshaf', []):
            if 'surah_list' in moshaf and str(surah['number']) in moshaf['surah_list']:
                available = True
                break
        
        if available:
            button_text = f"{surah['number']}. {surah['name']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"audio_surah_{reciter_id}_{surah['number']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"audio_page_{reciter_id}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"audio_page_{reciter_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🔙 العودة للقارئين", callback_data="audio_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🎵 *اختر سورة للاستماع بصوت {reciter_name}*\n\n"
        f"📄 الصفحة {page + 1} من {total_pages}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def search_quran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية البحث"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔍 *البحث في القرآن الكريم*\n\n"
        "اكتب الكلمة أو الجملة التي تريد البحث عنها:",
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
    msg = await update.message.reply_text("🔍 جاري البحث في القرآن الكريم...")
    
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
    
    message = f"🔍 *نتائج البحث عن: \"{query}\"*\n\n"
    message += f"{results}\n\n"
    message += "🌟 *يمكنك البحث مرة أخرى باستخدام /search*"
    
    keyboard = [
        [InlineKeyboardButton("🔍 بحث جديد", callback_data="search_quran")],
        [InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        # حذف رسالة "جاري البحث" أولاً
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    await start_from_callback(query, context)

async def surah_info(update: Update, context: ContextTypes.DEFAULT_TYPE, surah_number: int):
    """عرض معلومات السورة"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل معلومات السور")
        return
    
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    if not surah_data:
        await query.edit_message_text("❌ لم يتم العثور على السورة")
        return
    
    # جلب تفسير قصير للسورة
    tafsir_url = f"{BASE_URL}/surah/{surah_number}/ar.maududi"
    tafsir_data = await fetch_json(tafsir_url)
    
    tafsir_text = ""
    if tafsir_data and tafsir_data.get('code') == 200 and 'data' in tafsir_data:
        if 'tafsir' in tafsir_data['data'] and 'id' in tafsir_data['data']['tafsir']:
            tafsir_text = tafsir_data['data']['tafsir']['id']['long']
    
    message = f"📖 *{surah_data['name']} ({surah_data['englishName']})*\n\n"
    message += f"*رقم السورة:* {surah_data['number']}\n"
    message += f"*عدد الآيات:* {surah_data['numberOfAyahs']}\n"
    message += f"*نوع النزول:* {surah_data['revelationType']}\n"
    message += f"*الترتيب في النزول:* {surah_data['revelationOrder']}\n\n"
    
    if tafsir_text:
        # اختصار التفسير إذا كان طويلاً
        if len(tafsir_text) > 1000:
            tafsir_text = tafsir_text[:1000] + "..."
        message += f"*نبذة تفسيرية:*\n{tafsir_text}\n"
    
    keyboard = [
        [InlineKeyboardButton("📖 قراءة السورة", callback_data=f"read_surah_{surah_number}")],
        [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_menu_{surah_number}")],
        [InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

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

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الـ callback queries"""
    query = update.callback_query
    
    if query.data == "check_subscription":
        await check_subscription_callback(update, context)
    elif query.data == "browse_quran":
        await browse_quran(update, context)
    elif query.data.startswith("quran_page_"):
        await browse_page(update, context)
    elif query.data == "browse_juz":
        await browse_juz(update, context)
    elif query.data.startswith("juz_page_"):
        await browse_juz_page(update, context)
    elif query.data.startswith("surah_"):
        await show_surah(update, context)
    elif query.data.startswith("read_surah_"):
        await read_surah(update, context)
    elif query.data.startswith("continue_surah_"):
        await continue_reading(update, context)
    elif query.data.startswith("juz_"):
        await show_juz(update, context)
    elif query.data == "audio_menu":
        await audio_menu(update, context)
    elif query.data.startswith("audio_menu_"):
        await audio_menu(update, context)
    elif query.data.startswith("reciter_"):
        await play_audio(update, context)
    elif query.data.startswith("audio_page_"):
        await audio_page(update, context)
    elif query.data.startswith("audio_surah_"):
        await play_audio(update, context)
    elif query.data == "search_quran":
        await search_quran(update, context)
    elif query.data == "main_menu":
        await main_menu(update, context)
    elif query.data.startswith("info_surah_"):
        surah_number = int(query.data.split('_')[2])
        await surah_info(update, context, surah_number)
    elif query.data.startswith("read_juz_"):
        juz_number = int(query.data.split('_')[2])
        await read_juz(update, context, juz_number)
    elif query.data.startswith("continue_juz_"):
        await continue_juz(update, context)
    else:
        await query.answer("هذه الميزة قيد التطوير! 🚧")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل العادية"""
    if not await subscription_required(update, context):
        return
    
    # التحقق من وضع البحث
    if context.user_data.get('search_mode'):
        await perform_search(update, context)
        return
    
    await update.message.reply_text(
        "🌟 مرحباً بك في *سُطورٌ من السَّماء* ☁️\n\n"
        "📖 استخدم الأزرار أدناه للتنقل بين الخدمات\n\n"
        "💡 /start للعودة للقائمة الرئيسية",
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
