#!/usr/bin/env python3
"""
import_journals.py (оптимизированная версия)
=============================================
Импорт журналов из journalrank.rcsi.science в PostgreSQL.

Требует только psycopg2-binary, langcodes (для человекочитаемых названий языков).
langdetect больше не используется.

Перед запуском ОБЯЗАТЕЛЬНО создайте индексы:
  CREATE INDEX idx_journals_issn ON journals(issn);
  CREATE INDEX idx_journals_eissn ON journals(eissn);
  CREATE INDEX idx_journals_title ON journals(title);
  CREATE INDEX idx_journal_titles_title_text ON journal_titles(title_text);
"""

import json
import os
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Set

import psycopg2
import langcodes

# ─────────────────────────────────────────────────────────────────────────────
# Настройки подключения
# ─────────────────────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     int(os.environ.get("DB_PORT", "5432")),
    "dbname":   os.environ.get("DB_NAME", "publication_db"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
}

DATA_FILE = Path("journals.json")
DEFAULT_YEAR = 2023

# ─────────────────────────────────────────────────────────────────────────────
# Маппинг ключей JSON → названия баз данных
# ─────────────────────────────────────────────────────────────────────────────
DB_FIELD_TO_NAME: dict[str, str] = {
    "wos_cc": "WoS",
    "scopus": "Scopus",
    "rsci": "RSCI",
    "sherpa": "SHERPA/RoMEO",
    "doaj": "DOAJ",
    "erih": "ERIH+",
    "inspec": "INSPEC",
    "dblp": "DBLP",
    "msn": "MathSciNet",
    "zbm": "zbMATH",
    "medline": "MEDLINE",
    "embase": "Embase",
    "agricola": "AGRICOLA",
    "cab": "CAB Abstracts",
    "cpx": "Compendex (EI)",
    "georef": "GeoRef",
    "geobase": "Geobase",
    "oax": "OpenAlex",
    "job": "JournalTOCs",
    "sudoc": "SUDOC",
    "scilit": "Scilit",
    "wikidata": "Wikidata",
    "fatcat": "Fatcat",
    "dnb": "Deutsche Nationalbibliothek",
    "cas_core": "CAS Core",
    "cref": "Crossref",
    "fsta": "FSTA",
    "hsabs": "Historical Abstracts",
    "wpsa": "WPSA",
    "socabs": "Sociological Abstracts",
    "chim": "ChemInform",
    "zoorec": "Zoological Record",
    "biabs": "Biological Abstracts",
    "petro": "Petroleum Abstracts",
    "abdc22": "ABDC Journal Quality List 2022",
    "ajg21": "AJG 2021",
    "eclit": "ECLIT",
    "ecbiz": "ECBIZ",
}

