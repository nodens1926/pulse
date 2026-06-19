Команда для просмотра архитектуры проекта:
    Linux: tree -a -I "venv|__pycache__|*.pyc|.git|node_modules" 
    Windows: tree /F /A

# Очистить кеш сборки и пересобрать
docker compose build --no-cache backend
docker compose up --build
