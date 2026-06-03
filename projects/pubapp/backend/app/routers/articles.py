import re
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text
from app.database import get_db
from app.models import Article, Issue, Journal, AppUser, Database, JournalDatabase
from app.schemas import ArticleOut, PaginatedResponse
from app.auth import get_optional_user
from app.config import settings
from typing import Optional, List

router = APIRouter(prefix="/api/articles", tags=["articles"])


def _build_article_query(
    search=None, doi=None, author_id=None, journal_id=None,
    year_from=None, year_to=None, org_id=None, valid_support=None,
    project_number=None, dbs=None, quartile=None,
) -> tuple:
    conds = ["1=1"]
    params: dict = {}

    if search:
        conds.append("(LOWER(a.title) LIKE :search OR EXISTS (SELECT 1 FROM article_titles at2 WHERE at2.article_id=a.article_id AND LOWER(at2.title_text) LIKE :search))")
        params["search"] = f"%{search.lower()}%"
    if doi:
        conds.append("LOWER(a.doi) LIKE :doi")
        params["doi"] = f"%{doi.lower()}%"
    if author_id:
        conds.append("EXISTS (SELECT 1 FROM articles_authors aa WHERE aa.article_id=a.article_id AND aa.author_id=:author_id)")
        params["author_id"] = author_id
    if journal_id:
        conds.append("i.journal_id = :journal_id")
        params["journal_id"] = journal_id
    if year_from:
        conds.append("(i.year >= :year_from OR EXTRACT(YEAR FROM a.print_date) >= :year_from)")
        params["year_from"] = year_from
    if year_to:
        conds.append("(i.year <= :year_to OR EXTRACT(YEAR FROM a.print_date) <= :year_to)")
        params["year_to"] = year_to
    if org_id:
        conds.append("""EXISTS (
            SELECT 1 FROM articles_authors aa2
            JOIN author_affiliations af ON af.article_author_id = aa2.id
            WHERE aa2.article_id = a.article_id AND af.org_id = :org_id
        )""")
        params["org_id"] = org_id
    if valid_support == "true":
        conds.append("a.valid_support = TRUE")
    elif valid_support == "false":
        conds.append("a.valid_support = FALSE")
    elif valid_support == "null":
        conds.append("a.valid_support IS NULL")
    if project_number:
        conds.append("a.project_number = :project_number")
        params["project_number"] = project_number

    # DB filter: AND intersection — article must be in ALL selected DBs
    if dbs:
        for i, name in enumerate(dbs):
            safe = name.replace("'", "''")
            # Apply quartile ONLY to whitelist DBs (they have levels 1-4)
            is_wl = bool(re.search(r'белый список|white\s*list', name, re.IGNORECASE))
            q_cond = f"AND jd.quartile = {quartile}" if (quartile and is_wl) else ""
            conds.append(f"""EXISTS (
                SELECT 1 FROM journals_databases jd
                JOIN databases d ON d.db_id = jd.db_id
                WHERE jd.journal_id = i.journal_id
                  AND jd.is_included = TRUE
                  AND d.name = '{safe}'
                  {q_cond}
            )""")
    elif quartile:
        # Standalone quartile filter — only whitelist DBs have levels
        conds.append(f"""EXISTS (
            SELECT 1 FROM journals_databases jd
            JOIN databases d ON d.db_id = jd.db_id
            WHERE jd.journal_id = i.journal_id
              AND jd.is_included = TRUE
              AND jd.quartile = {quartile}
              AND (LOWER(d.name) LIKE '%list%' OR LOWER(d.name) LIKE '%белый%')
        )""")

    where = " AND ".join(conds)
    return where, params


