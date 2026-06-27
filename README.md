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
