import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DATA = Path('data/ammo-history.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; price-dashboard/1.0)'}

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()

def main():
    collected = []
    url = 'https://orzice.com/v/ammo?a=ammo&top=3-2&p=1'
    for page in range(1, 101):
        response = requests.get(url, headers=HEADERS, timeout=45)
        response.raise_for_status()
        table = BeautifulSoup(response.text, 'html.parser').find('table')
        if table is None:
            raise RuntimeError('source table was not found')
        rows = []
        for tr in table.select('tr'):
            cells = tr.find_all('td')
            name = tr.select_one('.item-name')
            if len(cells) != 10 or name is None:
                continue
            price = clean(cells[2].get_text()).replace(',', '')
            if not price.isdigit():
                raise RuntimeError('price format changed')
            rows.append({'name': clean(name.get_text()), 'price': int(price), 'page': page, 'url': url})
        if not rows:
            raise RuntimeError('source page had no price rows')
        collected.extend(rows)
        next_link = next((a.get('href') for a in table.find_all_next('a') if clean(a.get_text()) == '下一页 »'), None)
        if not next_link or next_link == '#':
            break
        url = urljoin(url, next_link)
    else:
        raise RuntimeError('page limit exceeded')
    if len({row['name'] for row in collected}) != len(collected):
        raise RuntimeError('duplicate ammo names found')
    history = json.loads(DATA.read_text(encoding='utf-8'))
    history['snapshots'].append({'capturedAt': datetime.now(timezone.utc).isoformat(), 'rows': collected})
    history['lastError'] = None
    history['scheduleStatus'] = 'active'
    DATA.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
    print('saved', len(collected), 'prices')

if __name__ == '__main__':
    main()
