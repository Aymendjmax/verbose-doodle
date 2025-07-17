# استخدام Python 3.11 slim كصورة أساسية
FROM python:3.11-slim

# تعيين متغير البيئة لتجنب إنشاء ملفات .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# تعيين مجلد العمل
WORKDIR /app

# نسخ ملف المتطلبات
COPY requirements.txt .

# تثبيت المتطلبات
RUN pip install --no-cache-dir -r requirements.txt

# نسخ ملف البوت
COPY main.py .

# تعيين المنفذ
EXPOSE 5000

# تشغيل البوت
CMD ["python", "main.py"]
