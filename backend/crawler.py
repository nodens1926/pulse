import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from collections import deque
import time
import logging

logger = logging.getLogger(__name__)

class WebCrawler:
    def __init__(self, max_pages=10, timeout=10, delay=0.5):
        self.max_pages = max_pages
        self.timeout = timeout
        self.delay = delay
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    
    def is_valid_url(self, url, base_domain):
        """Проверяет, является ли URL валидным и принадлежит ли он тому же домену"""
        try:
            parsed = urlparse(url)
            if parsed.netloc != base_domain:
                return False
            if parsed.fragment:
                return False
            excluded_extensions = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.mp4', '.mp3', '.zip', '.rar']
            if any(url.lower().endswith(ext) for ext in excluded_extensions):
                return False
            return True
        except:
            return False
    
    def extract_links(self, soup, base_url, base_domain):
        """Извлекает все ссылки со страницы"""
        links = set()
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            full_url = urljoin(base_url, href)
            if self.is_valid_url(full_url, base_domain):
                links.add(full_url)
        return links
    
    def crawl_page(self, url):
        """Сканирует страницу и возвращает контент и найденные ссылки"""
        try:
            response = requests.get(url, timeout=self.timeout, headers={
                'User-Agent': self.user_agent
            })
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title = soup.title.string if soup.title and soup.title.string else url
            
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            text = ' '.join(soup.stripped_strings)
            
            if not text:
                return None, set()
            
            parsed_url = urlparse(url)
            base_domain = parsed_url.netloc
            links = self.extract_links(soup, url, base_domain)
            
            return {
                'url': url,
                'title': title,
                'content': text
            }, links
            
        except Exception as e:
            logger.error(f"Ошибка при сканировании {url}: {e}")
            return None, set()
    
    def crawl_site(self, start_url):
        """Обходит сайт и возвращает список страниц"""
        parsed_url = urlparse(start_url)
        base_domain = parsed_url.netloc
        
        to_visit = deque([start_url])
        visited = set()
        pages = []
        
        while to_visit and len(pages) < self.max_pages:
            current_url = to_visit.popleft()
            
            if current_url in visited:
                continue
            
            logger.info(f"Сканирование страницы {len(pages) + 1}/{self.max_pages}: {current_url}")
            
            page_info, links = self.crawl_page(current_url)
            
            if page_info:
                pages.append(page_info)
                visited.add(current_url)
                
                for link in links:
                    if link not in visited and link not in to_visit:
                        to_visit.append(link)
            else:
                visited.add(current_url)
            
            time.sleep(self.delay)
        
        return pages