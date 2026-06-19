# Сборка проекта в корне
    docker compose up -d

# Очистить кеш сборки и пересобрать
    docker compose build --no-cache backend
    docker compose up --build
    
# Команда для просмотра архитектуры проекта:
    Linux: tree -a -I "venv|__pycache__|*.pyc|.git|node_modules|.venv|.idea"
    Windows: tree /F /A

# Сикреты:
/.env
/frontend/.htpasswd
/frontend/.env.production


    



