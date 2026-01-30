import os
import json
import logging
import asyncio
import aiohttp
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
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
from tenacity import retry, stop_after_attempt, wait_exponential

# ==================== إعدادات أساسية ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== فئات التحسين ====================

class QuranCache:
    """نظام تخزين مؤقت ذكي مع TTL وإدارة الذاكرة"""
    
    def __init__(self, ttl_minutes: int = 60, max_size: int = 100):
        self.cache: Dict[str, Tuple[Any, datetime]] = {}
        self.ttl = timedelta(minutes=ttl_minutes)
        self.max_size = max_size
        
    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            data, timestamp = self.cache[key]
            if datetime.now() - timestamp < self.ttl:
                return data
            else:
                del self.cache[key]
        return None
        
    def set(self, key: str, value: Any) -> None:
        if len(self.cache) >= self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
        self.cache[key] = (value, datetime.now())
        
    def clear(self) -> None:
        self.cache.clear()

class ImageManager:
    """مدير ذاكرة تخزين الصور"""
    
    def __init__(self, max_images: int = 20):
        self.image_cache: Dict[int, bytes] = {}
        self.access_times: Dict[int, datetime] = {}
        self.max_images = max_images
        
    async def get_image(self, page_number: int, download_func) -> bytes:
        if page_number in self.image_cache:
            self.access_times[page_number] = datetime.now()
            return self.image_cache[page_number]
            
        image_data = await download_func(page_number)
        
        if len(self.image_cache) >= self.max_images:
            oldest_key = min(self.access_times.items(), key=lambda x: x[1])[0]
            del self.image_cache[oldest_key]
            del self.access_times[oldest_key]
            
        self.image_cache[page_number] = image_data
        self.access_times[page_number] = datetime.now()
        return image_data
        
    def clear(self) -> None:
        self.image_cache.clear()
        self.access_times.clear()

