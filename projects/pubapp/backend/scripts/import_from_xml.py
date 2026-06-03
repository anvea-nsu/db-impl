#!/usr/bin/env python3
"""
import_pubs.py (согласованная версия)
=====================================
Импорт статей из XML (eLibrary) в БД публикаций.
Скрипт рассчитан на запуск ПОСЛЕ import_journals.py (JSON).
Особенности:
- Определение языка как в JSON‑скрипте (Unicode‑диапазоны + автоматическое
  пополнение таблицы languages через langcodes).
- Базы данных (Scopus, WoS, …) используются те же,
  что и в JSON‑скрипте.
- Белый список обрабатывается отдельно: создаются записи `White List {год}`
  в таблице databases, год берётся из тега <year> выпуска.
- ISSN/названия журналов не перезаписываются при расхождении, а пишутся
  предупреждения в лог (и в файл conflicts_xml.txt).
"""

import logging
import os
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

import psycopg2
from lxml import etree
import langcodes

# ──────────────────────────────────────────────────────────────────
# Настройки БД
# ──────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "dbname": os.environ.get("DB_NAME", "publication_db"),
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
}

# ──────────────────────────────────────────────────────────────────
# Маппинг флагов XML → читаемое имя базы данных
# (имена должны совпадать с теми, что в import_journals.py)
# ──────────────────────────────────────────────────────────────────
FLAG_DB_MAP = {
    "vak":        "ВАК",
    "rsci":       "RSCI",
    "wos":        "WoS",
    "scopus":     "Scopus",
    # white_list убран – обрабатывается отдельно
    "doaj":       "DOAJ",
}
ELIBRARY_DB_NAME = "eLibrary"

# ──────────────────────────────────────────────────────────────────
# Логирование
# ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("import_pubs.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("import_pubs")

_xml_conflicts: list[str] = []

def _record_xml_conflict(journal_title: str, field: str, in_db, in_file):
    msg = (f"КОНФЛИКТ (XML) | '{journal_title}' | поле '{field}' "
           f"| в БД: {in_db!r} | в XML: {in_file!r}")
    log.warning(msg)
    _xml_conflicts.append(msg)

# ──────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────
def _make_initials(full_name: str) -> str:
    parts = full_name.strip().split()
    if not parts:
        return ""
    return "".join(p[0].upper() + "." for p in parts)

def _truncate_initials(raw: str) -> str:
    if not raw:
        return raw
    if "." in raw:
        return raw[:10]
    return _make_initials(raw)[:10]

def _detect_lang(text: str) -> str:
    """Определение языка по Unicode‑диапазонам (как в JSON‑скрипте)."""
    if not text:
        return 'en'
    for ch in text:
        if 'А' <= ch <= 'я' or ch in 'Ёё':
            return 'ru'
        if '\u4e00' <= ch <= '\u9fff':
            return 'zh'
        if '\u3040' <= ch <= '\u309f' or '\u30a0' <= ch <= '\u30ff':
            return 'ja'
        if '\uac00' <= ch <= '\ud7af':
            return 'ko'
        if '\u0600' <= ch <= '\u06ff':
            return 'ar'
        if '\u0590' <= ch <= '\u05ff':
            return 'he'
    return 'en'

def _get_language_name(lang_code: str) -> str:
    try:
        return langcodes.get(lang_code).display_name('en')
    except:
        return lang_code

# ──────────────────────────────────────────────────────────────────
# Работа с языками (кэширование)
# ──────────────────────────────────────────────────────────────────
def load_existing_languages(cur) -> Set[str]:
    cur.execute("SELECT lang_id FROM languages")
    return {row[0] for row in cur.fetchall()}

def ensure_language(cur, lang_code: str, existing_langs: Set[str]):
    if lang_code in existing_langs:
        return
    name = _get_language_name(lang_code)
    cur.execute(
        "INSERT INTO languages (lang_id, name) VALUES (%s, %s) ON CONFLICT (lang_id) DO NOTHING",
        (lang_code, name),
    )
    existing_langs.add(lang_code)

# ──────────────────────────────────────────────────────────────────
# Справочники
# ──────────────────────────────────────────────────────────────────
def get_or_create_country(cur, code):
    if not code:
        return None
    cur.execute(
        "INSERT INTO countries (country_id, name) VALUES (%s, %s) ON CONFLICT (country_id) DO NOTHING",
        (code, code),
    )
    cur.execute("SELECT country_id FROM countries WHERE country_id = %s", (code,))
    return cur.fetchone()[0]

