FROM python:3.9-slim

WORKDIR /app

# تنصيب المكتبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# فتح البورت وتشغيل التطبيق
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]