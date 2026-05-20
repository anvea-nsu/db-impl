#!/usr/bin/env python3
"""
import_journals.py
==================
Импорт журналов из файла journalrank.rcsi.science в PostgreSQL.

Идемпотентный: безопасно запускать повторно с обновлённым файлом.
Логика:
  - Если журнал не найден → вставляем новую запись.
  - Если найден → дополняем пустые поля, конфликты фиксируем в лог.
  - Каждый журнал обрабатывается в отдельном savepoint —
    ошибка в одной записи не прерывает весь импорт.

Зависимости: psycopg2-binary
  pip install psycopg2-binary
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2 import sql as pgsql

# ─────────────────────────────────────────────────────────────────────────────
# НАСТРОЙКИ — измени под свои
# ─────────────────────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     "localhost",
    "port":     5432,
    "dbname":   "publication_db",   # <-- имя твоей БД
    "user":     "anvea",  # <-- пользователь PostgreSQL
    "password": "",  # <-- пароль
}

# Путь к скачанному файлу (положи его рядом со скриптом)
DATA_FILE = Path("journals.json")

# Год по умолчанию для таблицы journals_databases.
# В файле journalrank данные актуальны на 2023 год (поле level_2023).
DEFAULT_YEAR = 2023

# ─────────────────────────────────────────────────────────────────────────────
# Маппинг: ключ в JSON → читаемое название базы данных
# Используется для автоматического заполнения таблицы databases
# ─────────────────────────────────────────────────────────────────────────────

DB_FIELD_TO_NAME: dict[str, str] = {
    "wos_cc":   "Web of Science Core Collection",
    "scopus":   "Scopus",
    "rsci":     "RSCI",
    "sherpa":   "SHERPA/RoMEO",
    "doaj":     "DOAJ",
    "erih":     "ERIH+",
    "inspec":   "INSPEC",
    "dblp":     "DBLP",
    "msn":      "MathSciNet",
    "zbm":      "zbMATH",
    "medline":  "MEDLINE",
    "embase":   "Embase",
    "agricola": "AGRICOLA",
    "cab":      "CAB Abstracts",
    "cpx":      "Compendex (EI)",
    "georef":   "GeoRef",
    "geobase":  "Geobase",
    "oax":      "OpenAlex",
    "job":      "JournalTOCs",
    "sudoc":    "SUDOC",
    "scilit":   "Scilit",
    "wikidata": "Wikidata",
    "fatcat":   "Fatcat",
    "dnb":      "Deutsche Nationalbibliothek",
    "cas_core": "CAS Core",
    "cref":     "Crossref",
    "fsta":     "FSTA",
    "hsabs":    "Historical Abstracts",
    "wpsa":     "WPSA",
    "socabs":   "Sociological Abstracts",
    "chim":     "ChemInform",
    "zoorec":   "Zoological Record",
    "biabs":    "Biological Abstracts",
    "petro":    "Petroleum Abstracts",
    "abdc22":   "ABDC Journal Quality List 2022",
    "ajg21":    "AJG 2021",
    "eclit":    "ECLIT",
    "ecbiz":    "ECBIZ",
}

# ─────────────────────────────────────────────────────────────────────────────
# Логирование: в файл и в консоль одновременно
# ─────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("import.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# Отдельный список конфликтов — запишем в отдельный файл в конце
_conflicts: list[str] = []


def _record_conflict(journal_title: str, field: str, in_db, in_file):
    msg = (
        f"КОНФЛИКТ | '{journal_title}' | поле '{field}' "
        f"| в БД: {in_db!r} | в файле: {in_file!r}"
    )
    log.warning(msg)
    _conflicts.append(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _parse_year(date_str: Optional[str]) -> Optional[int]:
    """'DD.MM.YYYY' → int год. None если не распарсить."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%d.%m.%Y").year
    except ValueError:
        return None