class APIClient:
    """عميل API مع إعادة المحاولة التلقائية"""
    
    def __init__(self, timeout: int = 30, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    async def fetch_json(self, url: str, headers: Dict = None) -> Optional[Dict]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=self.timeout) as response:
                    if response.status == 200:
                        return await response.json()
                    logger.error(f"HTTP Error {response.status}: {url}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise

class QuranHelper:
    """أدوات مساعدة للتعامل مع القرآن"""
    
    @staticmethod
    def format_verse_text(verse_text: str, verse_number: int, surah_number: int) -> str:
        """تنسيق نص الآية"""
        if verse_number == 1 and surah_number != 9:
            basmala_variants = [
                "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                "بِسمِ اللَّهِ الرَّحمٰنِ الرَّحيمِ",
                "بِسْمِ اللهِ الرَّحْمٰنِ الرَّحِيْمِ"
            ]
            for variant in basmala_variants:
                if verse_text.startswith(variant):
                    verse_text = verse_text[len(variant):].strip()
                    break
        return f"{verse_text} ﴿{verse_number}﴾"
    
    @staticmethod
    def create_navigation_buttons(
        current: int, 
        total: int, 
        callback_prefix: str,
        include_home: bool = True
    ) -> List[List[InlineKeyboardButton]]:
        """إنشاء أزرار تنقل قابلة لإعادة الاستخدام"""
        keyboard = []
        
        # أزرار التنقل
        nav_buttons = []
        if current > 1:
            nav_buttons.append(InlineKeyboardButton(
                "⬅️ السابق", 
                callback_data=f"{callback_prefix}_{current-1}"
            ))
        if current < total:
            nav_buttons.append(InlineKeyboardButton(
                "التالي ➡️", 
                callback_data=f"{callback_prefix}_{current+1}"
            ))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # زر الرئيسية
        if include_home:
            keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
        
        return keyboard
    
    @staticmethod
    def split_long_text(text: str, max_length: int = 4000) -> List[str]:
        """تقسيم النصوص الطويلة"""
        if len(text) <= max_length:
            return [text]
        
        parts = []
        while len(text) > max_length:
            # حاول تقسيم عند فقرة
            split_point = text.rfind('\n\n', 0, max_length)
            if split_point == -1:
                split_point = text.rfind('\n', 0, max_length)
            if split_point == -1:
                split_point = max_length
            
            parts.append(text[:split_point])
            text = text[split_point:].strip()
        
        if text:
            parts.append(text)
        
        return parts

class PerformanceMonitor:
    """مراقب أداء البوت"""
    
    def __init__(self):
        self.request_times = defaultdict(list)
        self.error_counts = defaultdict(int)
        self.cache_hits = 0
        self.cache_misses = 0
        
    def record_request(self, endpoint: str, duration: float) -> None:
        self.request_times[endpoint].append(duration)
        if len(self.request_times[endpoint]) > 100:
            self.request_times[endpoint].pop(0)
            
    def record_error(self, endpoint: str) -> None:
        self.error_counts[endpoint] += 1
        
    def record_cache_hit(self) -> None:
        self.cache_hits += 1
        
    def record_cache_miss(self) -> None:
        self.cache_misses += 1
        
    def get_stats(self) -> Dict:
        return {
            'cache_hit_rate': self.cache_hits / (self.cache_hits + self.cache_misses) 
                if (self.cache_hits + self.cache_misses) > 0 else 0,
            'total_errors': sum(self.error_counts.values()),
            'endpoint_stats': {
                endpoint: {
                    'avg_response': sum(times)/len(times) if times else 0,
                    'total_requests': len(times),
                    'errors': self.error_counts[endpoint]
                }
                for endpoint in self.request_times
            }
        }

# ==================== المتغيرات البيئية ====================
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN غير موجود! الرجاء تعيينه في متغيرات البيئة")
    sys.exit(1)

CHANNEL_ID = os.getenv('CHANNEL_ID')
DEVELOPER_USERNAME = os.getenv('DEVELOPER_USERNAME', 'your_developer_username')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', 'your_channel_username')
PORT = int(os.getenv('PORT', 5000))
RENDER_EXTERNAL_URL = os.getenv('RENDER_EXTERNAL_URL', '')

# Google Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

# API URLs
BASE_URL = "https://api.alquran.cloud/v1"
RECITERS_API_URL = "https://quran.yousefheiba.com/api/reciters"
RECITER_AUDIO_API_URL = "https://quran.yousefheiba.com/api/reciterAudio?reciter_id={reciter_id}"
SURAH_AUDIO_API_URL = "https://quran.yousefheiba.com/api/surahAudio?reciter={reciter_short_name}&id={surah_id}"
QURAN_PAGES_IMAGE_API = "https://quran.yousefheiba.com/api/quranPagesImage"

# ==================== تخطيط صفحات المصحف ====================
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

# ==================== تخزين مؤقت محسن ====================
cache = QuranCache(ttl_minutes=30, max_size=150)
image_manager = ImageManager(max_images=30)
api_client = APIClient(timeout=30, max_retries=3)
performance_monitor = PerformanceMonitor()

# ==================== رسائل البوت ====================
MESSAGES = {
    'welcome': """🌟 *أهلاً وسهلاً {user_name} في* *سُطورٌ من السَّماء* ☁️

🕊️ *مرحباً بك في رفيقك الإيماني الشامل لتجربة قرآنية متكاملة*

✨ **ماذا نقدم لك؟**

📖 *مصحف ذكي متكامل:*
• تصفح القرآن بنسختين: نصية ومصورة عالية الجودة
• تجربة قراءة سلسة مع تقسيم آلي للصفحات
• تنقل سهل بين السور والآيات

📻 *راديو القرآن الكريم:*
• بث مباشر على مدار الساعة لتلاوات عطرة
• واجهة تفاعلية متطورة مع تحكم كامل
• تشغيل مستمر بدون انقطاع

🔍 *بحث ذكي متقدم:*
• بحث في آيات القرآن باستخدام الذكاء الاصطناعي
• تفسير مختصر للآيات مباشرة
• دعم البحث باللغة العربية والإنجليزية

🎵 *مكتبة تلاوات شاملة:*
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

🚀 *اختر الخدمة التي تناسبك من القائمة أدناه:*""",
    
    'subscription_required': """🌟 *مرحباً بك في بوت سُطورٌ من السَّماء* ☁️

📖 **شرط الاستخدام:**
يجب الاشتراك في قناتنا الرسمية لاستخدام خدمات البوت.

📣 **ماذا تقدم القناة؟**
• آيات قرآنية يومية مع تفسير مختصر 🌅
• أدعية وأذكار منتقاة 🤲
• محتوى إسلامي هادف ومميز ✨
• تنبيهات بالمناسبات الإسلامية 📅

🔔 **مزايا الاشتراك:**
• وصول كامل لجميع ميزات البوت
• تحديثات مستمرة للمحتوى
• دعم فني مباشر من المطور

🚀 **بعد الاشتراك، اضغط على زر التحقق**""",
    
    'main_menu': """✨ *سُطورٌ من السَّماء* ☁️

🕊️ **مرحباً بك في القائمة الرئيسية**

🌟 **خدماتنا المتكاملة:**

📖 **المصحف الشامل:**
• نسخة نصية كاملة
• نسخة مصورة عالية الجودة
• تجربة قراءة ممتعة

📻 **الراديو المباشر:**
• بث مستمر لتلاوات عطرة
• واجهة تحكم متطورة
• تشغيل على مدار الساعة

🔍 **البحث الذكي:**
• بحث متقدم بالذكاء الاصطناعي
• تفسير مختصر للآيات
• نتائج فورية ودقيقة

🎵 **مكتبة التلاوات:**
• مجموعة كبيرة من القراء
• جودة صوت عالية
• تحميل وتشغيل مباشر

📚 **الأجزاء والأحزاب:**
• تقسيم منظم للقرآن
• تسهيل الختمة اليومية
• تتبع التقدم الشخصي

🤖 **ميزات تقنية:**
• سرعة استجابة عالية
• واجهة مستخدم بديهية
• تحديثات مستمرة

🤲 *"وَهَـٰذَا كِتَابٌ أَنزَلْنَاهُ مُبَارَكٌ فَاتَّبِعُوهُ وَاتَّقُوا لَعَلَّكُمْ تُرْحَمُونَ"* (الأنعام: 155)

🚀 **اختر الخدمة التي تناسبك من القائمة أدناه:**"""
}

# ==================== Flask App ====================
app = Flask(__name__)

@app.route('/')
def index():
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

@app.route('/ping')
def ping():
    """نقطة النهاية لـ Render للحفاظ على البوت نشطاً"""
    return jsonify({"status": "active", "timestamp": time.time()})

@app.route('/health')
def health():
    stats = performance_monitor.get_stats()
    return jsonify({
        "health": "ok", 
        "timestamp": time.time(),
        "cache_stats": {
            "size": len(cache.cache),
            "hit_rate": f"{stats['cache_hit_rate']*100:.1f}%"
        },
        "performance": stats
    })

@app.route('/radio')
def radio():
    """صفحة الراديو المباشر"""
    return render_template_string(RADIO_HTML)

# ==================== HTML للراديو ====================
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
        * { margin: 0; padding: 0; box-sizing: border-box; }
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
        .logo-container { margin-bottom: 20px; }
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
        .controls-wrapper {
            background: rgba(255, 255, 255, 0.06);
            border-radius: 25px;
            padding: 20px 15px;
            border: 1px solid rgba(255, 255, 255, 0.15);
            box-shadow: inset 0 0 15px rgba(255, 255, 255, 0.02);
            margin-bottom: 20px;
        }
        .main-controls {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
            margin-bottom: 20px;
        }
        .control-group {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 6px;
        }
        .btn {
            background: none;
            border: none;
            color: var(--white);
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            justify-content: center;
            align-items: center;
            outline: none;
        }
        .btn:focus { outline: 2px solid rgba(255, 255, 255, 0.3); }
        .btn-skip {
            width: 45px;
            height: 45px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 50%;
            font-size: 1rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .btn-skip:hover {
            background: rgba(255, 255, 255, 0.2);
            transform: scale(1.05);
        }
        .btn-play {
            width: 70px;
            height: 70px;
            background: var(--white);
            color: var(--primary-blue);
            border-radius: 50%;
            font-size: 1.6rem;
            box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
        }
        .btn-play:hover {
            transform: scale(1.05);
            background: #f8f9fa;
        }
        .skip-text { font-size: 0.7rem; font-weight: bold; opacity: 0.8; }
        .volume-section {
            display: flex;
            flex-direction: column;
            gap: 10px;
            padding: 0 10px;
        }
        .volume-labels {
            display: flex;
            justify-content: space-between;
            font-size: 0.65rem;
            opacity: 0.6;
            font-weight: bold;
            padding: 0 5px;
        }
        .volume-bar-container {
            display: flex;
            align-items: center;
            gap: 12px;
            position: relative;
        }
        .volume-slider {
            -webkit-appearance: none;
            width: 100%;
            height: 5px;
            border-radius: 8px;
            background: linear-gradient(to left, rgba(255,255,255,0.4) var(--volume-percent), rgba(255,255,255,0.1) var(--volume-percent));
            outline: none;
            cursor: pointer;
        }
        .volume-slider::-webkit-slider-thumb {
            -webkit-appearance: none;
            appearance: none;
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background: var(--white);
            cursor: pointer;
            box-shadow: 0 0 8px rgba(0,0,0,0.5);
            border: 2px solid var(--light-blue);
        }
        .vol-icon { font-size: 0.9rem; width: 18px; text-align: center; opacity: 0.8; }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(0, 0, 0, 0.2);
            padding: 6px 15px;
            border-radius: 25px;
            font-size: 0.8rem;
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .dot {
            width: 7px;
            height: 7px;
            background: #ff4b2b;
            border-radius: 50%;
            box-shadow: 0 0 8px #ff4b2b;
        }
        .dot.active { animation: pulse-dot 1.5s infinite; }
        @keyframes pulse-dot {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.3); opacity: 0.5; }
            100% { transform: scale(1); opacity: 1; }
        }
        .btn-label {
            font-size: 0.55rem;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            opacity: 0.5;
        }
        .loading { opacity: 0.7; pointer-events: none; }
        .error-message {
            background: rgba(255, 0, 0, 0.1);
            border: 1px solid rgba(255, 0, 0, 0.3);
            border-radius: 10px;
            padding: 10px;
            margin: 10px 0;
            font-size: 0.8rem;
            display: none;
        }
    </style>
