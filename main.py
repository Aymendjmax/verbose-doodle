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
import re

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

# تحويل CHANNEL_ID إلى عدد صحيح
if CHANNEL_ID:
    CHANNEL_ID = int(CHANNEL_ID)
else:
    logger.error("يجب تعيين CHANNEL_ID في المتغيرات البيئية")
    exit(1)

# Quran.com API
BASE_URL = "https://api.quran.com/api/v4"

# قائمة القراء المتاحين
RECITERS = {
    7: "عبد الباسط عبد الصمد",
    8: "محمد صديق المنشاوي",
    9: "محمود خليل الحصري",
    10: "مشاري العفاسي",
    11: "أحمد بن علي العجمي"
}

# روابط الصوتيات (استخدام Quran.com API)
def get_audio_url(reciter_id, surah_number):
    return f"{BASE_URL}/chapter_recitations/{reciter_id}/{surah_number}"

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
    'search_results': {}
}

async def fetch_json(url):
    """جلب بيانات JSON من URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=15) as response:
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

async def load_surah_info():
    """تحميل معلومات السور"""
    if cache['surah_info'] is None:
        url = f"{BASE_URL}/chapters?language=ar"
        data = await fetch_json(url)
        if data and 'chapters' in data:
            cache['surah_info'] = data['chapters']
        else:
            logger.error("فشل في تحميل معلومات السور")
    return cache['surah_info']

async def load_juz_info():
    """تحميل معلومات الأجزاء"""
    if cache['juz_info'] is None:
        url = f"{BASE_URL}/juzs"
        data = await fetch_json(url)
        if data and 'juzs' in data:
            cache['juz_info'] = data['juzs']
        else:
            logger.error("فشل في تحميل معلومات الأجزاء")
    return cache['juz_info']

async def load_surah_data(surah_number):
    """تحميل بيانات سورة معينة"""
    if surah_number not in cache['surah_data']:
        url = f"{BASE_URL}/verses/by_chapter/{surah_number}?language=ar&words=false"
        data = await fetch_json(url)
        if data and 'verses' in data:
            verses = {}
            for verse in data['verses']:
                verse_number = verse['verse_number']
                verses[verse_number] = verse['text_uthmani']
            cache['surah_data'][surah_number] = verses
        else:
            logger.error(f"فشل في تحميل بيانات سورة {surah_number}")
    return cache['surah_data'].get(surah_number, {})

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
        [InlineKeyboardButton("📚 الأجزاء", callback_data="juz_list"), 
         InlineKeyboardButton("🎵 الصوتيات", callback_data="audio_menu")],
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
        [InlineKeyboardButton("📚 الأجزاء", callback_data="juz_list"), 
         InlineKeyboardButton("🎵 الصوتيات", callback_data="audio_menu")],
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
        button_text = f"{surah['id']}. {surah['name_arabic']} ({surah['verses_count']} آية)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"surah_{surah['id']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"browse_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"browse_page_{page+1}"))
    
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
        button_text = f"{surah['id']}. {surah['name_arabic']} ({surah['verses_count']} آية)"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"surah_{surah['id']}")])
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"browse_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ التالي", callback_data=f"browse_page_{page+1}"))
    
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
    surah_info = await load_surah_info()
    
    if not surah_data or not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السورة")
        return
    
    # الحصول على معلومات السورة
    surah_info_data = next((s for s in surah_info if s['id'] == surah_number), None)
    if not surah_info_data:
        await query.edit_message_text("❌ لم يتم العثور على معلومات السورة")
        return
    
    keyboard = [
        [InlineKeyboardButton("📖 قراءة السورة", callback_data=f"read_surah_{surah_number}")],
        [InlineKeyboardButton("🎵 الاستماع", callback_data=f"audio_menu_{surah_number}")],
        [InlineKeyboardButton("📊 معلومات السورة", callback_data=f"info_surah_{surah_number}")],
        [InlineKeyboardButton("🔙 العودة للمصحف", callback_data="browse_quran")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
📖 *{surah_info_data['name_arabic']}*

🔢 *رقم السورة:* {surah_number}
📍 *مكان النزول:* {surah_info_data['revelation_place'].capitalize()}
📝 *عدد الآيات:* {surah_info_data['verses_count']}

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
    surah_info = await load_surah_info()
    
    if not surah_data or not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السورة")
        return
    
    surah_info_data = next((s for s in surah_info if s['id'] == surah_number), None)
    if not surah_info_data:
        await query.edit_message_text("❌ لم يتم العثور على معلومات السورة")
        return
    
    # إنشاء نص السورة
    surah_text = f"📖 *{surah_info_data['name_arabic']}*\n\n"
    
    # إضافة البسملة للسور (عدا التوبة)
    if surah_number != 9:
        surah_text += "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ\n\n"
    
    verse_count = 0
    
    for verse_number, verse_text in surah_data.items():
        verse_count += 1
        surah_text += f"{verse_text} ﴿{verse_number}﴾\n\n"
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(surah_text) > 3500:
            keyboard = [[InlineKeyboardButton("⬇️ المتابعة", callback_data=f"continue_surah_{surah_number}_{verse_number}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                surah_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    # إضافة أزرار التنقل
    keyboard = [
        [InlineKeyboardButton("🎵 الاستماع", callback_data=f"audio_menu_{surah_number}")],
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
    surah_info = await load_surah_info()
    
    if not surah_data or not surah_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات السورة")
        return
    
    surah_info_data = next((s for s in surah_info if s['id'] == surah_number), None)
    if not surah_info_data:
        await query.edit_message_text("❌ لم يتم العثور على معلومات السورة")
        return
    
    # إنشاء نص السورة من الآية المحددة
    surah_text = f"📖 *{surah_info_data['name_arabic']}*\n\n"
    
    # فرز الآيات حسب أرقامها
    sorted_verses = sorted(surah_data.items(), key=lambda x: int(x[0]))
    
    # بدء من الآية المحددة
    for verse_number, verse_text in sorted_verses:
        if int(verse_number) < start_verse:
            continue
            
        surah_text += f"{verse_text} ﴿{verse_number}﴾\n\n"
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(surah_text) > 3500:
            keyboard = [[InlineKeyboardButton("⬇️ المتابعة", callback_data=f"continue_surah_{surah_number}_{verse_number}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                surah_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    # إضافة أزرار التنقل
    keyboard = [
        [InlineKeyboardButton("🎵 الاستماع", callback_data=f"audio_menu_{surah_number}")],
        [InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        surah_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def juz_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الأجزاء"""
    query = update.callback_query
    await query.answer()
    
    juz_info = await load_juz_info()
    if not juz_info:
        await query.edit_message_text("❌ خطأ في تحميل بيانات الأجزاء")
        return
    
    keyboard = []
    for juz in juz_info:
        juz_number = int(juz['juz_number'])
        button_text = f"الجزء {juz_number} - {juz['name_arabic']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"juz_{juz_number}")])
    
    keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📚 *أجزاء القرآن الكريم*\n\n"
        "اختر الجزء الذي تريد تصفحه:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def audio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الصوتيات"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    surah_number = int(data[2]) if len(data) > 2 else None
    
    keyboard = []
    for reciter_id, reciter_name in RECITERS.items():
        callback_data = f"reciter_{reciter_id}_{surah_number}" if surah_number else f"reciter_{reciter_id}"
        keyboard.append([InlineKeyboardButton(reciter_name, callback_data=callback_data)])
    
    if surah_number:
        keyboard.append([InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")])
    else:
        keyboard.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎵 *اختر القارئ:*",
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
    
    surah_info_data = next((s for s in surah_info if s['id'] == surah_number), None)
    if not surah_info_data:
        await query.edit_message_text("❌ لم يتم العثور على معلومات السورة")
        return
    
    surah_name = surah_info_data['name_arabic']
    reciter_name = RECITERS.get(reciter_id, "القارئ")
    
    # جلب روابط الصوتيات من Quran.com API
    audio_url = f"{BASE_URL}/chapter_recitations/{reciter_id}/{surah_number}"
    audio_data = await fetch_json(audio_url)
    
    if not audio_data or 'audio_files' not in audio_data:
        await query.edit_message_text("❌ خطأ في جلب روابط الصوتيات")
        return
    
    # إرسال ملف الصوت
    try:
        # نختار أول ملف صوتي متاح
        audio_file = audio_data['audio_files'][0]
        file_url = audio_file.get('url')
        if not file_url:
            await query.edit_message_text("❌ رابط الصوت غير متوفر")
            return
            
        await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=file_url,
            caption=f"🎧 سورة {surah_name} بصوت {reciter_name}",
            title=f"سورة {surah_name}",
            performer=reciter_name,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 العودة للقارئين", callback_data=f"audio_menu_{surah_number}")]
            ])
        )
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
        button_text = f"{surah['id']}. {surah['name_arabic']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"audio_surah_{reciter_id}_{surah['id']}")])
    
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
        f"🎵 *اختر سورة للاستماع بصوت {RECITERS.get(reciter_id, 'القارئ')}*\n\n"
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
    
    surahs_per_page = 10
    total_pages = (len(surah_info) + surahs_per_page - 1) // surahs_per_page
    
    start_idx = page * surahs_per_page
    end_idx = min(start_idx + surahs_per_page, len(surah_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        surah = surah_info[i]
        button_text = f"{surah['id']}. {surah['name_arabic']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"audio_surah_{reciter_id}_{surah['id']}")])
    
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
        f"🎵 *اختر سورة للاستماع بصوت {RECITERS.get(reciter_id, 'القارئ')}*\n\n"
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
    """تنفيذ البحث في القرآن"""
    search_text = update.message.text.strip()
    
    if len(search_text) < 3:
        await update.message.reply_text("🔍 يرجى إدخال كلمة مكونة من 3 أحرف على الأقل")
        return
    
    # مسح حالة البحث
    context.user_data.pop('search_mode', None)
    
    # إعلام المستخدم بأن البحث جاري
    await update.message.reply_text("🔍 جاري البحث في القرآن الكريم...")
    
    # جلب بيانات البحث من Quran.com API
    url = f"{BASE_URL}/search?q={search_text}&language=ar"
    search_result = await fetch_json(url)
    
    if not search_result or 'search' not in search_result:
        await update.message.reply_text("❌ لم يتم العثور على نتائج تطابق بحثك")
        return
    
    results = []
    surah_info = await load_surah_info()
    
    for result in search_result['search']['results']:
        # استخراج رقم السورة والآية من verse_key
        verse_key = result.get('verse_key', '')
        parts = verse_key.split(':')
        if len(parts) < 2:
            continue
            
        surah_number = int(parts[0])
        verse_number = int(parts[1])
        
        # الحصول على اسم السورة
        surah_name = next((s['name_arabic'] for s in surah_info if s['id'] == surah_number), f"سورة {surah_number}")
        
        results.append({
            'surah': surah_number,
            'verse': verse_number,
            'text': result.get('text', ''),
            'surah_name': surah_name
        })
    
    if not results:
        await update.message.reply_text("❌ لم يتم العثور على نتائج تطابق بحثك")
        return
    
    # حفظ النتائج في الذاكرة المؤقتة
    cache['search_results'][update.message.chat_id] = {
        'results': results,
        'page': 0,
        'query': search_text
    }
    
    # عرض الصفحة الأولى من النتائج
    await show_search_results(update, context)

async def show_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض نتائج البحث"""
    chat_id = update.callback_query.message.chat_id if update.callback_query else update.message.chat_id
    search_data = cache['search_results'].get(chat_id)
    
    if not search_data:
        await (update.callback_query or update.message).edit_message_text("❌ لم يتم العثور على بيانات البحث")
        return
    
    results = search_data['results']
    page = search_data['page']
    query = search_data['query']
    results_per_page = 5
    
    start_idx = page * results_per_page
    end_idx = min(start_idx + results_per_page, len(results))
    
    message = f"🔍 *نتائج البحث عن: \"{query}\"*\n\n"
    
    for i in range(start_idx, end_idx):
        result = results[i]
        message += f"*{result['surah_name']} ({result['surah']}:{result['verse']})*\n"
        message += f"{result['text']}\n\n"
    
    message += f"الصفحة {page + 1} من {(len(results) + results_per_page - 1) // results_per_page}"
    
    keyboard = []
    
    # أزرار التنقل
    if page > 0:
        keyboard.append(InlineKeyboardButton("⬅️ السابق", callback_data="search_prev"))
    if end_idx < len(results):
        keyboard.append(InlineKeyboardButton("➡️ التالي", callback_data="search_next"))
    
    if keyboard:
        keyboard_buttons = [keyboard]
    else:
        keyboard_buttons = []
    
    keyboard_buttons.append([InlineKeyboardButton("🔍 بحث جديد", callback_data="search_quran")])
    keyboard_buttons.append([InlineKeyboardButton("🏠 العودة للرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def navigate_search_results(update: Update, context: ContextTypes.DEFAULT_TYPE, direction: str):
    """التنقل بين صفحات نتائج البحث"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    search_data = cache['search_results'].get(chat_id)
    
    if not search_data:
        await query.edit_message_text("❌ لم يتم العثور على بيانات البحث")
        return
    
    if direction == "next":
        search_data['page'] += 1
    elif direction == "prev":
        search_data['page'] -= 1
    
    await show_search_results(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية"""
    query = update.callback_query
    await query.answer()
    
    await start_from_callback(query, context)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الـ callback queries"""
    query = update.callback_query
    
    if query.data == "check_subscription":
        await check_subscription_callback(update, context)
    elif query.data == "browse_quran":
        await browse_quran(update, context)
    elif query.data.startswith("browse_page_"):
        await browse_page(update, context)
    elif query.data.startswith("surah_"):
        await show_surah(update, context)
    elif query.data.startswith("read_surah_"):
        await read_surah(update, context)
    elif query.data.startswith("continue_surah_"):
        await continue_reading(update, context)
    elif query.data == "juz_list":
        await juz_list(update, context)
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
    elif query.data == "search_next":
        await navigate_search_results(update, context, "next")
    elif query.data == "search_prev":
        await navigate_search_results(update, context, "prev")
    elif query.data == "main_menu":
        await main_menu(update, context)
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
