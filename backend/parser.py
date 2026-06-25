from bs4 import BeautifulSoup
import re

def clean_html(html: str) -> str:
    """
    Вход: Сырой HTML-код (строка)
    Выход: Очищенный текст (строка)

    Что делает
    1. Удаляет все HTML-теги (<div>, <p>, <a>).
    2. Удаляет содержимое <script> и <style>.
    3. Убирает лишние пробелы и переносы строк.
    4. Извлекает текст из <title> отдельно (для ранжирования).
    """

    if not html or not isinstance(html, str):
        return ""
    
    soup = BeautifulSoup(html, 'lxml') #объект BeautifulSoup с парсером lxml
    
    #  удаляем все теги <script> и <style> вместе с их содержимым
    for script in soup(['script', 'style']):
        script.decompose()
    
    # извлекаем текст из <title>
    title_text = ""
    title_tag = soup.find('title')
    if title_tag:
        title_text = title_tag.get_text(strip=True)
    
    text = soup.get_text(separator=' ', strip=True) # весь текст из документа
    
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    if title_text and title_text not in text:
        text = f"{title_text}. {text}"
    
    return text



'''
# Вызов функции:
a = clean_html(
    """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Заголовок страницы</title>
        <style>
            body { color: red; }
        </style>
        <script>
            console.log("этот скрипт будет удален");
        </script>
    </head>
    <body>
        <h1>Главный заголовок</h1>
        <p>Это <b>важный</b> текст с <a href="#">ссылкой</a>.</p>
        <div>
            <p>Второй абзац с дополнительной <span>информацией</span>.</p>
        </div>
        <script>
            alert("этот скрипт тоже будет удален");
        </script>
    </body>
    </html>
    """
)
print(a)
# Возврат: Заголовок страницы Главный заголовок Это важный текст с ссылкой . Второй абзац с дополнительной информацией .
'''
