import re
from typing import Dict, List
from collections import Counter
from pymorphy3 import MorphAnalyzer

# стоп-слова
STOP_WORDS = {'и', 'в', 'во', 'не', 'что', 'он', 'на', 'я', 'с', 'со', 'как', 'а', 'то', 'все', 'она', 'так', 'его', 'но', 'да', 'ты', 'к', 'у', 'же',
    'вы', 'за', 'бы', 'по', 'только', 'ее', 'мне', 'было', 'вот', 'от', 'меня', 'еще', 'нет', 'о', 'из', 'него', 'до', 'нее', 'мной', 'них',
    'при', 'под', 'над', 'без', 'для', 'об', 'про', 'через', 'после', 'это', 'этом', 'этот', 'эта', 'эти', 'этого', 'этой', 'этих', 'этим',
    'весь', 'вся', 'все', 'всё', 'всю', 'всех', 'всеми', 'который', 'которая', 'которое', 'которые', 'которого', 'которой', 'которых'}


class Indexer:
    def __init__(self):
        """инициализация индексатора с загрузкой лемматизатора."""
        self.morph = MorphAnalyzer()

    def tokenize_and_count(self, text: str) -> Dict[str, int]:
        """
        Основная функция индексации текста.

        Аргументы:
            text: строка от parser.py

        Возвращает:
            словарь {"слово": частота, "другое": частота}

        Процесс:
            1. Токенизация — разбиваем текст на слова
            2. Приведение к нижнему регистру
            3. Лемматизация — приводим к нормальной форме
            4. Удаление стоп-слов
            5. Подсчёт частоты каждого слова
        """
        if not text or not isinstance(text, str):
            return {}

        # токенизация: находим все слова-символы
        words = re.findall(r'[а-яёa-z]+', text.lower(), re.UNICODE)

        # лемматизация + фильтрация стоп-слов и коротких слов
        lemmatized_words: List[str] = []
        for word in words:
            # пропускаю слова короче 2 символов
            if len(word) < 2:
                continue

            # Лемматизация через pymorphy2
            try:
                normal_form = self.morph.parse(word)[0].normal_form
            except Exception as e:
                # Если лемматизация не удалась, пропускаем слово
                print(f"Ошибка лемматизации слова '{word}': {e}")
                continue

            # Удаляем стоп-слова
            if normal_form not in STOP_WORDS:
                lemmatized_words.append(normal_form)

        return dict(Counter(lemmatized_words))

ind = Indexer()

def build_index(text: str) -> dict:
        """
        Основная функция, вызываемая из внешнего кода.

        Аргументы:
            text: Очищенный текст от parser.py (строка)

        Возвращает:
            Словарь вида {"слово": частота}
        """
        return ind.tokenize_and_count(text)


'''
Как использовать:

from parser import clean_html

sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Заголовок страницы</title>
        <style>body { color: red; }</style>
        <script>console.log("этот скрипт будет удален");</script>
    </head>
    <body>
        <h1>Главный заголовок</h1>
        <p>Это <b>важный</b> текст с <a href="#">ссылкой</a>.</p>
        <div>
            <p>Второй абзац с дополнительной <span>информацией</span>.</p>
        </div>
        <script>alert("этот скрипт тоже будет удален");</script>
    </body>
    </html>
"""

# парсим HTML
cleaned_text = clean_html(sample_html)

# индексируем
build_index(cleaned_text)
'''
