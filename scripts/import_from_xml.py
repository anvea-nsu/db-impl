#!/usr/bin/env python3
"""
import_pubs.py
==============
Импорт публикаций из XML (формат eLibrary) в базу данных научных публикаций.

Идемпотентен: повторный запуск не дублирует записи.
Ориентирован на структуру БД, предоставленную пользователем.
Не изменяет схему БД.

Зависимости: psycopg2-binary, lxml
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import psycopg2
from psycopg2 import sql as pgsql
from lxml import etree

# ─────────────────────────────────────────────────────────────────────────
# Конфигурация подключения к PostgreSQL
# ─────────────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "publication_db",  # <-- укажи свою БД
    "user": "anvea",
    "password": "",
}

# ─────────────────────────────────────────────────────────────────────────
# Сопоставление тегов XML → названия баз данных для флагов индексации
# ─────────────────────────────────────────────────────────────────────────
FLAG_DB_MAP = {
    "vak": "ВАК",
    "rsci": "RSCI",
    "wos": "Web of Science",
    "scopus": "Scopus",
    "white_list": "White List",
}

# Идентификатор источника данных — eLibrary
ELIBRARY_DB_NAME = "eLibrary"

# ─────────────────────────────────────────────────────────────────────────
# Логирование
# ─────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("import_pubs.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("import_pubs")


# ═════════════════════════════════════════════════════════════════════════
# Вспомогательные функции для работы с БД
# ═════════════════════════════════════════════════════════════════════════

def get_or_create_country(cur, country_code: str) -> int:
    """Возвращает country_id по коду страны (RUS, KAZ...), создавая запись при необходимости."""
    # Если кода нет — вернём None (уникальное ограничение не позволит вставить NULL)
    if not country_code:
        return None
    cur.execute(
        "INSERT INTO countries (country_id, name) VALUES (%s, %s) ON CONFLICT (country_id) DO NOTHING",
        (country_code, country_code)  # имя пока ставим равным коду, можно потом обновить
    )
    cur.execute("SELECT country_id FROM countries WHERE country_id = %s", (country_code,))
    return cur.fetchone()[0]


def get_or_create_city(cur, city_name: str, country_id: int) -> Optional[int]:
    """Возвращает city_id, создавая город, если его нет."""
    if not city_name:
        return None
    cur.execute(
        "INSERT INTO cities (name, country_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (city_name, country_id)
    )
    cur.execute(
        "SELECT city_id FROM cities WHERE name = %s AND (country_id = %s OR country_id IS NULL)",
        (city_name, country_id)
    )
    row = cur.fetchone()
    return row[0] if row else None


def get_or_create_org(
    cur,
    org_name: str,
    country_id: int,
    city_id: int,
    lang: str,
    org_elib_id: Optional[int],
    elib_db_id: int,
) -> int:
    """Ищет или создаёт организацию. Возвращает org_id."""
    # Сначала попытка найти по eLibrary ID
    if org_elib_id:
        cur.execute(
            "SELECT org_id FROM organizations_databases WHERE db_id = %s AND db_org_id = %s",
            (elib_db_id, str(org_elib_id))
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # По названию и городу
    cur.execute(
        """
        SELECT o.org_id FROM organizations o
        WHERE o.orgname = %s AND (o.city_id = %s OR o.city_id IS NULL)
        LIMIT 1
        """,
        (org_name, city_id)
    )
    row = cur.fetchone()
    if row:
        org_id = row[0]
    else:
        cur.execute(
            "INSERT INTO organizations (orgname, country_id, city_id) VALUES (%s, %s, %s) RETURNING org_id",
            (org_name, country_id, city_id)
        )
        org_id = cur.fetchone()[0]
        log.info(f"  + Org created: {org_name} (id={org_id})")

    # Локализованное название
    cur.execute(
        """
        INSERT INTO organization_names (org_id, name, lang, type)
        VALUES (%s, %s, %s, 'original')
        ON CONFLICT (org_id, name) DO NOTHING
        """,
        (org_id, org_name, lang)
    )

    # Связь с eLibrary
    if org_elib_id:
        cur.execute(
            """
            INSERT INTO organizations_databases (org_id, db_id, db_org_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (org_id, db_id) DO NOTHING
            ON CONFLICT (db_id, db_org_id) DO NOTHING
            """,
            (org_id, elib_db_id, str(org_elib_id))
        )

    return org_id


# ═════════════════════════════════════════════════════════════════════════
# Извлечение данных из XML-элемента <item>
# ═════════════════════════════════════════════════════════════════════════

def extract_text(el, xpath: str, default: str = "") -> str:
    """Безопасное извлечение текста по xpath."""
    try:
        return el.xpath(xpath)[0].text or default
    except (IndexError, AttributeError):
        return default


def extract_int(el, xpath: str, default: int = 0) -> int:
    try:
        return int(extract_text(el, xpath, ""))
    except ValueError:
        return default


def parse_article(article_el, elib_db_id: int) -> dict:
    """Разбирает один элемент <item> и возвращает словарь с данными."""
    data = {
        "elib_id": int(article_el.get("id")),
        "linkurl": extract_text(article_el, "linkurl"),
        "genre": extract_text(article_el, "genre"),
        "type": extract_text(article_el, "type"),
        "doi": extract_text(article_el, "doi"),
        "edn": extract_text(article_el, "edn"),
        "citation": extract_text(article_el, "citation"),
        "supported": extract_text(article_el, "supported"),
        "pages": extract_text(article_el, "pages"),
        "language": extract_text(article_el, "language"),
        "grnti": extract_text(article_el, "grnti"),
        "risc": extract_text(article_el, "risc"),
        "corerisc": extract_text(article_el, "corerisc"),
        "dateindexed": extract_text(article_el, "dateindexed"),
        # titles
        "titles": [],
        # journal
        "journal": {},
        # authors
        "authors": [],
    }

    # Заголовки
    titles_container = article_el.xpath("titles")
    if titles_container:
        for t in titles_container[0].xpath("title"):
            data["titles"].append({
                "lang": t.get("lang", "RU"),
                "text": (t.text or "").strip(),
            })

    # Информация о журнале
    source = article_el.xpath("source")
    if source:
        journal_el = source[0].xpath("journal")
        if journal_el:
            j = journal_el[0]
            data["journal"] = {
                "title": extract_text(j, "title"),
                "issn": extract_text(j, "issn"),
                "eissn": extract_text(j, "eissn"),
                "publisher": extract_text(j, "publisher"),
                "country": extract_text(j, "country"),
                "town": extract_text(j, "town"),
                "vak": extract_text(j, "vak"),
                "rsci": extract_text(j, "rsci"),
                "wos": extract_text(j, "wos"),
                "scopus": extract_text(j, "scopus"),
                "white_list": extract_text(j, "white_list"),
            }
        # Выпуск
        issue_el = source[0].xpath("issue")
        if issue_el:
            issue = issue_el[0]
            data["issue"] = {
                "year": extract_int(issue, "year"),
                "volume": extract_int(issue, "volume"),
                "number": extract_text(issue, "number"),
                "contnumber": extract_int(issue, "contnumber"),
            }

    # Авторы и аффилиации
    authors_container = article_el.xpath("authors")
    if authors_container:
        for auth_el in authors_container[0].xpath("author"):
            author_data = {
                "num": int(auth_el.get("num", 0)),
                "lang": auth_el.get("lang", "RU"),
                "lastname": extract_text(auth_el, "lastname"),
                "initials": extract_text(auth_el, "initials"),
                "email": extract_text(auth_el, "email"),
                "authorid": extract_int(auth_el, "authorid"),
                "aboutauthor": extract_text(auth_el, "aboutauthor"),
                "affiliations": [],
            }
            aff_container = auth_el.xpath("affiliations")
            if aff_container:
                for aff_el in aff_container[0].xpath("affiliation"):
                    aff = {
                        "num": int(aff_el.get("num", 0)),
                        "lang": aff_el.get("lang", "RU"),
                        "orgname": extract_text(aff_el, "orgname"),
                        "orgid": extract_int(aff_el, "orgid"),
                        "country": extract_text(aff_el, "country"),
                        "town": extract_text(aff_el, "town"),
                        "address": extract_text(aff_el, "address"),
                    }
                    author_data["affiliations"].append(aff)
            data["authors"].append(author_data)

    return data


# ═════════════════════════════════════════════════════════════════════════
# Обработка одной публикации (вставка в БД)
# ═════════════════════════════════════════════════════════════════════════

def process_publication(cur, pub: dict, db_ids: dict):
    """Вставляет или обновляет запись публикации и все связанные сущности."""
    elib_db_id = db_ids["eLibrary"]

    # ── Журнал ──────────────────────────────────────────────────────────
    j = pub["journal"]
    issn = j.get("issn") or None
    eissn = j.get("eissn") or None
    journal_title = j.get("title") or "Unknown Journal"
    # Определяем язык названия (эвристика)
    if any(ord(c) > 127 for c in journal_title):  # кириллица или другой не-ASCII
        title_lang = "ru"
    else:
        title_lang = "en"

    # Ищем journal_id
    journal_id = None
    for val in filter(None, [issn, eissn]):
        cur.execute(
            "SELECT journal_id FROM journals WHERE issn = %s OR eissn = %s",
            (val, val)
        )
        row = cur.fetchone()
        if row:
            journal_id = row[0]
            break
    if journal_id is None:
        # По названию
        cur.execute(
            "SELECT journal_id FROM journals WHERE LOWER(title) = LOWER(%s)",
            (journal_title,)
        )
        row = cur.fetchone()
        if row:
            journal_id = row[0]
        else:
            # Создаём новый журнал
            cur.execute(
                "INSERT INTO journals (title, issn, eissn) VALUES (%s, %s, %s) RETURNING journal_id",
                (journal_title, issn, eissn)
            )
            journal_id = cur.fetchone()[0]
            log.info(f"  + Journal: {journal_title} (id={journal_id})")
    else:
        # Дополняем пустые поля
        cur.execute("SELECT title, issn, eissn FROM journals WHERE journal_id = %s", (journal_id,))
        ex_title, ex_issn, ex_eissn = cur.fetchone()
        updates = {}
        if not ex_issn and issn:
            updates["issn"] = issn
        if not ex_eissn and eissn:
            updates["eissn"] = eissn
        if updates:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            cur.execute(f"UPDATE journals SET {set_clause} WHERE journal_id = %s",
                        [*updates.values(), journal_id])

    # Название журнала в journal_titles
    cur.execute(
        """
        INSERT INTO journal_titles (journal_id, lang, title_text)
        VALUES (%s, %s, %s)
        ON CONFLICT (journal_id, lang) DO NOTHING
        """,
        (journal_id, title_lang, journal_title)
    )

    # Издатель (publisher org)
    pub_name = j.get("publisher")
    if pub_name:
        pub_country = j.get("country")
        pub_town = j.get("town")
        country_id = get_or_create_country(cur, pub_country) if pub_country else None
        city_id = get_or_create_city(cur, pub_town, country_id) if pub_town else None
        pub_org_id = get_or_create_org(cur, pub_name, country_id, city_id, "ru", None, elib_db_id)
        cur.execute("UPDATE journals SET publisher_org_id = %s WHERE journal_id = %s",
                    (pub_org_id, journal_id))

    # Флаги индексации → journals_databases
    issue_year = pub.get("issue", {}).get("year", 2024)
    for flag, db_name in FLAG_DB_MAP.items():
        val = j.get(flag, "no")
        if val == "yes":
            db_id = db_ids[db_name]
            cur.execute(
                """
                INSERT INTO journals_databases (journal_id, db_id, year, is_included)
                VALUES (%s, %s, %s, true)
                ON CONFLICT (journal_id, db_id, year)
                DO UPDATE SET is_included = EXCLUDED.is_included
                """,
                (journal_id, db_id, issue_year)
            )

    # ── Выпуск ──────────────────────────────────────────────────────────
    issue = pub.get("issue", {})
    year = issue.get("year") or 2024
    volume = issue.get("volume") or None
    number = issue.get("number") or None
    contnumber = issue.get("contnumber") or None
    cur.execute(
        """
        INSERT INTO issues (journal_id, year, volume, number, contnumber)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (journal_id, year, volume, number) DO NOTHING
        """,
        (journal_id, year, volume, number, contnumber)
    )
    cur.execute(
        "SELECT issue_id FROM issues WHERE journal_id = %s AND year = %s AND volume IS NOT DISTINCT FROM %s AND number IS NOT DISTINCT FROM %s",
        (journal_id, year, volume, number)
    )
    issue_row = cur.fetchone()
    if not issue_row:
        raise Exception("Failed to get issue_id after insert")
    issue_id = issue_row[0]

    # ── Статья ──────────────────────────────────────────────────────────
    # Определяем основной язык статьи
    article_lang = pub["language"].lower() if pub["language"] else "ru"
    # Вычисляем количество авторов
    authors_count = len(pub["authors"])
    # Поддерживаемый проект (пытаемся вытащить номер)
    project_number = None
    if pub["supported"]:
        import re
        match = re.search(r"проект\s*(?:№|#)?\s*(\d[\d.]*)", pub["supported"], re.IGNORECASE)
        if match:
            try:
                project_number = int(float(match.group(1)))
            except ValueError:
                pass

    # Преобразуем дату
    print_date = None
    if pub["dateindexed"]:
        try:
            print_date = datetime.strptime(pub["dateindexed"], "%d.%m.%Y").date()
        except ValueError:
            pass

    cur.execute(
        """
        INSERT INTO articles (
            issue_id, title, linkurl, genre, type, pages,
            language, doi, edn, grnti, risc, corerisc,
            citation, supported, project_number, print_date, authors_count
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (issue_id, title) DO NOTHING
        RETURNING article_id
        """,
        (
            issue_id,
            pub["titles"][0]["text"] if pub["titles"] else "Без названия",
            pub["linkurl"] or None,
            pub["genre"] or None,
            pub["type"] or None,
            pub["pages"] or None,
            article_lang,
            pub["doi"] or None,
            pub["edn"] or None,
            pub["grnti"] or None,
            pub["risc"] == "yes",
            pub["corerisc"] == "yes",
            pub["citation"] or None,
            pub["supported"] or None,
            project_number,
            print_date,
            authors_count
        )
    )
    # Если статья уже была, получим её id
    cur.execute(
        "SELECT article_id FROM articles WHERE issue_id = %s AND title = %s",
        (issue_id, pub["titles"][0]["text"] if pub["titles"] else "Без названия")
    )
    article_row = cur.fetchone()
    if not article_row:
        raise Exception("Failed to get article_id")
    article_id = article_row[0]

    # article_titles (все языковые версии)
    for t in pub["titles"]:
        cur.execute(
            """
            INSERT INTO article_titles (article_id, lang, title_text)
            VALUES (%s, %s, %s)
            ON CONFLICT (article_id, lang) DO NOTHING
            """,
            (article_id, t["lang"].lower(), t["text"])
        )

    # articles_databases (связь с eLibrary)
    cur.execute(
        """
        INSERT INTO articles_databases (article_id, db_id, db_article_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (article_id, db_id) DO NOTHING
        """,
        (article_id, elib_db_id, str(pub["elib_id"]))
    )

    # ── Авторы и аффилиации ─────────────────────────────────────────────
    for auth in pub["authors"]:
        # Разбор имени
        lastname = auth["lastname"]
        initials = auth["initials"]
        firstname = middlename = None
        # Определяем, полное имя или инициалы
        if initials and "." in initials:
            # Инициалы (например, "А.П." или "З.И.")
            pass  # оставляем initials как есть
        else:
            # Полное имя, разбиваем на firstname и middlename
            parts = initials.strip().split()
            if len(parts) == 1:
                firstname = parts[0]
            elif len(parts) >= 2:
                firstname = parts[0]
                middlename = " ".join(parts[1:])

        # Ищем или создаём автора
        author_id = None
        if auth["authorid"]:
            cur.execute(
                "SELECT author_id FROM authors_databases WHERE db_id = %s AND db_author_id = %s",
                (elib_db_id, str(auth["authorid"]))
            )
            row = cur.fetchone()
            if row:
                author_id = row[0]
        if not author_id:
            # Ищем по имени (простой поиск по фамилии и инициалам)
            cur.execute(
                "SELECT author_id FROM authors WHERE lastname = %s AND initials = %s",
                (lastname, initials if initials else None)
            )
            row = cur.fetchone()
            if row:
                author_id = row[0]
            else:
                cur.execute(
                    """
                    INSERT INTO authors (firstname, middlename, lastname, initials, email)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING author_id
                    """,
                    (firstname, middlename, lastname, initials, auth.get("email") or None)
                )
                author_id = cur.fetchone()[0]
                log.info(f"  + Author: {lastname} {initials} (id={author_id})")

        # authors_databases
        if auth["authorid"]:
            cur.execute(
                """
                INSERT INTO authors_databases (author_id, db_id, db_author_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (author_id, db_id) DO NOTHING
                ON CONFLICT (db_id, db_author_id) DO NOTHING
                """,
                (author_id, elib_db_id, str(auth["authorid"]))
            )

        # author_names (локализованное)
        cur.execute(
            """
            INSERT INTO author_names (author_id, lang, firstname, middlename, lastname, initials)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (author_id, lang) DO NOTHING
            """,
            (author_id, auth["lang"], firstname, middlename, lastname, initials)
        )

        # Связь статьи с автором
        cur.execute(
            """
            INSERT INTO articles_authors (article_id, author_id, num, aboutauthor, affiliations_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (article_id, author_id) DO NOTHING
            """,
            (
                article_id,
                author_id,
                auth["num"],
                auth.get("aboutauthor") or None,
                len(auth["affiliations"])
            )
        )
        # Получаем id связи для аффилиаций
        cur.execute(
            "SELECT id FROM articles_authors WHERE article_id = %s AND author_id = %s",
            (article_id, author_id)
        )
        aa_id = cur.fetchone()[0]

        # Аффилиации
        for aff in auth["affiliations"]:
            country_id = get_or_create_country(cur, aff.get("country"))
            city_id = get_or_create_city(cur, aff.get("town"), country_id)
            org_id = get_or_create_org(
                cur, aff["orgname"], country_id, city_id,
                aff.get("lang", "ru"), aff.get("orgid"), elib_db_id
            )
            # Связь автор-организация
            cur.execute(
                """
                INSERT INTO author_affiliations (article_author_id, org_id, num, affiliation_as_given)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (article_author_id, org_id) DO NOTHING
                """,
                (aa_id, org_id, aff["num"], aff.get("orgname"))
            )

    return article_id


# ═════════════════════════════════════════════════════════════════════════
# Инициализация таблицы databases
# ═════════════════════════════════════════════════════════════════════════

def ensure_databases(cur) -> Dict[str, int]:
    """Создаёт записи баз данных, если их нет. Возвращает словарь {имя: db_id}."""
    db_names = {**FLAG_DB_MAP, "eLibrary": ELIBRARY_DB_NAME}
    result = {}
    for key, name in db_names.items():
        cur.execute(
            "INSERT INTO databases (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
            (name,)
        )
        cur.execute("SELECT db_id FROM databases WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            result[key] = row[0]
    # eLibrary отдельно
    return result


# ═════════════════════════════════════════════════════════════════════════
# Главная функция
# ═════════════════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <xml_file>")
        sys.exit(1)

    xml_path = Path(sys.argv[1])
    if not xml_path.exists():
        log.error(f"Файл не найден: {xml_path}")
        sys.exit(1)

    log.info("=" * 60)
    log.info(f"Запуск импорта: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info(f"XML файл: {xml_path.resolve()}")

    # Парсим XML с помощью lxml (потоковая обработка через iterparse для экономии памяти)
    log.info("Чтение XML...")
    context = etree.iterparse(str(xml_path), events=("end",), tag="item")
    articles = []
    for event, elem in context:
        articles.append(elem)
        # Очищаем память после обработки, но оставляем элементы для последующего разбора
    log.info(f"Найдено <item> элементов: {len(articles)}")

    # Подключаемся к БД
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    stats = {"processed": 0, "skipped": 0, "errors": 0}

    try:
        with conn.cursor() as cur:
            # Инициализация справочников
            db_ids = ensure_databases(cur)
            conn.commit()
            log.info(f"Databases: {list(db_ids.keys())}")

            for i, elem in enumerate(articles, 1):
                # Фильтруем только статьи в журнале
                genre_el = elem.xpath("genre")
                if not genre_el or genre_el[0].text != "статья в журнале":
                    stats["skipped"] += 1
                    continue

                # Разбираем публикацию
                try:
                    pub = parse_article(elem, db_ids["eLibrary"])
                except Exception as e:
                    log.error(f"Ошибка парсинга элемента {elem.get('id')}: {e}")
                    stats["errors"] += 1
                    continue

                # Обработка в savepoint
                cur.execute("SAVEPOINT sp_pub")
                try:
                    aid = process_publication(cur, pub, db_ids)
                    cur.execute("RELEASE SAVEPOINT sp_pub")
                    stats["processed"] += 1
                    if stats["processed"] % 50 == 0:
                        conn.commit()
                        log.info(f"  ... обработано {stats['processed']} статей")
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_pub")
                    log.error(f"Ошибка в статье {pub.get('elib_id')}: {e}")
                    stats["errors"] += 1

                # Очистка элемента, чтобы не занимать память
                elem.clear()

            conn.commit()

    except Exception as e:
        conn.rollback()
        log.critical(f"Критическая ошибка: {e}")
        raise
    finally:
        conn.close()

    log.info("=" * 60)
    log.info(f"Обработано статей:   {stats['processed']}")
    log.info(f"Пропущено (не статьи): {stats['skipped']}")
    log.info(f"Ошибок:              {stats['errors']}")
    log.info("Готово.")


if __name__ == "__main__":
    main()
