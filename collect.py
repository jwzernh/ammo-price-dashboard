import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'ammo-history.json'

def normalize_name(text):
    return re.sub(r'\s+', ' ', text).strip()

def next_url(href, current):
    if href == '#':
        return None
    target = urlparse(urljoin('https://orzice.com/v/ammo', href))
    values = parse_qs(target.query).get('p', [])
    if target.hostname != 'orzice.com' or target.path != '/v/ammo' or len(values) != 1 or not values[0].isdigit() or int(values[0]) != current + 1:
        raise ValueError('invalid next page')
    return 'https://orzice.com/v/ammo?p=' + values[0] + '&a=ammo&top=3-2'

def decode_rows(raw):
    rows = []
    for record in raw:
        if len(record['cells']) != 10:
            raise ValueError('unexpected source table')
        name = normalize_name(record['name'])
        price = record['cells'][2].strip().replace(',', '')
        if not name or not re.fullmatch(r'\d+', price):
            raise ValueError('invalid price row')
        rows.append({'name': name, 'price': int(price)})
    return rows

def collect():
    from playwright.sync_api import sync_playwright
    pages = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(locale='zh-CN', timezone_id='Asia/Shanghai')
        page = context.new_page()
        page.set_default_timeout(30000)
        url = 'https://orzice.com/v/ammo?a=ammo&top=3-2&p=1'
        try:
            while url:
                number = len(pages) + 1
                if number > 100:
                    raise ValueError('page limit exceeded')
                for attempt in range(2):
                    try:
                        response = page.goto(url, wait_until='domcontentloaded', timeout=45000)
                        if response is None or response.status >= 400:
                            raise RuntimeError('source response failed')
                        page.get_by_role('table').wait_for(state='visible')
                        page.get_by_role('navigation', name='pagination').get_by_text('第 ' + str(number) + ' 页', exact=True).wait_for()
                        break
                    except Exception:
                        if attempt:
                            raise
                        time.sleep(3)
                selected = page.get_by_role('combobox').evaluate_all('(els) => els.map(e => e.selectedOptions[0]?.textContent.trim())')
                if selected[:4] != ['等级', '从大到小', '全部等级', '全部子弹种类']:
                    raise ValueError('source sort changed')
                table = page.get_by_role('table')
                headers = table.get_by_role('columnheader').all_text_contents()
                if len(headers) != 10 or headers[2].strip() != '当前价格':
                    raise ValueError('price column changed')
                raw = table.locator('tr').evaluate_all("(els) => els.filter(e=>e.querySelector('td')).map(e=>({name:e.querySelector('.item-name')?.textContent ?? '',cells:Array.from(e.querySelectorAll('td')).map(c=>c.innerText)}))")
                rows = decode_rows(raw)
                href = page.get_by_role('navigation', name='pagination').get_by_role('link', name='下一页 »').get_attribute('href')
                following = next_url(href, number)
                pages.append({'number': number, 'url': url, 'rows': rows})
                url = following
                if url:
                    time.sleep(1)
        finally:
            context.close()
            browser.close()
    return pages

def main():
    pages = collect()
    rows = []
    for page in pages:
        rows.extend(dict(name=row['name'], price=row['price'], page=page['number'], url=page['url']) for row in page['rows'])
    if len(rows) < 90 or len({row['name'] for row in rows}) != len(rows):
        raise ValueError('incomplete ammo observation')
    history = json.loads(DATA.read_text(encoding='utf-8'))
    history['snapshots'].append({'capturedAt': datetime.now(timezone.utc).isoformat(), 'rows': rows})
    history['lastError'] = None
    history['scheduleStatus'] = 'active'
    DATA.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
    print('saved', len(rows), 'prices')

if __name__ == '__main__':
    main()
