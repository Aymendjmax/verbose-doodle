import os
import json
import logging
import asyncio
import aiohttp
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    ContextTypes, MessageHandler, filters
)
from telegram.constants import ParseMode, ChatAction
from flask import Flask, jsonify, render_template_string
import threading
import time
import sys
import socket

# إعداد التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# متغيرات البيئة
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN غير موجود! الرجاء تعيينه في متغيرات البيئة")
    sys.exit(1)

CHANNEL_ID = os.getenv('CHANNEL_ID')
DEVELOPER_USERNAME = os.getenv('DEVELOPER_USERNAME', 'your_developer_username')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', 'your_channel_username')
PORT = int(os.getenv('PORT', 5000))
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL', '')

# تغيير API الذكاء الاصطناعي إلى Google Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
if not GEMINI_API_KEY:
    logger.warning("⚠️ GEMINI_API_KEY غير موجود - ميزة البحث الذكي غير متاحة")
else:
    logger.info("✅ GEMINI_API_KEY موجود - البحث الذكي متاح")

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# الحصول على عنوان الويب تلقائياً
if RENDER_EXTERNAL_URL:
    BASE_WEB_URL = RENDER_EXTERNAL_URL.rstrip('/')
    logger.info(f"🌐 استخدام عنوان Render: {BASE_WEB_URL}")
else:
    try:
        # محاولة الحصول على عنوان IP
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        BASE_WEB_URL = f"http://{local_ip}:{PORT}"
        logger.info(f"🌐 استخدام العنوان المحلي: {BASE_WEB_URL}")
    except:
        BASE_WEB_URL = f"http://localhost:{PORT}"
        logger.info(f"🌐 استخدام localhost: {BASE_WEB_URL}")

# تحويل CHANNEL_ID إلى عدد صحيح
if CHANNEL_ID:
    try:
        CHANNEL_ID = int(CHANNEL_ID)
    except ValueError:
        logger.error(f"CHANNEL_ID غير صالح: {CHANNEL_ID}")
        CHANNEL_ID = 0
else:
    logger.warning("CHANNEL_ID غير موجود في المتغيرات البيئية")
    CHANNEL_ID = 0

# Quran API من alquran.vip
BASE_URL = "https://api.alquran.cloud/v1"

# API الصوتيات الجديد
RECITERS_API_URL = "https://quran.yousefheiba.com/api/reciters"
RECITER_AUDIO_API_URL = "https://quran.yousefheiba.com/api/reciterAudio?reciter_id={reciter_id}"
SURAH_AUDIO_API_URL = "https://quran.yousefheiba.com/api/surahAudio?reciter={reciter_short_name}&id={surah_id}"
QURAN_PAGES_IMAGE_API = "https://quran.yousefheiba.com/api/quranPagesImage"

# ترتيب السور في المصحف المصور
SURAH_PAGES_MAPPING = {
    1: (1, 1), 2: (2, 49), 3: (50, 76), 4: (77, 106), 5: (106, 127),
    6: (128, 150), 7: (151, 176), 8: (177, 186), 9: (187, 207), 10: (208, 221),
    11: (221, 235), 12: (235, 248), 13: (249, 255), 14: (255, 261), 15: (262, 267),
    16: (267, 281), 17: (282, 293), 18: (293, 304), 19: (305, 312), 20: (312, 321),
    21: (322, 331), 22: (332, 341), 23: (342, 349), 24: (350, 358), 25: (359, 366),
    26: (367, 376), 27: (377, 385), 28: (385, 396), 29: (396, 404), 30: (404, 410),
    31: (411, 414), 32: (415, 417), 33: (418, 427), 34: (428, 434), 35: (434, 440),
    36: (440, 445), 37: (446, 452), 38: (453, 458), 39: (458, 467), 40: (467, 476),
    41: (477, 482), 42: (483, 488), 43: (489, 495), 44: (496, 498), 45: (499, 502),
    46: (502, 506), 47: (507, 510), 48: (511, 514), 49: (515, 517), 50: (518, 520),
    51: (520, 523), 52: (523, 525), 53: (526, 528), 54: (528, 531), 55: (531, 534),
    56: (534, 537), 57: (537, 541), 58: (542, 545), 59: (545, 548), 60: (549, 551),
    61: (551, 552), 62: (553, 554), 63: (554, 555), 64: (556, 557), 65: (558, 559),
    66: (560, 561), 67: (562, 564), 68: (564, 566), 69: (566, 568), 70: (568, 570),
    71: (570, 571), 72: (572, 573), 73: (574, 575), 74: (575, 577), 75: (577, 578),
    76: (578, 580), 77: (580, 581), 78: (582, 583), 79: (583, 584), 80: (585, 585),
    81: (586, 586), 82: (587, 587), 83: (587, 589), 84: (589, 590), 85: (590, 591),
    86: (591, 591), 87: (592, 592), 88: (592, 593), 89: (593, 594), 90: (594, 595),
    91: (595, 595), 92: (595, 596), 93: (596, 596), 94: (596, 596), 95: (597, 597),
    96: (597, 598), 97: (598, 598), 98: (598, 599), 99: (599, 599), 100: (599, 600),
    101: (600, 600), 102: (600, 600), 103: (601, 601), 104: (601, 601), 105: (601, 602),
    106: (602, 602), 107: (602, 602), 108: (602, 602), 109: (603, 603), 110: (603, 603),
    111: (603, 603), 112: (604, 604), 113: (604, 604), 114: (604, 604)
}

