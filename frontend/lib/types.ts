export type User = {
  id: number;
  username: string;
  is_staff: boolean;
};

export type ScraperRun = {
  id: number | null;
  status: string;
  source: string | null;
  source_slug: string | null;
  city: string;
  category: string;
  saved: number;
  updated: number;
  fetched: number;
  error: string;
  started_at: string | null;
  finished_at: string | null;
  in_progress: boolean;
};

export type ScraperStatus = {
  running: boolean;
  worker_online: boolean;
  redis_online: boolean;
  session_started_at: string | null;
  session_saved: number;
  session_updated: number;
  last_error: string;
  cities: string[];
  categories: string[];
  next_city: string;
  next_category: string;
  current: ScraperRun | null;
  recent_runs: ScraperRun[];
  detail?: string;
};

export type PhoneRow = {
  id: number;
  phone: string;
  e164: string;
  business: string;
  city: string;
  state: string;
  category: string;
  source: string;
  source_slug: string;
  line_type: string;
  last_seen_at: string | null;
};

export type PhoneDetail = PhoneRow & {
  address: string;
  postal_code: string;
  area_code: string;
  raw_phone: string;
  source_url: string;
  source_query: string;
  validation: string;
  enrichment: string;
  carrier: string;
  risk_level: string;
  geography: string;
  first_seen_at: string | null;
  enriched_at: string | null;
};

export type PhonePage = {
  count: number;
  next: string | null;
  previous: string | null;
  results: PhoneRow[];
};

export type PhoneFilters = {
  states: string[];
  cities: string[];
  sources: { slug: string; name: string }[];
};

export type UsageSource = {
  slug: string;
  name: string;
  is_active: boolean;
  quota_status: string;
  quota_status_label: string;
  remaining: number | null;
  max: number | null;
  usable: number | null;
  used_percent: number | null;
  window_label: string;
  reset_at: string | null;
  last_successful_run_at: string | null;
  plain_english: string;
  needs_key: boolean;
  has_key: boolean;
  key_origin: string;
  key_hint: string;
};

export type Alert = {
  level: "error" | "warning";
  title: string;
  detail: string;
  href: string;
  slug: string | null;
};

export type UsagePayload = {
  phone_total: number;
  harvest_24h: { saved: number; failed: number; total: number };
  harvest_7d: { saved: number; failed: number; total: number };
  sources: UsageSource[];
  alerts: Alert[];
};

export type KeyCard = {
  slug: string;
  name: string;
  needs_key: boolean;
  has_key: boolean;
  connected: boolean;
  connection_label: string;
  key_origin: string;
  key_hint: string;
  is_active: boolean;
  quota_status: string;
  quota_status_label: string;
  plain_english: string;
  signup_url: string;
  steps: string[];
  warning: string;
  reset_at: string | null;
  verified?: boolean;
  message?: string;
};
