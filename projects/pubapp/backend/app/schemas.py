from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import date


# ── Auth ─────────────────────────────────────────────────────────────────────

class UserRegister(BaseModel):
    username: Optional[str] = None   # display name, optional, not unique
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


# ── Generic ──────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    items: List[Any]


# ── Organizations ─────────────────────────────────────────────────────────────

class OrganizationNameOut(BaseModel):
    id: int
    name: str
    lang: str
    type: Optional[str]

    class Config:
        from_attributes = True


class OrganizationOut(BaseModel):
    org_id: int
    orgname: Optional[str]
    country_id: Optional[str]
    city_id: Optional[int]
    names: List[OrganizationNameOut] = []

    class Config:
        from_attributes = True


class OrganizationCreate(BaseModel):
    orgname: Optional[str]
    country_id: Optional[str]
    city_id: Optional[int]


# ── Journals ──────────────────────────────────────────────────────────────────

class JournalTitleOut(BaseModel):
    title_id: int
    lang: str
    title_text: str

    class Config:
        from_attributes = True


class JournalDBEntry(BaseModel):
    db_name: str
    year: int
    is_included: bool
    quartile: Optional[int]
    if_value: Optional[float]


class JournalOut(BaseModel):
    journal_id: int
    title: str
    issn: Optional[str]
    eissn: Optional[str]
    website: Optional[str]
    doi_prefix: Optional[str]
    titles: List[JournalTitleOut] = []
    databases: List[JournalDBEntry] = []
    article_count: Optional[int] = None

    class Config:
        from_attributes = True


class JournalCreate(BaseModel):
    title: str
    issn: Optional[str]
    eissn: Optional[str]
    publisher_org_id: Optional[int]
    lang: Optional[str]
    website: Optional[str]
    doi_prefix: Optional[str]


# ── Authors ───────────────────────────────────────────────────────────────────

class AuthorNameOut(BaseModel):
    id: int
    lang: str
    firstname: Optional[str]
    middlename: Optional[str]
    lastname: str
    initials: Optional[str]

    class Config:
        from_attributes = True


class AuthorOut(BaseModel):
    author_id: int
    firstname: Optional[str]
    middlename: Optional[str]
    lastname: str
    initials: Optional[str]
    email: Optional[str]
    general_org_id: Optional[int]
    names: List[AuthorNameOut] = []

    class Config:
        from_attributes = True


class AuthorCreate(BaseModel):
    firstname: Optional[str]
    middlename: Optional[str]
    lastname: str
    initials: Optional[str]
    email: Optional[str]
    general_org_id: Optional[int]


class AuthorActivityStats(BaseModel):
    author_id: int
    lastname: str
    firstname: Optional[str]
    middlename: Optional[str]
    initials: Optional[str]
    total: int
    wos: int
    scopus: int
    vak: int
    whitelist_2023: int
    whitelist_2025: int
    risc: int
    q1: int
    q2: int
    q3: int
    q4: int


class AuthorKBPR(BaseModel):
    author_id: int
    org_id: int
    org_name: Optional[str]
    kbpr: float
    article_count: int


# ── Articles ──────────────────────────────────────────────────────────────────

class ArticleOut(BaseModel):
    article_id: int
    title: str
    doi: Optional[str]
    edn: Optional[str]
    pages: Optional[str]
    language: Optional[str]
    genre: Optional[str]
    type: Optional[str]
    risc: Optional[bool]
    corerisc: Optional[bool]
    valid_support: Optional[bool]
    project_number: Optional[int]
    print_date: Optional[date]
    authors_count: Optional[int]
    supported: Optional[str]
    linkurl: Optional[str]
    issue_id: int
    journal_title: Optional[str] = None
    journal_id: Optional[int] = None
    year: Optional[int] = None

    class Config:
        from_attributes = True


class ArticleCreate(BaseModel):
    issue_id: int
    title: str
    linkurl: Optional[str]
    genre: Optional[str]
    type: Optional[str]
    pages: Optional[str]
    language: Optional[str]
    doi: Optional[str]
    edn: Optional[str]
    grnti: Optional[str]
    risc: Optional[bool]
    corerisc: Optional[bool]
    supported: Optional[str]
    valid_support: Optional[bool]
    project_number: Optional[int]
    print_date: Optional[date]
    received_date: Optional[date]
    authors_count: Optional[int]


class ArticleContribution(BaseModel):
    article_id: int
    title: str
    org_contribution: float
    kbpr: float


# ── Statistics ────────────────────────────────────────────────────────────────

class PublicationStats(BaseModel):
    total: int
    wos: int
    scopus: int
    vak: int
    whitelist_2023: int
    whitelist_2025: int
    risc: int
    q1: int
    q2: int
    q3: int
    q4: int
    total_kbpr: float


# ── Import ────────────────────────────────────────────────────────────────────

class ImportResult(BaseModel):
    success: bool
    message: str
    log_output: str
    inserted: Optional[int] = None
    updated: Optional[int] = None
    errors: Optional[int] = None
