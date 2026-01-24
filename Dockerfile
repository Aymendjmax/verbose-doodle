FROM python:3.11-slim

WORKDIR /app

# نسخ ملفات المتطلبات أولاً لتحسين caching
COPY requirements.txt .

# تثبيت المتطلبات
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملفات التطبيق
COPY bot.py .
COPY radio.html .

# إنشاء مستخدم غير root للتشغيل
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# كشف المنفذ للتطبيق
EXPOSE 5000

# تشغيل التطبيق
CMD ["python", "bot.py"]