</head>
<body>
    <canvas id="starCanvas"></canvas>
    <div class="container">
        <div class="logo-container">
            <div class="logo-circle" id="logoCircle">
                <img src="https://i.postimg.cc/Qt8hQG08/IMG-20250905-074700-225.jpg" alt="Logo" onerror="this.src='https://via.placeholder.com/150/1e69b5/ffffff?text=Quran+Radio'">
            </div>
        </div>
        <h1>سطور من السماء</h1>
        <p class="subtitle">راديو القرآن الكريم المباشر</p>
        <div class="error-message" id="errorMessage"></div>
        <div class="controls-wrapper">
            <div class="main-controls">
                <div class="control-group">
                    <span class="btn-label">رجوع</span>
                    <button class="btn btn-skip" id="backwardBtn">
                        <i class="fas fa-backward-step"></i>
                    </button>
                    <span class="skip-text">10 ثواني</span>
                </div>
                <div class="control-group">
                    <span class="btn-label">تشغيل</span>
                    <button class="btn btn-play" id="playPauseBtn">
                        <i class="fas fa-play" id="playIcon"></i>
                    </button>
                    <span class="skip-text" id="playLabel">بدء البث</span>
                </div>
                <div class="control-group">
                    <span class="btn-label">تقديم</span>
                    <button class="btn btn-skip" id="forwardBtn">
                        <i class="fas fa-forward-step"></i>
                    </button>
                    <span class="skip-text">10 ثواني</span>
                </div>
            </div>
            <div class="volume-section">
                <div class="volume-labels">
                    <span>خفـض الصـوت</span>
                    <span>رفـع الصـوت</span>
                </div>
                <div class="volume-bar-container">
                    <i class="fas fa-volume-low vol-icon"></i>
                    <input type="range" class="volume-slider" id="volumeSlider" min="0" max="1" step="0.01" value="0.8" style="--volume-percent: 80%;">
                    <i class="fas fa-volume-high vol-icon"></i>
                </div>
            </div>
        </div>
        <div class="status-badge">
            <span class="dot active" id="statusDot"></span>
            <span id="statusText">جاهز للبث المباشر</span>
        </div>
    </div>
    <audio id="radioPlayer" preload="auto" crossorigin="anonymous">
        <source src="https://quran.yousefheiba.com/api/radio" type="audio/mpeg">
    </audio>
    <script>
        // --- Background Animation ---
        const canvas = document.getElementById('starCanvas');
        const ctx = canvas.getContext('2d');
        let stars = [];
        let animationId = null;
        function initCanvas() {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            stars = [];
            for (let i = 0; i < 80; i++) {
                stars.push({
                    x: Math.random() * canvas.width,
                    y: Math.random() * canvas.height,
                    size: Math.random() * 1.2,
                    opacity: Math.random() * 0.5 + 0.3,
                    speed: 0.003 + Math.random() * 0.005
                });
            }
        }
        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = "white";
            stars.forEach(s => {
                ctx.globalAlpha = s.opacity;
                ctx.beginPath();
                ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
                ctx.fill();
                s.opacity += s.speed;
                if (s.opacity > 0.8 || s.opacity < 0.3) s.speed = -s.speed;
            });
            ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
            ctx.lineWidth = 0.3;
            for (let i = 0; i < stars.length; i++) {
                for (let j = i + 1; j < stars.length; j++) {
                    let d = Math.hypot(stars[i].x - stars[j].x, stars[i].y - stars[j].y);
                    if (d < 100) {
                        ctx.beginPath();
                        ctx.moveTo(stars[i].x, stars[i].y);
                        ctx.lineTo(stars[j].x, stars[j].y);
                        ctx.stroke();
                    }
                }
            }
            animationId = requestAnimationFrame(draw);
        }
        function stopAnimation() {
            if (animationId) {
                cancelAnimationFrame(animationId);
                animationId = null;
            }
        }
        window.addEventListener('resize', () => {
            initCanvas();
            draw();
        });
        // --- Audio Logic ---
        const audio = document.getElementById('radioPlayer');
        const playPauseBtn = document.getElementById('playPauseBtn');
        const playIcon = document.getElementById('playIcon');
        const playLabel = document.getElementById('playLabel');
        const logoCircle = document.getElementById('logoCircle');
        const volumeSlider = document.getElementById('volumeSlider');
        const statusText = document.getElementById('statusText');
        const statusDot = document.getElementById('statusDot');
        const errorMessage = document.getElementById('errorMessage');
        const forwardBtn = document.getElementById('forwardBtn');
        const backwardBtn = document.getElementById('backwardBtn');
        let isPlaying = false;
        let isLoading = false;
        function showError(message) {
            errorMessage.textContent = message;
            errorMessage.style.display = 'block';
            setTimeout(() => {
                errorMessage.style.display = 'none';
            }, 5000);
        }
        function updateUI(playing, loading = false) {
            if (loading) {
                playPauseBtn.classList.add('loading');
                playIcon.className = 'fas fa-spinner fa-spin';
                playLabel.innerText = 'جاري التحميل...';
                statusText.innerText = 'جاري الاتصال بالخادم...';
                statusDot.style.background = '#ffa500';
                return;
            }
            playPauseBtn.classList.remove('loading');
            if (playing) {
                playIcon.className = 'fas fa-pause';
                playLabel.innerText = 'إيقاف مؤقت';
                logoCircle.classList.add('playing');
                statusText.innerText = 'بث مباشر الآن';
                statusDot.style.background = '#00ff00';
                statusDot.classList.add('active');
            } else {
                playIcon.className = 'fas fa-play';
                playLabel.innerText = 'تشغيل البث';
                logoCircle.classList.remove('playing');
                statusText.innerText = 'البث متوقف';
                statusDot.style.background = '#ff4b2b';
                statusDot.classList.remove('active');
            }
        }
        async function playRadio() {
            if (isLoading) return;
            try {
                isLoading = true;
                updateUI(false, true);
                const timestamp = new Date().getTime();
                audio.src = `https://quran.yousefheiba.com/api/radio?t=${timestamp}`;
                await audio.play();
                isPlaying = true;
                isLoading = false;
                updateUI(true);
                if (!animationId) {
                    initCanvas();
                    draw();
                }
            } catch (error) {
                console.error('Playback error:', error);
                isLoading = false;
                isPlaying = false;
                updateUI(false);
                if (error.name === 'NotAllowedError') {
                    showError('❌ تم رفض الإذن للتشغيل. يرجى النقر على الصفحة أولاً أو التحقق من إعدادات الصوت.');
                } else if (error.name === 'NotSupportedError') {
                    showError('❌ تنسيق الصوت غير مدعوم. حاول استخدام متصفح مختلف.');
                } else if (error.name === 'NetworkError') {
                    showError('❌ خطأ في الشبكة. تحقق من اتصال الإنترنت.');
                } else {
                    showError(`❌ خطأ في التشغيل: ${error.message}`);
                }
            }
        }
        function pauseRadio() {
            audio.pause();
            isPlaying = false;
            updateUI(false);
        }
        playPauseBtn.addEventListener('click', () => {
            if (isPlaying) {
                pauseRadio();
            } else {
                playRadio();
            }
        });
        forwardBtn.addEventListener('click', () => {
            if (isPlaying && !isNaN(audio.duration)) {
                audio.currentTime = Math.min(audio.currentTime + 10, audio.duration);
            }
        });
        backwardBtn.addEventListener('click', () => {
            if (isPlaying) {
                audio.currentTime = Math.max(audio.currentTime - 10, 0);
            }
        });
        volumeSlider.addEventListener('input', (e) => {
            const val = e.target.value;
            audio.volume = val;
            volumeSlider.style.setProperty('--volume-percent', (val * 100) + '%');
        });
        audio.addEventListener('waiting', () => {
            statusText.innerText = 'جاري التخزين المؤقت...';
        });
        audio.addEventListener('playing', () => {
            statusText.innerText = 'بث مباشر الآن';
        });
        audio.addEventListener('error', (e) => {
            console.error('Audio error:', e);
            isLoading = false;
            isPlaying = false;
            updateUI(false);
            showError('❌ خطأ في مصدر الصوت. حاول تحديث الصفحة.');
        });
        audio.addEventListener('ended', () => {
            isPlaying = false;
            updateUI(false);
        });
        window.addEventListener('load', () => {
            initCanvas();
            draw();
            audio.volume = volumeSlider.value;
            setTimeout(() => {
                statusText.innerHTML = '✨ اضغط على زر التشغيل للاستماع';
            }, 1000);
        });
        window.addEventListener('beforeunload', () => {
            pauseRadio();
            stopAnimation();
        });
        document.addEventListener('click', function firstClick() {
            audio.volume = 0.1;
            document.removeEventListener('click', firstClick);
        }, { once: true });
    </script>
