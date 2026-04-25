# База данных публикаций НИИ (eLibrary)

## Таблицы

**Справочники**
- [languages](#languages)
- [countries](#countries)
- [cities](#cities)

**Организации**
- [organizations](#organizations)
- [organization\_names](#organization_names)
- [organizations\_databases](#organizations_databases)

**Журналы**
- [journals](#journals)
- [journal\_titles](#journal_titles)
- [issues](#issues)

**Статьи**
- [articles](#articles)
- [article\_titles](#article_titles)
- [article\_databases](#article_databases)

**Авторы**
- [authors](#authors)
- [author\_names](#author_names)
- [article\_authors](#article_authors)
- [author\_affiliations](#author_affiliations)
- [authors\_databases](#authors_databases)

**Базы данных и индексирование**
- [databases](#databases)
- [journal\_databases](#journal_databases)
- [journal\_database\_ids](#journal_database_ids)

## languages

Справочник языков.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `lang_id` | CHAR(2) | PK | Код языка (ISO 639-1), напр. `ru`, `en` |
| `name` | VARCHAR(100) | NOT NULL | Название языка, напр. `Русский` |

## countries

Справочник стран.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `country_id` | CHAR(3) | PK | Код страны (ISO 3166-1 alpha-3), напр. `RUS`, `USA` |
| `name` | VARCHAR(100) | NOT NULL | Название страны, напр. `Россия` |

## cities

Справочник городов.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `city_id` | SERIAL | PK | Внутренний ID города |
| `name` | VARCHAR(100) | NOT NULL | Название города, напр. `Новосибирск` |
| `country_id` | CHAR(3) | FK → [countries](#countries) | Страна, в которой находится город |

## organizations

Организации, к которым аффилированы авторы.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `org_id` | SERIAL | PK | Внутренний ID организации |
| `orgname` | VARCHAR(500) | UNIQUE | Каноническое название организации; может быть пустым, если ещё не подгружено |
| `country_id` | CHAR(3) | FK → [countries](#countries) | Страна организации |
| `city_id` | INTEGER | FK → [cities](#cities) | Город организации |

## organization_names

Названия организации на разных языках.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `org_id` | INTEGER | NOT NULL, FK → [organizations](#organizations) | Ссылка на организацию |
| `name` | VARCHAR(500) | NOT NULL | Название организации на данном языке |
| `lang` | CHAR(2) | NOT NULL, FK → [languages](#languages) | Язык названия |
| `type` | VARCHAR(100) | | Тип названия, напр. `полное`, `сокращённое` |

**Уникальность:** `(org_id, name)`

## organizations_databases

Идентификаторы организации в внешних библиографических базах данных.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `org_id` | INTEGER | NOT NULL, FK → [organizations](#organizations) | Ссылка на организацию |
| `db_id` | INTEGER | NOT NULL, FK → [databases](#databases) | Ссылка на базу данных |
| `db_org_id` | VARCHAR(50) | NOT NULL | ID организации в указанной базе данных |

**Уникальность:** `(org_id, db_id)`, `(db_id, db_org_id)`

## journals

Журналы, в которых публикуются статьи.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `journal_id` | SERIAL | PK | Внутренний ID журнала |
| `title` | VARCHAR(500) | NOT NULL | Основное название журнала |
| `issn` | VARCHAR(20) | UNIQUE | Печатный ISSN, напр. `1560-7526` |
| `eissn` | VARCHAR(20) | UNIQUE | Электронный ISSN |
| `publisher_org_id` | INTEGER | FK → [organizations](#organizations) | Издательство (ссылка на организацию) |
| `lang` | CHAR(2) | FK → [languages](#languages) | Основной язык журнала |
| `website` | VARCHAR(500) | | Сайт журнала |
| `doi_prefix` | VARCHAR(100) | UNIQUE | Префикс DOI журнала, напр. `10.15372` |
| `translated_journal_id` | INTEGER | UNIQUE, FK → [journals](#journals) | Ссылка на журнал-перевод |

## journal_titles

Названия журнала на разных языках.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `title_id` | SERIAL | PK | Внутренний ID записи |
| `journal_id` | INTEGER | NOT NULL, FK → [journals](#journals) | Ссылка на журнал |
| `lang` | CHAR(2) | NOT NULL, FK → [languages](#languages) | Язык названия |
| `title_text` | TEXT | NOT NULL | Название журнала на данном языке |

**Уникальность:** `(journal_id, lang)`, `(journal_id, title_text)`

## issues

Отдельные выпуски журналов.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `issue_id` | SERIAL | PK | Внутренний ID выпуска |
| `journal_id` | INTEGER | NOT NULL, FK → [journals](#journals) | Ссылка на журнал |
| `year` | SMALLINT | NOT NULL | Год выпуска, напр. `2025` |
| `volume` | SMALLINT | | Том, напр. `28` |
| `number` | VARCHAR(20) | | Номер выпуска, напр. `1` |
| `contnumber` | INTEGER | | Сквозной номер выпуска, напр. `290` |

**Уникальность:** `(journal_id, year, volume, number)`

## articles

Статьи.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `article_id` | SERIAL | PK | Внутренний ID статьи (ID в конкретных БД хранится в [article_databases](#article_databases)) |
| `issue_id` | INTEGER | NOT NULL, FK → [issues](#issues) | Ссылка на выпуск журнала |
| `title` | TEXT | NOT NULL | Основное название статьи |
| `linkurl` | TEXT | | Прямая ссылка на статью в eLibrary |
| `genre` | VARCHAR(100) | | Жанр, напр. `статья в журнале` |
| `type` | VARCHAR(100) | | Тип, напр. `научная статья` |
| `pages` | VARCHAR(30) | | Страницы в выпуске, напр. `101-117` |
| `language` | CHAR(2) | FK → [languages](#languages) | Язык статьи |
| `doi` | VARCHAR(100) | UNIQUE | DOI, напр. `10.15372/SJNM20250108` |
| `edn` | VARCHAR(20) | UNIQUE | Идентификатор EDN в РИНЦ, напр. `MLKIYI` |
| `grnti` | VARCHAR(20) | | Код ГРНТИ, напр. `270000` |
| `risc` | BOOLEAN | | Входит в РИНЦ |
| `corerisc` | BOOLEAN | | Входит в ядро РИНЦ |
| `citation` | TEXT | UNIQUE | Готовая библиографическая ссылка |
| `supported` | TEXT | | Информация о финансировании / гранте |
| `valid_support` | BOOLEAN | | Валидность финансирования |
| `project_number` | SMALLINT | CHECK(1–100) | Номер базовой темы |
| `print_date` | DATE | | Дата печати |
| `received_date` | DATE | | Дата получения редакцией |
| `authors_count` | SMALLINT | CHECK(> 0) | Число авторов |
| `translated_article_id` | INTEGER | UNIQUE, FK → [articles](#articles) | Ссылка на статью-перевод |

**Уникальность:** `(issue_id, title)`, `doi`, `edn`, `citation`, `translated_article_id`

## article_titles

Названия статьи на разных языках.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `title_id` | SERIAL | PK | Внутренний ID записи |
| `article_id` | INTEGER | NOT NULL, FK → [articles](#articles) | Ссылка на статью |
| `lang` | CHAR(2) | NOT NULL, FK → [languages](#languages) | Язык названия |
| `title_text` | TEXT | NOT NULL | Название статьи на данном языке |

**Уникальность:** `(article_id, lang)`

## article_databases

Идентификаторы статьи во внешних библиографических базах данных (в т.ч. ID в РИНЦ).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `article_id` | INTEGER | NOT NULL, FK → [articles](#articles) | Ссылка на статью |
| `db_id` | INTEGER | NOT NULL, FK → [databases](#databases) | Ссылка на базу данных |
| `db_article_id` | VARCHAR(50) | NOT NULL | ID статьи в указанной базе данных, напр. `80288639` |

**Уникальность:** `(article_id, db_id)`, `(db_id, db_article_id)`

## authors

Авторы публикаций (нормализованы, без дублирования).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `author_id` | SERIAL | PK | Внутренний ID автора |
| `firstname` | VARCHAR(32) | | Имя, напр. `Зинаида` |
| `middlename` | VARCHAR(32) | | Отчество, напр. `Ивановна` |
| `lastname` | VARCHAR(32) | NOT NULL | Фамилия, напр. `Федотова` |
| `initials` | VARCHAR(10) | | Инициалы, напр. `З.И.` |
| `email` | VARCHAR(320) | | Электронная почта, напр. `zf@ict.nsc.ru` |
| `general_org_id` | INTEGER | FK → [organizations](#organizations) | Основная организация автора |

## author_names

ФИО автора на разных языках.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `author_id` | INTEGER | NOT NULL, FK → [authors](#authors) | Ссылка на автора |
| `lang` | CHAR(2) | NOT NULL, FK → [languages](#languages) | Язык записи ФИО |
| `firstname` | VARCHAR(32) | | Имя |
| `middlename` | VARCHAR(32) | | Отчество |
| `lastname` | VARCHAR(32) | NOT NULL | Фамилия |
| `initials` | VARCHAR(10) | | Инициалы |

**Уникальность:** `(author_id, lang)`

## article_authors

Связь статей и авторов.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `article_id` | INTEGER | NOT NULL, FK → [articles](#articles) | Ссылка на статью |
| `author_id` | INTEGER | NOT NULL, FK → [authors](#authors) | Ссылка на автора |
| `num` | SMALLINT | CHECK(> 0) | Порядковый номер автора в статье, напр. `1`, `2`, `3` |
| `aboutauthor` | VARCHAR(300) | | Должность / учёная степень, напр. `канд. техн. наук, доц.` |
| `affiliations_count` | SMALLINT | CHECK(> 0) | Число аффилиаций автора в данной статье |

**Уникальность:** `(article_id, author_id)`, `(article_id, num)`

## author_affiliations

Аффилиации авторов в рамках конкретной статьи. Один автор может быть привязан к нескольким организациям.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `article_author_id` | INTEGER | NOT NULL, FK → [article_authors](#article_authors) | Ссылка на запись автора в статье |
| `org_id` | INTEGER | NOT NULL, FK → [organizations](#organizations) | Ссылка на организацию |
| `num` | SMALLINT | CHECK(> 0) | Порядковый номер аффилиации у автора |
| `affiliation_as_given` | VARCHAR(500) | | Аффилиация в том виде, в каком она указана в оригинале статьи |

**Уникальность:** `(article_author_id, org_id)`, `(article_author_id, num)`

## authors_databases

Идентификаторы автора во внешних библиографических базах данных.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `author_id` | INTEGER | NOT NULL, FK → [authors](#authors) | Ссылка на автора |
| `db_id` | INTEGER | NOT NULL, FK → [databases](#databases) | Ссылка на базу данных |
| `db_author_id` | VARCHAR(50) | NOT NULL | ID автора в указанной базе данных, напр. `1909` |

**Уникальность:** `(author_id, db_id)`, `(db_id, db_author_id)`

## databases

Библиографические базы данных и системы индексирования (РИНЦ, Scopus, WoS, DOAJ, Белый список и др.).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `db_id` | SERIAL | PK | Внутренний ID базы данных |
| `name` | VARCHAR(200) | NOT NULL, UNIQUE | Название базы данных, напр. `РИНЦ`, `Scopus` |
| `website` | VARCHAR(500) | UNIQUE | Сайт базы данных |
| `quartile_prefix` | VARCHAR(10) | | Префикс обозначения квартиля, напр. `Q`, `К` |

## journal_databases

Факт и параметры индексирования журнала в конкретной базе данных за конкретный год.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `journal_id` | INTEGER | NOT NULL, FK → [journals](#journals) | Ссылка на журнал |
| `db_id` | INTEGER | NOT NULL, FK → [databases](#databases) | Ссылка на базу данных |
| `year` | SMALLINT | NOT NULL | Год индексирования |
| `is_included` | BOOLEAN | NOT NULL | Индексируется ли журнал в данном году |
| `quartile` | SMALLINT | | Квартиль журнала |
| `if_value` | FLOAT | CHECK(>= 0) | Импакт-фактор |
| `percentile` | FLOAT | CHECK(>= 0) | Перцентиль |

**Уникальность:** `(journal_id, db_id, year)`

## journal_database_ids

Идентификаторы журнала во внешних библиографических базах данных.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `journal_id` | INTEGER | NOT NULL, FK → [journals](#journals) | Ссылка на журнал |
| `db_id` | INTEGER | NOT NULL, FK → [databases](#databases) | Ссылка на базу данных |
| `db_journal_id` | VARCHAR(50) | NOT NULL | ID журнала в указанной базе данных |

**Уникальность:** `(journal_id, db_id)`, `(db_id, db_journal_id)`
