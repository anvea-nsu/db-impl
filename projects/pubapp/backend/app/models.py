from sqlalchemy import (
    Column, Integer, SmallInteger, String, Text, Boolean, Float,
    Date, ForeignKey, UniqueConstraint, CheckConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


# ── App Users (not in original schema) ──────────────────────────────────────

class AppUser(Base):
    __tablename__ = "app_users"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), nullable=True)          # display name, NOT unique
    email = Column(String(320), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # admin / user
    is_active = Column(Boolean, default=True)


# ── Reference tables ─────────────────────────────────────────────────────────

class Language(Base):
    __tablename__ = "languages"
    lang_id = Column(String(2), primary_key=True)
    name = Column(String(100), nullable=False)


class Country(Base):
    __tablename__ = "countries"
    country_id = Column(String(3), primary_key=True)
    name = Column(String(100), nullable=False)


class City(Base):
    __tablename__ = "cities"
    city_id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    country_id = Column(String(3), ForeignKey("countries.country_id", deferrable=True, initially="IMMEDIATE"))


class Database(Base):
    __tablename__ = "databases"
    db_id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False, unique=True)
    website = Column(String(500), unique=True)
    quartile_prefix = Column(String(10))


# ── Organizations ─────────────────────────────────────────────────────────────

class Organization(Base):
    __tablename__ = "organizations"
    org_id = Column(Integer, primary_key=True)
    orgname = Column(String(500), unique=True)
    country_id = Column(String(3), ForeignKey("countries.country_id", deferrable=True, initially="IMMEDIATE"))
    city_id = Column(Integer, ForeignKey("cities.city_id", deferrable=True, initially="IMMEDIATE"))

    names = relationship("OrganizationName", back_populates="organization", lazy="selectin")
    country = relationship("Country")
    city = relationship("City")


