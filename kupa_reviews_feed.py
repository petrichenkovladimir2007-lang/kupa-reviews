#!/usr/bin/env python3
"""
Парсер відгуків з Prom.ua → XML-фід відгуків для Google Merchant Center (v2.3)

Використання:
    python3 kupa_reviews_feed.py                # Повний запуск
    python3 kupa_reviews_feed.py --debug        # Дебаг-режим (1 сторінка)
    python3 kupa_reviews_feed.py --pages 5      # Парсити перші 5 сторінок

CRON (щодня о 3:00):
    0 3 * * * cd /path/to/script && python3 kupa_reviews_feed.py >> cron.log 2>&1
"""

import requests
import time
import re
import json
import hashlib
import logging
import argparse
import sys
import os
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# ============================================================
# КОНФІГУРАЦІЯ — редагуй під свого клієнта
# ============================================================

CONFIG = {
    # Базова URL магазину
    "base_url": "https://kupa.com.ua",

    # URL сторінки відгуків (перша сторінка)
    "testimonials_url": "https://kupa.com.ua/ua/testimonials",

    # Скільки всього сторінок (None = автодетект з пагінатора)
    "max_pages": None,

    # URL товарного фіда Google Merchant Center
    "product_feed_url": "https://kupa.com.ua/google_merchant_center.xml?hash_tag=0c045457fca549ec4c87b9e005e5b4f5&product_ids=&label_ids=&export_lang=uk&group_ids=130853985&nested_group_ids=130853985",

    # Назва магазину (для publisher)
    "publisher_name": "kupa.com.ua",

    # Favicon URL
    "favicon_url": "https://images.prom.ua/6246621447_w200_h100_internet-supermarket-kupa.jpg",

    # Назва агрегатора
    "aggregator_name": "prom.ua",

    # Вихідний файл
    "output_file": "kupa_reviews_feed.xml",

    # Затримка між запитами (секунди)
    "request_delay": 1.0,

    # User-Agent
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",

    # Маппінг текстових оцінок → числових
    "rating_map": {
        "Відмінно": 5,
        "Добре": 4,
        "Нормально": 3,
        "Погано": 2,
        "Жахливо": 1,
    },
}

# ============================================================
# ЛОГУВАННЯ
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("prom_reviews")


# ============================================================
# HTTP-СЕСІЯ
# ============================================================

def create_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": CONFIG["user_agent"],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.5",
    })
    return session


