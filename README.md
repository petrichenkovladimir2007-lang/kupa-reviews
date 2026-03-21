# kupa-reviews

Парсер відгуків з Prom.ua → XML-фід для Google Merchant Center (Product Reviews v2.3)

**Клієнт:** kupa.com.ua (Інтернет-супермаркет Купа)

**Фід:** https://petrichenkovladimir2007-lang.github.io/kupa-reviews/kupa_reviews_feed.xml

---

## Як це працює

1. GitHub Actions щодня о 05:00 (Київ) запускає `kupa_reviews_feed.py`
2. Скрипт завантажує товарний фід GMC та парсить всі сторінки відгуків з Prom.ua
3. Матчить відгуки з товарами за prom_id
4. Генерує XML-фід і деплоїть на GitHub Pages

## Результати (березень 2026)

| Параметр | Значення |
|---|---|
| Товарів у фіді GMC | ~4407 |
| Сторінок відгуків | ~149 (автодетект) |
| Відгуків зібрано | ~1486 |
| Записів у фіді | ~2416 |
| Розмір XML | ~2 MB |
| Час парсингу | ~5-7 хв |

## Структура репозиторію

```
kupa_reviews_feed.py              # Основний скрипт
requirements.txt                  # Залежності (requests, beautifulsoup4, lxml)
.github/workflows/update-feed.yml # GitHub Actions workflow
public/                           # GitHub Pages (XML генерується сюди)
INSTRUCTION.md                    # Детальна документація
```

## Запуск локально

```bash
pip install -r requirements.txt

python3 kupa_reviews_feed.py --debug      # 1 сторінка (тест)
python3 kupa_reviews_feed.py --pages 5    # Перші 5 сторінок
python3 kupa_reviews_feed.py              # Повний запуск
```

## Особливості

- HTML-структура відгуків: `li.cs-comments__item`, `span.cs-rating__state`
- Товари з відгуків — JSON в атрибуті `data-reviews-products`
- Завантаження товарного фіда через `resp.content` (bytes) — інакше кирилиця декодується як ISO-8859-1
- Детекція кінця пагінації через `resp.url` — Prom.ua редіректить неіснуючі сторінки на першу без 404
- Автодетект кількості сторінок з пагінатора (`data-pagination-pages-count`)
- `review_id` = `"RV" + MD5(author + date + prom_id + text[:30])[:6]`
- Один відгук з кількома товарами → кілька записів у XML

## Cron

```
0 3 * * *   →   щодня 03:00 UTC (05:00 Київ)
```
