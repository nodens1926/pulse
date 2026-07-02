# Описание
Pulse Search - это поисковая система с поддержкой семантического поиска и векторизации документов. 
Проект использует комбинацию TF-IDF и SBERT для точного ранжирования результатов, поддерживает русский и английский языки.

# Ключевые возможности
    - Гибридный поиск: TF-IDF (быстро) + SBERT (точно)

    - Индексация сайтов: Сканирование до 10 страниц на сайт

    - Семантический поиск: Понимание смысла, а не только ключевых слов

    - Похожие страницы: Рекомендации на основе семантической близости

    - Асинхронная индексация: Celery для фоновой обработки

    - Современный UI: React + TailwindCSS

# Технологический стек
Backend
Компонент	Технология	Версия
Веб-фреймворк	FastAPI	0.104.1
ORM	SQLAlchemy	2.0.23
База данных	PostgreSQL + pgvector	latest
Кэш/брокер	Redis	7-alpine
Асинхронные задачи	Celery	5.3.4
ML/Поиск	Sentence Transformers	2.3.0
Токенизация (RU)	pymorphy3	2.0.6
Токенизация (EN)	spaCy	3.7.2
Вычисления	NumPy, SciPy	1.24.3, 1.11.4

Frontend
Компонент	Технология	Версия
Фреймворк	React	18.2.0
Сборщик	Vite	8.1.0
Стили	TailwindCSS	4.3.1
Маршрутизация	React Router DOM	6.22.0
HTTP-клиент	Axios	1.6.0
Веб-сервер	Nginx	latest

# Структура докер-контейнеров, общая архитектура, наполнение БД
Находятся в папке docs в корне

# Запустить все сервисы в фоне
docker compose up -d

# Запустить с пересборкой образов
docker compose up -d --build

# Остановить все сервисы
docker compose down

# Остановить и удалить volumes (очистить БД)
docker compose down -v

# Посмотреть логи всех сервисов
docker compose logs

# Посмотреть логи конкретного сервиса (backend/worker)
docker compose logs backend
docker compose logs worker

# Посмотреть последние N строк логов
docker compose logs --tail 50

# Следить за логами в реальном времени
docker compose logs -f

# Статус контейнеров
docker compose ps

# Проверка, что бекенд жив
curl http://localhost:8000/

# Добавить сайт на индексацию
curl -X POST http://localhost:8000/api/sites \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "name": "Example Site"}'

# Добавить сайт без указания имени (URL станет именем)
curl -X POST http://localhost:8000/api/sites \
  -H "Content-Type: application/json" \
  -d '{"url": "https://httpbin.org/html"}'
  
# Статус всех сайтов
curl http://localhost:8000/api/status

# Статус конкретного сайта (подставь ID)
curl http://localhost:8000/api/status/1

# Поиск по одному слову
curl "http://localhost:8000/api/search?q=example&limit=10"

# Поиск по фразе (пробел кодируем как %20)
curl "http://localhost:8000/api/search?q=Example%20Domain&limit=10"

# Поиск с ограничением результатов (по умолчанию 10)
curl "http://localhost:8000/api/search?q=python&limit=5"

# Переиндексация всех данных (если нужно пересчитать индексы)
curl -X POST http://localhost:8000/api/reindex

# Проверить, что данные сохранились
curl http://localhost:8000/api/status

# Проверить, что поиск работает
curl "http://localhost:8000/api/search?q=domain&limit=10"
