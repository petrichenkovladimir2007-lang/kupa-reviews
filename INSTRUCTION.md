# Парсер відгуків Prom.ua → Google Merchant Center XML Feed v2.3

## Інструкція / Довідковий документ

---

## 1. Загальна інформація

| Параметр | Значення |
|---|---|
| **Клієнт** | kupa.com.ua (Інтернет-супермаркет Купа) |
| **GitHub** | petrichenkovladimir2007-lang/kupa-reviews |
| **Деплой** | GitHub Actions → GitHub Pages |
| **URL фіда** | https://petrichenkovladimir2007-lang.github.io/kupa-reviews/kupa_reviews_feed.xml |
| **CRON** | Щодня о 03:00 UTC (05:00 Київ) |
| **Формат** | Google Merchant Center Product Reviews v2.3 |
| **Аналогічний парсер** | medhome.py для medhome.in.ua (є в проекті) |

---

## 2. Як працює парсер (крок за кроком)

### Крок 1: Завантаження товарного фіда GMC

- URL фіда: `CONFIG["product_feed_url"]`
- **ВАЖЛИВО:** завантажувати через `fetch_bytes()` (resp.content), а НЕ через `fetch_page()` (resp.text)
- Причина: requests автоматично декодує XML як ISO-8859-1 (бо сервер не шле charset у Content-Type), і кирилиця перетворюється на кракозябри
- BeautifulSoup(xml_bytes, "xml") сам прочитає `<?xml encoding="UTF-8"?>` і декодує правильно
- Результат: словник `{ prom_id: product_info }`, де prom_id витягується з URL товару `/pNNNNNN-slug.html`

### Крок 2: Збір відгуків зі сторінок

- Починаємо з `https://kupa.com.ua/ua/testimonials`
- Далі `…/page_2`, `…/page_3` і т.д.
- **Автодетект кількості сторінок:** з пагінатора першої сторінки — атрибут `data-pagination-pages-count`
- **Детекція кінця пагінації:** Prom.ua при запиті неіснуючої page_N (наприклад page_150 при 149 сторінках) робить редірект на першу сторінку БЕЗ помилки 404. Тому перевіряємо `resp.url` — якщо у фінальному URL немає `/page_` — зупиняємось
- Затримка між запитами: 1 секунда (`CONFIG["request_delay"]`)
- Загальний час: ~3-5 хвилин на ~150 сторінок

### Крок 3: Парсинг HTML кожної сторінки

HTML-структура відгуків Prom.ua (стабільна, перевірено березень 2026):

```
<li class="cs-comments__item">
  <strong data-qaid="author_name">Яна Г.</strong>
  <time data-qaid="review_date" datetime="2026-03-20T09:59:34">20.03.2026</time>
  <span class="cs-rating__state" title="Рейтинг 5 з 5">Відмінно</span>
  <p data-qaid="review_text">Текст відгуку...</p>
  <div data-reviews-products='[{"id": 2212414563, "name": "Кора сосни...", "url": "/ua/p2212414563-...html"}]'>
  <li class="b-comments-tags__item" data-tag-title="Гарне обслуговування">
</li>
```

CSS-селектори:

| Поле | Селектор | Джерело |
|---|---|---|
| Блок відгуку | `li.cs-comments__item` | CSS-клас |
| Автор | `[data-qaid="author_name"]` | text |
| Дата/час | `[data-qaid="review_date"]` | атрибут `datetime` |
| Рейтинг | `span.cs-rating__state` | атрибут `title` → regex `(\d+)\s+з\s+(\d+)` |
| Текст | `[data-qaid="review_text"]` | text |
| Товари | `[data-reviews-products]` | JSON в атрибуті → `[{id, name, url}]` |
| Теги | `li.b-comments-tags__item` | атрибут `data-tag-title` |

### Крок 4: Матчинг відгуків з товарами

