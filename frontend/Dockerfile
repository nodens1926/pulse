# Сборка фронтенда
FROM node:22-alpine AS builder

WORKDIR /app

# Копируем package.json и устанавливаем зависимости
COPY package*.json ./
RUN npm install

# Копируем исходники и собираем
COPY . .
RUN npm run build

# Продакшен-сервер (Nginx)
FROM nginx:alpine

# Копируем собранные файлы в Nginx
COPY --from=builder /app/dist /usr/share/nginx/html

# Копируем конфиг Nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# КОПИРУЕМ .htpasswd В КОНТЕЙНЕР
COPY .htpasswd /etc/nginx/.htpasswd

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