</body>
</html>
'''

# ==================== دوال البيانات ====================

async def load_surah_info():
    """تحميل معلومات السور مع التخزين المؤقت"""
    cache_key = "surah_info"
    cached_data = cache.get(cache_key)
    if cached_data:
        performance_monitor.record_cache_hit()
        return cached_data
    
    performance_monitor.record_cache_miss()
    start_time = time.time()
    
    url = f"{BASE_URL}/surah"
    data = await api_client.fetch_json(url)
    
    if data and data.get('code') == 200 and 'data' in data:
        cache.set(cache_key, data['data'])
        duration = time.time() - start_time
        performance_monitor.record_request("load_surah_info", duration)
        return data['data']
    
    performance_monitor.record_error("load_surah_info")
    logger.error("فشل في تحميل معلومات السور")
    return None

async def load_surah_data(surah_number: int):
    """تحميل بيانات سورة محددة فقط عند الحاجة"""
    cache_key = f"surah_{surah_number}"
    cached_data = cache.get(cache_key)
    if cached_data:
        performance_monitor.record_cache_hit()
        return cached_data
    
    performance_monitor.record_cache_miss()
    start_time = time.time()
    
    url = f"{BASE_URL}/surah/{surah_number}/ar.alafasy"
    data = await api_client.fetch_json(url)
    
    if data and data.get('code') == 200 and 'data' in data:
        surah_data = data['data']
        result = {
            'verses': {ayah['numberInSurah']: ayah['text'] for ayah in surah_data['ayahs']},
            'name': surah_data['englishName'],
            'name_arabic': surah_data['name'],
            'revelation_type': surah_data['revelationType'],
            'ayahs_count': surah_data['numberOfAyahs']
        }
        
        cache.set(cache_key, result)
        duration = time.time() - start_time
        performance_monitor.record_request(f"load_surah_{surah_number}", duration)
        return result
    
    performance_monitor.record_error(f"load_surah_{surah_number}")
    return None

async def load_reciters():
    """تحميل قائمة القراء"""
    cache_key = "reciters"
    cached_data = cache.get(cache_key)
    if cached_data:
        performance_monitor.record_cache_hit()
        return cached_data
    
    performance_monitor.record_cache_miss()
    start_time = time.time()
    
    data = await api_client.fetch_json(RECITERS_API_URL)
    
    if data and 'reciters' in data:
        formatted_reciters = [
            {
                'id': int(reciter['reciter_id']),
                'name': reciter['reciter_name'],
                'short_name': reciter['reciter_short_name']
            }
            for reciter in data['reciters']
        ]
        
        cache.set(cache_key, formatted_reciters)
        duration = time.time() - start_time
        performance_monitor.record_request("load_reciters", duration)
        return formatted_reciters
    
    performance_monitor.record_error("load_reciters")
    return None

async def get_reciter_audio(reciter_id: int, surah_number: int) -> Optional[str]:
    """الحصول على رابط الصوت"""
    start_time = time.time()
    
    try:
        reciters = await load_reciters()
        if not reciters:
            return None
        
        reciter = next((r for r in reciters if r['id'] == reciter_id), None)
        if not reciter:
            return None
        
        audio_list_url = RECITER_AUDIO_API_URL.format(reciter_id=reciter_id)
        audio_data = await api_client.fetch_json(audio_list_url)
        
        if audio_data and 'audio_urls' in audio_data:
            for audio_info in audio_data['audio_urls']:
                if int(audio_info['surah_id']) == surah_number:
                    duration = time.time() - start_time
                    performance_monitor.record_request("get_reciter_audio", duration)
                    return audio_info['audio_url']
        
        duration = time.time() - start_time
        performance_monitor.record_request("get_reciter_audio", duration)
        return SURAH_AUDIO_API_URL.format(
            reciter_short_name=reciter['short_name'],
            surah_id=surah_number
        )
    
    except Exception as e:
        performance_monitor.record_error("get_reciter_audio")
        logger.error(f"Error getting reciter audio: {e}")
        return None

# ==================== دوال التحقق ====================

async def check_user_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من اشتراك المستخدم"""
    try:
        if not CHANNEL_ID:
            return True
            
        member = await context.bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"خطأ في التحقق من الاشتراك: {e}")
        return False

async def subscription_required(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من الاشتراك الإجباري"""
    if not CHANNEL_ID:
        return True
        
    user_id = update.effective_user.id
    
    if not await check_user_subscription(user_id, context):
        keyboard = [
            [InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")],
            [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            MESSAGES['subscription_required'],
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return False
    return True

# ==================== معالجات الأوامر ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية"""
    if not await subscription_required(update, context):
        return
    
    user_name = update.effective_user.first_name
    
    # إنشاء واجهة المستخدم
    radio_button = InlineKeyboardButton(
        "📻 راديو سطور من السماء", 
        web_app={"url": f"http://0.0.0.0:{PORT}/radio"}
    )
    
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف النصي", callback_data="browse_quran_text")],
        [InlineKeyboardButton("🖼️ المصحف المصور", callback_data="browse_quran_images")],
        [radio_button],
        [InlineKeyboardButton("🔍 بحث ذكي في القرآن", callback_data="search_quran")],
        [InlineKeyboardButton("📚 تصفح الأجزاء", callback_data="browse_juz")],
        [InlineKeyboardButton("🎵 مكتبة التلاوات", callback_data="audio_menu")],
        [InlineKeyboardButton("👨‍💻 المطور & الدعم", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        MESSAGES['welcome'].format(user_name=user_name),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """التحقق من الاشتراك"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if await check_user_subscription(user_id, context):
        await query.edit_message_text(
            "✅ *تم التحقق بنجاح!*\n\n"
            "🌟 **أهلاً بك في عالم القرآن الكريم** ☁️\n\n"
            "تم تفعيل حسابك بنجاح! يمكنك الآن الاستمتاع بجميع ميزات البوت.",
            parse_mode=ParseMode.MARKDOWN
        )
        await main_menu(update, context)
    else:
        await query.edit_message_text(
            "❌ *لم يتم العثور على اشتراكك*\n\n"
            "يبدو أنك لم تشترك في القناة بعد.\n\n"
            "📌 **خطوات الاشتراك:**\n"
            "1. اضغط على زر 'اشترك في القناة'\n"
            "2. انتظر حتى يتم تحميل القناة\n"
            "3. اضغط على زر 'اشتراك' أو 'Join'\n"
            "4. عد للبوت واضغط على 'تحقق من الاشتراك'",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔔 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")],
                [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_subscription")]
            ])
        )

# ==================== معالجات القوائم ====================

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """القائمة الرئيسية"""
    query = update.callback_query
    if query:
        await query.answer()
    
    radio_button = InlineKeyboardButton(
        "📻 راديو سطور من السماء", 
        web_app={"url": f"http://0.0.0.0:{PORT}/radio"}
    )
    
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف النصي", callback_data="browse_quran_text")],
        [InlineKeyboardButton("🖼️ المصحف المصور", callback_data="browse_quran_images")],
        [radio_button],
        [InlineKeyboardButton("🔍 بحث ذكي في القرآن", callback_data="search_quran")],
        [InlineKeyboardButton("📚 تصفح الأجزاء", callback_data="browse_juz")],
        [InlineKeyboardButton("🎵 مكتبة التلاوات", callback_data="audio_menu")],
        [InlineKeyboardButton("👨‍💻 المطور & الدعم", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = MESSAGES['main_menu']
    
    if query:
        try:
            await query.edit_message_text(
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
        except:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    else:
        await update.message.reply_text(
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

# ==================== دوال المصحف ====================

async def browse_quran_text(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """تصفح المصحف النصي"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور.")
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
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"quran_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"quran_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📖 *المصحف الشريف - النسخة النصية*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🔢 **السور:** {start_idx + 1} - {end_idx}\n\n"
        f"✨ **اختر السورة:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def show_surah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سورة معينة"""
    query = update.callback_query
    await query.answer()
    
    surah_number = int(query.data.split('_')[1])
    
    surah_data = await load_surah_data(surah_number)
    if not surah_data:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السورة.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📖 قراءة السورة", callback_data=f"read_surah_{surah_number}")],
        [InlineKeyboardButton("🖼️ عرض الصفحات المصورة", callback_data=f"surah_img_{surah_number}")],
        [InlineKeyboardButton("🎵 الاستماع للتلاوات", callback_data=f"audio_surah_{surah_number}")],
        [
            InlineKeyboardButton("⬅️ السابق", callback_data=f"surah_{surah_number-1 if surah_number > 1 else 1}"),
            InlineKeyboardButton("التالي ➡️", callback_data=f"surah_{surah_number+1 if surah_number < 114 else 114}")
        ],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = f"""
📖 *سورة {surah_data['name_arabic']} ({surah_data['name']})*

📊 **المعلومات:**
• 🔢 **الرقم:** {surah_number}
• 📝 **الآيات:** {surah_data['ayahs_count']}
• 📍 **النزول:** {surah_data['revelation_type']}

🌟 **اختر الإجراء:**
    """
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def read_surah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قراءة السورة"""
    query = update.callback_query
    await query.answer()
    
    surah_number = int(query.data.split('_')[2])
    surah_data = await load_surah_data(surah_number)
    
    if not surah_data:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل السورة.")
        return
    
    surah_text = f"📖 *سورة {surah_data['name_arabic']} ({surah_data['name']})*\n\n"
    
    if surah_number != 9:
        surah_text += "*بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ*\n\n"
    
    verses = surah_data['verses']
    sorted_verses = sorted(verses.items(), key=lambda x: int(x[0]))
    
    for verse_number, verse_text in sorted_verses:
        formatted_text = QuranHelper.format_verse_text(verse_text, int(verse_number), surah_number)
        surah_text += f"{formatted_text}\n\n"
        
        if len(surah_text) > 3000:
            keyboard = [
                [
                    InlineKeyboardButton("⬅️ عودة", callback_data=f"surah_{surah_number}"),
                    InlineKeyboardButton("متابعة ➡️", callback_data=f"continue_surah_{surah_number}_{verse_number}")
                ],
                [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                surah_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    keyboard = QuranHelper.create_navigation_buttons(surah_number, 114, "surah", include_home=True)
    
    await query.edit_message_text(
        surah_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def send_quran_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page_number: int, surah_number: int):
    """إرسال صفحة المصحف"""
    query = update.callback_query
    
    async def download_image(page_num):
        page_str = str(page_num).zfill(3)
        image_url = f"https://quran.yousefheiba.com/api/quran-pages/{page_str}.png"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=30) as response:
                if response.status == 200:
                    return await response.read()
                raise Exception(f"HTTP {response.status}")
    
    try:
        image_data = await image_manager.get_image(page_number, download_image)
        
        page_range = SURAH_PAGES_MAPPING.get(surah_number)
        if not page_range:
            await query.answer("❌ لم يتم العثور على نطاق الصفحات", show_alert=True)
            return
        
        total_surah_pages = page_range[1] - page_range[0] + 1
        current_in_surah = page_number - page_range[0] + 1
        
        caption = f"""
📖 *الصفحة {page_number} من 604*

📑 **في السورة:** {current_in_surah} من {total_surah_pages}

💡 **تلميحات:**
• يمكنك التكبير والتصغير في الصورة
• استخدم أزرار التنقل للانتقال بين الصفحات
        """
        
        keyboard = []
        nav_row = []
        if page_number > page_range[0]:
            nav_row.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"view_page_{page_number-1}_{surah_number}"))
        if page_number < page_range[1]:
            nav_row.append(InlineKeyboardButton("التالي ➡️", callback_data=f"view_page_{page_number+1}_{surah_number}"))
        
        if nav_row:
            keyboard.append(nav_row)
            
        keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=io.BytesIO(image_data),
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        if not query.message.photo:
            await query.message.delete()
            
    except Exception as e:
        logger.error(f"Error sending quran page: {e}")
        await query.answer("❌ تعذر تحميل الصفحة حالياً", show_alert=True)

# ==================== نظام البحث ====================

async def search_quran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البحث"""
    query = update.callback_query
    await query.answer()
    
    if not GEMINI_API_KEY:
        await query.edit_message_text(
            "⚠️ *ميزة البحث الذكي غير متاحة حالياً*\n\n"
            "🔧 **السبب:** لم يتم إعداد مفتاح Google Gemini API.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await query.edit_message_text(
        "🔍 *البحث الذكي في القرآن الكريم*\n\n"
        "🌟 **اكتب الكلمة أو الجملة التي تريد البحث عنها:**\n\n"
        "💡 **أمثلة:**\n"
        "• 'الرحمن الرحيم'\n"
        "• 'الصبر واليقين'\n"
        "• 'آيات عن الصلاة'",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data['search_mode'] = True

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ البحث"""
    if not GEMINI_API_KEY:
        await update.message.reply_text("⚠️ ميزة البحث غير متاحة حالياً.")
        return
    
    search_text = update.message.text.strip()
    
    if len(search_text) < 3:
        await update.message.reply_text("🔍 أدخل كلمة مكونة من 3 أحرف على الأقل.")
        return
    
    context.user_data.pop('search_mode', None)
    processing_msg = await update.message.reply_text("🔍 **جاري البحث...**")
    
    prompt = f"""
ابحث في القرآن عن: "{search_text}"
أعطني النتائج مع ذكر:
1. السورة ورقم الآية
2. نص الآية
3. تفسير مختصر
أجب باللغة العربية فقط.
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1024
        }
    }
    
    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=45) as response:
                if response.status == 200:
                    result = await response.json()
                    if 'candidates' in result and result['candidates']:
                        ai_reply = result['candidates'][0]['content']['parts'][0]['text']
                    else:
                        ai_reply = "❌ لم أتلق أي نتائج."
                else:
                    ai_reply = f"❌ خطأ في الخادم: {response.status}"
                    
    except Exception as e:
        logger.error(f"Search error: {e}")
        ai_reply = "❌ حدث خطأ في البحث."
    
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id,
            message_id=processing_msg.message_id
        )
    except:
        pass
    
    if ai_reply.startswith("❌"):
        await update.message.reply_text(ai_reply)
        return
    
    keyboard = [
        [InlineKeyboardButton("🔍 بحث جديد", callback_data="search_quran")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
    ]
    
    parts = QuranHelper.split_long_text(ai_reply)
    for i, part in enumerate(parts):
        if i == len(parts) - 1:
            await update.message.reply_text(
                f"🔍 *نتائج البحث عن:* \"{search_text}\"\n\n{part}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                f"🔍 *نتائج البحث عن:* \"{search_text}\"\n\n{part}",
                parse_mode=ParseMode.MARKDOWN
            )

# ==================== نظام التلاوات ====================

async def audio_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الصوتيات"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ حدث خطأ في تحميل السور.")
        return
    
    page = 0
    surahs_per_page = 10
    total_pages = (len(surah_info) + surahs_per_page - 1) // surahs_per_page
    
    start_idx = page * surahs_per_page
    end_idx = min(start_idx + surahs_per_page, len(surah_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        surah = surah_info[i]
        keyboard.append([InlineKeyboardButton(
            f"{surah['number']}. {surah['name']}", 
            callback_data=f"audio_surah_{surah['number']}"
        )])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"audio_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"audio_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
    
    await query.edit_message_text(
        "🎵 *مكتبة التلاوات الصوتية*\n\n"
        "✨ **اختر سورة لتستمع إلى تلاوتها:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_reciters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القراء"""
    query = update.callback_query
    await query.answer()
    
    surah_number = int(query.data.split('_')[2])
    reciters = await load_reciters()
    
    if not reciters:
        await query.edit_message_text("❌ لا يوجد قراء متاحين حالياً.")
        return
    
    page = 0
    reciters_per_page = 10
    total_pages = (len(reciters) + reciters_per_page - 1) // reciters_per_page
    
    start_idx = page * reciters_per_page
    end_idx = min(start_idx + reciters_per_page, len(reciters))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        reciter = reciters[i]
        keyboard.append([InlineKeyboardButton(
            f"🎧 {reciter['name']}", 
            callback_data=f"play_audio_{reciter['id']}_{surah_number}"
        )])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"reciters_page_{surah_number}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("التالي ➡️", callback_data=f"reciters_page_{surah_number}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")])
    
    await query.edit_message_text(
        f"🎵 *اختر القارئ للاستماع*\n\n"
        f"📖 **السورة:** {surah_number}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def play_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل التلاوة"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    reciter_id = int(data[2])
    surah_number = int(data[3])
    
    surah_info = await load_surah_info()
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    
    if not surah_data:
        await query.edit_message_text("❌ خطأ في معلومات السورة.")
        return
    
    reciters = await load_reciters()
    reciter = next((r for r in reciters if r['id'] == reciter_id), None)
    
    if not reciter:
        await query.edit_message_text("❌ خطأ في معلومات القارئ.")
        return
    
    await query.edit_message_text(f"⏳ **جاري التحميل...**")
    
    audio_url = await get_reciter_audio(reciter_id, surah_number)
    
    if not audio_url:
        await query.edit_message_text("❌ تعذر العثور على التلاوة.")
        return
    
    try:
        await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=audio_url,
            title=f"سورة {surah_data['name']} - {reciter['name']}",
            performer=reciter['name'],
            read_timeout=90,
            write_timeout=90
        )
        
        keyboard = [
            [InlineKeyboardButton("🎵 تلاوات أخرى", callback_data=f"reciters_{surah_number}")],
            [InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")]
        ]
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"🌟 *تم إرسال التلاوة بنجاح!*\n\n"
                 f"🎧 **القارئ:** {reciter['name']}\n"
                 f"📖 **السورة:** {surah_data['name']}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        await context.bot.delete_message(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id
        )
        
    except Exception as e:
        logger.error(f"Error sending audio: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"⚠️ *تعذر إرسال الملف مباشرة*\n\n"
                 f"🎧 **لكن يمكنك الاستماع من الرابط:**\n{audio_url}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 العودة", callback_data=f"reciters_{surah_number}")
            ]])
        )

# ==================== نظام معالجة Callbacks ====================

CALLBACK_HANDLERS = {
    'check_subscription': check_subscription_callback,
    'browse_quran_text': browse_quran_text,
    'browse_quran_images': lambda u, c: browse_quran_text(u, c, 0),
    'search_quran': search_quran,
    'browse_juz': lambda u, c: browse_quran_text(u, c, 0),
    'audio_menu': audio_menu,
    'main_menu': main_menu
}

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج Callbacks منظم"""
    query = update.callback_query
    data = query.data
    
    # البحث عن الhandler المناسب
    for prefix, handler in CALLBACK_HANDLERS.items():
        if data == prefix:
            await handler(update, context)
            return
    
    # Handlers للنماط
    if data.startswith("surah_"):
        await show_surah(update, context)
    elif data.startswith("read_surah_"):
        await read_surah(update, context)
    elif data.startswith("continue_surah_"):
        await read_surah(update, context)  # مبسط
    elif data.startswith("surah_img_"):
        surah_number = int(data.split('_')[2])
        page_range = SURAH_PAGES_MAPPING.get(surah_number, (1, 1))
        await send_quran_page(update, context, page_range[0], surah_number)
    elif data.startswith("view_page_"):
        parts = data.split('_')
        page_number = int(parts[2])
        surah_number = int(parts[3])
        await send_quran_page(update, context, page_number, surah_number)
    elif data.startswith("quran_page_"):
        page = int(data.split('_')[2])
        await browse_quran_text(update, context, page)
    elif data.startswith("audio_surah_"):
        await show_reciters(update, context)
    elif data.startswith("reciters_page_"):
        await show_reciters(update, context)  # مبسط
    elif data.startswith("play_audio_"):
        await play_audio(update, context)
    elif data.startswith("audio_page_"):
        page = int(data.split('_')[2])
        await audio_menu(update, context)  # مبسط
    else:
        await query.answer("🚧 الميزة قيد التطوير!", show_alert=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل"""
    if not await subscription_required(update, context):
        return
    
    if context.user_data.get('search_mode'):
        await perform_search(update, context)
        return
    
    await main_menu(update, context)

# ==================== تشغيل البوت ====================

def run_flask():
    """تشغيل Flask في thread منفصل"""
    logger.info(f"🌐 بدء خادم الويب على المنفذ {PORT}...")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def main():
    """الدالة الرئيسية"""
    # ✅ تشغيل Flask في thread خلفي (daemon)
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # ✅ تشغيل البوت في الـ main thread
    logger.info("🚀 بدء تشغيل البوت سُطورٌ من السَّماء...")
    logger.info(f"🌐 الراديو: http://0.0.0.0:{PORT}/radio")
    logger.info(f"🔍 البحث الذكي: {'✅ متاح' if GEMINI_API_KEY else '❌ غير متاح'}")
    logger.info("📖 المصحف الشريف جاهز")
    logger.info("📻 الراديو المباشر يعمل")
    logger.info("🎵 مكتبة التلاوات متاحة")
    logger.info("🤖 البوت يعمل بكامل طاقته!")
    
    # إنشاء وتشغيل البوت
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # تشغيل البوت (بدون drop_pending_updates لأفضل استقرار)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