# Flask app للـ ping
app = Flask(__name__)

@app.route('/')
def ping():
    return jsonify({
        "status": "البوت يعمل بنجاح! 🕊️", 
        "bot": "سُطورٌ من السَّماء ☁️",
        "services": {
            "quran_text": "متاح",
            "quran_images": "متاح",
            "radio": "متاح",
            "search": "متاح" if GEMINI_API_KEY else "غير متاح",
            "audio": "متاح",
            "juz": "متاح"
        }
    })

@app.route('/radio')
def radio():
    """صفحة الراديو المباشر"""
    return render_template_string(RADIO_HTML)

@app.route('/health')
def health():
    return jsonify({"health": "ok", "timestamp": time.time()})

def run_bot():
    """تشغيل البوت في thread منفصل"""
    # إنشاء التطبيق
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # تشغيل البوت
    logger.info("🚀 بدء تشغيل البوت سُطورٌ من السَّماء...")
    logger.info(f"🌐 الراديو: {BASE_WEB_URL}/radio")
    logger.info(f"🔍 البحث الذكي: {'✅ متاح' if GEMINI_API_KEY else '❌ غير متاح'}")
    logger.info("📖 المصحف الشريف جاهز")
    logger.info("📻 الراديو المباشر يعمل")
    logger.info("🎵 مكتبة التلاوات متاحة")
    logger.info("🤖 البوت يعمل بكامل طاقته!")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# الثوابت للـ Callback Data
CALLBACK_MAIN_MENU = "main_menu"
CALLBACK_CHECK_SUBSCRIPTION = "check_subscription"
CALLBACK_BROWSE_QURAN_TEXT = "browse_quran_text"
CALLBACK_BROWSE_QURAN_IMAGES = "browse_quran_images"
CALLBACK_SEARCH_QURAN = "search_quran"
CALLBACK_BROWSE_JUZ = "browse_juz"
CALLBACK_AUDIO_MENU = "audio_menu"

# الذاكرة المؤقتة للبيانات مع الطابع الزمني
cache = {
    'surah_info': {'data': None, 'timestamp': 0},
    'juz_info': {'data': None, 'timestamp': 0},
    'reciters': {'data': None, 'timestamp': 0},
    'surah_data': {},
    'search_results': {}
}

# مدة صلاحية الذاكرة المؤقتة (24 ساعة)
CACHE_EXPIRY = 86400

# HTML للراديو مباشرة في الكود
RADIO_HTML = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>راديو سطور من السماء - بث مباشر</title>
    <link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Tajawal:wght@300;400;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --primary-blue: #1e69b5;
            --light-blue: #4a90e2;
            --sky-blue: #87ceeb;
            --white: #ffffff;
            --glass-bg: rgba(255, 255, 255, 0.1);
            --glass-border: rgba(255, 255, 255, 0.2);
            --accent-glow: rgba(255, 255, 255, 0.5);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Tajawal', sans-serif;
            background: radial-gradient(circle at center, #1e4d8c 0%, #0d2a4d 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
            color: var(--white);
            position: relative;
            padding: 20px;
        }

        /* Background Canvas */
        #starCanvas {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 0;
        }

        .container {
            position: relative;
            z-index: 10;
            background: rgba(255, 255, 255, 0.08);
            backdrop-filter: blur(25px);
            -webkit-backdrop-filter: blur(25px);
            border: 1px solid var(--glass-border);
            border-radius: 30px;
            padding: 30px 25px;
            width: 100%;
            max-width: 400px;
            text-align: center;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
            animation: fadeIn 0.5s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .logo-container {
            margin-bottom: 20px;
        }

        .logo-circle {
            width: 150px;
            height: 150px;
            margin: 0 auto;
            border-radius: 50%;
            border: 3px solid rgba(255, 255, 255, 0.3);
            padding: 5px;
            background: rgba(255, 255, 255, 0.05);
            position: relative;
            transition: all 0.4s ease;
            overflow: hidden;
        }

        .logo-circle.playing {
            animation: pulseGlow 2s infinite;
            border-color: var(--white);
        }

        @keyframes pulseGlow {
            0% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.3); }
            70% { box-shadow: 0 0 0 15px rgba(255, 255, 255, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 255, 255, 0); }
        }

        .logo-circle img {
            width: 100%;
            height: 100%;
            border-radius: 50%;
            object-fit: cover;
            display: block;
        }

        h1 {
            font-family: 'Amiri', serif;
            font-size: 1.8rem;
            margin-bottom: 5px;
            text-shadow: 0 2px 10px rgba(0,0,0,0.3);
        }

        .subtitle {
            font-weight: 300;
            font-size: 0.9rem;
            margin-bottom: 25px;
            opacity: 0.7;
            letter-spacing: 1px;
        }
    </style>
