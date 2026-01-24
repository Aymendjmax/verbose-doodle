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

# تشغيل البوت في thread منفصل
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
    logger.info(f"📱 البوت: https://t.me/{(application.bot.username)}")
    logger.info(f"🌐 الراديو: {BASE_WEB_URL}/radio")
    logger.info(f"🔍 البحث الذكي: {'✅ متاح' if GEMINI_API_KEY else '❌ غير متاح'}")
    logger.info("📖 المصحف الشريف جاهز")
    logger.info("📻 الراديو المباشر يعمل")
    logger.info("🎵 مكتبة التلاوات متاحة")
    logger.info("🤖 البوت يعمل بكامل طاقته!")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

# الذاكرة المؤقتة للبيانات
cache = {
    'surah_info': None,
    'juz_info': None,
    'surah_data': {},
    'reciters': None,
    'search_results': {}
}

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

        /* Controls Box */
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

        .btn:focus {
            outline: 2px solid rgba(255, 255, 255, 0.3);
        }

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

        .skip-text {
            font-size: 0.7rem;
            font-weight: bold;
            opacity: 0.8;
        }

        /* Volume Section */
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

        .vol-icon {
            font-size: 0.9rem;
            width: 18px;
            text-align: center;
            opacity: 0.8;
        }

        /* Status Badge */
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

        .dot.active {
            animation: pulse-dot 1.5s infinite;
        }

        @keyframes pulse-dot {
            0% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.3); opacity: 0.5; }
            100% { transform: scale(1); opacity: 1; }
        }

        /* Tooltip style labels */
        .btn-label {
            font-size: 0.55rem;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            opacity: 0.5;
        }

        /* Loading State */
        .loading {
            opacity: 0.7;
            pointer-events: none;
        }

        /* Error Message */
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
            <!-- Main Controls -->
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

            <!-- Volume Section -->
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

            // Geometric lines
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
                
                // إضافة timestamp لمنع التخزين المؤقت
                const timestamp = new Date().getTime();
                audio.src = `https://quran.yousefheiba.com/api/radio?t=${timestamp}`;
                
                // محاولة التشغيل
                await audio.play();
                
                isPlaying = true;
                isLoading = false;
                updateUI(true);
                
                // بدء الرسوم المتحركة إذا لم تكن تعمل
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
            // Update CSS variable for progress bar effect
            volumeSlider.style.setProperty('--volume-percent', (val * 100) + '%');
        });

        // Event Listeners for Audio
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

        // تحميل الصفحة
        window.addEventListener('load', () => {
            initCanvas();
            draw();
            
            // اختبار الاتصال
            audio.volume = volumeSlider.value;
            
            // عرض رسالة ترحيب
            setTimeout(() => {
                statusText.innerHTML = '✨ اضغط على زر التشغيل للاستماع';
            }, 1000);
        });

        // تنظيف عند إغلاق الصفحة
        window.addEventListener('beforeunload', () => {
            pauseRadio();
            stopAnimation();
        });

        // إضافة تفاعل للنقر الأول للتغلب على قيود التشغيل التلقائي
        document.addEventListener('click', function firstClick() {
            audio.volume = 0.1;
            document.removeEventListener('click', firstClick);
        }, { once: true });
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
    """إرسال طلب POST والحصول على JSON"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data, headers=headers, timeout=30) as response:
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
        data = await fetch_json(RECITERS_API_URL)
        if data and 'reciters' in data:
            # تحويل البيانات للصيغة الموحدة
            formatted_reciters = []
            for reciter in data['reciters']:
                formatted_reciters.append({
                    'id': int(reciter['reciter_id']),  # تحويل لرقم
                    'name': reciter['reciter_name'],
                    'short_name': reciter['reciter_short_name']
                })
            cache['reciters'] = formatted_reciters
        else:
            logger.error("فشل في تحميل قائمة القراء")
    return cache['reciters']

async def get_reciter_audio(reciter_id: int, surah_number: int):
    """الحصول على رابط الصوت للقارئ والسورة من API الجديد"""
    reciters = await load_reciters()
    if not reciters:
        return None
    
    # البحث عن القارئ
    reciter = next((r for r in reciters if r['id'] == reciter_id), None)
    if not reciter:
        return None
    
    # جلب قائمة التسجيلات للقارئ
    audio_list_url = RECITER_AUDIO_API_URL.format(reciter_id=reciter_id)
    audio_data = await fetch_json(audio_list_url)
    
    if not audio_data or 'audio_urls' not in audio_data:
        # إذا لم نجد القائمة، ننشئ الرابط يدوياً
        return SURAH_AUDIO_API_URL.format(
            reciter_short_name=reciter['short_name'],
            surah_id=surah_number
        )
    
    # البحث عن رابط السورة المطلوبة
    for audio_info in audio_data['audio_urls']:
        if int(audio_info['surah_id']) == surah_number:
            # استخدام الرابط المباشر من القائمة
            return audio_info['audio_url']
    
    # إذا لم نجد الرابط في القائمة، ننشئه يدوياً
    return SURAH_AUDIO_API_URL.format(
        reciter_short_name=reciter['short_name'],
        surah_id=surah_number
    )

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
            "🌟 *مرحباً بك في بوت سُطورٌ من السَّماء* ☁️\n\n"
            "📖 **شرط الاستخدام:**\n"
            "يجب الاشتراك في قناتنا الرسمية لاستخدام خدمات البوت.\n\n"
            "📣 **ماذا تقدم القناة؟**\n"
            "• آيات قرآنية يومية مع تفسير مختصر 🌅\n"
            "• أدعية وأذكار منتقاة 🤲\n"
            "• محتوى إسلامي هادف ومميز ✨\n"
            "• تنبيهات بالمناسبات الإسلامية 📅\n\n"
            "🔔 **مزايا الاشتراك:**\n"
            "• وصول كامل لجميع ميزات البوت\n"
            "• تحديثات مستمرة للمحتوى\n"
            "• دعم فني مباشر من المطور\n\n"
            "🚀 **بعد الاشتراك، اضغط على زر التحقق**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البداية - الصفحة الرئيسية الأولى"""
    if not await subscription_required(update, context):
        return
    
    user_name = update.effective_user.first_name
    
    # إنشاء زر الراديو كزر ويب
    radio_button = InlineKeyboardButton(
        "📻 راديو سطور من السماء", 
        web_app={"url": f"{BASE_WEB_URL}/radio"}
    )
    
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف النصي", callback_data="browse_quran_text")],
        [InlineKeyboardButton("🖼️ المصحف المصور عالي الجودة", callback_data="browse_quran_images")],
        [radio_button],
        [InlineKeyboardButton("🔍 بحث ذكي في القرآن", callback_data="search_quran")],
        [InlineKeyboardButton("📚 تصفح الأجزاء والأحزاب", callback_data="browse_juz")],
        [InlineKeyboardButton("🎵 مكتبة التلاوات الصوتية", callback_data="audio_menu")],
        [InlineKeyboardButton("👨‍💻 المطور & الدعم", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_message = f"""
🌟 *أهلاً وسهلاً {user_name} في* *سُطورٌ من السَّماء* ☁️

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
        # إعادة توجيه للقائمة الرئيسية
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
                [InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_subscription")]
            ])
        )

async def start_from_callback(query, context):
    """بدء القائمة الرئيسية من callback"""
    # إنشاء زر الراديو كزر ويب
    radio_button = InlineKeyboardButton(
        "📻 راديو سطور من السماء", 
        web_app={"url": f"{BASE_WEB_URL}/radio"}
    )
    
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف النصي", callback_data="browse_quran_text")],
        [InlineKeyboardButton("🖼️ المصحف المصور عالي الجودة", callback_data="browse_quran_images")],
        [radio_button],
        [InlineKeyboardButton("🔍 بحث ذكي في القرآن", callback_data="search_quran")],
        [InlineKeyboardButton("📚 تصفح الأجزاء والأحزاب", callback_data="browse_juz")],
        [InlineKeyboardButton("🎵 مكتبة التلاوات الصوتية", callback_data="audio_menu")],
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

async def browse_quran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح المصحف - عرض قائمة السور مباشرة"""
    query = update.callback_query
    await query.answer()
    await browse_quran_text(update, context)

async def browse_quran_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح المصحف النصي"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور. يرجى المحاولة لاحقاً.")
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
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"quran_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"quran_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # إزالة زر الراديو من الصفحات الفرعية
    keyboard.append([InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
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
    await query.answer()
    
    page = int(query.data.split('_')[2])
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور. يرجى المحاولة لاحقاً.")
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
    
    # إزالة زر الراديو من الصفحات الفرعية
    keyboard.append([InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📖 *المصحف الشريف - النسخة النصية*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🔢 **السور المعروضة:** {start_idx + 1} - {end_idx}\n\n"
        f"✨ **اختر السورة التي تريد قراءتها:**\n\n"
        f"💡 **ملاحظة:** يمكنك التنقل بين الصفحات باستخدام الأزرار أدناه",
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
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السورة. يرجى المحاولة لاحقاً.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📖 قراءة السورة كاملة", callback_data=f"read_surah_{surah_number}")],
        [InlineKeyboardButton("🖼️ عرض الصفحات المصورة", callback_data=f"surah_img_{surah_number}")],
        [InlineKeyboardButton("🎵 الاستماع للتلاوات", callback_data=f"audio_surah_{surah_number}")],
        [
            InlineKeyboardButton("⬅️ السورة السابقة", callback_data=f"surah_{surah_number-1 if surah_number > 1 else 1}"),
            InlineKeyboardButton("السورة التالية ➡️", callback_data=f"surah_{surah_number+1 if surah_number < 114 else 114}")
        ],
        [InlineKeyboardButton("🔙 العودة لقائمة السور", callback_data="browse_quran_text")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
📖 *سورة {surah_data['name_arabic']} ({surah_data['name']})*

📊 **معلومات السورة:**
• 🔢 **رقم السورة:** {surah_number}
• 📝 **عدد الآيات:** {surah_data['ayahs_count']} آية
• 📍 **نوع النزول:** {surah_data['revelation_type']}
• 📚 **الترتيب في القرآن:** {surah_number}

🌟 **اختر الإجراء المناسب:**

1️⃣ **قراءة السورة:** عرض النص الكامل للآيات
2️⃣ **المصحف المصور:** تصفح صفحات السورة بصيغة الصور
3️⃣ **التلاوات الصوتية:** الاستماع للسورة بأصوات مختلفة
4️⃣ **التنقل بين السور:** الانتقال للسورة السابقة أو التالية

💡 **نصيحة:** يمكنك الاستماع للسورة أثناء قراءتها للحصول على تجربة متكاملة.
    """
    
    try:
        # التحقق من نوع الرسالة الحالية (إذا كانت صورة، نرسل رسالة نصية جديدة ونحذف الصورة)
        if query.message.photo:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            await query.message.delete()
        else:
            # التعديل العادي إذا كانت الرسالة نصية
            await query.edit_message_text(
                message_text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error in show_surah UI update: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def browse_quran_images(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    """قائمة السور للمصحف المصور"""
    query = update.callback_query
    await query.answer()
    
    surah_info = await load_surah_info()
    if not surah_info:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور. يرجى المحاولة لاحقاً.")
        return
    
    surahs_per_page = 10
    total_pages = (len(surah_info) + surahs_per_page - 1) // surahs_per_page
    
    start_idx = page * surahs_per_page
    end_idx = min(start_idx + surahs_per_page, len(surah_info))
    
    keyboard = []
    for i in range(start_idx, end_idx):
        surah = surah_info[i]
        button_text = f"{surah['number']}. {surah['name']}"
        # توجيه المستخدم لصفحة معلومات السورة بدلاً من الصور مباشرة
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"surah_{surah['number']}")])
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"quran_img_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"quran_img_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # إزالة زر الراديو من الصفحات الفرعية
    keyboard.append([InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
🖼️ *المصحف الشريف - النسخة المصورة*

🌟 **مميزات النسخة المصورة:**
• 📸 جودة عالية للصور
• 📖 تجربة قراءة أقرب للورقية
• 🎯 دقة في العرض والخطوط
• 💾 إمكانية التكبير والتصغير

📊 **الإحصائيات:**
• عدد الصفحات: 604 صفحة
• تغطية كاملة للقرآن الكريم
• دعم جميع الأجهزة

📄 **الصفحة:** {page + 1} من {total_pages}
🔢 **السور المعروضة:** {start_idx + 1} - {end_idx}

✨ **اختر السورة التي تريد عرض صفحاتها:**

💡 **ملاحظة:** اضغط على اسم السورة للانتقال لصفحة المعلومات ثم اختر 'عرض الصفحات المصورة'
    """
    
    try:
        # Check if current message is a photo message
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
        logger.error(f"Error in browse_quran_images: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def browse_quran_images_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تصفح صفحات السور للمصحف المصور"""
    query = update.callback_query
    page = int(query.data.split('_')[3])
    await browse_quran_images(update, context, page)

async def show_surah_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض أول صفحة من السورة المصورة"""
    query = update.callback_query
    await query.answer()
    
    surah_number = int(query.data.split('_')[2])
    page_range = SURAH_PAGES_MAPPING.get(surah_number)
    
    if not page_range:
        await query.edit_message_text("❌ **عذراً:** لم يتم العثور على صفحات هذه السورة في قاعدة البيانات.")
        return
        
    start_page = page_range[0]
    await send_quran_page(update, context, start_page, surah_number)

async def view_quran_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض صفحة محددة من المصحف"""
    query = update.callback_query
    await query.answer()
    
    data = query.data.split('_')
    page_number = int(data[2])
    surah_number = int(data[3])
    
    await send_quran_page(update, context, page_number, surah_number)

async def send_quran_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page_number: int, surah_number: int):
    """إرسال صفحة المصحف كصورة بعد تحميلها"""
    query = update.callback_query
    
    # تنسيق رقم الصفحة للرابط (001.png)
    page_str = str(page_number).zfill(3)
    # رابط الموقع الذي يوفر الصور
    image_url = f"https://quran.yousefheiba.com/api/quran-pages/{page_str}.png"
    
    surah_info = await load_surah_info()
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    surah_name = surah_data['name'] if surah_data else f"سورة {surah_number}"
    surah_name_arabic = surah_data['name'] if surah_data else ""
    
    page_range = SURAH_PAGES_MAPPING.get(surah_number)
    if not page_range:
        await query.answer("❌ لم يتم العثور على نطاق الصفحات لهذه السورة", show_alert=True)
        return
    
    total_surah_pages = page_range[1] - page_range[0] + 1
    current_in_surah = page_number - page_range[0] + 1
    
    caption = f"""
📖 *{surah_name_arabic} ({surah_name})*

📊 **معلومات الصفحة:**
• 📄 **رقم الصفحة:** {page_number} من 604
• 📑 **الصفحة في السورة:** {current_in_surah} من {total_surah_pages}
• 🔢 **رقم السورة:** {surah_number}
• 📝 **عدد آيات السورة:** {surah_data['numberOfAyahs'] if surah_data else 'غير معروف'}

💡 **تلميحات:**
• يمكنك التكبير والتصغير في الصورة
• استخدم أزرار التنقل للانتقال بين الصفحات
• اضغط على 'العودة للسورة' لمزيد من الخيارات
    """
    
    keyboard = []
    nav_row = []
    if page_number > page_range[0]:
        nav_row.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"view_page_{page_number-1}_{surah_number}"))
    if page_number < page_range[1]:
        nav_row.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"view_page_{page_number+1}_{surah_number}"))
    
    if nav_row:
        keyboard.append(nav_row)
        
    # أزرار السور التالية والسابقة للمصحف المصور
    surah_nav_img = []
    if surah_number > 1:
        surah_nav_img.append(InlineKeyboardButton("⬅️ السورة السابقة", callback_data=f"surah_{surah_number-1}"))
    if surah_number < 114:
        surah_nav_img.append(InlineKeyboardButton("السورة التالية ➡️", callback_data=f"surah_{surah_number+1}"))
    if surah_nav_img:
        keyboard.append(surah_nav_img)
        
    keyboard.append([InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")])
    keyboard.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # إعلام المستخدم أننا نحمل الصورة
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id, 
        action=ChatAction.UPLOAD_PHOTO
    )
    
    try:
        # 1. تحميل الصورة من الرابط
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url, timeout=30) as response:
                if response.status != 200:
                    raise Exception(f"Failed to load image: HTTP {response.status}")
                
                # التحقق من نوع المحتوى
                content_type = response.headers.get('Content-Type', '')
                if 'image' not in content_type:
                    raise Exception(f"Not an image: {content_type}")
                
                # قراءة بيانات الصورة
                image_data = await response.read()
                
                # التحقق من حجم البيانات
                if len(image_data) > 10_000_000:  # 10MB
                    raise Exception("Image too large")
                
                # إنشاء كائن BytesIO من البيانات
                photo_file = io.BytesIO(image_data)
                photo_file.name = f"page_{page_str}.png"
        
        # 2. محاولة تعديل الرسالة الحالية (إذا كانت صورة)
        if query.message.photo:
            from telegram import InputMediaPhoto
            # إعادة تعيين المؤشر لبداية الملف
            photo_file.seek(0)
            try:
                await query.edit_message_media(
                    media=InputMediaPhoto(media=photo_file, caption=caption, parse_mode=ParseMode.MARKDOWN),
                    reply_markup=reply_markup
                )
                return
            except Exception as edit_error:
                logger.warning(f"Failed to edit message, sending new: {edit_error}")
                # استمر في إرسال رسالة جديدة
        
        # 3. إرسال الصورة كرسالة جديدة
        # إعادة تعيين المؤشر لبداية الملف
        photo_file.seek(0)
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=photo_file,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )
        
        # 4. حذف الرسالة القديمة إذا لم تكن صورة
        if not query.message.photo:
            try:
                await query.message.delete()
            except:
                pass
                
    except asyncio.TimeoutError:
        logger.error(f"Timeout loading image: {image_url}")
        await query.answer("❌ انتهت المهلة في تحميل الصورة. يرجى المحاولة مرة أخرى.", show_alert=True)
    except aiohttp.ClientError as e:
        logger.error(f"Network error loading image: {e}")
        await query.answer("❌ خطأ في الشبكة أثناء تحميل الصورة. يرجى التحقق من اتصالك.", show_alert=True)
    except Exception as e:
        logger.error(f"Error loading/sending quran page: {e}")
        
        # Fallback: استخدام الطريقة القديمة (إرسال الرابط مباشرة) كحل أخير
        try:
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=image_url,
                caption=caption + "\n\n⚠️ _تم استخدام النسخة الاحتياطية_",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            if not query.message.photo:
                await query.message.delete()
        except Exception as e2:
            logger.error(f"Fallback also failed: {e2}")
            await query.answer("❌ عذراً، تعذر تحميل هذه الصفحة حالياً. يرجى المحاولة مرة أخرى.", show_alert=True)

async def read_surah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قراءة السورة كاملة"""
    query = update.callback_query
    await query.answer()
    
    surah_number = int(query.data.split('_')[2])
    
    # تحميل بيانات السورة
    surah_data = await load_surah_data(surah_number)
    
    if not surah_data:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السورة. يرجى المحاولة لاحقاً.")
        return
    
    # إنشاء نص السورة
    surah_text = f"📖 *سورة {surah_data['name_arabic']} ({surah_data['name']})*\n\n"
    
    # إضافة البسملة للسور (عدا التوبة)
    if surah_number != 9:
        surah_text += "*بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ*\n\n"
    
    # فرز الآيات حسب أرقامها
    verses = surah_data['verses']
    sorted_verses = sorted(verses.items(), key=lambda x: int(x[0]))
    
    for verse_number, verse_text in sorted_verses:
        # إزالة البسملة من بداية الآية الأولى إذا كانت موجودة (لتجنب التكرار)
        display_text = verse_text
        if int(verse_number) == 1 and surah_number != 9:
            # تنظيف النص من البسملة بأشكالها المختلفة
            basmala_variants = [
                "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                "بِسمِ اللَّهِ الرَّحمٰنِ الرَّحيمِ",
                "بِسْمِ اللهِ الرَّحْمٰنِ الرَّحِيْمِ"
            ]
            for variant in basmala_variants:
                if display_text.startswith(variant):
                    display_text = display_text[len(variant):].strip()
                    break
        
        surah_text += f"{display_text} ﴿{verse_number}﴾\n\n"
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(surah_text) > 3000:
            keyboard = [
                [
                    InlineKeyboardButton("⬅️ عودة", callback_data=f"surah_{surah_number}"),
                    InlineKeyboardButton("المتابعة ➡️", callback_data=f"continue_surah_{surah_number}_{verse_number}")
                ],
                [
                    InlineKeyboardButton("⬅️ السورة السابقة", callback_data=f"read_surah_{surah_number-1 if surah_number > 1 else 1}"),
                    InlineKeyboardButton("السورة التالية ➡️", callback_data=f"read_surah_{surah_number+1 if surah_number < 114 else 114}")
                ],
                [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_surah_{surah_number}")],
                [InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")],
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                surah_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    keyboard = []
    # أزرار السور التالية والسابقة للمصحف كنص
    surah_nav = []
    if surah_number > 1:
        surah_nav.append(InlineKeyboardButton("⬅️ السورة السابقة", callback_data=f"read_surah_{surah_number-1}"))
    if surah_number < 114:
        surah_nav.append(InlineKeyboardButton("السورة التالية ➡️", callback_data=f"read_surah_{surah_number+1}"))
    if surah_nav:
        keyboard.append(surah_nav)

    keyboard.append([InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_surah_{surah_number}")])
    keyboard.append([InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")])
    keyboard.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")])
    
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
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السورة. يرجى المحاولة لاحقاً.")
        return
    
    # إنشاء نص السورة من الآية المحددة
    surah_text = f"📖 *سورة {surah_data['name_arabic']} ({surah_data['name']})*\n\n"
    surah_text += "*...تتمة السورة...*\n\n"
    
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
            # إزالة البسملة المتكررة
            display_text = verse_text
            if verse_num == 1 and surah_number != 9:
                basmala_variants = [
                    "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
                    "بِسمِ اللَّهِ الرَّحمٰنِ الرَّحيمِ",
                    "بِسْمِ اللهِ الرَّحْمٰنِ الرَّحِيْمِ"
                ]
                for variant in basmala_variants:
                    if display_text.startswith(variant):
                        display_text = display_text[len(variant):].strip()
                        break
            else:
                display_text = verse_text
        else:
            display_text = verse_text
            
        surah_text += f"{display_text} ﴿{verse_number}﴾\n\n"
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(surah_text) > 3000:
            keyboard = [
                [
                    InlineKeyboardButton("⬅️ عودة", callback_data=f"surah_{surah_number}"),
                    InlineKeyboardButton("المتابعة ➡️", callback_data=f"continue_surah_{surah_number}_{verse_number}")
                ],
                [
                    InlineKeyboardButton("⬅️ السورة السابقة", callback_data=f"read_surah_{surah_number-1 if surah_number > 1 else 1}"),
                    InlineKeyboardButton("السورة التالية ➡️", callback_data=f"read_surah_{surah_number+1 if surah_number < 114 else 114}")
                ],
                [InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_surah_{surah_number}")],
                [InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")],
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                surah_text + "\n*...يتبع*",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup
            )
            return
    
    # إضافة أزرار التنقل
    keyboard = []
    nav_row = []
    if surah_number > 1:
        nav_row.append(InlineKeyboardButton("⬅️ السورة السابقة", callback_data=f"read_surah_{surah_number-1}"))
    if surah_number < 114:
        nav_row.append(InlineKeyboardButton("السورة التالية ➡️", callback_data=f"read_surah_{surah_number+1}"))
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([InlineKeyboardButton("🎵 الاستماع للتلاوة", callback_data=f"audio_surah_{surah_number}")])
    keyboard.append([InlineKeyboardButton("🔙 العودة للسورة", callback_data=f"surah_{surah_number}")])
    keyboard.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")])
    
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
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات الأجزاء. يرجى المحاولة لاحقاً.")
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
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"juz_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"juz_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # إزالة زر الراديو من الصفحات الفرعية
    keyboard.append([InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📚 *أجزاء القرآن الكريم*\n\n"
        f"📊 **معلومات الأجزاء:**\n"
        f"• عدد الأجزاء: 30 جزء\n"
        f"• كل جزء يحتوي على 20 صفحة تقريباً\n"
        f"• الأجزاء مقسمة لتسهيل ختم القرآن\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"اختر الجزء الذي تريد قراءته:\n\n"
        f"💡 **نصيحة:** يمكنك تقسيم قراءة جزء يومياً لختم القرآن في شهر.",
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
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات الأجزاء. يرجى المحاولة لاحقاً.")
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
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"juz_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"juz_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # إزالة زر الراديو من الصفحات الفرعية
    keyboard.append([InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📚 *أجزاء القرآن الكريم*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"اختر الجزء الذي تريد قراءته:\n\n"
        f"💡 **نصيحة:** اضغط على اسم الجزء لعرض خيارات القراءة.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def show_juz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات الجزء"""
    query = update.callback_query
    await query.answer()
    
    juz_number = int(query.data.split('_')[1])
    
    keyboard = [
        [InlineKeyboardButton("📖 قراءة الجزء كاملاً", callback_data=f"read_juz_{juz_number}")],
        [InlineKeyboardButton("🎵 الاستماع للجزء", callback_data=f"audio_juz_{juz_number}")],
        [
            InlineKeyboardButton("⬅️ الجزء السابق", callback_data=f"juz_{juz_number-1 if juz_number > 1 else 1}"),
            InlineKeyboardButton("الجزء التالي ➡️", callback_data=f"juz_{juz_number+1 if juz_number < 30 else 30}")
        ],
        [InlineKeyboardButton("🔙 العودة لقائمة الأجزاء", callback_data="browse_juz")],
        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = f"""
📚 *الجزء {juz_number}*

📊 **معلومات الجزء:**
• 🔢 **رقم الجزء:** {juz_number} من 30
• 📖 **عدد الصفحات:** حوالي 20 صفحة
• 🕐 **مدة القراءة:** 20-30 دقيقة تقريباً
• 📈 **التقدم:** {round((juz_number/30)*100, 1)}% من القرآن

🌟 **خيارات متاحة:**

1️⃣ **قراءة الجزء:** عرض النص الكامل للجزء
2️⃣ **الاستماع للجزء:** تلاوة صوتية للجزء كاملاً
3️⃣ **التنقل بين الأجزاء:** الانتقال للجزء السابق أو التالي

💡 **نصيحة للختمة:**
اقرأ جزءاً يومياً لتختم القرآن في شهر واحد.
يمكنك تقسيم الجزء إلى أربعة أرباع (5 صفحات لكل ربع).
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
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور. يرجى المحاولة لاحقاً.")
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
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"audio_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"audio_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # إزالة زر الراديو من الصفحات الفرعية
    keyboard.append([InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎵 *مكتبة التلاوات الصوتية*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n\n"
        "✨ **اختر سورة لتستمع إلى تلاوتها:**\n\n"
        "🌟 **مميزات المكتبة الصوتية:**\n"
        "• 📻 مجموعة كبيرة من أشهر القراء\n"
        "• 🎧 جودة صوت عالية (HQ)\n"
        "• ⏯️ إمكانية التحكم في التشغيل\n"
        "• 💾 تشغيل مباشر أو تحميل\n\n"
        "🔊 **القراء المتاحون:**\n"
        "مشاري العفاسي، سعد الغامدي، عبدالباسط، وغيرهم الكثير",
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
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في تحميل بيانات السور. يرجى المحاولة لاحقاً.")
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
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"audio_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"audio_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # إزالة زر الراديو من الصفحات الفرعية
    keyboard.append([InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "🎵 *مكتبة التلاوات الصوتية*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🔢 **السور المعروضة:** {start_idx + 1} - {end_idx}\n\n"
        "✨ **اختر سورة لتستمع إلى تلاوتها:**\n\n"
        "💡 **تلميح:** يمكنك البحث عن قارئ محدد باستخدام زر البحث",
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
        await query.edit_message_text("❌ **خطأ:** لم يتم تحديد السورة بشكل صحيح.")
        return
    
    # جلب القُراء المتاحين
    reciters = await load_reciters()
    if not reciters:
        await query.edit_message_text("❌ **عذراً:** لا يوجد قُراء متاحين حالياً. يرجى المحاولة لاحقاً.")
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
        await query.edit_message_text("❌ **عذراً:** لا يوجد قُراء متاحين لهذه السورة حالياً.")
        return
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"reciters_page_{surah_number}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"reciters_page_{surah_number}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # إضافة زر البحث عن قارئ
    keyboard.append([InlineKeyboardButton("🔍 البحث عن قارئ محدد", callback_data=f"search_reciter_{surah_number}")])
    
    keyboard.append([
        InlineKeyboardButton("🔙 العودة للسور", callback_data="audio_menu"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # جلب اسم السورة
    surah_info = await load_surah_info()
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    surah_name = surah_data['name'] if surah_data else f"سورة {surah_number}"
    surah_name_arabic = surah_data['name'] if surah_data else ""
    
    await query.edit_message_text(
        f"🎵 *قائمة القراء لسورة {surah_name_arabic} ({surah_name})*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🎤 **عدد القراء المتاحين:** {len(reciters)}\n\n"
        "✨ **اختر القارئ المفضل لديك:**\n\n"
        "🌟 **مميزات التشغيل:**\n"
        "• 🔊 جودة صوت عالية\n"
        "• ⏯️ تحكم كامل في التشغيل\n"
        "• 📥 إمكانية التحميل\n"
        "• 🔄 إعادة التشغيل التلقائي\n\n"
        "💡 **تلميح:** اضغط على اسم القارئ للاستماع مباشرة",
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
        await query.edit_message_text("❌ **عذراً:** لا يوجد قُراء متاحين حالياً. يرجى المحاولة لاحقاً.")
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
        await query.edit_message_text("❌ **عذراً:** لا يوجد قُراء متاحين لهذه السورة حالياً.")
        return
    
    # أزرار التنقل
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ الصفحة السابقة", callback_data=f"reciters_page_{surah_number}_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("الصفحة التالية ➡️", callback_data=f"reciters_page_{surah_number}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # إضافة زر البحث عن قارئ
    keyboard.append([InlineKeyboardButton("🔍 البحث عن قارئ محدد", callback_data=f"search_reciter_{surah_number}")])
    
    keyboard.append([
        InlineKeyboardButton("🔙 العودة للسور", callback_data="audio_menu"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # جلب اسم السورة
    surah_info = await load_surah_info()
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    surah_name = surah_data['name'] if surah_data else f"سورة {surah_number}"
    surah_name_arabic = surah_data['name'] if surah_data else ""
    
    await query.edit_message_text(
        f"🎵 *قائمة القراء لسورة {surah_name_arabic} ({surah_name})*\n\n"
        f"📄 **الصفحة:** {page + 1} من {total_pages}\n"
        f"🎤 **القراء المعروضون:** {start_idx + 1} - {end_idx}\n\n"
        "✨ **اختر القارئ المفضل لديك:**\n\n"
        "💡 **تلميح:** يمكنك استخدام زر البحث للعثور على قارئ محدد",
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
        await query.edit_message_text("❌ **خطأ:** رقم السورة غير صحيح.")
        return
    
    surah_data = next((s for s in surah_info if s['number'] == surah_number), None)
    if not surah_data:
        await query.edit_message_text("❌ **عذراً:** لم يتم العثور على معلومات السورة.")
        return
    
    surah_name = surah_data['name']
    surah_name_arabic = surah_data['name']
    
    # جلب معلومات القارئ
    reciters = await load_reciters()
    reciter = next((r for r in reciters if r['id'] == reciter_id), None)
    if not reciter:
        await query.edit_message_text("❌ **عذراً:** لم يتم العثور على معلومات القارئ.")
        return
    
    reciter_name = reciter['name']
    
    # إعلام المستخدم بأن التحميل جارٍ
    await query.edit_message_text(f"⏳ **جاري التحميل...**\n\n🎧 سورة *{surah_name}*\n🎤 بصوت *{reciter_name}*\n\n⏳ يرجى الانتظار...")
    
    # جلب رابط الصوت
    audio_url = await get_reciter_audio(reciter_id, surah_number)
    
    if not audio_url:
        await query.edit_message_text("❌ **عذراً:** تعذر العثور على التلاوة المطلوبة.")
        return
    
    # إرسال ملف الصوت بدون أي نص أو أزرار
    try:
        # الرسالة الأولى: الملف الصوتي فقط
        audio_msg = await context.bot.send_audio(
            chat_id=query.message.chat_id,
            audio=audio_url,
            title=f"سورة {surah_name} - {reciter_name}",
            performer=reciter_name,
            read_timeout=90,
            write_timeout=90,
            connect_timeout=90,
            pool_timeout=90
        )
        
        # الرسالة الثانية: النص والأزرار
        message_text = f"""
🌟 *تم إرسال التلاوة بنجاح!*

📖 **معلومات التلاوة:**
• 🎧 **القارئ:** {reciter_name}
• 📖 **السورة:** {surah_name_arabic} ({surah_name})
• 🔢 **رقم السورة:** {surah_number}
• 📝 **عدد الآيات:** {surah_data['numberOfAyahs']} آية
• ⏱️ **المدة التقريبية:** {surah_data['numberOfAyahs']//3} دقيقة

✨ **خيارات إضافية:**

💡 **نصائح للاستماع:**
• استمع في مكان هادئ للتركيز
• حاول متابعة القراءة من المصحف
• كرر الاستماع للآيات الصعبة
• استفد من الوقت في السيارة أو المواصلات
        """
        
        keyboard = [
            [InlineKeyboardButton("🎵 تلاوات أخرى للسورة", callback_data=f"reciters_{surah_number}")],
            [InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu")]
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

📖 **معلومات التلاوة:**
• **السورة:** *{surah_name_arabic} ({surah_name})*
• **القارئ:** *{reciter_name}*
• **الرابط:** متوفر بالضغط على الزر أدناه

👨‍💻 **ملاحظة فنية:**
بعض السور الكبيرة قد تواجه صعوبة في الإرسال المباشر بسبب:
• قيود حجم الملف في نظام تيليجرام
• مدة التسجيلات الطويلة
• اتصال الإنترنت

🎯 **الحلول المقترحة:**
1. اضغط على الزر للاستماع مباشرة من المتصفح
2. جرب سوراً أقصر للتجربة المباشرة
3. استخدم الراديو للاستماع المستمر

✨ **السور القصيرة تعمل بشكل ممتاز!**
        """
        
        # إرسال الرسالة مع الزر
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎧 استمع الآن من المتصفح", url=audio_url)],
                [InlineKeyboardButton("🔙 العودة للقارئين", callback_data=f"reciters_{surah_number}")]
            ])
        )
        
        # حذف رسالة "جاري التحميل"
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=query.message.message_id)

