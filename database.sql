CREATE TABLE languages (
  lang_id  char(2)      PRIMARY KEY,
  name     varchar(100) NOT NULL
);

CREATE TABLE countries (
  country_id  char(3)      PRIMARY KEY,
  name        varchar(100) NOT NULL
);

CREATE TABLE databases (
  db_id            SERIAL       PRIMARY KEY,
  name             varchar(200) NOT NULL UNIQUE,
  website          varchar(500) UNIQUE,
  quartile_prefix  varchar(10)
);

CREATE TABLE cities (
  city_id     SERIAL       PRIMARY KEY,
  name        varchar(100) NOT NULL,
  country_id  char(3)      REFERENCES countries (country_id) DEFERRABLE INITIALLY IMMEDIATE
);

CREATE TABLE organizations (
  org_id      SERIAL       PRIMARY KEY,
  orgname     varchar(500) UNIQUE,
  country_id  char(3)      REFERENCES countries (country_id) DEFERRABLE INITIALLY IMMEDIATE,
  city_id     integer      REFERENCES cities    (city_id)    DEFERRABLE INITIALLY IMMEDIATE
);

CREATE TABLE organization_names (
  id      SERIAL       PRIMARY KEY,
  org_id  integer      NOT NULL REFERENCES organizations (org_id) DEFERRABLE INITIALLY IMMEDIATE,
  name    varchar(500) NOT NULL,
  lang    char(2)      NOT NULL REFERENCES languages     (lang_id) DEFERRABLE INITIALLY IMMEDIATE,
  type    varchar(100),

  UNIQUE (org_id, name)
);

CREATE TABLE organizations_databases (
  id         SERIAL      PRIMARY KEY,
  org_id     integer     NOT NULL REFERENCES organizations (org_id) DEFERRABLE INITIALLY IMMEDIATE,
  db_id      integer     NOT NULL REFERENCES databases     (db_id)  DEFERRABLE INITIALLY IMMEDIATE,
  db_org_id  varchar(50) NOT NULL,

  UNIQUE (org_id, db_id),
  UNIQUE (db_id, db_org_id)
);

