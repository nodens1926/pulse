import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Tuple, Optional, Dict, Any
import logging
import time
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)


# 1. НАСТРОЙКА СЕССИИ REQUESTS С ПОВТОРНЫМИ ПОПЫТКАМИ
def get_session_with_retries(
        retries: int = 3,
        backoff_factor: float = 1.0,
        status_forcelist: tuple = (500, 502, 503, 504)
) -> requests.Session:

    session = requests.Session()

    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "HEAD"]
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session


# 2. ОСНОВНАЯ ФУНКЦИЯ КРАУЛЕРА
def crawl(
        url: str,
        timeout: int = 10,
        user_agent: str = "PulseBot/1.0 (+https://pulse-search.com/bot)",
        max_redirects: int = 5,
        follow_redirects: bool = True
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[int]]:

    if not url:
        return None, None, "URL is empty", None

    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None, None, f"Invalid URL: {url}", None
    except Exception as e:
        return None, None, f"URL parsing error: {e}", None

    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'identity',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    session = get_session_with_retries()

    try:
        logger.info(f"🌐 Загрузка: {url}")
        start_time = time.time()

        response = session.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=follow_redirects,
            stream=True
        )

        elapsed = time.time() - start_time

        if response.status_code >= 400:
            logger.warning(f"⚠️ HTTP {response.status_code} для {url}")
            return None, response.url, f"HTTP {response.status_code}", response.status_code

        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
            logger.warning(f"⚠️ Не HTML-контент: {content_type} для {url}")
            return None, response.url, f"Not HTML: {content_type}", response.status_code

        content_length = response.headers.get('Content-Length')
        if content_length and int(content_length) > 10 * 1024 * 1024:
            logger.warning(f"⚠️ Слишком большой файл: {content_length} байт для {url}")
            return None, response.url, "File too large (>10MB)", response.status_code

        html = response.text

        if not html or len(html.strip()) < 10:
            logger.warning(f"⚠️ Пустой или слишком короткий HTML для {url}")
            return None, response.url, "Empty HTML", response.status_code

        logger.info(f"✅ Загружено {len(html)} байт за {elapsed:.2f}с: {url}")

        return html, response.url, None, response.status_code

    except requests.exceptions.Timeout:
        error = f"Timeout after {timeout}s"
        logger.error(f"⏱️ {error}: {url}")
        return None, None, error, None

    except requests.exceptions.ConnectionError as e:
        error = f"Connection error: {str(e)[:100]}"
        logger.error(f"🔌 {error}: {url}")
        return None, None, error, None

    except requests.exceptions.TooManyRedirects:
        error = f"Too many redirects (max {max_redirects})"
        logger.error(f"🔄 {error}: {url}")
        return None, None, error, None

    except requests.exceptions.SSLError as e:
        error = f"SSL error: {str(e)[:100]}"
        logger.error(f"🔒 {error}: {url}")
        return None, None, error, None

    except requests.exceptions.RequestException as e:
        error = f"Request error: {str(e)[:100]}"
        logger.error(f"❌ {error}: {url}")
        return None, None, error, None

    except Exception as e:
        error = f"Unexpected error: {str(e)[:100]}"
        logger.error(f"💥 {error}: {url}")
        return None, None, error, None


# 3. ФУНКЦИИ ДЛЯ ИЗВЛЕЧЕНИЯ ССЫЛОК
def extract_links(html: str, base_url: str) -> list:

    if not html or not base_url:
        return []

    try:
        from bs4 import BeautifulSoup
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

        # Удаляем дубликаты
        unique_links = list(dict.fromkeys(links))
        logger.debug(f"🔗 Найдено {len(unique_links)} уникальных ссылок")
        return unique_links

    except Exception as e:
        logger.error(f"❌ Ошибка при извлечении ссылок: {e}")
        return []


def get_domain(url: str) -> str:

    try:
        parsed = urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


# 4. ФУНКЦИИ ДЛЯ ПРОВЕРКИ ДОСТУПНОСТИ САЙТА
def check_site_health(url: str, timeout: int = 5) -> Dict[str, Any]:

    result = {
        "url": url,
        "alive": False,
        "status_code": None,
        "response_time": None,
        "error": None
    }

    try:
        start_time = time.time()
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        elapsed = time.time() - start_time

        result["alive"] = response.status_code < 400
        result["status_code"] = response.status_code
        result["response_time"] = round(elapsed, 3)

    except requests.exceptions.Timeout:
        result["error"] = "Timeout"
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection error"
    except Exception as e:
        result["error"] = str(e)[:100]

    return result