- Кожен відгук містить 1-3 товари (JSON-масив)
- Для кожного товару з відгуку перевіряємо: чи є його `id` (prom_id) у словнику товарів з GMC-фіда
- Якщо є → створюємо пару (review, product) для XML
- **Один відгук з 3 товарами → 3 окремих `<review>` у фіді** (з однаковим текстом, різними товарами)
- Відгуки без матчу — пропускаються (GMC вимагає прив'язку до product)

### Крок 5: Генерація XML

- Формат: Google Merchant Center Product Reviews v2.3
- `review_id` = `"RV" + MD5(author + date + prom_id + text[:30])[:6]` — унікальний для кожної пари відгук×товар
- `content` = текст відгуку + теги через крапку. **ВАЖЛИВО:** `text.rstrip(". ")` перед склейкою, щоб не було подвійної крапки `".."`
- `review_timestamp` = з атрибуту `datetime` (ISO 8601 + `+02:00`)
- `product_url` додає `?source=merchant_center` якщо його немає
- Дедуплікація за `review_id` (set seen_ids)

---

## 3. Структура XML-фіда

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xsi:noNamespaceSchemaLocation="…/product_reviews.xsd">
    <version>2.3</version>
    <aggregator><n>prom.ua</n></aggregator>
    <publisher>
        <n>kupa.com.ua</n>
        <favicon>https://images.prom.ua/…</favicon>
    </publisher>
    <reviews>
        <review>
            <review_id>RV1F6388</review_id>
            <reviewer><n>Яна Г.</n></reviewer>
            <review_timestamp>2026-03-20T09:59:34+02:00</review_timestamp>
            <content>Текст + теги через крапку</content>
            <review_url type='group'>https://kupa.com.ua/ua/testimonials</review_url>
            <ratings><overall min='1' max='5'>5</overall></ratings>
            <products><product>
                <product_ids>
                    <mpns><mpn>2212414563</mpn></mpns>
                    <brands><brand>BrandName</brand></brands>  <!-- якщо є -->
                </product_ids>
                <product_name>Кора сосни…</product_name>
                <product_url>https://kupa.com.ua/ua/p2212414563-…?source=merchant_center</product_url>
            </product></products>
        </review>
    </reviews>
</feed>
```

---

## 4. GitHub Actions: деплой

### Файл: `.github/workflows/update-feed.yml`

```yaml
name: Update Reviews Feed
on:
  schedule:
    - cron: '0 3 * * *'
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: mkdir -p ./public          # ← ОБОВ'ЯЗКОВО окремим степом!
      - run: python3 kupa_reviews_feed.py --output ./public/kupa_reviews_feed.xml
      - uses: actions/upload-pages-artifact@v3
        with:
          path: ./public

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

### Важливі нюанси:

1. **`mkdir -p ./public` — ОКРЕМИЙ степ** перед запуском скрипта. Якщо об'єднати з python через `&&` — може не спрацювати
2. **GitHub Pages source = GitHub Actions** (Settings → Pages → Source)
3. **Папка `.github` — прихована на Mac** (Cmd+Shift+. щоб побачити). Якщо не завантажилась — створити workflow прямо в GitHub UI через Actions → "set up a workflow yourself"

---

## 5. Баги, які ми ловили, і їх фікси

### Баг 1: Кракозябри у назвах товарів (product_name)

**Симптом:** `ÐÐ¾ÑÐ° ÑÐ¾ÑÐ½Ð¸` замість "Кора сосни"

**Причина:** `requests.get()` декодує відповідь сервера як ISO-8859-1, бо сервер GMC-фіда не шле `charset` у заголовку `Content-Type`. XML-декларація `<?xml encoding="UTF-8"?>` ігнорується requests.

**Фікс:** Використовувати `resp.content` (сирі байти) замість `resp.text`:
```python
def fetch_bytes(session, url):
    resp = session.get(url, timeout=30)
    return resp.content  # bytes, не text

xml_bytes = fetch_bytes(session, url)
soup = BeautifulSoup(xml_bytes, "xml")  # BS4 сам прочитає encoding з XML
```

**НЕ ПРАЦЮЄ:** `resp.encoding = "utf-8"` — ламає інші запити (HTML-сторінки)

### Баг 2: Подвійна крапка ".." у content

**Симптом:** `"чудово.. Гарне обслуговування"`

**Причина:** Текст відгуку закінчується крапкою, а теги додаються через `. `, що дає `"текст.. тег"`

**Фікс:**
```python
text = review["text"].rstrip(". ")  # прибираємо крапку/пробіл перед склейкою
```

### Баг 3: Нескінченний парсинг (скрипт не зупиняється)

**Симптом:** Скрипт парсить 200, 300, 400 сторінок хоча їх лише 149

**Причина:** Prom.ua при запиті неіснуючої page_N (наприклад page_150) редіректить на першу сторінку БЕЗ HTTP 404. Скрипт отримує валідний HTML з 10 відгуками і парсить їх по колу.

**Фікс:** Перевіряти фінальний URL після редіректу:
```python
html, final_url = fetch_page(session, url)  # fetch_page повертає (text, resp.url)
if page_num > 1 and "/page_" not in final_url:
    log.info(f"Редірект — остання сторінка була {page_num - 1}")
    break
```

### Баг 4: FileNotFoundError на GitHub Actions

**Симптом:** `FileNotFoundError: './public/kupa_reviews_feed.xml'`

**Причина:** Папка `./public` не існує на сервері GitHub Actions

**Фікс:** Додати `mkdir -p ./public` як ОКРЕМИЙ степ у workflow ПЕРЕД запуском скрипта

---

## 6. Конфігурація (CONFIG)

| Параметр | Значення | Опис |
|---|---|---|
| `base_url` | `https://kupa.com.ua` | Базова URL |
| `testimonials_url` | `https://kupa.com.ua/ua/testimonials` | Сторінка відгуків |
| `max_pages` | `None` | None = автодетект з пагінатора |
| `product_feed_url` | `https://kupa.com.ua/google_merchant_center.xml?...` | GMC XML-фід |
| `publisher_name` | `kupa.com.ua` | Назва для XML |
| `favicon_url` | `https://images.prom.ua/6246621447_w200_h100_...` | Іконка |
| `aggregator_name` | `prom.ua` | Агрегатор |
| `output_file` | `kupa_reviews_feed.xml` | Вихідний файл |
| `request_delay` | `1.0` | Затримка між запитами (сек) |

---

## 7. Запуск

```bash
python3 kupa_reviews_feed.py --debug        # Тест: 1 сторінка
python3 kupa_reviews_feed.py --pages 5      # Перші 5 сторінок
python3 kupa_reviews_feed.py                # Повний запуск (автодетект)
python3 kupa_reviews_feed.py --output /path  # Зберегти у вказаний файл
```

---

## 8. Типові результати (березень 2026)

- Товарів у фіді GMC: ~4407
- Сторінок відгуків: ~149 (автодетект)
- Відгуків зібрано: ~1486
- Пар (review × product) для XML: ~2428
- Унікальних записів у фіді: ~2416
- Розмір XML: ~2 MB
- Час парсингу: ~5-7 хвилин

---

## 9. Адаптація під інший магазин

Для нового магазину на Prom.ua потрібно змінити лише CONFIG:
1. `base_url`, `testimonials_url` — URL магазину
2. `product_feed_url` — URL товарного фіда GMC
3. `publisher_name`, `favicon_url` — інформація про магазин

HTML-структура відгуків однакова для всіх магазинів на Prom.ua (cs-comments__item).
Приклад: medhome.py використовує ту ж структуру для medhome.in.ua.
