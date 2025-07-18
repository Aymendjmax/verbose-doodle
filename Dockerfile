# استخدام صورة أساسية خفيفة الوزن
FROM python:3.11-slim-bullseye

# تعيين متغيرات البيئة
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DEBIAN_FRONTEND noninteractive

# تثبيت التبعيات النظامية
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# إنشاء مجلد التطبيق
WORKDIR /app

# نسخ ملفات المشروع
COPY requirements.txt main.py ./

# تثبيت التبعيات
RUN pip install --no-cache-dir -r requirements.txt

# فتح منفذ التطبيق
EXPOSE 5000

# تشغيل البوت
CMD ["python", "main.py"]
