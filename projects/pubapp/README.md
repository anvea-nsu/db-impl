# ПубликацииНИИ — Система управления научными публикациями ФИЦ ИВТ

Полнофункциональное веб-приложение для управления и анализа научных публикаций на базе PostgreSQL, FastAPI и React.

---

## Стек технологий

| Слой | Технологии |
|------|-----------|
| **Frontend** | React 18 + TypeScript, Ant Design 5, Vite, Zustand, React Router 6 |
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), asyncpg |
| **БД** | PostgreSQL 16 |
| **Авторизация** | JWT (python-jose + bcrypt) |
| **Импорт** | psycopg2-binary + lxml (запуск скриптов через subprocess) |

---

## Быстрый старт (Docker)

```bash
# 1. Скопировать database.sql в корень проекта
cp /path/to/database.sql ./

# 2. Запустить
docker compose up -d

# 3. Открыть
# Frontend:  http://localhost:5173
# API docs:  http://localhost:8000/docs
```

Первый зарегистрированный пользователь автоматически получает роль **admin**.

---

## Локальный запуск без Docker

### Backend

```bash
cd backend

# Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # или .venv\Scripts\activate на Windows

# Установить зависимости
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
# Отредактировать .env — вписать параметры БД

# Создать схему БД
psql -U postgres -d publication_db -f ../database.sql
psql -U postgres -d publication_db -f ../init_users.sql

# Запустить сервер
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Открыть http://localhost:5173
```

---

## Функциональные страницы

### 1. Организации
- Поиск по каноническому названию и любому локализованному названию из `organization_names`

### 2. Журналы
- **Вкладка «Поиск и фильтры»**: поиск по названию/ISSN/eISSN, фильтр по БД (пересечение — AND), фильтр по квартилю
- **Вкладка «Топ-10»**: журналы по числу публикаций за период
- Для каждого журнала показываются все базы данных (WoS, Scopus, ВАК, БС 2023, БС 2025) с квартилями и импакт-фактором

### 3. Авторы
- Поиск по фамилии/имени/инициалам/email
- Панель анализа (Drawer):
  - **3.2** — Публикационная активность: всего / WoS / Scopus / ВАК / БС 2023 / БС 2025 / РИНЦ / Q1–Q4
  - **3.3** — То же при `valid_support = true`
  - **3.4** — Число публикаций с `valid_support = false`
  - **3.5** — КБПР для автора и организации (по Белому списку)
- Фильтр по диапазону лет для всех показателей

### 4. Публикации
- **Вкладка «Поиск и фильтры»**: по названию, DOI, автору, журналу, году, организации, `valid_support`, `project_number`, базам данных (объединение — OR) + квартиль
- **Вкладка «ВАК (не в Scopus/WoS/БС)»** — требование 4.3
- **Вкладка «Вне всех баз»** — требование 4.4
- **Кнопка «%»** у каждой публикации — вклад (%) и КБПР организации (4.5, 4.6), список авторов с их аффилиациями

### 5. Статистика
- **5.1** — Сводные показатели: всего / WoS / Scopus / ВАК / БС 2023 / БС 2025 / РИНЦ / Q1–Q4
- **5.2** — Суммарный КБПР (по Белому списку выбранного года)
- Фильтры: организация, `valid_support`, `project_number`, диапазон лет, год Белого списка

---

## Импорт данных

Кнопки «Импорт XML» и «Импорт JSON» доступны в левой панели только для **admin**.

| Кнопка | Скрипт | Формат |
|--------|--------|--------|
| Импорт XML | `scripts/import_from_xml.py` | XML-выгрузка из eLibrary |
| Импорт JSON | `scripts/import_from_json.py` | JSON с journalrank.rcsi.science |

После выбора файла бэкенд сохраняет его во временный файл и запускает соответствующий скрипт через `subprocess`. Прогресс и лог импорта отображаются в модальном окне.

---

## Формулы расчёта

### Коэффициент квартиля (k) — по Белому списку

| Квартиль | k |
|----------|---|
| Q1 | 1.0 |
| Q2 | 0.75 |
| Q3 | 0.5 |
| Q4 | 0.25 |
| Включён без квартиля | 0.1 |
| Не включён | 0.0 |

### Вклад организации в публикацию

```
вклад = Σ (1 / n_aff_i) / N
```

- `n_aff_i` — число аффилиаций автора `i` в данной статье (`articles_authors.affiliations_count`)
- `N` — общее число авторов статьи (`articles.authors_count`)
- Сумма берётся только по авторам, у которых есть аффилиация с данной организацией

### КБПР публикации для организации

```
КБПР = k × вклад
```

### КБПР автора для организации (за период)

```
КБПР_автора = Σ_{статьи} [ k_статьи × (1 / n_aff_автора) / N_статьи ]
```

---

## Структура проекта

```
pubapp/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI приложение
│   │   ├── config.py          # Настройки из .env
│   │   ├── database.py        # AsyncSession SQLAlchemy
│   │   ├── models.py          # ORM-модели всех таблиц + app_users
│   │   ├── schemas.py         # Pydantic-схемы
│   │   ├── auth.py            # JWT + зависимости
│   │   └── routers/
│   │       ├── auth.py        # /api/auth/*
│   │       ├── organizations.py
│   │       ├── journals.py
│   │       ├── authors.py
│   │       ├── articles.py
│   │       ├── statistics.py
│   │       ├── import_.py     # /api/import/xml|json
│   │       └── admin.py       # /api/admin/* (только admin)
│   ├── scripts/
│   │   ├── import_from_xml.py # Исходный скрипт + патч env vars
│   │   └── import_from_json.py
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/client.ts      # Axios + все эндпоинты
│   │   ├── store/authStore.ts # Zustand
│   │   ├── types/index.ts
│   │   ├── components/AppLayout.tsx
│   │   └── pages/
│   │       ├── Login.tsx / Register.tsx
│   │       ├── Organizations.tsx
│   │       ├── Journals.tsx
│   │       ├── Authors.tsx
│   │       ├── Articles.tsx
│   │       ├── Statistics.tsx
│   │       └── admin/AdminPanel.tsx
│   └── Dockerfile
├── database.sql               # Исходная схема БД
├── init_users.sql             # Таблица app_users
├── docker-compose.yml
└── README.md
```

---

## Роли пользователей

| Роль | Доступ |
|------|--------|
| `user` | Все публичные страницы: организации, журналы, авторы, публикации, статистика |
| `admin` | Всё выше + Админка (CRUD всех таблиц) + Импорт XML/JSON |

---

## Белые списки — раздельные записи в БД

При импорте через JSON-скрипт используются названия `"White List"`. В production необходимо вручную или через скрипт добавить записи:

```sql
INSERT INTO databases (name, quartile_prefix) VALUES
  ('Белый список 2023', 'К'),
  ('Белый список 2025', 'К')
ON CONFLICT (name) DO NOTHING;
```

---

## Глобальный параметр организации

ФИЦ ИВТ задаётся через переменные окружения:

```env
DEFAULT_ORG_NAME=ФИЦ ИВТ
DEFAULT_ORG_ID=1    # ID из таблицы organizations
```

Во всех расчётах вклада и КБПР используется этот org_id по умолчанию, если не передан явно.
