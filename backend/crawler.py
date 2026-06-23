import requests
from bs4 import BeautifulSoup
import json

def parse_page(url):
    """Парсинг одной страницы"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Удаляем скрипты и стили
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Извлекаем данные
        data = {
            'url': url,
            'title': soup.find('title').get_text().strip() if soup.find('title') else '',
            'h1': soup.find('h1').get_text().strip() if soup.find('h1') else '',
            'description': soup.find('meta', attrs={'name': 'description'}).get('content', '') if soup.find('meta', attrs={'name': 'description'}) else '',
            'keywords': soup.find('meta', attrs={'name': 'keywords'}).get('content', '') if soup.find('meta', attrs={'name': 'keywords'}) else '',
            'text': soup.get_text()[:1000]  # Первые 1000 символов текста
        }
        
        # Все ссылки
        links = []
        for a in soup.find_all('a', href=True):
            links.append(a['href'])
        data['links_count'] = len(links)
        data['first_5_links'] = links[:5]  # Первые 5 ссылок
        
        return data
        
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

# Использование
url = "https://hh.ru"  # URL
result = parse_page(url)

if result:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # Сохраняем в файл
    with open('parsed_page.json', 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("✅ Данные сохранены в parsed_page.json")