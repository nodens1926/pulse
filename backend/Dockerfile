FROM python:3.10-slim

WORKDIR /app

# Устанавливаем системные зависимости для NLP
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Устанавливаем модель spaCy (ДОБАВЬТЕ ЭТИ СТРОКИ)
RUN python -m spacy download en_core_web_sm

# Копируем весь код
COPY . .

# Команда по умолчанию (запускает только uvicorn)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
