# Сборка проекта в корне
    docker compose up -d

# Очистить кеш сборки и пересобрать
    docker compose build --no-cache 
    docker compose up --build
    
# Команда для просмотра архитектуры проекта:
    Linux: tree -a -I "venv|__pycache__|*.pyc|.git|node_modules|.venv|.idea"
    Windows: tree /F /A

# Сикреты:
/.env, /frontend/.htpasswd, /frontend/.env.production

# Войти в консоль контейнера
docker exec -it pulse-backend /bin/bash

# Остановите всё (включая тома)
docker compose down -v

# Логи
docker compose logs -f backend
docker compose logs -f worker

# ===Проверка  индексации и поиска===

# 1. Найти ID сайта stackoverflow.com
curl "http://localhost:8000/api/sites" | jq '.sites[] | select(.url | contains("stackoverflow")) | {id, url, status}'

# 2. Удалить сайт (замените ID на правильный, сейчас это 12)
curl -X DELETE "http://localhost:8000/api/sites/12"

# 3. Проверить, что сайт удалён
curl "http://localhost:8000/api/sites" | jq '.sites[] | .url'

# 4. Остановить все контейнеры (данные БД сохранятся)
docker compose down

# 5. Очистить кеш Docker
docker system prune -f
docker builder prune -f

# 6. Запустить контейнеры заново
docker compose up -d

# 7. Подождать 15 секунд для полного запуска
sleep 15

# 8. Проверить health
curl http://localhost:8000/health | jq .

# 9. Добавить сайт
curl -X POST "http://localhost:8000/api/sites?url=stackoverflow.com"

# 10. Смотреть логи worker
docker compose logs -f worker

# 11. Поиск по "stackoverflow"
curl "http://localhost:8000/api/search?q=stackoverflow" | jq .

# 12. Поиск по "stack"
curl "http://localhost:8000/api/search?q=stack" | jq .

# 13. Поиск по "overflow"
curl "http://localhost:8000/api/search?q=overflow" | jq .