class OrganizationName(Base):
    __tablename__ = "organization_names"
    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.org_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    name = Column(String(500), nullable=False)
    lang = Column(String(2), ForeignKey("languages.lang_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    type = Column(String(100))
    organization = relationship("Organization", back_populates="names")
    __table_args__ = (UniqueConstraint("org_id", "name"),)


class OrganizationDatabase(Base):
    __tablename__ = "organizations_databases"
    id = Column(Integer, primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.org_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_id = Column(Integer, ForeignKey("databases.db_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_org_id = Column(String(50), nullable=False)
    __table_args__ = (
        UniqueConstraint("org_id", "db_id"),
        UniqueConstraint("db_id", "db_org_id"),
    )


# ── Journals ──────────────────────────────────────────────────────────────────

class Journal(Base):
    __tablename__ = "journals"
    journal_id = Column(Integer, primary_key=True)
    title = Column(String(500), nullable=False)
    issn = Column(String(20), unique=True)
    eissn = Column(String(20), unique=True)
    publisher_org_id = Column(Integer, ForeignKey("organizations.org_id", deferrable=True, initially="IMMEDIATE"))
    lang = Column(String(2), ForeignKey("languages.lang_id", deferrable=True, initially="IMMEDIATE"))
    website = Column(String(500))
    doi_prefix = Column(String(100), unique=True)
    translated_journal_id = Column(Integer, ForeignKey("journals.journal_id", deferrable=True, initially="DEFERRED"), unique=True)

    titles = relationship("JournalTitle", back_populates="journal", lazy="selectin")


class JournalTitle(Base):
    __tablename__ = "journal_titles"
    title_id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.journal_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    lang = Column(String(2), ForeignKey("languages.lang_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    title_text = Column(Text, nullable=False)
    journal = relationship("Journal", back_populates="titles")
    __table_args__ = (
        UniqueConstraint("journal_id", "lang"),
        UniqueConstraint("journal_id", "title_text"),
    )


class JournalDatabase(Base):
    __tablename__ = "journals_databases"
    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.journal_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_id = Column(Integer, ForeignKey("databases.db_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    year = Column(SmallInteger, nullable=False)
    is_included = Column(Boolean, nullable=False)
    quartile = Column(SmallInteger)
    if_value = Column(Float)
    percentile = Column(Float)
    __table_args__ = (UniqueConstraint("journal_id", "db_id", "year"),)


class JournalDatabaseId(Base):
    __tablename__ = "journal_database_ids"
    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.journal_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_id = Column(Integer, ForeignKey("databases.db_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_journal_id = Column(String(50), nullable=False)
    __table_args__ = (UniqueConstraint("db_id", "db_journal_id"),)


# ── Issues ────────────────────────────────────────────────────────────────────

class Issue(Base):
    __tablename__ = "issues"
    issue_id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.journal_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    year = Column(SmallInteger, nullable=False)
    volume = Column(SmallInteger)
    number = Column(String(20))
    contnumber = Column(Integer)
    __table_args__ = (UniqueConstraint("journal_id", "year", "volume", "number"),)


# ── Articles ──────────────────────────────────────────────────────────────────

class Article(Base):
    __tablename__ = "articles"
    article_id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("issues.issue_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    title = Column(Text, nullable=False)
    linkurl = Column(Text)
    genre = Column(String(100))
    type = Column(String(100))
    pages = Column(String(30))
    language = Column(String(2), ForeignKey("languages.lang_id", deferrable=True, initially="IMMEDIATE"))
    doi = Column(String(100), unique=True)
    edn = Column(String(20), unique=True)
    grnti = Column(String(20))
    risc = Column(Boolean)
    corerisc = Column(Boolean)
    citation = Column(Text, unique=True)
    supported = Column(Text)
    valid_support = Column(Boolean)
    project_number = Column(SmallInteger)
    print_date = Column(Date)
    received_date = Column(Date)
    authors_count = Column(SmallInteger)
    translated_article_id = Column(Integer, ForeignKey("articles.article_id", deferrable=True, initially="DEFERRED"), unique=True)
    __table_args__ = (
        UniqueConstraint("issue_id", "title"),
        CheckConstraint("project_number BETWEEN 1 AND 100"),
        CheckConstraint("authors_count > 0"),
    )


class ArticleTitle(Base):
    __tablename__ = "article_titles"
    title_id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.article_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    lang = Column(String(2), ForeignKey("languages.lang_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    title_text = Column(Text, nullable=False)
    __table_args__ = (UniqueConstraint("article_id", "lang"),)


class ArticleDatabase(Base):
    __tablename__ = "articles_databases"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.article_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_id = Column(Integer, ForeignKey("databases.db_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_article_id = Column(String(50), nullable=False)
    __table_args__ = (
        UniqueConstraint("article_id", "db_id"),
        UniqueConstraint("db_id", "db_article_id"),
    )


# ── Authors ───────────────────────────────────────────────────────────────────

class Author(Base):
    __tablename__ = "authors"
    author_id = Column(Integer, primary_key=True)
    firstname = Column(String(32))
    middlename = Column(String(32))
    lastname = Column(String(32), nullable=False)
    initials = Column(String(10))
    email = Column(String(320))
    general_org_id = Column(Integer, ForeignKey("organizations.org_id", deferrable=True, initially="IMMEDIATE"))

    names = relationship("AuthorName", back_populates="author", lazy="selectin")


class AuthorName(Base):
    __tablename__ = "author_names"
    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("authors.author_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    lang = Column(String(2), ForeignKey("languages.lang_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    firstname = Column(String(32))
    middlename = Column(String(32))
    lastname = Column(String(32), nullable=False)
    initials = Column(String(10))
    author = relationship("Author", back_populates="names")
    __table_args__ = (UniqueConstraint("author_id", "lang"),)


class ArticleAuthor(Base):
    __tablename__ = "articles_authors"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.article_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    author_id = Column(Integer, ForeignKey("authors.author_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    num = Column(SmallInteger)
    aboutauthor = Column(String(300))
    affiliations_count = Column(SmallInteger)
    __table_args__ = (
        UniqueConstraint("article_id", "author_id"),
        UniqueConstraint("article_id", "num"),
        CheckConstraint("num > 0"),
        CheckConstraint("affiliations_count > 0"),
    )


class AuthorAffiliation(Base):
    __tablename__ = "author_affiliations"
    id = Column(Integer, primary_key=True)
    article_author_id = Column(Integer, ForeignKey("articles_authors.id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    org_id = Column(Integer, ForeignKey("organizations.org_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    num = Column(SmallInteger)
    affiliation_as_given = Column(String(500))
    __table_args__ = (
        UniqueConstraint("article_author_id", "org_id"),
        UniqueConstraint("article_author_id", "num"),
    )


class AuthorDatabase(Base):
    __tablename__ = "authors_databases"
    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("authors.author_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_id = Column(Integer, ForeignKey("databases.db_id", deferrable=True, initially="IMMEDIATE"), nullable=False)
    db_author_id = Column(String(50), nullable=False)
    __table_args__ = (
        UniqueConstraint("author_id", "db_id"),
        UniqueConstraint("db_id", "db_author_id"),
    )
