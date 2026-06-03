from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text
from app.database import get_db
from app.models import Author, AuthorName, AppUser, Database, JournalDatabase, Organization
from app.schemas import AuthorOut, PaginatedResponse
from app.auth import get_optional_user
from app.config import settings
from typing import Optional, List

router = APIRouter(prefix="/api/authors", tags=["authors"])

WHITELIST_PATTERN = "%list%"

# ── КБПР coefficient table ────────────────────────────────────────────────────
# Белый список level (quartile field): 1→20, 2→10, 3→5, 4→2.5
# Not in any Белый список but in ВАК: 0.12
# Not indexed at all: 0
K_BY_QUARTILE = {1: 20.0, 2: 10.0, 3: 5.0, 4: 2.5}
K_VAK = 0.12

def _k_case(quartile_col: str = "quartile", vak_col: str = "vak_journal_id") -> str:
    return f"""CASE
            WHEN {quartile_col} = 1 THEN 20.0
            WHEN {quartile_col} = 2 THEN 10.0
            WHEN {quartile_col} = 3 THEN  5.0
            WHEN {quartile_col} = 4 THEN  2.5
            WHEN {vak_col} IS NOT NULL THEN 0.12
            ELSE 0.0
        END"""


async def _resolve_org(db: AsyncSession, org_search: Optional[str]) -> tuple:
    if org_search:
        r = await db.execute(
            select(Organization.org_id, Organization.orgname)
            .where(Organization.orgname.ilike(f"%{org_search}%"))
            .limit(1)
        )
        row = r.fetchone()
        if row:
            return row[0], row[1]
    r = await db.execute(
        select(Organization.org_id, Organization.orgname)
        .where(Organization.orgname.ilike("%ФИЦ ИВТ%"))
        .limit(1)
    )
    row = r.fetchone()
    return (row[0], row[1]) if row else (settings.DEFAULT_ORG_ID, "ФИЦ ИВТ")


async def _get_whitelist_names(db: AsyncSession) -> List[str]:
    rows = await db.execute(
        select(Database.name)
        .join(JournalDatabase, JournalDatabase.db_id == Database.db_id)
        .where(JournalDatabase.is_included == True)
        .where(Database.name.ilike(WHITELIST_PATTERN))
        .distinct()
        .order_by(Database.name)
    )
    return [r[0] for r in rows.all()]


