# Kupa Reviews Feed — GitHub Actions

Парсер відгуків з Prom.ua → XML-фід для Google Merchant Center.  
Запускається автоматично щодня через GitHub Actions, результат доступний через GitHub Pages.

## Швидкий старт

1. Створи **приватний** репозиторій на GitHub
2. Завантаж усі файли з цієї папки в репозиторій
3. Увімкни GitHub Pages: **Settings → Pages → Source → GitHub Actions**
4. Запусти вручну: **Actions → Update Reviews Feed → Run workflow**
5. Через 3-5 хвилин фід буде доступний за URL:

```
https://ТВІЙ-USERNAME.github.io/НАЗВА-РЕПО/kupa_reviews_feed.xml
```

6. Цей URL підключи в **Google Merchant Center → Growth → Product Reviews**

## Файли

| Файл | Опис |
|---|---|
| `kupa_reviews_feed.py` | Основний скрипт парсера |
| `requirements.txt` | Python-залежності |
| `.github/workflows/update-feed.yml` | GitHub Actions — щоденний запуск о 03:00 UTC |
| `public/index.html` | Заглушка для GitHub Pages |
| `public/kupa_reviews_feed.xml` | XML-фід (генерується автоматично) |

## Розклад

- **Автоматично:** щодня о 03:00 UTC (05:00 Київ)
- **Вручну:** GitHub → Actions → Run workflow
