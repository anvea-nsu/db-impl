from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, text
from app.database import get_db
from app.models import Organization, OrganizationName
from app.schemas import OrganizationOut, OrganizationCreate, PaginatedResponse
from app.auth import get_optional_user
from app.models import AppUser
from typing import Optional

router = APIRouter(prefix="/api/organizations", tags=["organizations"])


@router.get("", response_model=PaginatedResponse)
async def list_organizations(
    search: Optional[str] = Query(None, description="Search by any name"),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _: Optional[AppUser] = Depends(get_optional_user),
):
    query = select(Organization).distinct()

    if search:
        search_lower = f"%{search.lower()}%"
        query = query.outerjoin(OrganizationName, OrganizationName.org_id == Organization.org_id)
        query = query.where(
            or_(
                func.lower(Organization.orgname).like(search_lower),
                func.lower(OrganizationName.name).like(search_lower),
            )
        )

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()

    result = await db.execute(query.offset(skip).limit(limit))
    orgs = result.scalars().all()

    return PaginatedResponse(total=total, items=[OrganizationOut.model_validate(o) for o in orgs])


@router.get("/{org_id}", response_model=OrganizationOut)
async def get_organization(org_id: int, db: AsyncSession = Depends(get_db), _: Optional[AppUser] = Depends(get_optional_user)):
    result = await db.execute(select(Organization).where(Organization.org_id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        from fastapi import HTTPException
        raise HTTPException(404, "Organization not found")
    return OrganizationOut.model_validate(org)
