from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text
from app.database import get_db
from app.models import Journal, JournalTitle, JournalDatabase, Database, AppUser
from app.schemas import JournalOut, JournalTitleOut, JournalDBEntry, PaginatedResponse
from app.auth import get_optional_user
from typing import Optional, List

router = APIRouter(prefix="/api/journals", tags=["journals"])


async def enrich_journal(journal: Journal, db: AsyncSession) -> JournalOut:
    db_rows = await db.execute(
        select(JournalDatabase, Database.name)
        .join(Database, Database.db_id == JournalDatabase.db_id)
        .where(JournalDatabase.journal_id == journal.journal_id)
        .order_by(Database.name, JournalDatabase.year.desc())
    )
    db_entries = [
        JournalDBEntry(
            db_name=row[1],
            year=row[0].year,
            is_included=row[0].is_included,
            quartile=row[0].quartile,
            if_value=row[0].if_value,
        )
        for row in db_rows.all()
    ]
    out = JournalOut.model_validate(journal)
    out.databases = db_entries
    return out


@router.get("/available-dbs")
async def available_dbs(db: AsyncSession = Depends(get_db)):
    """Return all distinct database names that have at least one journal entry."""
    rows = await db.execute(
        select(Database.db_id, Database.name)
        .join(JournalDatabase, JournalDatabase.db_id == Database.db_id)
        .where(JournalDatabase.is_included == True)
        .distinct()
        .order_by(Database.name)
    )
    return [{"db_id": r[0], "name": r[1]} for r in rows.all()]


@router.get("", response_model=PaginatedResponse)
async def list_journals(
    search: Optional[str] = Query(None),
    dbs: Optional[List[str]] = Query(None, description="Filter by DB names (exact match, AND logic)"),
    quartile: Optional[int] = Query(None, ge=1, le=4),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    query = select(Journal).distinct()

    if search:
        sl = f"%{search.lower()}%"
        query = query.outerjoin(JournalTitle, JournalTitle.journal_id == Journal.journal_id)
        query = query.where(
            or_(
                func.lower(Journal.title).like(sl),
                func.lower(JournalTitle.title_text).like(sl),
                func.lower(Journal.issn).like(sl),
                func.lower(Journal.eissn).like(sl),
            )
        )

    # Filter by DB intersection (AND logic) — dbs contains exact DB names
    if dbs:
        for db_name in dbs:
            subq = (
                select(JournalDatabase.journal_id)
                .join(Database, Database.db_id == JournalDatabase.db_id)
                .where(Database.name == db_name, JournalDatabase.is_included == True)
            )
            # Apply quartile filter ONLY to whitelist DBs — other DBs don't have levels
            is_whitelist = bool(__import__('re').search(r'белый список|white\s*list', db_name, __import__('re').IGNORECASE))
            if quartile and is_whitelist:
                subq = subq.where(JournalDatabase.quartile == quartile)
            query = query.where(Journal.journal_id.in_(subq))
    elif quartile:
        # Standalone quartile filter — only in whitelist DBs
        from sqlalchemy import func as _func
        subq = (
            select(JournalDatabase.journal_id)
            .join(Database, Database.db_id == JournalDatabase.db_id)
            .where(
                JournalDatabase.is_included == True,
                JournalDatabase.quartile == quartile,
                Database.name.ilike('%list%'),
            )
        )
        query = query.where(Journal.journal_id.in_(subq))

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    journals = (await db.execute(query.offset(skip).limit(limit))).scalars().all()
    items = [await enrich_journal(j, db) for j in journals]

    return PaginatedResponse(total=total, items=items)


@router.get("/top10", response_model=List[dict])
async def top10_journals(
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    filters = ""
    params: dict = {}
    if year_from:
        filters += " AND i.year >= :year_from"
        params["year_from"] = year_from
    if year_to:
        filters += " AND i.year <= :year_to"
        params["year_to"] = year_to

    sql = text(f"""
        SELECT j.journal_id, j.title, j.issn, j.eissn,
               COUNT(a.article_id) AS article_count
        FROM journals j
        JOIN issues i ON i.journal_id = j.journal_id
        JOIN articles a ON a.issue_id = i.issue_id
        WHERE 1=1 {filters}
        GROUP BY j.journal_id, j.title, j.issn, j.eissn
        ORDER BY article_count DESC
        LIMIT 10
    """)
    rows = (await db.execute(sql, params)).fetchall()
    return [
        {"journal_id": r[0], "title": r[1], "issn": r[2], "eissn": r[3], "article_count": r[4]}
        for r in rows
    ]


@router.get("/{journal_id}", response_model=JournalOut)
async def get_journal(
    journal_id: int,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    result = await db.execute(select(Journal).where(Journal.journal_id == journal_id))
    journal = result.scalar_one_or_none()
    if not journal:
        raise HTTPException(404, "Journal not found")
    return await enrich_journal(journal, db)
