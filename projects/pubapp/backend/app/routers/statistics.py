from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from app.database import get_db
from app.models import AppUser, Database, JournalDatabase, Organization
from app.auth import get_optional_user
from app.config import settings
from typing import Optional

router = APIRouter(prefix="/api/statistics", tags=["statistics"])

WHITELIST_PATTERN = "%list%"   # "White List …" or "Белый список …"


async def _resolve_org(db: AsyncSession, org_search: Optional[str], org_id: Optional[int]):
    """Return (org_id, org_name). Search by name substring or fall back to ФИЦ ИВТ."""
    if org_search:
        r = await db.execute(
            select(Organization.org_id, Organization.orgname)
            .where(Organization.orgname.ilike(f"%{org_search}%"))
            .limit(1)
        )
        row = r.fetchone()
        if row:
            return row[0], row[1]
    if org_id:
        r = await db.execute(
            select(Organization.org_id, Organization.orgname)
            .where(Organization.org_id == org_id)
        )
        row = r.fetchone()
        if row:
            return row[0], row[1]
    # fallback: ФИЦ ИВТ
    r = await db.execute(
        select(Organization.org_id, Organization.orgname)
        .where(Organization.orgname.ilike("%ФИЦ ИВТ%"))
        .limit(1)
    )
    row = r.fetchone()
    if row:
        return row[0], row[1]
    return settings.DEFAULT_ORG_ID, "ФИЦ ИВТ"


async def _get_whitelist_names(db: AsyncSession):
    rows = await db.execute(
        select(Database.name)
        .join(JournalDatabase, JournalDatabase.db_id == Database.db_id)
        .where(JournalDatabase.is_included == True)
        .where(Database.name.ilike(WHITELIST_PATTERN))
        .distinct()
        .order_by(Database.name)
    )
    return [r[0] for r in rows.all()]


def _build_stats_conditions(org_id, valid_support, project_number, year_from, year_to) -> tuple:
    conds = ["1=1"]
    params: dict = {}
    if org_id:
        conds.append("""EXISTS (
            SELECT 1 FROM articles_authors aa2
            JOIN author_affiliations af ON af.article_author_id = aa2.id
            WHERE aa2.article_id = a.article_id AND af.org_id = :filter_org_id
        )""")
        params["filter_org_id"] = org_id
    if valid_support == "true":
        conds.append("a.valid_support = TRUE")
    elif valid_support == "false":
        conds.append("a.valid_support = FALSE")
    elif valid_support == "null":
        conds.append("a.valid_support IS NULL")
    if project_number:
        conds.append("a.project_number = :project_number")
        params["project_number"] = project_number
    if year_from:
        conds.append("(i.year >= :yf OR EXTRACT(YEAR FROM a.print_date) >= :yf)")
        params["yf"] = year_from
    if year_to:
        conds.append("(i.year <= :yt OR EXTRACT(YEAR FROM a.print_date) <= :yt)")
        params["yt"] = year_to
    return " AND ".join(conds), params


@router.get("/available-dbs")
async def available_dbs(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(Database.name)
        .join(JournalDatabase, JournalDatabase.db_id == Database.db_id)
        .where(JournalDatabase.is_included == True)
        .distinct()
        .order_by(Database.name)
    )
    return [r[0] for r in rows.all()]


@router.get("/org-search")
async def org_search(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
):
    """Typeahead search for organizations by name."""
    rows = await db.execute(
        select(Organization.org_id, Organization.orgname)
        .where(Organization.orgname.ilike(f"%{q}%"))
        .order_by(Organization.orgname)
        .limit(20)
    )
    return [{"org_id": r[0], "orgname": r[1]} for r in rows.all()]


