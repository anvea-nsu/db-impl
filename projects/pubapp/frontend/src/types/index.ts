export interface Paginated<T> {
  total: number;
  items: T[];
}

export interface OrgName { id: number; name: string; lang: string; type?: string }
export interface Organization { org_id: number; orgname?: string; country_id?: string; city_id?: number; names: OrgName[] }

export interface JournalTitle { title_id: number; lang: string; title_text: string }
export interface JournalDBEntry { db_name: string; year: number; is_included: boolean; quartile?: number; if_value?: number }
export interface Journal {
  journal_id: number; title: string; issn?: string; eissn?: string;
  website?: string; doi_prefix?: string; titles: JournalTitle[]; databases: JournalDBEntry[];
  article_count?: number;
}

export interface AuthorName { id: number; lang: string; firstname?: string; middlename?: string; lastname: string; initials?: string }
export interface Author {
  author_id: number; firstname?: string; middlename?: string; lastname: string;
  initials?: string; email?: string; general_org_id?: number; names: AuthorName[];
}

export interface AuthorActivityStats {
  author_id: number; lastname: string; firstname?: string; middlename?: string; initials?: string;
  total: number; wos: number; scopus: number; vak: number;
  whitelist_2023: number; whitelist_2025: number; risc: number;
  q1: number; q2: number; q3: number; q4: number;
}

export interface AuthorKBPR {
  author_id: number; org_id: number; org_name?: string; kbpr: number; article_count: number;
}

export interface Article {
  article_id: number; title: string; doi?: string; edn?: string; pages?: string;
  language?: string; genre?: string; type?: string; risc?: boolean; corerisc?: boolean;
  valid_support?: boolean; project_number?: number; print_date?: string;
  authors_count?: number; supported?: string; linkurl?: string; issue_id: number;
  journal_title?: string; journal_id?: number; year?: number;
}

export interface PublicationStats {
  total: number; wos: number; scopus: number; vak: number;
  whitelist_2023: number; whitelist_2025: number; risc: number;
  q1: number; q2: number; q3: number; q4: number; total_kbpr: number;
}

export interface ImportResult {
  success: boolean; message: string; log_output: string;
  inserted?: number; updated?: number; errors?: number;
}