# ─────────────────────────────────────────────────────────────────────────────
# Логирование
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("import.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("import_journals")

_conflicts: list[str] = []

def _record_conflict(journal_title: str, field: str, in_db, in_file):
    msg = (f"КОНФЛИКТ | '{journal_title}' | поле '{field}' "
           f"| в БД: {in_db!r} | в файле: {in_file!r}")
    log.warning(msg)
    _conflicts.append(msg)

# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────
def _parse_year(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").year
    except ValueError:
        return None

def _split_issns(issns: list[str]) -> tuple[Optional[str], Optional[str]]:
    if len(issns) > 2:
        log.warning(f"Больше двух ISSN: {issns} — лишние игнорируются")
    issn = issns[0] if len(issns) >= 1 else None
    eissn = issns[1] if len(issns) >= 2 else None
    return issn, eissn

def _detect_lang(text: str) -> str:
    """
    Быстрое определение языка по символам Unicode.
    Если не удалось — 'en'.
    """
    if not text:
        return 'en'
    for ch in text:
        if 'А' <= ch <= 'я' or ch in 'Ёё':
            return 'ru'
        if '\u4e00' <= ch <= '\u9fff':          # китайские
            return 'zh'
        if '\u3040' <= ch <= '\u309f' or '\u30a0' <= ch <= '\u30ff':  # японские
            return 'ja'
        if '\uac00' <= ch <= '\ud7af':          # корейские
            return 'ko'
        if '\u0600' <= ch <= '\u06ff':          # арабские
            return 'ar'
        if '\u0590' <= ch <= '\u05ff':          # иврит
            return 'he'
    return 'en'

def _get_language_name(lang_code: str) -> str:
    """Человекочитаемое название языка по коду."""
    try:
        return langcodes.get(lang_code).display_name('en')
    except:
        return lang_code

# ─────────────────────────────────────────────────────────────────────────────
# Работа с языками (с кэшированием)
# ─────────────────────────────────────────────────────────────────────────────
def load_existing_languages(cur) -> Set[str]:
    """Возвращает множество кодов языков, уже присутствующих в БД."""
    cur.execute("SELECT lang_id FROM languages")
    return {row[0] for row in cur.fetchall()}

def ensure_language(cur, lang_code: str, existing_langs: Set[str]):
    """Добавляет язык в БД, если его ещё нет. Обновляет кэш existing_langs."""
    if lang_code in existing_langs:
        return
    name = _get_language_name(lang_code)
    cur.execute(
        "INSERT INTO languages (lang_id, name) VALUES (%s, %s) ON CONFLICT (lang_id) DO NOTHING",
        (lang_code, name),
    )
    existing_langs.add(lang_code)

# ─────────────────────────────────────────────────────────────────────────────
# Инициализация баз данных
# ─────────────────────────────────────────────────────────────────────────────
def ensure_databases(cur) -> dict[str, int]:
    result: dict[str, int] = {}
    for field_key, db_name in DB_FIELD_TO_NAME.items():
        cur.execute("SELECT db_id FROM databases WHERE name = %s", (db_name,))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO databases (name) VALUES (%s) ON CONFLICT (name) DO NOTHING RETURNING db_id",
                (db_name,)
            )
            row = cur.fetchone()
        if not row:
            cur.execute("SELECT db_id FROM databases WHERE name = %s", (db_name,))
            row = cur.fetchone()
        if row:
            result[field_key] = row[0]
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

# ─────────────────────────────────────────────────────────────────────────────
# Поиск журнала
# ─────────────────────────────────────────────────────────────────────────────
def find_journal_id(cur, issn, eissn, titles) -> Optional[int]:
    # Поиск по ISSN
    for val in filter(None, [issn, eissn]):
        cur.execute(
            "SELECT journal_id FROM journals WHERE issn = %s OR eissn = %s",
            (val, val),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # Поиск по названию
    for title in titles:
        cur.execute(
            "SELECT journal_id FROM journals WHERE LOWER(title) = LOWER(%s)",
            (title,),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        cur.execute(
            "SELECT journal_id FROM journal_titles WHERE LOWER(title_text) = LOWER(%s)",
            (title,),
        )
        row = cur.fetchone()
        if row:
            return row[0]
    return None

# ─────────────────────────────────────────────────────────────────────────────
# Вставка идентификатора журнала в БД
# ─────────────────────────────────────────────────────────────────────────────
def _insert_journal_db_id(cur, journal_id, db_id, ext_id, main_title):
    ext_str = str(ext_id)
    cur.execute(
        "INSERT INTO journal_database_ids (journal_id, db_id, db_journal_id) "
        "VALUES (%s, %s, %s) ON CONFLICT (db_id, db_journal_id) DO NOTHING",
        (journal_id, db_id, ext_str),
    )

# ─────────────────────────────────────────────────────────────────────────────
# Обработка одного журнала
# ─────────────────────────────────────────────────────────────────────────────
def process_journal(cur, record: dict, db_ids: dict[str, int], existing_langs: Set[str]) -> str:
    titles: list[str] = record.get("title", [])
    main_title = titles[0] if titles else "БЕЗ НАЗВАНИЯ"
    issns = record.get("issns", [])
    issn, eissn = _split_issns(issns)

    journal_id = find_journal_id(cur, issn, eissn, titles)
    status = "skipped"

    if journal_id is None:
        cur.execute(
            "INSERT INTO journals (title, issn, eissn) VALUES (%s, %s, %s) RETURNING journal_id",
            (main_title, issn, eissn),
        )
        journal_id = cur.fetchone()[0]
        log.info(f"  + Добавлен: '{main_title}' (id={journal_id})")
        status = "inserted"
    else:
        cur.execute(
            "SELECT title, issn, eissn FROM journals WHERE journal_id = %s",
            (journal_id,),
        )
        ex_title, ex_issn, ex_eissn = cur.fetchone()

        updates = {}
        if ex_issn is None and issn:
            updates["issn"] = issn
        elif ex_issn and issn and ex_issn != issn:
            if not (ex_issn == eissn or ex_eissn == issn):
                _record_conflict(main_title, "issn", ex_issn, issn)

        if ex_eissn is None and eissn:
            updates["eissn"] = eissn
        elif ex_eissn and eissn and ex_eissn != eissn:
            if not (ex_eissn == issn or ex_issn == eissn):
                _record_conflict(main_title, "eissn", ex_eissn, eissn)

        if updates:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            cur.execute(
                f"UPDATE journals SET {set_clause} WHERE journal_id = %s",
                [*updates.values(), journal_id],
            )
            log.info(f"  ~ Обновлён id={journal_id} '{main_title}': {list(updates.keys())}")
            status = "updated"

    # Названия в journal_titles (автоматическое добавление языка)
    for title_text in titles:
        lang = _detect_lang(title_text)
        ensure_language(cur, lang, existing_langs)

        cur.execute(
            "INSERT INTO journal_titles (journal_id, lang, title_text) "
            "VALUES (%s, %s, %s) ON CONFLICT (journal_id, lang) DO NOTHING",
            (journal_id, lang, title_text),
        )
        if cur.rowcount == 0:
            cur.execute(
                "SELECT title_text FROM journal_titles WHERE journal_id = %s AND lang = %s",
                (journal_id, lang),
            )
            row = cur.fetchone()
            if row and row[0].lower() != title_text.lower():
                _record_conflict(main_title, f"journal_titles[{lang}]", row[0], title_text)

    # Индексирование
    for field_key, db_id in db_ids.items():
        db_data = record.get(field_key)
        if not isinstance(db_data, dict):
            continue
        is_included: bool = bool(db_data.get("value", False))
        year: int = _parse_year(db_data.get("update")) or DEFAULT_YEAR

        cur.execute(
            "INSERT INTO journals_databases (journal_id, db_id, year, is_included) "
            "VALUES (%s, %s, %s, %s) ON CONFLICT (journal_id, db_id, year) "
            "DO UPDATE SET is_included = EXCLUDED.is_included",
            (journal_id, db_id, year, is_included),
        )

        ext_ids = db_data.get("id")
        if isinstance(ext_ids, list):
            for ext_id in ext_ids:
                _insert_journal_db_id(cur, journal_id, db_id, ext_id, main_title)
        elif isinstance(ext_ids, str):
            _insert_journal_db_id(cur, journal_id, db_id, ext_ids, main_title)

    # ── Белый список ─────────────────────────────────────────────────────────
    # Членство определяется НАЛИЧИЕМ поля "level_YYYY": N на верхнем уровне.
    # Поле "white_list" может присутствовать как дополнительный источник,
    # но основной признак — level_YYYY.
    #
    # Собираем все level_YYYY из записи
    wl_entries: list[tuple[int, int]] = []  # [(year, level), ...]
    for key, val in record.items():
        if key.startswith("level_") and val is not None:
            try:
                yr = int(key[6:])   # "level_2023" → 2023
                lv = int(val)       # уровень 1-4
                if 1990 <= yr <= 2100 and 1 <= lv <= 4:
                    wl_entries.append((yr, lv))
            except (ValueError, TypeError):
                pass

    # Также обрабатываем legacy-поле white_list (если нет level_YYYY)
    white_data = record.get("white_list")
    if not wl_entries and isinstance(white_data, dict) and white_data.get("value"):
        wl_year = (_parse_year(white_data.get("update"))
                   or _parse_year(record.get("date_accepted"))
                   or DEFAULT_YEAR)
        raw_level = white_data.get("level") or white_data.get("category") or white_data.get("tier")
        try:
            wl_level = int(raw_level) if raw_level is not None else None
        except (ValueError, TypeError):
            wl_level = None
        wl_entries.append((wl_year, wl_level))

    for wl_year, wl_quartile in wl_entries:
        wl_db_id = ensure_white_list_db(cur, wl_year)
        cur.execute(
            "INSERT INTO journals_databases (journal_id, db_id, year, is_included, quartile) "
            "VALUES (%s, %s, %s, true, %s) "
            "ON CONFLICT (journal_id, db_id, year) DO UPDATE "
            "SET is_included = EXCLUDED.is_included, "
            "    quartile = COALESCE(EXCLUDED.quartile, journals_databases.quartile)",
            (journal_id, wl_db_id, wl_year, wl_quartile),
        )
        if isinstance(white_data, dict):
            ext_ids = white_data.get("id")
            if isinstance(ext_ids, list):
                for ext_id in ext_ids:
                    _insert_journal_db_id(cur, journal_id, wl_db_id, ext_id, main_title)
            elif isinstance(ext_ids, str):
                _insert_journal_db_id(cur, journal_id, wl_db_id, ext_ids, main_title)

    return status

# ─────────────────────────────────────────────────────────────────────────────
# Главная функция
# ─────────────────────────────────────────────────────────────────────────────
def main():
    global DATA_FILE
    if len(sys.argv) >= 2:
        DATA_FILE = Path(sys.argv[1])

    log.info("=" * 60)
    log.info(f"Запуск импорта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Файл данных:    {DATA_FILE.resolve()}")

    if not DATA_FILE.exists():
        log.error(f"Файл не найден: {DATA_FILE}")
        sys.exit(1)

    with open(DATA_FILE, encoding="utf-8") as f:
        data = json.load(f)
    total = len(data)
    log.info(f"Записей в файле: {total}")

    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    try:
        with conn.cursor() as cur:
            # Шаг 1: базы данных
            log.info("Инициализация таблицы databases...")
            db_ids = ensure_databases(cur)
            conn.commit()
            log.info(f"  Баз данных в маппинге: {len(db_ids)}")

            # Шаг 2: загружаем существующие языки
            log.info("Загрузка существующих языков...")
            existing_langs = load_existing_languages(cur)
            log.info(f"  Языков в БД: {len(existing_langs)}")

            # Шаг 3: импорт журналов
            log.info("Импорт журналов...")
            for i, record in enumerate(data, start=1):
                titles = record.get("title", [])
                label = titles[0] if titles else f"запись #{i}"

                cur.execute("SAVEPOINT sp_journal")
                try:
                    status = process_journal(cur, record, db_ids, existing_langs)
                    stats[status] += 1
                    cur.execute("RELEASE SAVEPOINT sp_journal")
                except psycopg2.Error as e:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_journal")
                    log.error(f"  ✗ Ошибка '{label}': {e}")
                    stats["errors"] += 1

                if i % 1000 == 0:
                    conn.commit()
                    log.info(f"  ... обработано {i}/{total}")

        conn.commit()
    except Exception as e:
        conn.rollback()
        log.critical(f"Критическая ошибка: {e}")
        raise
    finally:
        conn.close()

    # Итоги
    log.info("=" * 60)
    log.info(f"Добавлено:     {stats['inserted']}")
    log.info(f"Обновлено:     {stats['updated']}")
    log.info(f"Без изменений: {stats['skipped']}")
    log.info(f"Ошибок:        {stats['errors']}")
    log.info(f"Конфликтов:    {len(_conflicts)}")

    if _conflicts:
        conflict_file = Path("conflicts.txt")
        with open(conflict_file, "w", encoding="utf-8") as f:
            f.write(f"Конфликты при импорте {datetime.now()}\n")
            f.write("=" * 60 + "\n")
            f.write("\n".join(_conflicts))
        log.info(f"Конфликты записаны в: {conflict_file.resolve()}")

    log.info("=" * 60)

if __name__ == "__main__":
    main()