@router.get("/overview")
async def statistics_overview(
    org_search: Optional[str] = Query(None, description="Organization name substring"),
    valid_support: Optional[str] = Query(None),
    project_number: Optional[int] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    whitelist_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    resolved_org_id, resolved_org_name = await _resolve_org(db, org_search, None)

    # Build article filter — no org filter for counts, only for КБПР
    where, params = _build_stats_conditions(
        None, valid_support, project_number, year_from, year_to
    )

    wl_names = await _get_whitelist_names(db)

    # Dynamic whitelist columns
    wl_cases = "".join(
        f",\n            COUNT(DISTINCT CASE WHEN jd_wl_{i}.db_name IS NOT NULL THEN b.article_id END) AS wl_{i}"
        for i, wl in enumerate(wl_names)
    )
    wl_joins = "".join(
        f"\n        LEFT JOIN jdb jd_wl_{i} ON jd_wl_{i}.journal_id = b.journal_id AND jd_wl_{i}.db_name = '{wl.replace(chr(39), chr(39)*2)}'"
        for i, wl in enumerate(wl_names)
    )

    sql = text(f"""
        WITH base AS (
            SELECT DISTINCT a.article_id, a.risc, i.journal_id
            FROM articles a
            JOIN issues i ON i.issue_id = a.issue_id
            WHERE {where}
        ),
        jdb AS (
            SELECT jd.journal_id, d.name AS db_name, jd.quartile, jd.is_included
            FROM journals_databases jd
            JOIN databases d ON d.db_id = jd.db_id
            WHERE jd.is_included = TRUE
        )
        SELECT
            COUNT(DISTINCT b.article_id) AS total,
            -- WoS
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') THEN b.article_id END) AS wos,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') AND jd_wos.quartile=1 THEN b.article_id END) AS wos_q1,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') AND jd_wos.quartile=2 THEN b.article_id END) AS wos_q2,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') AND jd_wos.quartile=3 THEN b.article_id END) AS wos_q3,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') AND jd_wos.quartile=4 THEN b.article_id END) AS wos_q4,
            -- Scopus
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' THEN b.article_id END) AS scopus,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' AND jd_scp.quartile=1 THEN b.article_id END) AS scp_q1,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' AND jd_scp.quartile=2 THEN b.article_id END) AS scp_q2,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' AND jd_scp.quartile=3 THEN b.article_id END) AS scp_q3,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' AND jd_scp.quartile=4 THEN b.article_id END) AS scp_q4,
            -- ВАК
            COUNT(DISTINCT CASE WHEN LOWER(jd_vak.db_name) = 'вак' THEN b.article_id END) AS vak,
            -- РИНЦ
            COUNT(DISTINCT CASE WHEN b.risc = TRUE THEN b.article_id END) AS risc
            {wl_cases}
        FROM base b
        LEFT JOIN jdb jd_wos ON jd_wos.journal_id = b.journal_id AND (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos')
        LEFT JOIN jdb jd_scp ON jd_scp.journal_id = b.journal_id AND LOWER(jd_scp.db_name) = 'scopus'
        LEFT JOIN jdb jd_vak ON jd_vak.journal_id = b.journal_id AND LOWER(jd_vak.db_name) = 'вак'
        {wl_joins}
    """)
    row = (await db.execute(sql, params)).fetchone()

    # Whitelist quartiles (per-list)
    wl_quartiles = {}
    for i, wl in enumerate(wl_names):
        safe = wl.replace("'", "''")
        wq = await db.execute(text(f"""
            SELECT
              COUNT(DISTINCT CASE WHEN jd.quartile=1 THEN a.article_id END),
              COUNT(DISTINCT CASE WHEN jd.quartile=2 THEN a.article_id END),
              COUNT(DISTINCT CASE WHEN jd.quartile=3 THEN a.article_id END),
              COUNT(DISTINCT CASE WHEN jd.quartile=4 THEN a.article_id END),
              COUNT(DISTINCT a.article_id)
            FROM articles a
            JOIN issues i ON i.issue_id = a.issue_id
            LEFT JOIN journals_databases jd ON jd.journal_id = i.journal_id
              AND jd.db_id = (SELECT db_id FROM databases WHERE name='{safe}' LIMIT 1)
              AND jd.is_included = TRUE
            WHERE {where}
        """), params)
        wqr = wq.fetchone()
        wl_quartiles[wl] = {"q1": wqr[0] or 0, "q2": wqr[1] or 0, "q3": wqr[2] or 0, "q4": wqr[3] or 0, "total": wqr[4] or 0}

    result = {
        "total":  row[0] or 0,
        "wos":    row[1] or 0,
        "wos_quartiles": {"q1": row[2] or 0, "q2": row[3] or 0, "q3": row[4] or 0, "q4": row[5] or 0},
        "scopus": row[6] or 0,
        "scp_quartiles": {"q1": row[7] or 0, "q2": row[8] or 0, "q3": row[9] or 0, "q4": row[10] or 0},
        "vak":    row[11] or 0,
        "risc":   row[12] or 0,
        "whitelists": {wl_names[i]: (row[13 + i] or 0) for i in range(len(wl_names))},
        "whitelist_quartiles": wl_quartiles,
        "org_id": resolved_org_id,
        "org_name": resolved_org_name,
    }

    # КБПР calculation
    kbpr_wl = whitelist_name
    kbpr_params = dict(params)
    kbpr_params["kbpr_org_id"] = resolved_org_id

    if kbpr_wl:
        safe_wl = kbpr_wl.replace("'", "''")
        kbpr_sql = text(f"""
            WITH base AS (
                SELECT DISTINCT a.article_id, a.authors_count, i.journal_id
                FROM articles a JOIN issues i ON i.issue_id = a.issue_id
                WHERE {where}
            ),
            org_contribs AS (
                SELECT b.article_id, b.authors_count,
                       SUM(1.0 / NULLIF(aa.affiliations_count, 0)) AS contrib_sum,
                       jd_wl.quartile AS quartile,
                       jd_vak.journal_id AS vak_id
                FROM base b
                JOIN articles_authors aa ON aa.article_id = b.article_id
                JOIN author_affiliations af ON af.article_author_id = aa.id AND af.org_id = :kbpr_org_id
                LEFT JOIN journals_databases jd_wl ON jd_wl.journal_id = b.journal_id
                    AND jd_wl.db_id = (SELECT db_id FROM databases WHERE name = '{safe_wl}' LIMIT 1)
                    AND jd_wl.is_included = TRUE
                LEFT JOIN journals_databases jd_vak ON jd_vak.journal_id = b.journal_id
                    AND jd_vak.db_id = (SELECT db_id FROM databases WHERE LOWER(name) = 'вак' LIMIT 1)
                    AND jd_vak.is_included = TRUE
                GROUP BY b.article_id, b.authors_count, jd_wl.quartile, jd_vak.journal_id
            )
            SELECT COALESCE(SUM(
                (contrib_sum / NULLIF(authors_count, 0)) *
                CASE
                    WHEN quartile = 1 THEN 20.0
                    WHEN quartile = 2 THEN 10.0
                    WHEN quartile = 3 THEN  5.0
                    WHEN quartile = 4 THEN  2.5
                    WHEN vak_id IS NOT NULL THEN 0.12
                    ELSE 0.0
                END
            ), 0)
            FROM org_contribs
        """)
        kbpr_row = (await db.execute(kbpr_sql, kbpr_params)).fetchone()
        result["total_kbpr"] = float(kbpr_row[0] or 0)
        result["kbpr_whitelist"] = kbpr_wl
        result["kbpr_mode"] = "single"
    else:
        # Best quartile across all whitelists
        wl_ids_subq = f"SELECT db_id FROM databases WHERE name ILIKE '{WHITELIST_PATTERN}'"
        kbpr_sql = text(f"""
            WITH base AS (
                SELECT DISTINCT a.article_id, a.authors_count, i.journal_id
                FROM articles a JOIN issues i ON i.issue_id = a.issue_id WHERE {where}
            ),
            best_q AS (
                SELECT jd.journal_id, MIN(jd.quartile) AS best_q, BOOL_OR(jd.is_included) AS any_inc
                FROM journals_databases jd
                WHERE jd.db_id IN ({wl_ids_subq}) AND jd.is_included = TRUE
                GROUP BY jd.journal_id
            ),
            org_contribs AS (
                SELECT b.article_id, b.authors_count,
                       SUM(1.0 / NULLIF(aa.affiliations_count, 0)) AS contrib_sum,
                       bq.best_q AS quartile,
                       jd_vak.journal_id AS vak_id
                FROM base b
                JOIN articles_authors aa ON aa.article_id = b.article_id
                JOIN author_affiliations af ON af.article_author_id = aa.id AND af.org_id = :kbpr_org_id
                LEFT JOIN best_q bq ON bq.journal_id = b.journal_id
                LEFT JOIN journals_databases jd_vak ON jd_vak.journal_id = b.journal_id
                    AND jd_vak.db_id = (SELECT db_id FROM databases WHERE LOWER(name) = 'вак' LIMIT 1)
                    AND jd_vak.is_included = TRUE
                GROUP BY b.article_id, b.authors_count, bq.best_q, jd_vak.journal_id
            )
            SELECT COALESCE(SUM(
                (contrib_sum / NULLIF(authors_count, 0)) *
                CASE
                    WHEN quartile = 1 THEN 20.0
                    WHEN quartile = 2 THEN 10.0
                    WHEN quartile = 3 THEN  5.0
                    WHEN quartile = 4 THEN  2.5
                    WHEN vak_id IS NOT NULL THEN 0.12
                    ELSE 0.0
                END
            ), 0)
            FROM org_contribs
        """)
        kbpr_row = (await db.execute(kbpr_sql, kbpr_params)).fetchone()
        result["total_kbpr"] = float(kbpr_row[0] or 0)
        result["kbpr_whitelist"] = None
        result["kbpr_mode"] = "best_across_all"

    return result