CREATE TABLE journals (
  journal_id             SERIAL       PRIMARY KEY,
  title                  varchar(500) NOT NULL,
  issn                   varchar(20)  UNIQUE,
  eissn                  varchar(20)  UNIQUE,
  publisher_org_id       integer      REFERENCES organizations (org_id)  DEFERRABLE INITIALLY IMMEDIATE,
  lang                   char(2)      REFERENCES languages     (lang_id) DEFERRABLE INITIALLY IMMEDIATE,
  website                varchar(500),
  doi_prefix             varchar(100) UNIQUE,
  translated_journal_id  integer      UNIQUE REFERENCES journals (journal_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE journal_titles (
  title_id    SERIAL   PRIMARY KEY,
  journal_id  integer  NOT NULL REFERENCES journals  (journal_id) DEFERRABLE INITIALLY IMMEDIATE,
  lang        char(2)  NOT NULL REFERENCES languages (lang_id)    DEFERRABLE INITIALLY IMMEDIATE,
  title_text  text     NOT NULL,

  UNIQUE (journal_id, lang),
  UNIQUE (journal_id, title_text)
);

CREATE TABLE journals_databases (
  id          SERIAL    PRIMARY KEY,
  journal_id  integer   NOT NULL REFERENCES journals  (journal_id) DEFERRABLE INITIALLY IMMEDIATE,
  db_id       integer   NOT NULL REFERENCES databases (db_id)      DEFERRABLE INITIALLY IMMEDIATE,
  year        smallint  NOT NULL,
  is_included boolean   NOT NULL,
  quartile    smallint,
  if_value    float     CHECK (if_value  >= 0),
  percentile  float     CHECK (percentile >= 0),

  UNIQUE (journal_id, db_id, year)
);

CREATE TABLE journal_database_ids (
  id             SERIAL      PRIMARY KEY,
  journal_id     integer     NOT NULL REFERENCES journals  (journal_id) DEFERRABLE INITIALLY IMMEDIATE,
  db_id          integer     NOT NULL REFERENCES databases (db_id)      DEFERRABLE INITIALLY IMMEDIATE,
  db_journal_id  varchar(50) NOT NULL,

  -- UNIQUE (journal_id, db_id),
  UNIQUE (db_id, db_journal_id)
);

CREATE TABLE issues (
  issue_id    SERIAL      PRIMARY KEY,
  journal_id  integer     NOT NULL REFERENCES journals (journal_id) DEFERRABLE INITIALLY IMMEDIATE,
  year        smallint    NOT NULL,
  volume      smallint,
  number      varchar(20),
  contnumber  integer,

  UNIQUE (journal_id, year, volume, number)
);

CREATE TABLE articles (
  article_id             SERIAL      PRIMARY KEY,
  issue_id               integer     NOT NULL REFERENCES issues    (issue_id)   DEFERRABLE INITIALLY IMMEDIATE,
  title                  text        NOT NULL,
  linkurl                text,
  genre                  varchar(100),
  type                   varchar(100),
  pages                  varchar(30),
  language               char(2)     REFERENCES languages (lang_id) DEFERRABLE INITIALLY IMMEDIATE,
  doi                    varchar(100) UNIQUE,
  edn                    varchar(20)  UNIQUE,
  grnti                  varchar(20),
  risc                   boolean,
  corerisc               boolean,
  citation               text         UNIQUE,
  supported              text,
  valid_support          boolean,
  project_number         smallint     CHECK (project_number BETWEEN 1 AND 100),
  print_date             date,
  received_date          date,
  authors_count          smallint     CHECK (authors_count > 0),
  translated_article_id  integer      UNIQUE REFERENCES articles (article_id) DEFERRABLE INITIALLY DEFERRED,

  UNIQUE (issue_id, title)
);

CREATE TABLE articles_databases (
  id             SERIAL      PRIMARY KEY,
  article_id     integer     NOT NULL REFERENCES articles  (article_id) DEFERRABLE INITIALLY IMMEDIATE,
  db_id          integer     NOT NULL REFERENCES databases (db_id)      DEFERRABLE INITIALLY IMMEDIATE,
  db_article_id  varchar(50) NOT NULL,

  UNIQUE (article_id, db_id),
  UNIQUE (db_id, db_article_id)
);

CREATE TABLE article_titles (
  title_id    SERIAL   PRIMARY KEY,
  article_id  integer  NOT NULL REFERENCES articles  (article_id) DEFERRABLE INITIALLY IMMEDIATE,
  lang        char(2)  NOT NULL REFERENCES languages (lang_id)    DEFERRABLE INITIALLY IMMEDIATE,
  title_text  text     NOT NULL,

  UNIQUE (article_id, lang)
);

CREATE TABLE authors (
  author_id       SERIAL       PRIMARY KEY,
  firstname       varchar(32),
  middlename      varchar(32),
  lastname        varchar(32)  NOT NULL,
  initials        varchar(10),
  email           varchar(320),
  general_org_id  integer      REFERENCES organizations (org_id) DEFERRABLE INITIALLY IMMEDIATE
);

CREATE TABLE author_names (
  id          SERIAL      PRIMARY KEY,
  author_id   integer     NOT NULL REFERENCES authors   (author_id) DEFERRABLE INITIALLY IMMEDIATE,
  lang        char(2)     NOT NULL REFERENCES languages (lang_id)   DEFERRABLE INITIALLY IMMEDIATE,
  firstname   varchar(32),
  middlename  varchar(32),
  lastname    varchar(32) NOT NULL,
  initials    varchar(10),

  UNIQUE (author_id, lang)
);

CREATE TABLE articles_authors (
  id                  SERIAL    PRIMARY KEY,
  article_id          integer   NOT NULL REFERENCES articles (article_id) DEFERRABLE INITIALLY IMMEDIATE,
  author_id           integer   NOT NULL REFERENCES authors  (author_id)  DEFERRABLE INITIALLY IMMEDIATE,
  num                 smallint  CHECK (num > 0),
  aboutauthor         varchar(300),
  affiliations_count  smallint  CHECK (affiliations_count > 0),

  UNIQUE (article_id, author_id),
  UNIQUE (article_id, num)
);

CREATE TABLE author_affiliations (
  id                   SERIAL       PRIMARY KEY,
  article_author_id    integer      NOT NULL REFERENCES articles_authors (id)     DEFERRABLE INITIALLY IMMEDIATE,
  org_id               integer      NOT NULL REFERENCES organizations    (org_id)  DEFERRABLE INITIALLY IMMEDIATE,
  num                  smallint     CHECK (num > 0),
  affiliation_as_given varchar(500),

  UNIQUE (article_author_id, org_id),
  UNIQUE (article_author_id, num)
);

CREATE TABLE authors_databases (
  id            SERIAL      PRIMARY KEY,
  author_id     integer     NOT NULL REFERENCES authors   (author_id) DEFERRABLE INITIALLY IMMEDIATE,
  db_id         integer     NOT NULL REFERENCES databases (db_id)     DEFERRABLE INITIALLY IMMEDIATE,
  db_author_id  varchar(50) NOT NULL,

  UNIQUE (author_id, db_id),
  UNIQUE (db_id, db_author_id)
);



INSERT INTO languages (lang_id, name) VALUES
  ('en', 'English'),
  ('ru', 'Russian'),
  ('de', 'German'),
  ('fr', 'French'),
  ('es', 'Spanish'),
  ('zh', 'Chinese'),
  ('ja', 'Japanese'),
  ('pt', 'Portuguese'),
  ('it', 'Italian'),
  ('pl', 'Polish');