@router.get("", response_model=PaginatedResponse)
async def list_articles(
    search: Optional[str] = None,
    doi: Optional[str] = None,
    author_id: Optional[int] = None,
    journal_id: Optional[int] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    org_id: Optional[int] = None,
    valid_support: Optional[str] = Query(None),
    project_number: Optional[int] = None,
    dbs: Optional[List[str]] = Query(None),
    quartile: Optional[int] = Query(None, ge=1, le=4),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    where, params = _build_article_query(
        search, doi, author_id, journal_id, year_from, year_to, org_id,
        valid_support, project_number, dbs, quartile
    )

    count_sql = text(f"""
        SELECT COUNT(*)
        FROM articles a
        JOIN issues i ON i.issue_id = a.issue_id
        WHERE {where}
    """)
    total = (await db.execute(count_sql, params)).scalar()

    data_sql = text(f"""
        SELECT a.article_id, a.title, a.doi, a.edn, a.pages, a.language, a.genre, a.type,
               a.risc, a.corerisc, a.valid_support, a.project_number, a.print_date,
               a.authors_count, a.supported, a.linkurl, a.issue_id, j.title AS journal_title,
               j.journal_id, i.year
        FROM articles a
        JOIN issues i ON i.issue_id = a.issue_id
        JOIN journals j ON j.journal_id = i.journal_id
        WHERE {where}
        ORDER BY i.year DESC, a.article_id DESC
        LIMIT :limit OFFSET :skip
    """)
    params["limit"] = limit
    params["skip"] = skip

    rows = (await db.execute(data_sql, params)).fetchall()
    items = [
        ArticleOut(
            article_id=r[0], title=r[1], doi=r[2], edn=r[3], pages=r[4],
            language=r[5], genre=r[6], type=r[7], risc=r[8], corerisc=r[9],
            valid_support=r[10], project_number=r[11], print_date=r[12],
            authors_count=r[13], supported=r[14], linkurl=r[15], issue_id=r[16],
            journal_title=r[17], journal_id=r[18], year=r[19],
        )
        for r in rows
    ]
    return PaginatedResponse(total=total, items=items)


def _in_db(db_name: str) -> str:
    safe = db_name.replace("'", "''")
    # Special case: WoS can be stored as 'WoS' or old name 'Web of Science ...'
    if db_name.lower() in ('wos', 'web of science', 'web of science core collection'):
        return """(EXISTS (
        SELECT 1 FROM journals_databases jd2 JOIN databases d2 ON d2.db_id=jd2.db_id
        WHERE jd2.journal_id=i.journal_id AND jd2.is_included=TRUE
          AND (LOWER(d2.name) LIKE '%web of science%' OR LOWER(d2.name) = 'wos')
    ))"""
    return f"""(EXISTS (
        SELECT 1 FROM journals_databases jd2 JOIN databases d2 ON d2.db_id=jd2.db_id
        WHERE jd2.journal_id=i.journal_id AND jd2.is_included=TRUE AND d2.name='{safe}'
    ))"""


def _not_in_any_whitelist() -> str:
    """NOT in any database whose name matches 'Белый список %'"""
    return """NOT EXISTS (
        SELECT 1 FROM journals_databases jd3 JOIN databases d3 ON d3.db_id=jd3.db_id
        WHERE jd3.journal_id=i.journal_id AND jd3.is_included=TRUE AND d3.name LIKE 'Белый список %'
    )"""


@router.get("/vak-only")
async def vak_only_articles(
    author_id: Optional[int] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    """Articles in journals in ВАК but NOT in Scopus, WoS, or any Белый список."""
    conds = ["1=1"]
    params: dict = {}
    if author_id:
        conds.append("EXISTS (SELECT 1 FROM articles_authors aa WHERE aa.article_id=a.article_id AND aa.author_id=:author_id)")
        params["author_id"] = author_id
    if year_from:
        conds.append("(i.year >= :yf OR EXTRACT(YEAR FROM a.print_date) >= :yf)")
        params["yf"] = year_from
    if year_to:
        conds.append("(i.year <= :yt OR EXTRACT(YEAR FROM a.print_date) <= :yt)")
        params["yt"] = year_to

    extra_where = " AND ".join(conds)
    no_wl = _not_in_any_whitelist()

    sql = text(f"""
        SELECT a.article_id, a.title, a.doi, a.valid_support, i.year, j.title AS journal_title, j.journal_id
        FROM articles a
        JOIN issues i ON i.issue_id = a.issue_id
        JOIN journals j ON j.journal_id = i.journal_id
        WHERE {extra_where}
          AND {_in_db('ВАК')}
          AND NOT {_in_db('Scopus')}
          AND NOT {_in_db('wos')}
          AND {no_wl}
        ORDER BY i.year DESC
        LIMIT :limit OFFSET :skip
    """)
    count_sql = text(f"""
        SELECT COUNT(*) FROM articles a JOIN issues i ON i.issue_id = a.issue_id
        JOIN journals j ON j.journal_id = i.journal_id
        WHERE {extra_where}
          AND {_in_db('ВАК')}
          AND NOT {_in_db('Scopus')}
          AND NOT {_in_db('wos')}
          AND {no_wl}
    """)
    total = (await db.execute(count_sql, params)).scalar()
    params["limit"] = limit
    params["skip"] = skip
    rows = (await db.execute(sql, params)).fetchall()
    return {
        "total": total,
        "items": [{"article_id": r[0], "title": r[1], "doi": r[2], "valid_support": r[3],
                   "year": r[4], "journal_title": r[5], "journal_id": r[6]} for r in rows]
    }


@router.get("/not-indexed")
async def not_indexed_articles(
    author_id: Optional[int] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    """Articles NOT in ВАК, Scopus, WoS or any Белый список."""
    conds = ["1=1"]
    params: dict = {}
    if author_id:
        conds.append("EXISTS (SELECT 1 FROM articles_authors aa WHERE aa.article_id=a.article_id AND aa.author_id=:author_id)")
        params["author_id"] = author_id
    if year_from:
        conds.append("(i.year >= :yf OR EXTRACT(YEAR FROM a.print_date) >= :yf)")
        params["yf"] = year_from
    if year_to:
        conds.append("(i.year <= :yt OR EXTRACT(YEAR FROM a.print_date) <= :yt)")
        params["yt"] = year_to

    extra_where = " AND ".join(conds)
    no_wl = _not_in_any_whitelist()
    no_index = f"NOT {_in_db('ВАК')} AND NOT {_in_db('Scopus')} AND NOT {_in_db('wos')} AND {no_wl}"

    sql = text(f"""
        SELECT a.article_id, a.title, a.doi, a.valid_support, i.year, j.title AS journal_title, j.journal_id
        FROM articles a
        JOIN issues i ON i.issue_id = a.issue_id
        JOIN journals j ON j.journal_id = i.journal_id
        WHERE {extra_where} AND {no_index}
        ORDER BY i.year DESC LIMIT :limit OFFSET :skip
    """)
    count_sql = text(f"""
        SELECT COUNT(*) FROM articles a JOIN issues i ON i.issue_id=a.issue_id
        JOIN journals j ON j.journal_id=i.journal_id
        WHERE {extra_where} AND {no_index}
    """)
    total = (await db.execute(count_sql, params)).scalar()
    params["limit"] = limit
    params["skip"] = skip
    rows = (await db.execute(sql, params)).fetchall()
    return {
        "total": total,
        "items": [{"article_id": r[0], "title": r[1], "doi": r[2], "valid_support": r[3],
                   "year": r[4], "journal_title": r[5], "journal_id": r[6]} for r in rows]
    }


@router.get("/{article_id}/contribution")
async def article_contribution(
    article_id: int,
    org_id: Optional[int] = Query(None),
    whitelist_name: Optional[str] = Query(None, description="Exact whitelist DB name"),
    org_search: Optional[str] = Query(None, description="Organization name search"),
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    """Calculate contribution (%) and КБПР for organization in a publication."""
    from app.models import Organization
    # Resolve org by search string first, then by ID, then default
    if org_search:
        r = await db.execute(
            select(Organization.org_id, Organization.orgname)
            .where(Organization.orgname.ilike(f"%{org_search}%")).limit(1)
        )
        row = r.fetchone()
        if row:
            org_id = row[0]
            org_name_resolved = row[1]
        else:
            org_id = settings.DEFAULT_ORG_ID
            org_name_resolved = None
    elif org_id:
        r = await db.execute(select(Organization.org_id, Organization.orgname).where(Organization.org_id == org_id))
        row = r.fetchone()
        org_name_resolved = row[1] if row else None
    else:
        r = await db.execute(select(Organization.org_id, Organization.orgname).where(Organization.orgname.ilike("%ФИЦ ИВТ%")).limit(1))
        row = r.fetchone()
        if row:
            org_id = row[0]; org_name_resolved = row[1]
        else:
            org_id = settings.DEFAULT_ORG_ID; org_name_resolved = None

    # resolve whitelist name: use provided or fallback to latest
    if not whitelist_name:
        from sqlalchemy import select as _sel
        _r = await db.execute(_sel(Database.name).where(Database.name.ilike("%list%")).order_by(Database.name.desc()).limit(1))
        whitelist_name = _r.scalar_one_or_none() or ""
    wl_name = whitelist_name

    # Get article basic info
    article_sql = text("""
        SELECT a.article_id, a.authors_count, i.journal_id
        FROM articles a
        JOIN issues i ON i.issue_id = a.issue_id
        WHERE a.article_id = :article_id
    """)
    article_row = (await db.execute(article_sql, {"article_id": article_id})).fetchone()
    if not article_row:
        raise HTTPException(404, "Article not found")

    authors_count = article_row[1] or 0
    journal_id = article_row[2]

    # Get org contribution: sum of 1/affiliations_count for each author affiliated with org
    contrib_sql = text("""
        SELECT COALESCE(SUM(1.0 / NULLIF(aa.affiliations_count, 0)), 0) AS contrib_sum
        FROM articles_authors aa
        JOIN author_affiliations af ON af.article_author_id = aa.id
        WHERE aa.article_id = :article_id AND af.org_id = :org_id
    """)
    contrib_row = (await db.execute(contrib_sql, {"article_id": article_id, "org_id": org_id})).fetchone()
    contrib_sum = float(contrib_row[0] or 0)

    # Get whitelist quartile for the journal
    wl_sql = text("""
        SELECT jd.quartile, jd.is_included
        FROM journals_databases jd
        JOIN databases d ON d.db_id = jd.db_id
        WHERE jd.journal_id = :journal_id AND d.name = :wl_name AND jd.is_included = TRUE
        LIMIT 1
    """)
    wl_row = (await db.execute(wl_sql, {"journal_id": journal_id, "wl_name": wl_name})).fetchone()
    quartile = wl_row[0] if wl_row else 0
    wl_included = wl_row[1] if wl_row else False

    contribution = contrib_sum / authors_count if authors_count else 0
    # K coefficients: БС Q1=20, Q2=10, Q3=5, Q4=2.5; ВАК (not in БС)=0.12; else=0
    k_by_q = {1: 20.0, 2: 10.0, 3: 5.0, 4: 2.5}
    if quartile and quartile in k_by_q:
        k = k_by_q[quartile]
    else:
        # check VAK
        vak_row = await db.execute(text("""
            SELECT jd.journal_id FROM journals_databases jd
            JOIN databases d ON d.db_id = jd.db_id
            WHERE jd.journal_id = :jid AND LOWER(d.name) = 'вак' AND jd.is_included = TRUE
            LIMIT 1
        """), {"jid": journal_id})
        k = 0.12 if vak_row.fetchone() else 0.0
    kbpr = contribution * k

    # Get author details
    authors_sql = text("""
        SELECT au.author_id, au.lastname, au.firstname, au.initials,
               aa.affiliations_count, aa.num,
               ARRAY(SELECT o.orgname FROM author_affiliations af3
                     JOIN organizations o ON o.org_id = af3.org_id
                     WHERE af3.article_author_id = aa.id) AS affiliations
        FROM articles_authors aa
        JOIN authors au ON au.author_id = aa.author_id
        WHERE aa.article_id = :article_id
        ORDER BY aa.num
    """)
    author_rows = (await db.execute(authors_sql, {"article_id": article_id})).fetchall()

    return {
        "article_id": article_id,
        "org_id": org_id,
        "org_name": org_name_resolved,
        "contribution_pct": round(contribution * 100, 2),
        "kbpr": round(kbpr, 4),
        "quartile": quartile,
        "whitelist_name": wl_name,
        "authors": [
            {
                "author_id": r[0], "lastname": r[1], "firstname": r[2],
                "initials": r[3], "num": r[5],
                "affiliations_count": r[4], "affiliations": r[6]
            }
            for r in author_rows
        ]
    }