def fetch_page(session, url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text, resp.url  # повертаємо і фінальний URL (після редіректів)
        except requests.RequestException as e:
            log.warning(f"Спроба {attempt}/{retries} для {url}: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    log.error(f"Не вдалося завантажити: {url}")
    return None, None


def fetch_bytes(session, url, retries=3):
    """Завантажити як сирі байти (для XML-фідів з проблемним кодуванням)."""
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.content  # bytes, не text
        except requests.RequestException as e:
            log.warning(f"Спроба {attempt}/{retries} для {url}: {e}")
            if attempt < retries:
                time.sleep(2 ** attempt)
    log.error(f"Не вдалося завантажити: {url}")
    return None


# ============================================================
# ПАРСИНГ ТОВАРНОГО ФІДА (Google Merchant Center XML)
# ============================================================

def parse_product_feed(session):
    """
    Завантажує GMC XML-фід → словник { prom_id: product_info }.
    prom_id витягується з URL товару (/pNNNNNN-slug.html).
    """
    log.info("Завантажую товарний фід...")
    xml_bytes = fetch_bytes(session, CONFIG["product_feed_url"])
    if not xml_bytes:
        log.error("Не вдалося завантажити товарний фід!")
        return {}

    # Передаємо сирі байти — BeautifulSoup прочитає encoding з XML-декларації
    soup = BeautifulSoup(xml_bytes, "xml")
    products = {}

    items = soup.find_all("item") or soup.find_all("entry") or soup.find_all("product")

    for item in items:
        product = {}
        id_tag = item.find("g:id") or item.find("id")
        title_tag = item.find("g:title") or item.find("title")
        link_tag = item.find("g:link") or item.find("link")
        brand_tag = item.find("g:brand") or item.find("brand")
        mpn_tag = item.find("g:mpn") or item.find("mpn")

        product["id"] = id_tag.text.strip() if id_tag else ""
        product["title"] = title_tag.text.strip() if title_tag else ""
        product["link"] = link_tag.text.strip() if link_tag else ""
        product["brand"] = brand_tag.text.strip() if brand_tag else ""
        product["mpn"] = mpn_tag.text.strip() if mpn_tag else product["id"]

        # Витягуємо prom_id з URL
        url_match = re.search(r'/p(\d+)-', product["link"])
        if url_match:
            prom_id = url_match.group(1)
            product["prom_id"] = prom_id
            products[prom_id] = product

    log.info(f"Завантажено {len(products)} товарів з фіда")
    return products


# ============================================================
# ПАРСИНГ СТОРІНКИ ВІДГУКІВ
# ============================================================

def detect_max_pages(soup):
    """Автодетект кількості сторінок з пагінатора Prom.ua."""
    paginator = soup.select_one('[data-bazooka="Paginator"]')
    if paginator:
        count = paginator.get("data-pagination-pages-count")
        if count:
            return int(count)
    return None


def parse_reviews_page(html, page_num, debug=False):
    """
    Парсить одну сторінку відгуків.
    Повертає (reviews_list, max_pages_or_None).
    """
    soup = BeautifulSoup(html, "html.parser")

    # Автодетект кількості сторінок (тільки з першої)
    max_pages = detect_max_pages(soup) if page_num == 1 else None

    reviews = []
    items = soup.select("li.cs-comments__item")

    if debug:
        log.info(f"Знайдено {len(items)} блоків li.cs-comments__item")

    for i, item in enumerate(items):
        review = parse_review_item(item, debug=(debug and i < 3))
        if review:
            reviews.append(review)

    return reviews, max_pages


def parse_review_item(item, debug=False):
    """
    Парсить один <li class='cs-comments__item'>.

    HTML-структура Prom.ua:
    - Автор: <strong data-qaid="author_name">
    - Дата:  <time data-qaid="review_date" datetime="...">
    - Рейтинг: <span class="cs-rating__state" title="Рейтинг N з 5">
    - Текст: <p data-qaid="review_text">
    - Товари: <div data-reviews-products='[{"id":..., "name":..., "url":...}]'>
    - Теги:  <li class="b-comments-tags__item" data-tag-title="...">
    """

    review = {
        "author": "",
        "date": "",
        "datetime_iso": "",
        "rating": 5,
        "rating_text": "",
        "text": "",
        "products": [],
        "tags": [],
    }

    # ---- Автор ----
    author_el = item.select_one('[data-qaid="author_name"]')
    if author_el:
        review["author"] = author_el.get_text(strip=True)

    # ---- Дата ----
    date_el = item.select_one('[data-qaid="review_date"]')
    if date_el:
        review["datetime_iso"] = date_el.get("datetime", "")
        review["date"] = date_el.get_text(strip=True)

    # ---- Рейтинг ----
    rating_el = item.select_one("span.cs-rating__state")
    if rating_el:
        review["rating_text"] = rating_el.get_text(strip=True)
        title = rating_el.get("title", "")
        m = re.search(r'(\d+)\s+з\s+(\d+)', title)
        if m:
            review["rating"] = int(m.group(1))
        elif review["rating_text"] in CONFIG["rating_map"]:
            review["rating"] = CONFIG["rating_map"][review["rating_text"]]

    # ---- Текст відгуку ----
    text_el = item.select_one('[data-qaid="review_text"]')
    if text_el:
        review["text"] = text_el.get_text(strip=True)

    # ---- Товари (JSON з data-reviews-products) ----
    products_el = item.select_one('[data-reviews-products]')
    if products_el:
        try:
            products_json = products_el.get("data-reviews-products", "[]")
            products_list = json.loads(products_json)
            for p in products_list:
                review["products"].append({
                    "id": str(p.get("id", "")),
                    "name": p.get("name", ""),
                    "url": p.get("url", ""),
                })
        except (json.JSONDecodeError, TypeError) as e:
            if debug:
                log.warning(f"Помилка парсингу JSON товарів: {e}")

    # ---- Теги ----
    tag_els = item.select("li.b-comments-tags__item")
    for tag in tag_els:
        tag_title = tag.get("data-tag-title", "")
        if tag_title:
            review["tags"].append(tag_title)

    if debug:
        log.info(f"  Автор: {review['author']}")
        log.info(f"  Дата: {review['date']} ({review['datetime_iso']})")
        log.info(f"  Рейтинг: {review['rating']} ({review['rating_text']})")
        log.info(f"  Текст: {review['text'][:100] if review['text'] else '(пусто)'}")
        log.info(f"  Товари: {len(review['products'])} шт")
        for p in review["products"][:3]:
            log.info(f"    → [{p['id']}] {p['name'][:60]}")
        log.info(f"  Теги: {review['tags']}")
        log.info("")

    return review if review["author"] else None


# ============================================================
# ЗБІР ВСІХ ВІДГУКІВ
# ============================================================

def collect_all_reviews(session, max_pages_override=None, debug=False):
    all_reviews = []
    max_pages = max_pages_override or CONFIG["max_pages"] or 9999

    for page_num in range(1, max_pages + 1):
        if page_num == 1:
            url = CONFIG["testimonials_url"]
        else:
            url = f"{CONFIG['testimonials_url']}/page_{page_num}"

        log.info(f"Сторінка {page_num}: {url}")
        html, final_url = fetch_page(session, url)

        if not html:
            log.warning(f"Пропускаю сторінку {page_num}")
            continue

        # Детекція редіректу: Prom.ua редіректить на першу сторінку
        # коли запитуєш неіснуючу page_N
        if page_num > 1 and final_url:
            if "/page_" not in final_url:
                log.info(f"Редірект на {final_url} — остання сторінка була {page_num - 1}")
                break

        reviews, detected_max = parse_reviews_page(html, page_num, debug=(debug and page_num == 1))

        # Автодетект max_pages з першої сторінки
        if detected_max and not max_pages_override and not CONFIG["max_pages"]:
            max_pages = detected_max
            log.info(f"Автодетект: {max_pages} сторінок")

        if not reviews:
            log.info(f"Сторінка {page_num} пуста — зупиняюсь")
            break

        all_reviews.extend(reviews)
        log.info(f"  → {len(reviews)} відгуків (всього: {len(all_reviews)})")

        if debug:
            break

        time.sleep(CONFIG["request_delay"])

    return all_reviews


# ============================================================
# МАТЧИНГ ВІДГУКІВ З ТОВАРАМИ З ФІДА
# ============================================================

def match_and_expand_reviews(reviews, products_feed):
    """
    Кожен відгук має кілька товарів (JSON).
    Для GMC: ОКРЕМИЙ <review> для кожного товару, який є у фіді.
    """
    matched_pairs = []
    reviews_without_product = 0
    reviews_no_match = 0

    for review in reviews:
        if not review["products"]:
            reviews_without_product += 1
            continue

        found_any = False
        for product in review["products"]:
            prom_id = product["id"]
            if prom_id in products_feed:
                matched_pairs.append((review, products_feed[prom_id]))
                found_any = True

        if not found_any:
            reviews_no_match += 1

    log.info(f"Матчинг результат:")
    log.info(f"  {len(matched_pairs)} пар (review × product) для XML")
    log.info(f"  {reviews_without_product} відгуків без товарів")
    log.info(f"  {reviews_no_match} відгуків — товари не у фіді")
    return matched_pairs


# ============================================================
# ГЕНЕРАЦІЯ XML-ФІДА ВІДГУКІВ
# ============================================================

def generate_review_id(review, product):
    raw = f"{review['author']}_{review['date']}_{product.get('prom_id', '')}_{review['text'][:30]}"
    hash_hex = hashlib.md5(raw.encode("utf-8")).hexdigest()[:6].upper()
    return f"RV{hash_hex}"


def format_timestamp(review):
    iso = review.get("datetime_iso", "")
    if iso:
        try:
            dt = datetime.fromisoformat(iso)
            return dt.strftime("%Y-%m-%dT%H:%M:%S+02:00")
        except ValueError:
            pass
    date_str = review.get("date", "")
    try:
        dt = datetime.strptime(date_str, "%d.%m.%Y")
        return dt.strftime("%Y-%m-%dT10:00:00+02:00")
    except ValueError:
        return datetime.now().strftime("%Y-%m-%dT10:00:00+02:00")


def build_content(review):
    parts = []
    if review["text"]:
        # Прибираємо крапку/пробіл в кінці тексту перед додаванням тегів
        text = review["text"].rstrip(". ")
        parts.append(text)
    if review["tags"]:
        parts.append(". ".join(review["tags"]))
    if not parts:
        parts.append(review.get("rating_text") or "Відмінно")
    return ". ".join(parts)


def escape_xml(text):
    if not text:
        return ""
    text = str(text)
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    text = text.replace("'", "&apos;")
    return text


def generate_xml_feed(matched_pairs):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<feed xmlns:vc="http://www.w3.org/2007/XMLSchema-versioning" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:noNamespaceSchemaLocation='
        '"http://www.google.com/shopping/reviews/schema/product/2.3/product_reviews.xsd">',
        "    <version>2.3</version>",
        "    <aggregator>",
        f"        <n>{escape_xml(CONFIG['aggregator_name'])}</n>",
        "    </aggregator>",
        "    <publisher>",
        f"        <n>{escape_xml(CONFIG['publisher_name'])}</n>",
        f"        <favicon>{escape_xml(CONFIG['favicon_url'])}</favicon>",
        "    </publisher>",
        "    <reviews>",
    ]

    seen_ids = set()

    for review, product in matched_pairs:
        review_id = generate_review_id(review, product)
        if review_id in seen_ids:
            continue
        seen_ids.add(review_id)

        timestamp = format_timestamp(review)
        content = build_content(review)
        rating = review["rating"]

        mpn = product.get("mpn") or product.get("prom_id") or product.get("id", "")
        brand = product.get("brand", "")
        product_name = product.get("title", "")
        product_url = product.get("link", "")

        if product_url and "source=merchant_center" not in product_url:
            sep = "&" if "?" in product_url else "?"
            product_url += f"{sep}source=merchant_center"

        line = (
            f"<review>"
            f"<review_id>{escape_xml(review_id)}</review_id>"
            f"<reviewer><n>{escape_xml(review['author'])}</n></reviewer>"
            f"<review_timestamp>{timestamp}</review_timestamp>"
            f"<content>{escape_xml(content)}</content>"
            f"<review_url type='group'>{escape_xml(CONFIG['testimonials_url'])}</review_url>"
            f"<ratings><overall min='1' max='5'>{rating}</overall></ratings>"
            f"<products><product><product_ids>"
            f"<mpns><mpn>{escape_xml(mpn)}</mpn></mpns>"
        )

        if brand:
            line += f"<brands><brand>{escape_xml(brand)}</brand></brands>"

        line += (
            f"</product_ids>"
            f"<product_name>{escape_xml(product_name)}</product_name>"
            f"<product_url>{escape_xml(product_url)}</product_url>"
            f"</product></products></review>"
        )

        lines.append(f"\t{line}")

    lines.append("    </reviews>")
    lines.append("</feed>")

    log.info(f"XML: {len(seen_ids)} унікальних відгуків у фіді")
    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Prom.ua Reviews → GMC XML Feed")
    parser.add_argument("--debug", action="store_true", help="Дебаг-режим (1 сторінка)")
    parser.add_argument("--pages", type=int, default=None, help="Кількість сторінок")
    parser.add_argument("--output", type=str, default=None, help="Вихідний файл")
    args = parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)

    output_file = args.output or CONFIG["output_file"]
    max_pages = 1 if args.debug else args.pages

    log.info("=" * 60)
    log.info(f"Prom.ua Reviews Parser → GMC XML Feed")
    log.info(f"Магазин: {CONFIG['publisher_name']}")
    log.info("=" * 60)

    session = create_session()

    # 1. Товарний фід
    products_feed = parse_product_feed(session)
    if not products_feed:
        log.error("Товарний фід пустий — перевір URL!")
        sys.exit(1)

    # 2. Відгуки
    reviews = collect_all_reviews(session, max_pages_override=max_pages, debug=args.debug)
    log.info(f"Всього зібрано: {len(reviews)} відгуків")

    if not reviews:
        log.error("Жодного відгуку не знайдено!")
        sys.exit(1)

    # 3. Матчинг
    matched_pairs = match_and_expand_reviews(reviews, products_feed)

    if not matched_pairs:
        log.error("Жодного відгуку не зматчилось з товарами у фіді!")
        log.error("Перевір: prom_id товарів у відгуках vs prom_id у фіді")
        if reviews and reviews[0]["products"]:
            sample_ids = [p["id"] for p in reviews[0]["products"][:3]]
            feed_ids = list(products_feed.keys())[:5]
            log.error(f"  Приклад ID з відгуків: {sample_ids}")
            log.error(f"  Приклад ID з фіда: {feed_ids}")
        sys.exit(1)

    # 4. XML
    xml_content = generate_xml_feed(matched_pairs)

    # 5. Зберігаємо
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(xml_content)

    file_size = os.path.getsize(output_file)
    log.info(f"Фід збережено: {output_file}")
    log.info(f"Розмір: {file_size / 1024:.1f} KB")
    log.info("Готово!")


if __name__ == "__main__":
    main()
