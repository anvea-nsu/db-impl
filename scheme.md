# База данных публикаций НИИ (eLibrary)

## Таблицы

- [organizations](#organizations)
- [journals](#journals)
- [issues](#issues)
- [items](#items)
- [authors](#authors)
- [item\_authors](#item_authors) !
- [author\_affiliations](#author_affiliations)
- [titles](#titles) !
- [abstracts](#abstracts)
- [keywords](#keywords)
- [codes](#codes)
- [references](#references)

---

## organizations

Организации, к которым аффилированы авторы.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `org_id` | SERIAL | PK | Внутренний ID организации |
| `orgname` | VARCHAR(500) | NOT NULL | Полное название организации |
| `country` | CHAR(3) | | Код страны (ISO), напр. `RUS` |
| `town` | VARCHAR(100) | | Город |

---

## journals

Журналы, в которых публикуются статьи.

| Колонка               | Тип          | Ограничения | Описание                                           |
| --------------------- | ------------ | ----------- | -------------------------------------------------- |
| `journal_id`          | SERIAL       | PK          | Внутренний ID журнала                              |
| `title`               | VARCHAR(500) | NOT NULL    | Название журнала                                   |
| `issn + eissn`        | VARCHAR(20)  |             | Международный стандартный номер, напр. `1560-7526` |
| `publisher`           | VARCHAR(500) |             | Издательство                                       |
| `country`             | CHAR(3)      |             | Страна издания                                     |
| `town`                | VARCHAR(100) |             | Город издания                                      |
| `vak`                 | BOOLEAN      |             | Входит в перечень ВАК                              |
| `rsci ( + corerisc )` | BOOLEAN      |             | Входит в РИНЦ                                      |
| `wos`                 | BOOLEAN      |             | Входит в Web of Science                            |
| `scopus`              | BOOLEAN      |             | Входит в Scopus                                    |
| `white_list`          | BOOLEAN      |             | Входит в белый список журналов                     |
| `doaj`                | BOOLEAN      |             | Входит в Directory of Open Access Journals         |

---

## issues

Отдельные выпуски журналов.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `issue_id` | SERIAL | PK | Внутренний ID выпуска |
| `journal_id` | INTEGER | FK → [[#journals]] | Ссылка на журнал |
| `year` | SMALLINT | NOT NULL | Год выпуска, напр. `2025` |
| `volume` | SMALLINT | | Том, напр. `28` |
| `number` | VARCHAR(20) | | Номер выпуска, напр. `1` |
| `contnumber` | INTEGER | | Сквозной номер выпуска, напр. `290` |

---

## items

Статьи.

| Колонка         | Тип          | Ограничения      | Описание                                 |
| --------------- | ------------ | ---------------- | ---------------------------------------- |
| `item_id`       | INTEGER      | PK               | ID статьи из eLibrary, напр. `80288639`  |
| `issue_id`      | INTEGER      | FK → [[#issues]] | Ссылка на выпуск журнала                 |
| `linkurl`       | TEXT         |                  | Прямая ссылка на статью в eLibrary       |
| `genre`         | VARCHAR(100) |                  | Жанр, напр. `статья в журнале`           |
| `type`          | VARCHAR(100) |                  | Тип, напр. `научная статья`              |
| `pages`         | VARCHAR(30)  |                  | Страницы в выпуске, напр. `101-117`      |
| `language`      | CHAR(2)      |                  | Язык статьи, напр. `RU`                  |
| `--cited`       | SMALLINT     |                  | Число цитирований                        |
| `--dateindexed` | DATE         |                  | Дата индексации в eLibrary               |
| `doi`           | VARCHAR(100) |                  | DOI, напр. `10.15372/SJNM20250108`       |
| `edn`           | VARCHAR(20)  |                  | Идентификатор EDN в РИНЦ, напр. `MLKIYI` |
| `grnti`         | VARCHAR(20)  |                  | Код ГРНТИ, напр. `270000`                |
| `risc`          | BOOLEAN      |                  | Входит в РИНЦ                            |
| `corerisc`      | BOOLEAN      |                  | Входит в ядро РИНЦ                       |
| `citation`      | TEXT         |                  | Готовая библиографическая ссылка         |
| `supported`     | TEXT         |                  | Информация о финансировании / гранте     |

---

## authors

Авторы публикаций (нормализованы, без дублирования).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `author_id` | SERIAL | PK | Внутренний ID автора |
| `elibrary_author_id` | INTEGER | UNIQUE | ID автора в системе eLibrary, напр. `1909` |
| `lastname` | VARCHAR(200) | NOT NULL | Фамилия, напр. `Федотова` |
| `initials` | VARCHAR(200) | | Имя и отчество, напр. `Зинаида Ивановна` |
| `email` | VARCHAR(200) | | Электронная почта, напр. `zf@ict.nsc.ru` |

+ добавить имя фамилию отчество.
+ сделать имя_en, имя_ru и т.д.
+ добавить поле основная организация.

---

## item_authors

Cтатьи @ авторы.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `item_id` | INTEGER | PK, FK → [[#items]] | Ссылка на статью |
| `author_id` | INTEGER | PK, FK → [[#authors]] | Ссылка на автора |
| `num` | SMALLINT | | Порядковый номер автора в статье, напр. `1`, `2`, `3` |
| `--aboutauthor` | VARCHAR(300) | | Должность / учёная степень, напр. `канд. техн. наук, доц.` |

---

## author_affiliations

Аффилиации авторов в рамках конкретной статьи. Один автор может быть привязан к нескольким организациям.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `id` | SERIAL | PK | Внутренний ID записи |
| `item_id` | INTEGER | FK → [[#items]] | Ссылка на статью |
| `author_id` | INTEGER | FK → [[#authors]] | Ссылка на автора |
| `org_id` | INTEGER | FK → [[#organizations]] | Ссылка на организацию |
| `num` | SMALLINT | | Порядковый номер аффилиации у автора |

+ вместо item_id и autor_id сделать item_autors_id
---

## -- titles (сделать просто en и ru в items)

Заголовки статей (возможны несколько языков).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `title_id` | SERIAL | PK | Внутренний ID |
| `item_id` | INTEGER | FK → [[#items]] | Ссылка на статью |
| `lang` | CHAR(2) | | Язык заголовка, напр. `RU`, `EN` |
| `title_text` | TEXT | NOT NULL | Текст заголовка |

---

## -- abstracts

Аннотации статей (возможны несколько языков).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `abstract_id` | SERIAL | PK | Внутренний ID |
| `item_id` | INTEGER | FK → [[#items]] | Ссылка на статью |
| `lang` | CHAR(2) | | Язык аннотации, напр. `RU`, `EN` |
| `abstract_text` | TEXT | | Текст аннотации |

---

## -- keywords

Ключевые слова статей (возможны несколько языков).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `keyword_id` | SERIAL | PK | Внутренний ID |
| `item_id` | INTEGER | FK → [[#items]] | Ссылка на статью |
| `lang` | CHAR(2) | | Язык ключевого слова, напр. `RU`, `EN` |
| `keyword_text` | VARCHAR(300) | | Ключевое слово, напр. `long surface waves` |

---

## codes

Классификационные коды статей (УДК и др.).

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `code_id` | SERIAL | PK | Внутренний ID |
| `item_id` | INTEGER | FK → [[#items]] | Ссылка на статью |
| `code_type` | VARCHAR(50) | | Тип классификатора, напр. `УДК` |
| `code_value` | VARCHAR(50) | | Значение кода, напр. `532.59` |

---

## references

Список литературы, указанной в статье.

| Колонка | Тип | Ограничения | Описание |
|---|---|---|---|
| `reference_id` | SERIAL | PK | Внутренний ID |
| `item_id` | INTEGER | FK → [[#items]] | Ссылка на статью |
| `num` | SMALLINT | | Порядковый номер ссылки, напр. `1`, `2`, `3` |
| `reference_text` | TEXT | | Полный текст библиографической ссылки |