def _split_issns(issns: list[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Разбивает список ISSN на (issn, eissn).

    ПРОБЛЕМА (на которую указал преподаватель):
    В файле ISSN и eISSN перемешаны без пометок, какой из них какой.
    Оба имеют формат XXXX-XXXX, различить автоматически невозможно.

    РЕШЕНИЕ:
    Первый элемент → issn (печатный), второй → eissn (электронный).
    Это условное назначение. При сравнении с уже существующими данными
    скрипт проверяет ОБА порядка, чтобы не считать перестановку конфликтом.
    """
    if len(issns) > 2:
        log.warning(f"Больше двух ISSN: {issns} — лишние игнорируются")
    issn  = issns[0] if len(issns) >= 1 else None
    eissn = issns[1] if len(issns) >= 2 else None
    return issn, eissn


# ─────────────────────────────────────────────────────────────────────────────
# Инициализация справочника databases
# ─────────────────────────────────────────────────────────────────────────────

def ensure_databases(cur) -> dict[str, int]:
    """
    Добавляет в таблицу databases все БД из маппинга, если их там ещё нет.
    Возвращает словарь {ключ_json: db_id}.
    """
    result: dict[str, int] = {}
    for field_key, db_name in DB_FIELD_TO_NAME.items():
        cur.execute(
            "INSERT INTO databases (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
            (db_name,)
        )
        cur.execute("SELECT db_id FROM databases WHERE name = %s", (db_name,))
        row = cur.fetchone()
        if row:
            result[field_key] = row[0]
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Поиск журнала в БД
# ─────────────────────────────────────────────────────────────────────────────

def find_journal_id(
    cur,
    issn:   Optional[str],
    eissn:  Optional[str],
    titles: list[str],
) -> Optional[int]:
    """
    Ищет журнал в БД по нескольким критериям (в порядке надёжности):
    1. По issn или eissn — в ОБОИХ полях таблицы journals (т.к. назначение условное).
    2. По точному совпадению названия (регистронезависимо).
    Возвращает journal_id или None.
    """
    # 1. По ISSN (проверяем оба поля, т.к. в файле они могут быть перепутаны)
    for val in filter(None, [issn, eissn]):
        cur.execute(
            "SELECT journal_id FROM journals WHERE issn = %s OR eissn = %s",
            (val, val),
        )
        row = cur.fetchone()
        if row:
            return row[0]

    # 2. По названию: сначала в основной таблице, потом в journal_titles
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
# Обработка одного журнала
# ─────────────────────────────────────────────────────────────────────────────

def process_journal(cur, record: dict, db_ids: dict[str, int]) -> str:
    """
    Вставляет новый журнал или обновляет существующий.
    Возвращает статус: 'inserted' | 'updated' | 'skipped'.
    """
    titles: list[str] = record.get("title", [])
    main_title = titles[0] if titles else "БЕЗ НАЗВАНИЯ"
    issns = record.get("issns", [])
    issn, eissn = _split_issns(issns)

    journal_id = find_journal_id(cur, issn, eissn, titles)
    status = "skipped"

    # ── ВСТАВКА нового журнала ────────────────────────────────────────────────
    if journal_id is None:
        cur.execute(
            "INSERT INTO journals (title, issn, eissn) VALUES (%s, %s, %s) RETURNING journal_id",
            (main_title, issn, eissn),
        )
        journal_id = cur.fetchone()[0]
        log.info(f"  + Добавлен: '{main_title}' (id={journal_id})")
        status = "inserted"

    # ── ОБНОВЛЕНИЕ существующего журнала ──────────────────────────────────────
    else:
        cur.execute(
            "SELECT title, issn, eissn FROM journals WHERE journal_id = %s",
            (journal_id,),
        )
        ex_title, ex_issn, ex_eissn = cur.fetchone()

        updates: dict[str, object] = {}

        # Дополняем issn / eissn, если поле пустое
        if ex_issn is None and issn:
            updates["issn"] = issn
        elif ex_issn and issn and ex_issn != issn:
            # Перестановка — не конфликт, просто перепутаны местами в файле
            if ex_issn == eissn or ex_eissn == issn:
                pass
            else:
                _record_conflict(main_title, "issn", ex_issn, issn)

        if ex_eissn is None and eissn:
            updates["eissn"] = eissn
        elif ex_eissn and eissn and ex_eissn != eissn:
            if ex_eissn == issn or ex_issn == eissn:
                pass
            else:
                _record_conflict(main_title, "eissn", ex_eissn, eissn)

        if updates:
            set_clause = ", ".join(f"{k} = %s" for k in updates)
            cur.execute(
                f"UPDATE journals SET {set_clause} WHERE journal_id = %s",
                [*updates.values(), journal_id],
            )
            log.info(f"  ~ Обновлён id={journal_id} '{main_title}': {list(updates.keys())}")
            status = "updated"

    # ── Названия → journal_titles ─────────────────────────────────────────────
    # Все названия из массива title[] сохраняем с lang='en',
    # т.к. в файле journalrank названия на английском.
    # Если у журнала несколько названий (например, аббревиатура),
    # второе и последующие вставятся как отдельные строки с тем же lang.
    # Из-за уникального ограничения (journal_id, lang) хранится только одно
    # название на язык — поэтому используем ON CONFLICT DO NOTHING
    # и логируем, если название отличается от уже записанного.
    for title_text in titles:
        cur.execute(
            """
            INSERT INTO journal_titles (journal_id, lang, title_text)
            VALUES (%s, 'en', %s)
            ON CONFLICT (journal_id, lang) DO NOTHING
            """,
            (journal_id, title_text),
        )
        if cur.rowcount == 0:
            # Запись на этот язык уже есть — проверяем, не другое ли название
            cur.execute(
                "SELECT title_text FROM journal_titles WHERE journal_id = %s AND lang = 'en'",
                (journal_id,),
            )
            row = cur.fetchone()
            if row and row[0].lower() != title_text.lower():
                _record_conflict(main_title, "journal_titles[en]", row[0], title_text)

    # ── Индексирование → journals_databases + journal_database_ids ────────────
    for field_key, db_id in db_ids.items():
        db_data = record.get(field_key)
        if not isinstance(db_data, dict):
            continue

        is_included: bool = bool(db_data.get("value", False))
        year: int = _parse_year(db_data.get("update")) or DEFAULT_YEAR

        # journals_databases: факт индексирования за год
        cur.execute(
            """
            INSERT INTO journals_databases (journal_id, db_id, year, is_included)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (journal_id, db_id, year)
            DO UPDATE SET is_included = EXCLUDED.is_included
            """,
            (journal_id, db_id, year, is_included),
        )

        # journal_database_ids: внешние идентификаторы журнала в этой БД
        ext_ids = db_data.get("id")
        if isinstance(ext_ids, list):
            for ext_id in ext_ids:
                cur.execute(
                    """
                    INSERT INTO journal_database_ids (journal_id, db_id, db_journal_id)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (db_id, db_journal_id) DO NOTHING
                    """,
                    (journal_id, db_id, str(ext_id)),
                )
        elif isinstance(ext_ids, str):
            cur.execute(
                """
                INSERT INTO journal_database_ids (journal_id, db_id, db_journal_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (db_id, db_journal_id) DO NOTHING
                """,
                (journal_id, db_id, ext_ids),
            )

    return status


# ─────────────────────────────────────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────────────────────────────────────

def main():
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
            # Шаг 1: наполнить таблицу databases
            log.info("Инициализация таблицы databases...")
            db_ids = ensure_databases(cur)
            conn.commit()
            log.info(f"  Баз данных в маппинге: {len(db_ids)}")

            # Шаг 2: обработать каждый журнал в отдельном savepoint
            log.info("Импорт журналов...")
            for i, record in enumerate(data, start=1):
                titles = record.get("title", [])
                label = titles[0] if titles else f"запись #{i}"

                cur.execute("SAVEPOINT sp_journal")
                try:
                    status = process_journal(cur, record, db_ids)
                    stats[status] += 1
                    cur.execute("RELEASE SAVEPOINT sp_journal")
                except psycopg2.Error as e:
                    cur.execute("ROLLBACK TO SAVEPOINT sp_journal")
                    log.error(f"  ✗ Ошибка '{label}': {e}")
                    stats["errors"] += 1

                # Промежуточный коммит каждые 500 журналов
                if i % 500 == 0:
                    conn.commit()
                    log.info(f"  ... обработано {i}/{total}")

        conn.commit()

    except Exception as e:
        conn.rollback()
        log.critical(f"Критическая ошибка: {e}")
        raise
    finally:
        conn.close()

    # ── Итоги ─────────────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("ИТОГИ:")
    log.info(f"  Добавлено:   {stats['inserted']}")
    log.info(f"  Обновлено:   {stats['updated']}")
    log.info(f"  Без изменений: {stats['skipped']}")
    log.info(f"  Ошибок:      {stats['errors']}")
    log.info(f"  Конфликтов:  {len(_conflicts)}")

    if _conflicts:
        conflict_file = Path("conflicts.txt")
        with open(conflict_file, "w", encoding="utf-8") as f:
            f.write(f"Конфликты при импорте {datetime.now()}\n")
            f.write("=" * 60 + "\n")
            f.write("\n".join(_conflicts))
        log.info(f"  Конфликты записаны в: {conflict_file.resolve()}")

    log.info("=" * 60)


if __name__ == "__main__":
    main()