@router.get("", response_model=PaginatedResponse)
async def list_authors(
    search: Optional[str] = Query(None),
    skip: int = 0, limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    query = select(Author).distinct()
    if search:
        sl = f"%{search.lower()}%"
        query = query.outerjoin(AuthorName, AuthorName.author_id == Author.author_id)
        query = query.where(or_(
            func.lower(Author.lastname).like(sl),
            func.lower(Author.firstname).like(sl),
            func.lower(Author.middlename).like(sl),
            func.lower(Author.initials).like(sl),
            func.lower(Author.email).like(sl),
            func.lower(AuthorName.lastname).like(sl),
            func.lower(AuthorName.firstname).like(sl),
        ))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar()
    authors = (await db.execute(query.offset(skip).limit(limit))).scalars().all()
    return PaginatedResponse(total=total, items=[AuthorOut.model_validate(a) for a in authors])


@router.get("/org-search")
async def org_search_endpoint(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(
        select(Organization.org_id, Organization.orgname)
        .where(Organization.orgname.ilike(f"%{q}%"))
        .order_by(Organization.orgname)
        .limit(20)
    )
    return [{"org_id": r[0], "orgname": r[1]} for r in rows.all()]


@router.get("/{author_id}", response_model=AuthorOut)
async def get_author(
    author_id: int,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    result = await db.execute(select(Author).where(Author.author_id == author_id))
    author = result.scalar_one_or_none()
    if not author:
        raise HTTPException(404, "Author not found")
    return AuthorOut.model_validate(author)


@router.get("/{author_id}/activity")
async def author_activity(
    author_id: int,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    valid_support: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    author = (await db.execute(select(Author).where(Author.author_id == author_id))).scalar_one_or_none()
    if not author:
        raise HTTPException(404, "Author not found")

    wl_names = await _get_whitelist_names(db)

    conds = ["aa.author_id = :author_id"]
    params: dict = {"author_id": author_id}
    if year_from:
        conds.append("(i.year >= :year_from OR EXTRACT(YEAR FROM a.print_date) >= :year_from)")
        params["year_from"] = year_from
    if year_to:
        conds.append("(i.year <= :year_to OR EXTRACT(YEAR FROM a.print_date) <= :year_to)")
        params["year_to"] = year_to
    if valid_support == "true":
        conds.append("a.valid_support = TRUE")
    elif valid_support == "false":
        conds.append("a.valid_support = FALSE")
    elif valid_support == "null":
        conds.append("a.valid_support IS NULL")
    where = " AND ".join(conds)

    wl_cases = "".join(
        f",\n            COUNT(DISTINCT CASE WHEN jd_wl_{i}.db_name IS NOT NULL THEN b.article_id END) AS wl_{i}"
        for i, wl in enumerate(wl_names)
    )
    wl_joins = "".join(
        f"\n        LEFT JOIN journal_dbs jd_wl_{i} ON jd_wl_{i}.journal_id = b.journal_id AND jd_wl_{i}.db_name = '{wl.replace(chr(39), chr(39)*2)}'"
        for i, wl in enumerate(wl_names)
    )

    sql = text(f"""
        WITH base AS (
            SELECT DISTINCT a.article_id, a.risc, i.journal_id
            FROM articles_authors aa
            JOIN articles a ON a.article_id = aa.article_id
            JOIN issues i ON i.issue_id = a.issue_id
            WHERE {where}
        ),
        journal_dbs AS (
            SELECT jd.journal_id, d.name AS db_name, jd.quartile
            FROM journals_databases jd
            JOIN databases d ON d.db_id = jd.db_id
            WHERE jd.is_included = TRUE
        )
        SELECT
            COUNT(DISTINCT b.article_id) AS total,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') THEN b.article_id END) AS wos,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') AND jd_wos.quartile=1 THEN b.article_id END) AS wos_q1,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') AND jd_wos.quartile=2 THEN b.article_id END) AS wos_q2,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') AND jd_wos.quartile=3 THEN b.article_id END) AS wos_q3,
            COUNT(DISTINCT CASE WHEN (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos') AND jd_wos.quartile=4 THEN b.article_id END) AS wos_q4,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' THEN b.article_id END) AS scopus,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' AND jd_scp.quartile=1 THEN b.article_id END) AS scp_q1,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' AND jd_scp.quartile=2 THEN b.article_id END) AS scp_q2,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' AND jd_scp.quartile=3 THEN b.article_id END) AS scp_q3,
            COUNT(DISTINCT CASE WHEN LOWER(jd_scp.db_name) = 'scopus' AND jd_scp.quartile=4 THEN b.article_id END) AS scp_q4,
            COUNT(DISTINCT CASE WHEN LOWER(jd_vak.db_name) = 'вак' THEN b.article_id END) AS vak,
            COUNT(DISTINCT CASE WHEN b.risc = TRUE THEN b.article_id END) AS risc
            {wl_cases}
        FROM base b
        LEFT JOIN journal_dbs jd_wos ON jd_wos.journal_id = b.journal_id AND (LOWER(jd_wos.db_name) LIKE '%web of science%' OR LOWER(jd_wos.db_name) = 'wos')
        LEFT JOIN journal_dbs jd_scp ON jd_scp.journal_id = b.journal_id AND LOWER(jd_scp.db_name) = 'scopus'
        LEFT JOIN journal_dbs jd_vak ON jd_vak.journal_id = b.journal_id AND LOWER(jd_vak.db_name) = 'вак'
        {wl_joins}
    """)
    row = (await db.execute(sql, params)).fetchone()

    wl_quartiles = {}
    for wl in wl_names:
        safe = wl.replace("'", "''")
        wqr = (await db.execute(text(f"""
            SELECT
              COUNT(DISTINCT CASE WHEN jd.quartile=1 THEN b.article_id END),
              COUNT(DISTINCT CASE WHEN jd.quartile=2 THEN b.article_id END),
              COUNT(DISTINCT CASE WHEN jd.quartile=3 THEN b.article_id END),
              COUNT(DISTINCT CASE WHEN jd.quartile=4 THEN b.article_id END)
            FROM (
                SELECT DISTINCT a.article_id, i.journal_id
                FROM articles_authors aa
                JOIN articles a ON a.article_id = aa.article_id
                JOIN issues i ON i.issue_id = a.issue_id
                WHERE {where}
            ) b
            LEFT JOIN journals_databases jd ON jd.journal_id = b.journal_id
              AND jd.db_id = (SELECT db_id FROM databases WHERE name='{safe}' LIMIT 1)
              AND jd.is_included = TRUE
        """), params)).fetchone()
        wl_quartiles[wl] = {"q1": wqr[0] or 0, "q2": wqr[1] or 0, "q3": wqr[2] or 0, "q4": wqr[3] or 0}

    return {
        "author_id": author_id,
        "lastname": author.lastname, "firstname": author.firstname,
        "middlename": author.middlename, "initials": author.initials,
        "total": row[0] or 0,
        "wos": row[1] or 0,
        "wos_quartiles": {"q1": row[2] or 0, "q2": row[3] or 0, "q3": row[4] or 0, "q4": row[5] or 0},
        "scopus": row[6] or 0,
        "scp_quartiles": {"q1": row[7] or 0, "q2": row[8] or 0, "q3": row[9] or 0, "q4": row[10] or 0},
        "vak": row[11] or 0,
        "risc": row[12] or 0,
        "whitelists": {wl_names[i]: (row[13 + i] or 0) for i in range(len(wl_names))},
        "whitelist_quartiles": wl_quartiles,
    }


@router.get("/{author_id}/invalid-support-count")
async def author_invalid_support_count(
    author_id: int,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    conds = ["aa.author_id = :author_id", "a.valid_support = FALSE"]
    params: dict = {"author_id": author_id}
    if year_from:
        conds.append("(i.year >= :yf OR EXTRACT(YEAR FROM a.print_date) >= :yf)")
        params["yf"] = year_from
    if year_to:
        conds.append("(i.year <= :yt OR EXTRACT(YEAR FROM a.print_date) <= :yt)")
        params["yt"] = year_to
    sql = text(f"""
        SELECT COUNT(DISTINCT a.article_id)
        FROM articles_authors aa
        JOIN articles a ON a.article_id = aa.article_id
        JOIN issues i ON i.issue_id = a.issue_id
        WHERE {' AND '.join(conds)}
    """)
    return {"author_id": author_id, "count": (await db.execute(sql, params)).scalar() or 0}


@router.get("/{author_id}/kbpr")
async def author_kbpr(
    author_id: int,
    org_search: Optional[str] = Query(None),
    whitelist_name: Optional[str] = Query(None),
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    """
    КБПР автора для организации:
      contribution = (1/N) * Σ(1/m_i)  — для авторов публикации с аффилиацией org
        N   = общее число авторов статьи
        m_i = число аффилиаций i-го автора
      K:  БС Q1→20, Q2→10, Q3→5, Q4→2.5;  ВАК (не в БС)→0.12;  иначе→0
      КБПР = Σ(contribution × K)
    """
    resolved_org_id, resolved_org_name = await _resolve_org(db, org_search)

    conds = ["aa.author_id = :author_id", "af.org_id = :org_id"]
    params: dict = {"author_id": author_id, "org_id": resolved_org_id}
    if year_from:
        conds.append("(i.year >= :yf OR EXTRACT(YEAR FROM a.print_date) >= :yf)")
        params["yf"] = year_from
    if year_to:
        conds.append("(i.year <= :yt OR EXTRACT(YEAR FROM a.print_date) <= :yt)")
        params["yt"] = year_to

    where = " AND ".join(conds)

    if whitelist_name:
        # Single whitelist
        safe_wl = whitelist_name.replace("'", "''")
        wl_join = f"""LEFT JOIN journals_databases jd_wl ON jd_wl.journal_id = c.journal_id
            AND jd_wl.db_id = (SELECT db_id FROM databases WHERE name = '{safe_wl}' LIMIT 1)
            AND jd_wl.is_included = TRUE"""
        quartile_col = "jd_wl.quartile"
    else:
        # Best quartile across all whitelists
        wl_join = f"""LEFT JOIN (
            SELECT jd.journal_id, MIN(jd.quartile) AS quartile
            FROM journals_databases jd
            WHERE jd.db_id IN (SELECT db_id FROM databases WHERE name ILIKE '{WHITELIST_PATTERN}')
              AND jd.is_included = TRUE
            GROUP BY jd.journal_id
        ) jd_wl ON jd_wl.journal_id = c.journal_id"""
        quartile_col = "jd_wl.quartile"

    sql = text(f"""
        WITH author_articles AS (
            -- One row per (article, author-with-org-affiliation)
            SELECT DISTINCT
                a.article_id,
                a.authors_count            AS n_authors,
                aa.affiliations_count      AS m_i,
                i.journal_id
            FROM articles_authors aa
            JOIN articles a  ON a.article_id  = aa.article_id
            JOIN issues i    ON i.issue_id    = a.issue_id
            JOIN author_affiliations af ON af.article_author_id = aa.id
            WHERE {where}
        ),
        contribution_per_article AS (
            -- contribution = (1/N) * Σ(1/m_i)
            SELECT
                article_id,
                journal_id,
                SUM(1.0 / NULLIF(m_i, 0)) / NULLIF(MAX(n_authors), 0) AS contribution
            FROM author_articles
            GROUP BY article_id, journal_id
        ),
        with_k AS (
            SELECT
                c.article_id,
                c.contribution,
                {_k_case(quartile_col, 'jd_vak.journal_id')} AS k
            FROM contribution_per_article c
            {wl_join}
            LEFT JOIN journals_databases jd_vak ON jd_vak.journal_id = c.journal_id
                AND jd_vak.db_id = (SELECT db_id FROM databases WHERE LOWER(name) = 'вак' LIMIT 1)
                AND jd_vak.is_included = TRUE
        )
        SELECT
            COUNT(DISTINCT article_id)          AS article_count,
            COALESCE(SUM(contribution * k), 0)  AS total_kbpr
        FROM with_k
    """)

    row = (await db.execute(sql, params)).fetchone()
    return {
        "author_id": author_id,
        "org_id": resolved_org_id,
        "org_name": resolved_org_name,
        "kbpr": float(row[1] or 0),
        "article_count": int(row[0] or 0),
        "whitelist_name": whitelist_name,
        "kbpr_mode": "single" if whitelist_name else "best_across_all",
        "formula": "contribution=(1/N)*Σ(1/m_i); K: Q1=20, Q2=10, Q3=5, Q4=2.5, ВАК=0.12",
    }
