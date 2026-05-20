# PubDB Admin — веб-интерфейс для базы данных публикаций

## Требования

| Что нужно | Версия | Как установить |
|-----------|--------|----------------|
| Node.js   | ≥ 18   | `brew install node` |
| PostgreSQL | ≥ 14  | `brew install postgresql@16` |
| Python 3  | ≥ 3.10 | `brew install python` |
| psycopg2  | —      | `pip3 install psycopg2-binary` |
| lxml      | —      | `pip3 install lxml` |

---

## Шаг 1 — Создай базу данных PostgreSQL

```bash
# Запусти PostgreSQL (если ещё не запущен)
brew services start postgresql@16

# Создай БД и пользователя
psql postgres -c "CREATE USER anvea WITH PASSWORD '';"
psql postgres -c "CREATE DATABASE publication_db OWNER anvea;"

# Примени схему
psql -U anvea -d publication_db -f database.sql
```

> **Примечание**: если твой пользователь PostgreSQL или имя БД отличаются,
> отредактируй переменные окружения в следующем шаге.

---

## Шаг 2 — Установи зависимости Node.js

```bash
cd pubdb-admin
npm install
```

---

## Шаг 3 — Запусти сервер

```bash
# С настройками по умолчанию (user=anvea, db=publication_db)
npm start

# Или с кастомными параметрами подключения:
DB_HOST=localhost \
DB_PORT=5432 \
DB_NAME=publication_db \
DB_USER=anvea \
DB_PASSWORD=mypassword \
npm start
```

Открой браузер: **http://localhost:3000**

---

## Структура проекта

```
pubdb-admin/
├── server.js              # Express backend (REST API)
├── package.json
├── public/
│   └── index.html         # Фронтенд (всё в одном файле)
└── scripts/
    ├── import_from_xml.py  # Импорт статей из XML (eLibrary)
    └── import_from_json.py # Импорт журналов из JSON (journalrank)
```

---

## Функции интерфейса

### Просмотр и редактирование таблиц
- Все таблицы из схемы отображаются в левой панели
- Клик по таблице → загружает строки с пагинацией (50 строк/страница)
- Сортировка по любой колонке — клик по заголовку
- Поиск по текстовым полям — строка поиска вверху
- Добавить строку — кнопка **+ Add Row**
- Редактировать строку — кнопка **Edit** (появляется при наведении)
- Удалить строку — кнопка **Del** (с подтверждением)

### Импорт данных
- **Import XML** — загружает XML-файл из eLibrary, запускает `import_from_xml.py`
- **Import JSON** — загружает JSON-файл журналов (journalrank.rcsi.science), запускает `import_from_json.py`
- Лог выполнения Python-скрипта отображается в реальном времени в интерфейсе

### Статистика
- Верхняя панель показывает количество статей, журналов, авторов, организаций, баз данных и выпусков
- Клик по цифре — открывает соответствующую таблицу

---

## Горячие клавиши

| Комбинация | Действие |
|-----------|----------|
| `Esc` | Закрыть модальное окно |
| `Cmd+Enter` | Сохранить строку в форме редактирования |