async def search_quran(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية البحث"""
    query = update.callback_query
    await query.answer()
    
    # التحقق من وجود مفتاح API
    if not GEMINI_API_KEY:
        await query.edit_message_text(
            "⚠️ *ميزة البحث الذكي غير متاحة حالياً*\n\n"
            "🔧 **السبب:** لم يتم إعداد مفتاح Google Gemini API.\n\n"
            "💡 **ماذا يمكنك أن تفعل؟**\n"
            "• استخدم الميزات الأخرى للبوت\n"
            "• تواصل مع المطور لإضافة المفتاح\n"
            "• جرب البحث عن طريق تصفح السور مباشرة\n\n"
            "🌟 **الميزات المتاحة:**\n"
            "• 📖 تصفح كامل القرآن\n"
            "• 📻 راديو مباشر\n"
            "• 🎵 مكتبة التلاوات\n"
            "• 📚 تصفح الأجزاء والأحزاب",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await query.edit_message_text(
        "🔍 *البحث الذكي في القرآن الكريم*\n\n"
        "🌟 **مميزات البحث:**\n"
        "• بحث متقدم باستخدام الذكاء الاصطناعي\n"
        "• دعم البحث باللغة العربية والإنجليزية\n"
        "• تفسير مختصر للآيات مباشرة\n"
        "• عرض السياق الكامل للآية\n\n"
        "📝 **أمثلة للبحث:**\n"
        "• 'الرحمن الرحيم'\n"
        "• 'الصبر واليقين'\n"
        "• 'الجنة والنار'\n"
        "• 'التوبة والمغفرة'\n"
        "• 'آيات عن الصلاة'\n\n"
        "✨ **اكتب الكلمة أو الجملة التي تريد البحث عنها:**\n\n"
        "💡 **تلميح:** كلما كانت الكلمة أكثر تحديداً، كانت النتائج أدق.",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data['search_mode'] = True

async def perform_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ البحث في القرآن باستخدام Google Gemini API"""
    
    # تحقق من وجود مفتاح API
    if not GEMINI_API_KEY:
        await update.message.reply_text(
            "⚠️ **عذراً:** ميزة البحث الذكي غير متاحة حالياً.\n\n"
            "🔧 **السبب:** لم يتم تعيين مفتاح Google Gemini API.\n\n"
            "💡 **ماذا يمكنك أن تفعل؟**\n"
            "• استخدم ميزات البوت الأخرى المتاحة\n"
            "• تواصل مع المطور لإضافة المفتاح\n"
            "• جرب البحث عن طريق كلمات محددة يدوياً"
        )
        return
    
    search_text = update.message.text.strip()
    
    if len(search_text) < 3:
        await update.message.reply_text("🔍 **تنبيه:** يرجى إدخال كلمة مكونة من 3 أحرف على الأقل للحصول على نتائج دقيقة.")
        return
    
    # مسح حالة البحث
    context.user_data.pop('search_mode', None)
    
    # إعلام المستخدم بأن البحث جارٍ
    processing_msg = await update.message.reply_text("🔍 **جاري البحث...**\n\n⏳ يرجى الانتظار قليلاً...")
    
    # إعداد بيانات الطلب لـ Google Gemini API
    prompt = f"""
أنت مساعد متخصص في القرآن الكريم. 
ابحث في القرآن عن: "{search_text}"
أعطني النتائج مباشرة مع ذكر:
1. السورة ورقم الآية
2. نص الآية
3. تفسير مختصر (سطرين كحد أقصى)

إجابة مباشرة بدون مقدمة أو خاتمة.
أجب باللغة العربية فقط.
    """
    
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 1024
        },
        "safetySettings": [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_NONE"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_NONE"
            }
        ]
    }
    
    # URL مع المفتاح
    url = f"{GEMINI_API_URL}?key={GEMINI_API_KEY}"
    
    headers = {
        'Content-Type': 'application/json'
    }
    
    # إرسال طلب البحث
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers, timeout=45) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Gemini API Response: {json.dumps(result, ensure_ascii=False)[:500]}")
                    
                    # استخراج النص من الاستجابة
                    if 'candidates' in result and len(result['candidates']) > 0:
                        candidate = result['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            ai_reply = candidate['content']['parts'][0]['text']
                        else:
                            ai_reply = "❌ **عذراً:** لم أتمكن من استخراج النتائج من الرد."
                    else:
                        ai_reply = "❌ **عذراً:** لم أتلق أي نتائج من API."
                        
                elif response.status == 400:
                    ai_reply = "❌ **خطأ في الطلب:** ربما البحث يحتوي على محتوى غير مسموح به."
                elif response.status == 401:
                    ai_reply = "❌ **خطأ في المصادقة:** مفتاح API غير صالح أو منتهي الصلاحية."
                elif response.status == 429:
                    ai_reply = "❌ **تجاوز الحد:** تم تجاوز عدد الطلبات المسموح بها. يرجى المحاولة لاحقاً."
                else:
                    error_text = await response.text()
                    logger.error(f"Gemini API Error {response.status}: {error_text}")
                    ai_reply = f"❌ **خطأ في الخادم:** {response.status}. يرجى المحاولة لاحقاً."
                    
    except asyncio.TimeoutError:
        logger.error("Timeout error with Gemini API")
        ai_reply = "❌ **انتهت المهلة:** استغرقت العملية وقتاً طويلاً. يرجى المحاولة مرة أخرى."
    except aiohttp.ClientError as e:
        logger.error(f"Network error: {e}")
        ai_reply = "❌ **خطأ في الشبكة:** تعذر الاتصال بخادم البحث. تحقق من اتصالك بالإنترنت."
    except Exception as e:
        logger.error(f"Unexpected error in search: {e}")
        ai_reply = "❌ **خطأ غير متوقع:** حدث خطأ ما. يرجى المحاولة مرة أخرى."
    
    # حذف رسالة "جاري البحث"
    try:
        await context.bot.delete_message(
            chat_id=update.message.chat_id,
            message_id=processing_msg.message_id
        )
    except:
        pass
    
    # إذا لم نتمكن من الحصول على رد
    if not ai_reply or ai_reply.startswith("❌"):
        await update.message.reply_text(
            f"{ai_reply}\n\n"
            "💡 **اقتراحات للبحث:**\n"
            "• جرب استخدام كلمات مختلفة\n"
            "• تأكد من اتصال الإنترنت\n"
            "• انتظر قليلاً ثم حاول مرة أخرى\n"
            "• استخدم البحث عن طريق السور والآيات المباشرة"
        )
        return
    
    # تنظيف النتائج
    ai_reply = ai_reply.strip()
    
    # حفظ النتائج في الذاكرة المؤقتة
    cache['search_results'][update.message.chat_id] = {
        'results': ai_reply,
        'query': search_text
    }
    
    # عرض النتائج
    await show_search_results(update, context)

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
            await update.callback_query.edit_message_text("❌ **عذراً:** لم يتم العثور على بيانات البحث. يرجى إجراء بحث جديد.")
        else:
            await update.message.reply_text("❌ **عذراً:** لم يتم العثور على بيانات البحث. يرجى إجراء بحث جديد.")
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
    
    # إزالة زر الراديو من نتائج البحث
    keyboard = [
        [InlineKeyboardButton("🔍 بحث جديد", callback_data="search_quran")],
        [InlineKeyboardButton("🏠 العودة للقائمة الرئيسية", callback_data="main_menu")]
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
                    text=f"🔍 *نتائج البحث عن:* \"{query}\"\n\n{part}\n\n"
                         "🌟 **هل تود البحث عن شيء آخر?**\n\n"
                         "💡 **تلميح:** يمكنك استخدام البحث للعثور على:\n"
                         "• آيات عن مواضيع محددة\n"
                         "• تفسير كلمات معينة\n"
                         "• مقارنة بين آيات متشابهة",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔍 *نتائج البحث عن:* \"{query}\"\n\n{part}",
                    parse_mode=ParseMode.MARKDOWN
                )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🔍 *نتائج البحث عن:* \"{query}\"\n\n{results}\n\n"
                 "🌟 **هل تود البحث عن شيء آخر?**\n\n"
                 "💡 **تلميح:** البحث متاح 24/7 بأي وقت تشاء.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """العودة للقائمة الرئيسية - الصفحة الرئيسية الثانية"""
    query = update.callback_query
    await query.answer()
    
    # إنشاء زر الراديو كزر ويب مع تصميم مميز
    radio_button = InlineKeyboardButton(
        "📻 راديو سطور من السماء", 
        web_app={"url": f"{BASE_WEB_URL}/radio"}
    )
    
    keyboard = [
        [InlineKeyboardButton("📖 تصفح المصحف النصي", callback_data="browse_quran_text")],
        [InlineKeyboardButton("🖼️ المصحف المصور عالي الجودة", callback_data="browse_quran_images")],
        [radio_button],
        [InlineKeyboardButton("🔍 بحث ذكي في القرآن", callback_data="search_quran")],
        [InlineKeyboardButton("📚 تصفح الأجزاء والأحزاب", callback_data="browse_juz")],
        [InlineKeyboardButton("🎵 مكتبة التلاوات الصوتية", callback_data="audio_menu")],
        [InlineKeyboardButton("👨‍💻 المطور & الدعم", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = """
✨ *سُطورٌ من السَّماء* ☁️

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

🚀 **اختر الخدمة التي تناسبك من القائمة أدناه:**
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
        logger.error(f"Error in main_menu UI update: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )

async def search_reciter_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب اسم القارئ للبحث"""
    query = update.callback_query
    await query.answer()
    
    surah_number = int(query.data.split('_')[2])
    context.user_data['search_reciter_surah'] = surah_number
    context.user_data['search_reciter_mode'] = True
    
    await query.edit_message_text(
        "🔍 *البحث عن قارئ محدد*\n\n"
        "🌟 **كيفية البحث:**\n"
        "• اكتب اسم القارئ أو جزء منه\n"
        "• يمكنك البحث باللغة العربية أو الإنجليزية\n"
        "• الأسماء غير الحساسة لحالة الأحرف\n\n"
        "📝 **أمثلة:**\n"
        "• 'مشاري العفاسي'\n"
        "• 'سعد الغامدي'\n"
        "• 'عبدالباسط'\n"
        "• 'الحصري'\n\n"
        "✨ **من فضلك اكتب اسم القارئ الذي تبحث عنه:**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 إلغاء والعودة", callback_data=f"reciters_{surah_number}")
        ]])
    )

async def perform_reciter_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنفيذ البحث عن القارئ"""
    search_query = update.message.text.strip().lower()
    surah_number = context.user_data.get('search_reciter_surah')
    
    # مسح حالة البحث
    context.user_data.pop('search_reciter_mode', None)
    
    reciters = await load_reciters()
    if not reciters:
        await update.message.reply_text("❌ **عذراً:** حدث خطأ في تحميل قائمة القراء. يرجى المحاولة لاحقاً.")
        return
        
    # البحث عن القراء المطابقين
    matched_reciters = [r for r in reciters if search_query in r['name'].lower()]
    
    if not matched_reciters:
        keyboard = [[InlineKeyboardButton("🔙 العودة للقائمة", callback_data=f"reciters_{surah_number}")]]
        await update.message.reply_text(
            f"❌ **لم يتم العثور على نتائج:**\n\n"
            f"بحثت عن: *{search_query}*\n"
            f"عدد القراء الكلي: {len(reciters)}\n\n"
            "💡 **اقتراحات:**\n"
            "• تحقق من كتابة الاسم بشكل صحيح\n"
            "• جرب كتابة جزء من الاسم فقط\n"
            "• استخدم الأسماء المشهورة\n"
            "• ابحث باللغة العربية",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
        
    keyboard = []
    for reciter in matched_reciters[:15]:  # عرض أول 15 نتيجة فقط
        keyboard.append([InlineKeyboardButton(f"🎧 {reciter['name']}", callback_data=f"play_audio_{reciter['id']}_{surah_number}")])
        
    keyboard.append([InlineKeyboardButton("🔍 بحث جديد", callback_data=f"search_reciter_{surah_number}")])
    
    keyboard.append([
        InlineKeyboardButton("🔙 العودة للسور", callback_data="audio_menu"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="main_menu")
    ])
    
    await update.message.reply_text(
        f"🔍 *نتائج البحث عن:* {search_query}\n\n"
        f"🎤 **عدد النتائج:** {len(matched_reciters)}\n"
        f"📖 **السورة:** {surah_number}\n\n"
        "✨ **اختر القارئ المطلوب:**\n\n"
        "💡 **تلميح:** اضغط على اسم القارئ للاستماع مباشرة",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def read_juz(update: Update, context: ContextTypes.DEFAULT_TYPE, juz_number: int):
    """قراءة الجزء كاملاً"""
    query = update.callback_query
    await query.answer()
    
    # إعلام المستخدم بأن التحميل جارٍ
    await query.edit_message_text(f"⏳ **جاري التحميل...**\n\n📖 **الجزء {juz_number}**\n\n⏳ يرجى الانتظار، هذه العملية قد تستغرق بضع ثوانٍ...")
    
    # جلب بيانات الجزء
    url = f"{BASE_URL}/juz/{juz_number}/ar.alafasy"
    data = await fetch_json(url)
    
    if not data or data.get('code') != 200 or 'data' not in data:
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في جلب بيانات الجزء. يرجى المحاولة لاحقاً.")
        return
    
    juz_data = data['data']
    if not juz_data or 'ayahs' not in juz_data:
        await query.edit_message_text("❌ **عذراً:** لا توجد آيات في هذا الجزء.")
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
        await query.edit_message_text("❌ **عذراً:** حدث خطأ في جلب بيانات الجزء. يرجى المحاولة لاحقاً.")
        return
    
    juz_data = data['data']
    if not juz_data or 'ayahs' not in juz_data:
        await query.edit_message_text("❌ **عذراً:** لا توجد آيات في هذا الجزء.")
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
    elif query.data == "browse_quran_text":
        await browse_quran_text(update, context)
    elif query.data == "browse_quran_images":
        await browse_quran_images(update, context)
    elif query.data.startswith("quran_img_page_"):
        await browse_quran_images_page(update, context)
    elif query.data.startswith("surah_img_"):
        await show_surah_image(update, context)
    elif query.data.startswith("view_page_"):
        await view_quran_page(update, context)
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
    elif query.data.startswith("audio_page_"):
        await audio_page(update, context)
    elif query.data.startswith("audio_surah_"):
        await show_reciters(update, context)
    elif query.data.startswith("reciters_page_"):
        await reciters_page(update, context)
    elif query.data.startswith("reciters_"):
        await show_reciters(update, context)
    elif query.data.startswith("search_reciter_"):
        await search_reciter_prompt(update, context)
    elif query.data.startswith("play_audio_"):
        await play_audio(update, context)
    elif query.data == "search_quran":
        await search_quran(update, context)
    elif query.data == "main_menu":
        await main_menu(update, context)
    elif query.data.startswith("read_juz_"):
        juz_number = int(query.data.split('_')[2])
        await read_juz(update, context, juz_number)
    elif query.data.startswith("continue_juz_"):
        await continue_juz(update, context)
    elif query.data.startswith("audio_juz_"):
        # هذه الميزة قيد التطوير
        await query.answer("🚧 هذه الميزة قيد التطوير! ستكون متاحة قريباً.", show_alert=True)
    else:
        await query.answer("🚧 هذه الميزة قيد التطوير! ستكون متاحة قريباً.", show_alert=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل العادية"""
    if not await subscription_required(update, context):
        return
    
    # التحقق من وضع البحث عن القراء
    if context.user_data.get('search_reciter_mode'):
        await perform_reciter_search(update, context)
        return
    
    # التحقق من وضع البحث
    if context.user_data.get('search_mode'):
        await perform_search(update, context)
        return
    
    await update.message.reply_text(
        "✨ *مرحباً بك في بوت سُطورٌ من السَّماء* ☁️\n\n"
        "🌟 **كيفية الاستخدام:**\n"
        "• استخدم الأزرار للتنقل بين الخدمات\n"
        "• اضغط على /start للعودة للقائمة الرئيسية\n"
        "• اختر الخدمة المناسبة من القوائم\n\n"
        "📖 **خدماتنا:**\n"
        "• المصحف النصي والمصور\n"
        "• الراديو المباشر للقرآن\n"
        "• البحث الذكي في الآيات\n"
        "• مكتبة التلاوات الصوتية\n"
        "• تصفح الأجزاء والأحزاب\n\n"
        "💡 **نصيحة:** استخدم القوائم المنبثقة للوصول السريع للخدمات.\n\n"
        "🤲 *بارك الله فيك وجعل القرآن رفيقك في الدنيا والآخرة*",
        parse_mode=ParseMode.MARKDOWN
    )

def main():
    """الدالة الرئيسية - تشغيل كل شيء"""
    # تشغيل البوت في thread منفصل
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # تشغيل Flask في الخيط الرئيسي (مهم لـ Render)
    logger.info(f"🌐 بدء خادم الويب على المنفذ {PORT}...")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

if __name__ == '__main__':
    main()
