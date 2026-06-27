from bs4 import BeautifulSoup
import re
from typing import Tuple, Optional, List
import logging

logger = logging.getLogger(__name__)


def clean_html(html: str, max_length: int = 10000) -> Tuple[str, str, Optional[str]]:

    if not html or not isinstance(html, str):
        return "", "", ""

    soup = BeautifulSoup(html, 'lxml')

    for tag in soup(['script', 'style', 'noscript', 'iframe', 'nav', 'footer', 'header']):
        tag.decompose()

    title = ""
    title_tag = soup.find('title')
    if title_tag:
        title = title_tag.get_text(strip=True)

    description = ""
    meta_desc = soup.find('meta', attrs={'name': 'description'})
    if meta_desc and meta_desc.get('content'):
        description = meta_desc.get('content', '').strip()

    text = soup.get_text(separator=' ', strip=True)

    text = re.sub(r'\s+', ' ', text)
    text = text.strip()

    if len(text) > max_length:
        text = text[:max_length] + "..."

    if not text and description:
        text = description
    if not text and title:
        text = title

    return title, description, text


def extract_title(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, 'lxml')
    title_tag = soup.find('title')
    if title_tag:
        return title_tag.get_text(strip=True)
    return ""


def extract_text_for_indexing(html: str) -> Tuple[str, str]:

    title, description, text = clean_html(html)

    if not title and description:
        title = description[:255]

    return title, text


def extract_links(html: str, base_url: str) -> List[str]:

    if not html or not base_url:
        return []

    try:
        from urllib.parse import urljoin
        soup = BeautifulSoup(html, 'lxml')
        links = []

        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href')
            if not href:
                continue

            absolute_url = urljoin(base_url, href)

            if absolute_url.startswith(('http://', 'https://')):
                absolute_url = absolute_url.split('#')[0]
                links.append(absolute_url)

        unique_links = list(dict.fromkeys(links))
        logger.debug(f"Найдено {len(unique_links)} уникальных ссылок")
        return unique_links

    except Exception as e:
        logger.error(f"Ошибка при извлечении ссылок: {e}")
        return []


def get_domain(url: str) -> str:
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


if __name__ == "__main__":
    test_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Заголовок страницы</title>
        <meta name="description" content="Это мета-описание страницы для SEO">
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

    title, description, text = clean_html(test_html)

    print("=" * 50)
    print(f"ЗАГОЛОВОК: {title}")
    print(f"ОПИСАНИЕ: {description}")
    print(f"ТЕКСТ: {text}")
    print("=" * 50)

    # Тест извлечения ссылок
    links = extract_links(test_html, "http://example.com")
    print(f"ССЫЛКИ: {links}")