def get_or_create_city(cur, name, country_id):
    if not name:
        return None
    # SELECT first to avoid wasting SERIAL sequence values on conflicts
    cur.execute(
        "SELECT city_id FROM cities WHERE name = %s AND country_id = %s",
        (name, country_id),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO cities (name, country_id) VALUES (%s, %s) "
        "ON CONFLICT (name, country_id) DO NOTHING RETURNING city_id",
        (name, country_id),
    )
    row = cur.fetchone()
    if row:
        return row[0]
    # Race condition: another process inserted it between our SELECT and INSERT
    cur.execute(
        "SELECT city_id FROM cities WHERE name = %s AND country_id = %s",
        (name, country_id),
    )
    row = cur.fetchone()
    return row[0] if row else None

def get_or_create_org(cur, org_name, country_id, city_id, lang,
                      org_elib_id, elib_db_id, existing_langs: Set[str]):
    # поиск по eLibrary ID
    if org_elib_id:
        cur.execute(
            "SELECT org_id FROM organizations_databases WHERE db_id = %s AND db_org_id = %s",
            (elib_db_id, str(org_elib_id)),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # поиск по точному названию
    cur.execute("SELECT org_id FROM organizations WHERE orgname = %s", (org_name,))
    row = cur.fetchone()
    if row:
        org_id = row[0]
    else:
        cur.execute(
            "INSERT INTO organizations (orgname, country_id, city_id) VALUES (%s, %s, %s) RETURNING org_id",
            (org_name, country_id, city_id),
        )
        org_id = cur.fetchone()[0]
        log.info(f"  + Org created: {org_name} (id={org_id})")

    # локализованное название
    ensure_language(cur, lang, existing_langs)   # <-- авто‑добавление языка
    cur.execute(
        "INSERT INTO organization_names (org_id, name, lang, type) VALUES (%s, %s, %s, 'original') "
        "ON CONFLICT (org_id, name) DO NOTHING",
        (org_id, org_name, lang),
    )

    # связь с eLibrary
    if org_elib_id:
        cur.execute(
            "INSERT INTO organizations_databases (org_id, db_id, db_org_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (org_id, db_id) DO NOTHING",
            (org_id, elib_db_id, str(org_elib_id)),
        )
        cur.execute(
            "INSERT INTO organizations_databases (org_id, db_id, db_org_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (db_id, db_org_id) DO NOTHING",
            (org_id, elib_db_id, str(org_elib_id)),
        )
    return org_id

# ──────────────────────────────────────────────────────────────────
# Инициализация баз данных
# ──────────────────────────────────────────────────────────────────
def ensure_databases(cur):
    db_names = {"eLibrary": ELIBRARY_DB_NAME}
    db_names.update(FLAG_DB_MAP)
    result = {}
    for key, name in db_names.items():
        cur.execute("INSERT INTO databases (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (name,))
        cur.execute("SELECT db_id FROM databases WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            result[key] = row[0]
    return result

def ensure_white_list_db(cur, year: int) -> int:
    """Возвращает db_id для базы 'White List {year}', создавая при необходимости."""
    name = f"Белый список {year}"
    cur.execute("SELECT db_id FROM databases WHERE name = %s", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT INTO databases (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING db_id",
        (name,)
    )
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("SELECT db_id FROM databases WHERE name = %s", (name,))
    return cur.fetchone()[0]

# ──────────────────────────────────────────────────────────────────
# Парсинг XML
# ──────────────────────────────────────────────────────────────────
def extract(el, xpath, default=""):
    try:
        return el.xpath(xpath)[0].text or default
    except (IndexError, AttributeError):
        return default

def extract_int(el, xpath, default=0):
    try:
        return int(extract(el, xpath, ""))
    except ValueError:
        return default

def parse_article(article_el, elib_db_id):
    data = {
        "elib_id": int(article_el.get("id")),
        "linkurl": extract(article_el, "linkurl"),
        "genre": extract(article_el, "genre"),
        "type": extract(article_el, "type"),
        "doi": extract(article_el, "doi"),
        "edn": extract(article_el, "edn"),
        "citation": extract(article_el, "citation"),
        "supported": extract(article_el, "supported"),
        "pages": extract(article_el, "pages"),
        "language": extract(article_el, "language"),
        "grnti": extract(article_el, "grnti"),
        "risc": extract(article_el, "risc"),
        "corerisc": extract(article_el, "corerisc"),
        "dateindexed": extract(article_el, "dateindexed"),
        "titles": [],
        "journal": {},
        "authors": [],
    }
    # заголовки
    tc = article_el.xpath("titles")
    if tc:
        for t in tc[0].xpath("title"):
            data["titles"].append({
                "lang": (t.get("lang") or "RU").lower(),
                "text": (t.text or "").strip()
            })
    # журнал
    src = article_el.xpath("source")
    if src:
        j_el = src[0].xpath("journal")
        if j_el:
            j = j_el[0]
            data["journal"] = {
                "title": extract(j, "title"),
                "issn": extract(j, "issn") or None,
                "eissn": extract(j, "eissn") or None,
                "publisher": extract(j, "publisher"),
                "country": extract(j, "country"),
                "town": extract(j, "town"),
                "vak": extract(j, "vak"),
                "rsci": extract(j, "rsci"),
                "wos": extract(j, "wos"),
                "scopus": extract(j, "scopus"),
                "white_list": extract(j, "white_list"),
                "doaj": extract(j, "doaj"),
            }
        issue_el = src[0].xpath("issue")
        if issue_el:
            iss = issue_el[0]
            data["issue"] = {
                "year": extract_int(iss, "year"),
                "volume": extract_int(iss, "volume") or None,
                "number": extract(iss, "number") or None,
                "contnumber": extract_int(iss, "contnumber") or None,
            }
    # авторы
    ac = article_el.xpath("authors")
    if ac:
        for auth_el in ac[0].xpath("author"):
            raw_initials = extract(auth_el, "initials")
            auth = {
                "num": int(auth_el.get("num", 0)),
                "lang": (auth_el.get("lang") or "RU").lower(),
                "lastname": extract(auth_el, "lastname"),
                "initials": _truncate_initials(raw_initials),
                "raw_initials": raw_initials,
                "email": extract(auth_el, "email"),
                "authorid": extract_int(auth_el, "authorid"),
                "aboutauthor": extract(auth_el, "aboutauthor"),
                "affiliations": [],
            }
            aff_c = auth_el.xpath("affiliations")
            if aff_c:
                for aff_el in aff_c[0].xpath("affiliation"):
                    aff = {
                        "num": int(aff_el.get("num", 0)),
                        "lang": (aff_el.get("lang") or "RU").lower(),
                        "orgname": extract(aff_el, "orgname"),
                        "orgid": extract_int(aff_el, "orgid"),
                        "country": extract(aff_el, "country"),
                        "town": extract(aff_el, "town"),
                        "address": extract(aff_el, "address"),
                    }
                    auth["affiliations"].append(aff)
            data["authors"].append(auth)
    return data

# ──────────────────────────────────────────────────────────────────
# Вставка одной статьи
# ──────────────────────────────────────────────────────────────────
def process_publication(cur, pub, db_ids, existing_langs: Set[str]):
    elib_id = db_ids["eLibrary"]

    # ── Журнал ──────────────────────────────────────────────────────
    j = pub["journal"]
    issn = j.get("issn")
    eissn = j.get("eissn")
    j_title = j.get("title") or "Без названия"

    journal_id = None
    for val in filter(None, [issn, eissn]):
        cur.execute("SELECT journal_id FROM journals WHERE issn = %s OR eissn = %s", (val, val))
        row = cur.fetchone()
        if row:
            journal_id = row[0]
            break
    if journal_id is None:
        cur.execute("SELECT journal_id FROM journals WHERE LOWER(title) = LOWER(%s)", (j_title,))
        row = cur.fetchone()
        if row:
            journal_id = row[0]
        else:
            cur.execute(
                "INSERT INTO journals (title, issn, eissn) VALUES (%s, %s, %s) RETURNING journal_id",
                (j_title, issn, eissn),
            )
            journal_id = cur.fetchone()[0]
            log.info(f"  + Journal: {j_title} (id={journal_id})")
    else:
        cur.execute("SELECT title, issn, eissn FROM journals WHERE journal_id = %s", (journal_id,))
        ex_title, ex_issn, ex_eissn = cur.fetchone()

        updates = {}
        # дополняем ISSN только если поле пустое
        if issn:
            if not ex_issn:
                updates["issn"] = issn
            elif ex_issn != issn:
                if not (ex_issn == eissn or ex_eissn == issn):
                    _record_xml_conflict(j_title, "issn", ex_issn, issn)
        if eissn:
            if not ex_eissn:
                updates["eissn"] = eissn
            elif ex_eissn != eissn:
                if not (ex_eissn == issn or ex_issn == eissn):
                    _record_xml_conflict(j_title, "eissn", ex_eissn, eissn)

        if updates:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            cur.execute(
                f"UPDATE journals SET {set_clause} WHERE journal_id = %s",
                [*updates.values(), journal_id],
            )
            log.info(f"  ~ Journal updated id={journal_id}: {list(updates.keys())}")

    # journal_titles
    j_lang = _detect_lang(j_title)
    ensure_language(cur, j_lang, existing_langs)
    cur.execute(
        "INSERT INTO journal_titles (journal_id, lang, title_text) VALUES (%s, %s, %s) "
        "ON CONFLICT (journal_id, lang) DO NOTHING",
        (journal_id, j_lang, j_title),
    )

    # Издатель
    pub_name = j.get("publisher")
    if pub_name:
        cid = get_or_create_country(cur, j.get("country")) if j.get("country") else None
        city_id = get_or_create_city(cur, j.get("town"), cid) if j.get("town") else None
        pid = get_or_create_org(cur, pub_name, cid, city_id, "ru", None, elib_id, existing_langs)
        cur.execute("UPDATE journals SET publisher_org_id = %s WHERE journal_id = %s", (pid, journal_id))

    # Флаги → journals_databases
    year = pub.get("issue", {}).get("year", 2024)
    for flag, db_name in FLAG_DB_MAP.items():
        val = j.get(flag, "no")
        if val == "yes":
            db_id_flag = db_ids[flag]
            cur.execute(
                "INSERT INTO journals_databases (journal_id, db_id, year, is_included) VALUES (%s, %s, %s, true) "
                "ON CONFLICT (journal_id, db_id, year) DO UPDATE SET is_included = EXCLUDED.is_included",
                (journal_id, db_id_flag, year),
            )

    # journal_database_ids (связь журнал ↔ eLibrary по ISSN)
    if issn or eissn:
        j_db_id = issn or eissn
        cur.execute(
            "INSERT INTO journal_database_ids (journal_id, db_id, db_journal_id) "
            "VALUES (%s, %s, %s) ON CONFLICT (db_id, db_journal_id) DO NOTHING",
            (journal_id, elib_id, j_db_id),
        )

    # ── Белый список (отдельно, с фиксированным годом 2023) ────────────
    # XML из eLibrary не содержит год белого списка — считаем 2023
    if j.get("white_list") == "yes":
        wl_db_id = ensure_white_list_db(cur, 2023)
        cur.execute(
            "INSERT INTO journals_databases (journal_id, db_id, year, is_included) "
            "VALUES (%s, %s, %s, true) "
            "ON CONFLICT (journal_id, db_id, year) DO UPDATE SET is_included = EXCLUDED.is_included",
            (journal_id, wl_db_id, year),
        )
        # связи с идентификаторами: можно записать ISSN
        if issn or eissn:
            cur.execute(
                "INSERT INTO journal_database_ids (journal_id, db_id, db_journal_id) "
                "VALUES (%s, %s, %s) ON CONFLICT (db_id, db_journal_id) DO NOTHING",
                (journal_id, wl_db_id, issn or eissn),
            )

    # ── Выпуск ──────────────────────────────────────────────────────
    iss = pub.get("issue", {})
    cur.execute(
        "INSERT INTO issues (journal_id, year, volume, number, contnumber) VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (journal_id, year, volume, number) DO NOTHING",
        (journal_id, year, iss.get("volume"), iss.get("number"), iss.get("contnumber")),
    )
    cur.execute(
        "SELECT issue_id FROM issues WHERE journal_id = %s AND year = %s "
        "AND volume IS NOT DISTINCT FROM %s AND number IS NOT DISTINCT FROM %s",
        (journal_id, year, iss.get("volume"), iss.get("number")),
    )
    issue_id = cur.fetchone()[0]

    # ── Статья ──────────────────────────────────────────────────────
    main_title = pub["titles"][0]["text"] if pub["titles"] else "Без названия"
    raw_lang = (pub["language"] or "ru").lower()[:2]
    ensure_language(cur, raw_lang, existing_langs)   # язык статьи

    authors_count = max(len(pub["authors"]), 1)

    proj_num = None
    if pub["supported"]:
        m = re.search(r"проект\s*(?:№|#)?\s*(\d[\d.]*)", pub["supported"], re.IGNORECASE)
        if m:
            try:
                val = int(float(m.group(1)))
                if 1 <= val <= 100:
                    proj_num = val
            except (ValueError, OverflowError):
                pass

    print_date = None
    if pub["dateindexed"]:
        try:
            print_date = datetime.strptime(pub["dateindexed"], "%d.%m.%Y").date()
        except ValueError:
            pass

    cur.execute(
        """INSERT INTO articles (issue_id, title, linkurl, genre, type, pages,
           language, doi, edn, grnti, risc, corerisc, citation, supported,
           project_number, print_date, authors_count)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (issue_id, title) DO NOTHING RETURNING article_id""",
        (
            issue_id, main_title, pub["linkurl"] or None, pub["genre"] or None,
            pub["type"] or None, pub["pages"] or None, raw_lang,
            pub["doi"] or None, pub["edn"] or None, pub["grnti"] or None,
            pub["risc"] == "yes", pub["corerisc"] == "yes",
            pub["citation"] or None, pub["supported"] or None,
            proj_num, print_date, authors_count,
        ),
    )
    row = cur.fetchone()
    if row:
        article_id = row[0]
    else:
        cur.execute(
            "SELECT article_id FROM articles WHERE issue_id = %s AND title = %s",
            (issue_id, main_title),
        )
        article_id = cur.fetchone()[0]

    # article_titles
    for t in pub["titles"]:
        lang = t["lang"]
        ensure_language(cur, lang, existing_langs)
        cur.execute(
            "INSERT INTO article_titles (article_id, lang, title_text) VALUES (%s, %s, %s) "
            "ON CONFLICT (article_id, lang) DO NOTHING",
            (article_id, lang, t["text"]),
        )

    # article_databases
    cur.execute(
        "INSERT INTO articles_databases (article_id, db_id, db_article_id) VALUES (%s, %s, %s) "
        "ON CONFLICT (article_id, db_id) DO NOTHING",
        (article_id, elib_id, str(pub["elib_id"])),
    )
    cur.execute(
        "INSERT INTO articles_databases (article_id, db_id, db_article_id) VALUES (%s, %s, %s) "
        "ON CONFLICT (db_id, db_article_id) DO NOTHING",
        (article_id, elib_id, str(pub["elib_id"])),
    )

    # ── Авторы ──────────────────────────────────────────────────────
    for auth in pub["authors"]:
        lastname = auth["lastname"]
        initials = auth["initials"]
        raw_init = auth["raw_initials"]

        firstname = middlename = None
        if "." not in raw_init:
            parts = raw_init.strip().split()
            if len(parts) >= 1:
                firstname = parts[0]
            if len(parts) >= 2:
                middlename = " ".join(parts[1:])

        # поиск/создание автора
        author_id = None
        if auth["authorid"]:
            cur.execute(
                "SELECT author_id FROM authors_databases WHERE db_id = %s AND db_author_id = %s",
                (elib_id, str(auth["authorid"])),
            )
            row = cur.fetchone()
            if row:
                author_id = row[0]
        if not author_id:
            cur.execute(
                "SELECT author_id FROM authors WHERE lastname = %s AND initials = %s",
                (lastname, initials if initials else None),
            )
            row = cur.fetchone()
            if row:
                author_id = row[0]
            else:
                cur.execute(
                    "INSERT INTO authors (firstname, middlename, lastname, initials, email) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING author_id",
                    (firstname, middlename, lastname, initials, auth.get("email") or None),
                )
                author_id = cur.fetchone()[0]
                log.info(f"  + Author: {lastname} {initials} (id={author_id})")

        # authors_databases
        if auth["authorid"]:
            cur.execute(
                "INSERT INTO authors_databases (author_id, db_id, db_author_id) VALUES (%s, %s, %s) "
                "ON CONFLICT (author_id, db_id) DO NOTHING",
                (author_id, elib_id, str(auth["authorid"])),
            )
            cur.execute(
                "INSERT INTO authors_databases (author_id, db_id, db_author_id) VALUES (%s, %s, %s) "
                "ON CONFLICT (db_id, db_author_id) DO NOTHING",
                (author_id, elib_id, str(auth["authorid"])),
            )

        # author_names
        auth_lang = auth["lang"]
        ensure_language(cur, auth_lang, existing_langs)
        cur.execute(
            "INSERT INTO author_names (author_id, lang, firstname, middlename, lastname, initials) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (author_id, lang) DO NOTHING",
            (author_id, auth_lang, firstname, middlename, lastname, initials),
        )

        # articles_authors
        cur.execute(
            "INSERT INTO articles_authors (article_id, author_id, num, aboutauthor, affiliations_count) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (article_id, author_id) DO NOTHING",
            (
                article_id,
                author_id,
                auth["num"],
                auth.get("aboutauthor") or None,
                max(len(auth["affiliations"]), 1),
            ),
        )
        cur.execute(
            "SELECT id FROM articles_authors WHERE article_id = %s AND author_id = %s",
            (article_id, author_id),
        )
        aa_id = cur.fetchone()[0]

        # аффилиации
        for aff in auth["affiliations"]:
            cid = get_or_create_country(cur, aff.get("country"))
            city_id = get_or_create_city(cur, aff.get("town"), cid)
            org_id = get_or_create_org(
                cur, aff["orgname"], cid, city_id, aff["lang"],
                aff.get("orgid"), elib_id, existing_langs
            )
            cur.execute(
                "INSERT INTO author_affiliations (article_author_id, org_id, num, affiliation_as_given) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (article_author_id, org_id) DO NOTHING",
                (aa_id, org_id, aff["num"], aff["orgname"]),
            )
    return article_id

# ──────────────────────────────────────────────────────────────────
# Главная функция
# ──────────────────────────────────────────────────────────────────
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
    log.info(f"XML: {xml_path.resolve()}")

    context = etree.iterparse(str(xml_path), events=("end",), tag="item")
    articles = []
    for event, elem in context:
        articles.append(elem)
    log.info(f"Найдено <item>: {len(articles)}")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    stats = {"processed": 0, "skipped": 0, "errors": 0}

    try:
        with conn.cursor() as cur:
            db_ids = ensure_databases(cur)
            conn.commit()
            log.info(f"Databases: {list(db_ids.keys())}")

            # загружаем существующие языки
            existing_langs = load_existing_languages(cur)
            log.info(f"Языков в БД: {len(existing_langs)}")

            for i, elem in enumerate(articles, 1):
                genre_el = elem.xpath("genre")
                if not genre_el or genre_el[0].text != "статья в журнале":
                    stats["skipped"] += 1
                    elem.clear()
                    continue

                try:
                    pub = parse_article(elem, db_ids["eLibrary"])
                except Exception as e:
                    log.error(f"Ошибка парсинга элемента {elem.get('id')}: {e}")
                    stats["errors"] += 1
                    elem.clear()
                    continue

                cur.execute("SAVEPOINT sp_pub")
                try:
                    process_publication(cur, pub, db_ids, existing_langs)
                    cur.execute("RELEASE SAVEPOINT sp_pub")
                    stats["processed"] += 1
                    if stats["processed"] % 50 == 0:
                        conn.commit()
                        log.info(f"  ... обработано {stats['processed']} статей")
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_pub")
                    log.error(f"Ошибка в статье {pub.get('elib_id')}: {e}")
                    stats["errors"] += 1

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
    log.info(f"Конфликтов (XML):    {len(_xml_conflicts)}")

    if _xml_conflicts:
        conflict_file = Path("conflicts_xml.txt")
        with open(conflict_file, "w", encoding="utf-8") as f:
            f.write(f"Конфликты при импорте XML {datetime.now()}\n")
            f.write("=" * 60 + "\n")
            f.write("\n".join(_xml_conflicts))
        log.info(f"Конфликты записаны в: {conflict_file.resolve()}")

    log.info("Готово.")


if __name__ == "__main__":
    main()
