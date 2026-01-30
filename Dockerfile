FROM python:3.11-slim

WORKDIR /app

# تثبيت التبعيات النظامية
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# نسخ متطلبات التطبيق
COPY requirements.txt .

# تثبيت المتطلبات
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ ملفات التطبيق
COPY bot.py .

# إنشاء مستخدم غير root
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

USER botuser

# كشف المنفذ
EXPOSE 5000

# متغيرات البيئة الافتراضية
ENV PORT=5000
ENV BOT_TOKEN=""
ENV CHANNEL_ID=""
ENV DEVELOPER_USERNAME="your_developer_username"
ENV CHANNEL_USERNAME="your_channel_username"
ENV GEMINI_API_KEY=""
ENV RENDER_EXTERNAL_URL=""

# تشغيل التطبيق
CMD ["python", "bot.py"]