</head>
<body>
    <canvas id="starCanvas"></canvas>
    <div class="container">
        <div class="logo-container">
            <div class="logo-circle" id="logoCircle">
                <img src="https://i.ibb.co/LzX6X6X/logo.png" alt="Logo">
            </div>
        </div>
        <h1>سُطورٌ من السَّماء</h1>
        <p class="subtitle">راديو القرآن الكريم - بث مباشر</p>
        <div class="controls-wrapper">
            <audio id="audioPlayer" src="https://qurango.net/radio/mix"></audio>
            <button id="playBtn" class="play-btn"><i class="fas fa-play"></i></button>
        </div>
    </div>
    <script>
        const audio = document.getElementById('audioPlayer');
        const playBtn = document.getElementById('playBtn');
        const logoCircle = document.getElementById('logoCircle');
        
        playBtn.addEventListener('click', () => {
            if (audio.paused) {
                audio.play();
                playBtn.innerHTML = '<i class="fas fa-pause"></i>';
                logoCircle.classList.add('playing');
            } else {
                audio.pause();
                playBtn.innerHTML = '<i class="fas fa-play"></i>';
                logoCircle.classList.remove('playing');
            }
        });
    </script>
</body>
</html>
'''

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
    """إرسال بيانات JSON إلى URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers, timeout=30) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"خطأ في إرسال البيانات إلى {url}: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"خطأ في الاتصال بـ {url}: {e}")
        return None

async def load_surah_info():
    """تحميل معلومات السور مع آلية انتهاء الصلاحية"""
    now = time.time()
    if cache['surah_info']['data'] is None or (now - cache['surah_info']['timestamp'] > CACHE_EXPIRY):
        url = f"{BASE_URL}/surah"
        data = await fetch_json(url)
        if data and data.get('code') == 200 and 'data' in data:
            cache['surah_info']['data'] = data['data']
            cache['surah_info']['timestamp'] = now
            logger.info("✅ تم تحديث بيانات السور بنجاح.")
        else:
            logger.error("فشل في تحميل معلومات السور")
    return cache['surah_info']['data']

async def load_juz_info():
    """تحميل معلومات الأجزاء مع آلية انتهاء الصلاحية"""
    now = time.time()
    if cache['juz_info']['data'] is None or (now - cache['juz_info']['timestamp'] > CACHE_EXPIRY):
        juzs = []
        for i in range(1, 31):
            juzs.append({
                "number": i,
                "name_arabic": f"الجزء {i}",
            })
        cache['juz_info']['data'] = juzs
        cache['juz_info']['timestamp'] = now
    return cache['juz_info']['data']

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
    """تحميل قائمة القراء مع آلية انتهاء الصلاحية"""
    now = time.time()
    if cache['reciters']['data'] is None or (now - cache['reciters']['timestamp'] > CACHE_EXPIRY):
        data = await fetch_json(RECITERS_API_URL)
        if data and 'reciters' in data:
            formatted_reciters = []
            for reciter in data['reciters']:
                formatted_reciters.append({
                    'id': int(reciter['reciter_id']),
                    'name': reciter['reciter_name'],
                    'short_name': reciter['reciter_short_name']
                })
            cache['reciters']['data'] = formatted_reciters
            cache['reciters']['timestamp'] = now
            logger.info("✅ تم تحديث قائمة القراء بنجاح.")
        else:
            logger.error("فشل في تحميل قائمة القراء")
    return cache['reciters']['data']

async def get_reciter_audio(reciter_id: int, surah_number: int):
    """الحصول على رابط الصوت للقارئ والسورة من API الجديد"""
    reciters = await load_reciters()
    if not reciters:
        return None
    reciter = next((r for r in reciters if r['id'] == reciter_id), None)
    if not reciter:
        return None
    url = SURAH_AUDIO_API_URL.format(reciter_short_name=reciter['short_name'], surah_id=surah_number)
    data = await fetch_json(url)
    if data and 'audio_url' in data:
        return data['audio_url']
    return None

async def create_paginated_keyboard(items, page, callback_prefix, items_per_page=10, extra_data=None):
    """دالة مساعدة لإنشاء لوحة مفاتيح مقسمة إلى صفحات"""
    total_pages = (len(items) + items_per_page - 1) // items_per_page
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(items))

    keyboard = []
    for i in range(start_idx, end_idx):
        item = items[i]
        if 'numberOfAyahs' in item: # للسور
            text = f"{item['number']}. {item['name']} ({item['numberOfAyahs']} آية)"
            callback = f"{callback_prefix}_{item['number']}"
        elif 'short_name' in item: # للقراء
            text = f"🎧 {item['name']}"
            callback = f"play_audio_{item['id']}_{extra_data}"
        elif 'name_arabic' in item and 'number' in item: # للأجزاء
            text = item['name_arabic']
            callback = f"{callback_prefix}_{item['number']}"
        else:
            text = str(item)
            callback = f"{callback_prefix}_{i}"
        keyboard.append([InlineKeyboardButton(text, callback_data=callback)])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابقة", callback_data=f"{callback_prefix}_page_{extra_data + '_' if extra_data else ''}{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالية ➡️", callback_data=f"{callback_prefix}_page_{extra_data + '_' if extra_data else ''}{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data=CALLBACK_MAIN_MENU)])
    return InlineKeyboardMarkup(keyboard), start_idx, end_idx, total_pages

async def check_user_subscription(user_id, context):
    """التحقق من اشتراك المستخدم في القناة"""
    if not CHANNEL_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start"""
    user = update.effective_user
    user_id = user.id
    
    # التحقق من الاشتراك
    if not await check_user_subscription(user_id, context):
        keyboard = [
            [InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data=CALLBACK_CHECK_SUBSCRIPTION)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"👋 أهلاً بك يا {user.first_name}!\n\n"
            f"لاستخدام البوت، يجب عليك الاشتراك في قناتنا أولاً لدعمنا واستمرار الخدمة.\n\n"
            f"📌 اشترك ثم اضغط على زر التحقق بالأسفل.",
            reply_markup=reply_markup
        )
        return

    # القائمة الرئيسية
    radio_button = InlineKeyboardButton(
        "📻 راديو سطور من السماء", 
        web_app={"url": f"{BASE_WEB_URL}/radio"}
    )
    
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف النصي", callback_data=CALLBACK_BROWSE_QURAN_TEXT)],
        [InlineKeyboardButton("🖼️ المصحف المصور عالي الجودة", callback_data=CALLBACK_BROWSE_QURAN_IMAGES)],
        [radio_button],
        [InlineKeyboardButton("🔍 بحث ذكي في القرآن", callback_data=CALLBACK_SEARCH_QURAN)],
        [InlineKeyboardButton("📚 تصفح الأجزاء والأحزاب", callback_data=CALLBACK_BROWSE_JUZ)],
        [InlineKeyboardButton("🎵 مكتبة التلاوات الصوتية", callback_data=CALLBACK_AUDIO_MENU)],
        [InlineKeyboardButton("👨‍💻 المطور & الدعم", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = f"""
🌟 **أهلاً بك في بوت "سُطورٌ من السَّماء"** ☁️

هذا البوت هو رفيقك الشامل لخدمة القرآن الكريم، حيث يجمع بين جمال التلاوة ودقة النص وتقنيات البحث الحديثة.

📖 **ماذا يقدم لك البوت؟**

✨ *المصحف الشريف:*
• نسخة نصية واضحة للقراءة والتدبر
• نسخة مصورة عالية الجودة (مصحف المدينة)
• تفسير ميسر لكل آية

📻 *البث المباشر:*
• راديو يعمل على مدار الساعة
• تلاوات مختارة لأجمل الأصوات
• واجهة ويب متطورة للاستماع

🎵 *المكتبة الصوتية:*
• مجموعة كبيرة من أشهر القراء العالميين
• جودة صوت عالية مع خيارات متعددة
• تحميل وتشغيل مباشر

📚 *تصفح مرن:*
• تصفح حسب الأجزاء والأحزاب
• تقسيم منطقي لتسهيل الختمة
• إمكانية القراءة المستمرة

🤖 *ميزات تقنية متقدمة:*
• سرعة استجابة عالية
• واجهة مستخدم بديهية
• تحديثات مستمرة وتحسينات

🤲 *"وَقَالَ الرَّسُولُ يَا رَبِّ إِنَّ قَوْمِي اتَّخَذُوا هَٰذَا الْقُرْآنَ مَهْجُورًا"* (الفرقان: 30)

💎 *نهدي لك هذا البوت لتكون القرآن رفيقك في كل وقت*

🚀 *اختر الخدمة التي تناسبك من القائمة أدناه:*
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
            "🌟 **أهلاً بك في عالم القرآن الكريم** ☁️\n\n"
            "تم تفعيل حسابك بنجاح! يمكنك الآن الاستمتاع بجميع ميزات البوت:\n\n"
            "• 📖 تصفح المصحف كاملاً\n"
            "• 📻 الاستماع للراديو المباشر\n"
            "• 🔍 البحث الذكي في الآيات\n"
            "• 🎵 مكتبة التلاوات الصوتية\n\n"
            "🚀 **اختر الخدمة التي تريدها:**",
            parse_mode=ParseMode.MARKDOWN
        )
        await asyncio.sleep(1)
        await start_from_callback(query, context)
    else:
        await query.edit_message_text(
            "❌ *لم يتم العثور على اشتراكك*\n\n"
            "يبدو أنك لم تشترك في القناة بعد.\n\n"
            "📌 **خطوات الاشتراك:**\n"
            "1. اضغط على زر 'اشترك في القناة'\n"
            "2. انتظر حتى يتم تحميل القناة\n"
            "3. اضغط على زر 'اشتراك' أو 'Join'\n"
            "4. عد للبوت واضغط على 'تحقق من الاشتراك'\n\n"
            "🔔 **ملاحظة:**\n"
            "إذا كنت مشتركاً بالفعل، قد تحتاج لتفعيل الإشعارات أو الانتظار قليلاً حتى يتم تحديث حالتك.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")],
                [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data=CALLBACK_CHECK_SUBSCRIPTION)]
            ])
        )

async def start_from_callback(query, context):
    """بدء القائمة الرئيسية من callback"""
    radio_button = InlineKeyboardButton(
        "📻 راديو سطور من السماء", 
        web_app={"url": f"{BASE_WEB_URL}/radio"}
    )
    
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف النصي", callback_data=CALLBACK_BROWSE_QURAN_TEXT)],
        [InlineKeyboardButton("🖼️ المصحف المصور عالي الجودة", callback_data=CALLBACK_BROWSE_QURAN_IMAGES)],
        [radio_button],
        [InlineKeyboardButton("🔍 بحث ذكي في القرآن", callback_data=CALLBACK_SEARCH_QURAN)],
        [InlineKeyboardButton("📚 تصفح الأجزاء والأحزاب", callback_data=CALLBACK_BROWSE_JUZ)],
        [InlineKeyboardButton("🎵 مكتبة التلاوات الصوتية", callback_data=CALLBACK_AUDIO_MENU)],
        [InlineKeyboardButton("👨‍💻 المطور & الدعم", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = """
✨ *سُطورٌ من السَّماء* ☁️

🕊️ **القائمة الرئيسية - اختر خدمتك المفضلة**

🌟 *خدماتنا المتكاملة:*

1️⃣ **المصحف الشامل:** تصفح كامل القرآن بنسختين
2️⃣ **الراديو المباشر:** بث مستمر لتلاوات عطرة
3️⃣ **البحث الذكي:** ابحث في الآيات بتقنية الذكاء الاصطناعي
4️⃣ **التلاوات الصوتية:** مكتبة شاملة لأجمل الأصوات
5️⃣ **الأجزاء والأحزاب:** تصفح منظم للقرآن الكريم

🚀 *اختر الخدمة التي تريدها من القائمة أدناه:*
    """
    
    try:
        if query.message.photo:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            await query.message.delete()
        else:
            await query.edit_message_text(
                text=message_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error in start_from_callback: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def browse_quran_text(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    """تصفح المصحف النصي"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور. يرجى المحاولة لاحقاً.")
        return
    
    reply_markup, start_idx, end_idx, total_pages = await create_paginated_keyboard(
        surah_info, page, "surah", items_per_page=10
    )
    
    await query.edit_message_text(
        f"📖 *المصحف الشريف - النسخة النصية*\n\n"
        f"📊 **الإحصائيات:**\n"
        f"• عدد السور: 114 سورة\n"
        f"• عدد الآيات: 6,236 آية\n"
        f"• عدد الأجزاء: 30 جزء\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🔢 **السور المعروضة:** {start_idx + 1} - {end_idx}\n\n"
        f"✨ **اختر السورة التي تريد قراءتها:**\n\n"
        f"💡 **ملاحظة:** يمكنك التنقل بين الصفحات باستخدام الأزرار أدناه",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من السور"""
    query = update.callback_query
    page = int(query.data.split('_')[-1])
    await browse_quran_text(update, context, page=page)

async def browse_quran_images(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    """تصفح المصحف المصور"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور.")
        return
    
    reply_markup, start_idx, end_idx, total_pages = await create_paginated_keyboard(
        surah_info, page, "quran_img", items_per_page=10
    )
    
    await query.edit_message_text(
        f"🖼️ *المصحف المصور عالي الجودة*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🔢 **السور المعروضة:** {start_idx + 1} - {end_idx}\n\n"
        f"✨ **اختر السورة لعرض صفحاتها المصورة:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_quran_images_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من المصحف المصور"""
    query = update.callback_query
    page = int(query.data.split('_')[-1])
    await browse_quran_images(update, context, page=page)

async def browse_juz(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    """تصفح الأجزاء"""
    query = update.callback_query
    await query.answer()
    
    juz_info = await load_juz_info()
    reply_markup, start_idx, end_idx, total_pages = await create_paginated_keyboard(
        juz_info, page, "juz", items_per_page=10
    )
    
    await query.edit_message_text(
        f"📚 *تصفح القرآن الكريم بالأجزاء*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"✨ **اختر الجزء الذي تريد تصفحه:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def browse_juz_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من الأجزاء"""
    query = update.callback_query
    page = int(query.data.split('_')[-1])
    await browse_juz(update, context, page=page)

async def audio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    """قائمة التلاوات الصوتية"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور.")
        return
    
    reply_markup, start_idx, end_idx, total_pages = await create_paginated_keyboard(
        surah_info, page, "audio_surah", items_per_page=10
    )
    
    await query.edit_message_text(
        "🎵 *مكتبة التلاوات الصوتية*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🔢 **السور المعروضة:** {start_idx + 1} - {end_idx}\n\n"
        "✨ **اختر سورة لتستمع إلى تلاوتها:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def audio_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من التلاوات"""
    query = update.callback_query
    page = int(query.data.split('_')[-1])
    await audio_menu(update, context, page=page)

async def show_reciters(update: Update, context: ContextTypes.DEFAULT_TYPE, surah_number=None, page=0):
    """عرض قائمة القراء لسورة محددة"""
    query = update.callback_query
    await query.answer()
    
    if surah_number is None:
        data = query.data.split('_')
        surah_number = int(data[2])
    
    reciters = await load_reciters()
    if not reciters:
        await query.edit_message_text("❌ **عذراً:** لا يوجد قُراء متاحين حالياً.")
        return
    
    reply_markup, start_idx, end_idx, total_pages = await create_paginated_keyboard(
        reciters, page, "reciters", items_per_page=10, extra_data=str(surah_number)
    )
    
    # إضافة زر البحث عن قارئ
    keyboard = list(reply_markup.inline_keyboard)
    keyboard.insert(-1, [InlineKeyboardButton("🔍 البحث عن قارئ محدد", callback_data=f"search_reciter_{surah_number}")])
    keyboard.insert(-1, [InlineKeyboardButton("🔙 العودة للسور", callback_data=CALLBACK_AUDIO_MENU)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    surah_info = await load_surah_info()
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    surah_name = surah_data['name'] if surah_data else f"سورة {surah_number}"
    
    await query.edit_message_text(
        f"🎵 *قائمة القراء لسورة {surah_name}*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🎤 **عدد القراء المتاحين:** {len(reciters)}\n\n"
        "✨ **اختر القارئ المفضل لديك:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def reciters_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحة معينة من القراء"""
    query = update.callback_query
    data = query.data.split('_')
    surah_number = int(data[2])
    page = int(data[3])
    await show_reciters(update, context, surah_number=surah_number, page=page)

async def send_quran_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال صفحة المصحف المصور"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    # quran_img_NUMBER
    surah_number = int(data[2])
    
    # الحصول على نطاق الصفحات للسورة
    page_range = SURAH_PAGES_MAPPING.get(surah_number)
    if not page_range:
        await query.edit_message_text("❌ **عذراً:** لم يتم العثور على صفحات لهذه السورة.")
        return
    
    start_page, end_page = page_range
    current_page = start_page
    
    await send_specific_quran_page(query, context, current_page, surah_number)

async def send_specific_quran_page(query, context, page_number, surah_number):
    """إرسال صفحة محددة من المصحف"""
    try:
        # إظهار حالة "يرسل صورة"
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_PHOTO)
        
        image_url = f"{QURAN_PAGES_IMAGE_API}?page={page_number}"
        
        # أزرار التنقل بين الصفحات
        page_range = SURAH_PAGES_MAPPING.get(surah_number)
        start_page, end_page = page_range
        
        keyboard = []
        nav_row = []
        if page_number > start_page:
            nav_row.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"view_page_{page_number-1}_{surah_number}"))
        if page_number < end_page:
            nav_row.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"view_page_{page_number+1}_{surah_number}"))
        
        if nav_row:
            keyboard.append(nav_row)
        
        keyboard.append([InlineKeyboardButton("🔙 العودة لقائمة السور", callback_data=CALLBACK_BROWSE_QURAN_IMAGES)])
        keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data=CALLBACK_MAIN_MENU)])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption = f"📖 **صفحة رقم {page_number}**\n\n✨ سورة رقم {surah_number}"
        
        from telegram import InputMediaPhoto
        try:
            if query.message.photo:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=image_url, caption=caption, parse_mode=ParseMode.MARKDOWN),
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=image_url,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
                await query.message.delete()
        except Exception as e:
            logger.error(f"Error editing/sending photo: {e}")
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=image_url,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            try: await query.message.delete()
            except: pass
            
    except Exception as e:
        logger.error(f"Error sending quran page: {e}")
        await query.message.reply_text(
            "⚠️ عذراً، حدث خطأ أثناء تحميل الصفحة. هل تريد المحاولة مرة أخرى؟",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 إعادة المحاولة", callback_data=f"view_page_{page_number}_{surah_number}")
            ]])
        )

async def play_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل تلاوة السورة"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    reciter_id = int(data[2])
    surah_number = int(data[3])
    
    surah_info = await load_surah_info()
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    
    await query.edit_message_text(f"⏳ جاري تحضير التلاوة لـ {surah_data['name']}... يرجى الانتظار.")
    
    audio_url = await get_reciter_audio(reciter_id, surah_number)
    if not audio_url:
        await query.edit_message_text("❌ **عذراً:** لم يتم العثور على رابط الصوت لهذه السورة.")
        return
    
    try:
        await context.bot.send_chat_action(chat_id=query.message.chat_id, action=ChatAction.UPLOAD_VOICE)
        
        keyboard = [
            [InlineKeyboardButton("🔙 العودة للقراء", callback_data=f"reciters_{surah_number}")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data=CALLBACK_MAIN_MENU)]
        ]
        
        await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=audio_url,
            caption=f"🎵 تلاوة سورة {surah_data['name']}\n✨ استماعاً طيباً",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.message.delete()
    except Exception as e:
        logger.error(f"Error playing audio: {e}")
        await query.message.reply_text("❌ فشل إرسال الملف الصوتي. قد يكون الرابط غير متاح حالياً.")

async def search_quran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية البحث"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 **البحث الذكي في القرآن الكريم**\n\n"
        "أرسل الكلمة أو الموضوع الذي تريد البحث عنه.\n"
        "مثال: 'آيات الصبر' أو 'الجنة' أو 'يا أيها الذين آمنوا'\n\n"
        "💡 سأقوم بالبحث في الآيات وتفسيرها باستخدام الذكاء الاصطناعي.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data=CALLBACK_MAIN_MENU)]])
    )
    context.user_data['state'] = 'searching'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    state = context.user_data.get('state')
    if state == 'searching':
        await perform_search(update, context)
    elif state == 'searching_reciter':
        await perform_reciter_search(update, context)

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ البحث باستخدام Gemini"""
    query_text = update.message.text
    if not GEMINI_API_KEY:
        await update.message.reply_text("❌ ميزة البحث الذكي غير متاحة حالياً.")
        return
    
    msg = await update.message.reply_text("🔍 جاري البحث والتحليل... يرجى الانتظار ⏳")
    
    prompt = f"""
    أنت مساعد خبير في القرآن الكريم. ابحث عن الآيات المتعلقة بـ: "{query_text}"
    يجب أن تكون النتائج دقيقة ومن المصحف الشريف.
    أرجع النتائج بتنسيق JSON فقط كقائمة من الكائنات، كل كائن يحتوي على:
    - surah: اسم السورة
    - ayah_number: رقم الآية
    - text: نص الآية
    - tafsir: شرح موجز جداً للآية
    أقصى عدد للنتائج هو 5.
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{GEMINI_API_URL}?key={GEMINI_API_KEY}", json=payload) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    text_response = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # محاولة استخراج JSON من الرد
                    try:
                        import re
                        json_match = re.search(r'\[.*\]', text_response, re.DOTALL)
                        if json_match:
                            results = json.loads(json_match.group())
                            
                            response_text = f"🔍 **نتائج البحث عن: {query_text}**\n\n"
                            for res in results:
                                response_text += f"📖 **{res['surah']} ({res['ayah_number']})**\n"
                                response_text += f"« {res['text']} »\n"
                                response_text += f"💡 *التفسير:* {res['tafsir']}\n\n"
                                response_text += "---"
                            
                            await msg.edit_text(response_text, parse_mode=ParseMode.MARKDOWN)
                        else:
                            await msg.edit_text(text_response)
                    except:
                        await msg.edit_text(text_response)
                else:
                    await msg.edit_text("❌ حدث خطأ أثناء الاتصال بمحرك البحث.")
    except Exception as e:
        logger.error(f"Search error: {e}")
        await msg.edit_text("❌ حدث خطأ غير متوقع أثناء البحث.")
    
    context.user_data['state'] = None

async def perform_reciter_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """البحث عن قارئ محدد"""
    search_query = update.message.text
    surah_number = context.user_data.get('search_surah_number')
    
    reciters = await load_reciters()
    results = [r for r in reciters if search_query in r['name']]
    
    if not results:
        await update.message.reply_text(
            f"❌ لم يتم العثور على قراء يطابقون '{search_query}'.\n"
            "جرب كتابة جزء من الاسم (مثلاً: 'العفاسي' أو 'المنشاوي')."
        )
        return
    
    keyboard = []
    for r in results[:10]:
        keyboard.append([InlineKeyboardButton(f"🎧 {r['name']}", callback_data=f"play_audio_{r['id']}_{surah_number}")])
    
    keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة", callback_data=f"reciters_{surah_number}")])
    
    await update.message.reply_text(
        f"🔍 **نتائج البحث عن القارئ: {search_query}**\n"
        f"اختر القارئ للاستماع لسورة {surah_number}:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['state'] = None

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغطات الأزرار"""
    query = update.callback_query
    data = query.data
    
    # خريطة الدوال البسيطة
    CALLBACK_MAP = {
        CALLBACK_MAIN_MENU: start_from_callback,
        CALLBACK_CHECK_SUBSCRIPTION: check_subscription_callback,
        CALLBACK_BROWSE_QURAN_TEXT: browse_quran_text,
        CALLBACK_BROWSE_QURAN_IMAGES: browse_quran_images,
        CALLBACK_SEARCH_QURAN: search_quran,
        CALLBACK_BROWSE_JUZ: browse_juz,
        CALLBACK_AUDIO_MENU: audio_menu,
    }
    
    if data in CALLBACK_MAP:
        await CALLBACK_MAP[data](update, context)
        return

    # معالجة الحالات المعقدة
    if data.startswith("surah_page_"):
        page = int(data.split('_')[-1])
        await browse_quran_text(update, context, page=page)
    elif data.startswith("surah_"):
        # عرض السورة (نص) - هنا نحتاج دالة عرض السورة التي لم أضفها بعد
        await show_surah_text(update, context)
    elif data.startswith("quran_img_page_"):
        page = int(data.split('_')[-1])
        await browse_quran_images(update, context, page=page)
    elif data.startswith("quran_img_"):
        await send_quran_page(update, context)
    elif data.startswith("view_page_"):
        parts = data.split('_')
        await send_specific_quran_page(query, context, int(parts[2]), int(parts[3]))
    elif data.startswith("juz_page_"):
        page = int(data.split('_')[-1])
        await browse_juz(update, context, page=page)
    elif data.startswith("juz_"):
        # عرض الجزء - لم أضفها بعد
        await show_juz_text(update, context)
    elif data.startswith("audio_surah_page_"):
        page = int(data.split('_')[-1])
        await audio_menu(update, context, page=page)
    elif data.startswith("audio_surah_"):
        await show_reciters(update, context)
    elif data.startswith("reciters_page_"):
        await reciters_page(update, context)
    elif data.startswith("reciters_"):
        await show_reciters(update, context)
    elif data.startswith("play_audio_"):
        await play_audio(update, context)
    elif data.startswith("search_reciter_"):
        surah_number = int(data.split('_')[2])
        context.user_data['state'] = 'searching_reciter'
        context.user_data['search_surah_number'] = surah_number
        await query.edit_message_text("🔍 أرسل اسم القارئ الذي تبحث عنه:")

# دوال عرض النصوص (سورة وجزء)
async def show_surah_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    surah_number = int(query.data.split('_')[1])
    surah_data = await load_surah_data(surah_number)
    
    if not surah_data:
        await query.answer("❌ فشل تحميل بيانات السورة.")
        return
    
    text = f"📖 **سورة {surah_data['name_arabic']}**\n\n"
    for num, verse in surah_data['verses'].items():
        text += f"﴿{verse}﴾ ({num}) "
    
    # تقسيم النص إذا كان طويلاً جداً
    if len(text) > 4000:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts[:-1]:
            await context.bot.send_message(chat_id=query.message.chat_id, text=part)
        text = parts[-1]
    
    keyboard = [[InlineKeyboardButton("🔙 العودة للسور", callback_data=CALLBACK_BROWSE_QURAN_TEXT)]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def show_juz_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    juz_number = int(query.data.split('_')[1])
    await query.answer(f"جاري تحميل الجزء {juz_number}...")
    # تبسيطاً، سنعرض رسالة مؤقتة
    await query.edit_message_text(f"📚 الجزء {juz_number} متاح قريباً بشكل كامل.", 
                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 العودة", callback_data=CALLBACK_BROWSE_JUZ)]]))

if __name__ == "__main__":
    # تشغيل Flask في thread
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT, use_reloader=False)).start()
    # تشغيل البوت
    run_bot()
