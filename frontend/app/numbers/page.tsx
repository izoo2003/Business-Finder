"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import AppShell from "@/components/AppShell";
import { api, ApiError, downloadCsv } from "@/lib/api";
import type { PhoneDetail, PhoneFilters, PhoneRow } from "@/lib/types";

export default function NumbersPage() {
  const [filters, setFilters] = useState<PhoneFilters>({ states: [], cities: [], sources: [] });
  const [q, setQ] = useState("");
  const [state, setState] = useState("");
  const [source, setSource] = useState("");
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [rows, setRows] = useState<PhoneRow[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [previous, setPrevious] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<PhoneDetail | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (state) params.set("state", state);
    if (source) params.set("source", source);
    params.set("page", String(page));
    const text = params.toString();
    return text ? `?${text}` : "";
  }, [q, state, source, page]);

  useEffect(() => {
    api.phoneFilters().then(setFilters).catch(() => undefined);
  }, []);

  useEffect(() => {
    setError("");
    api
      .phones(query)
      .then((payload) => {
        setRows(payload.results);
        setCount(payload.count);
        setNext(payload.next);
        setPrevious(payload.previous);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load numbers.");
      });
  }, [query]);

  function onSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
  }

  async function openRow(row: PhoneRow) {
    try {
      setSelected(await api.phone(row.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open that number.");
    }
  }

  async function exportCsv() {
    try {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (state) params.set("state", state);
      if (source) params.set("source", source);
      const text = params.toString();
      await downloadCsv(text ? `?${text}` : "");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download.");
    }
  }

  return (
    <AppShell>
      <h1 className="page-title">Numbers</h1>
      <p className="lede">
        Every collected phone with the business, state, and source it came from.
        Click a row for the rest of the details.
      </p>
      {error ? <div className="banner">{error}</div> : null}

      <form className="filters" onSubmit={onSearch}>
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
          placeholder="Search business, city, or phone"
        />
        <select
          value={state}
          onChange={(e) => {
            setState(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All states</option>
          {filters.states.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
        <select
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All sources</option>
          {filters.sources.map((item) => (
            <option key={item.slug} value={item.slug}>
              {item.name}
            </option>
          ))}
        </select>
        <button className="ghost" type="button" onClick={exportCsv}>
          Download spreadsheet
        </button>
      </form>

      <p className="hint">{count} number{count === 1 ? "" : "s"}</p>

      <table className="ledger">
        <thead>
          <tr>
            <th>Phone</th>
            <th>Business</th>
            <th>State</th>
            <th>City</th>
            <th>Source</th>
            <th>Category</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={6}>No numbers yet. Start the scraper to collect some.</td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.id} onClick={() => openRow(row)}>
                <td className="phone">{row.phone}</td>
                <td>{row.business}</td>
                <td>{row.state || "—"}</td>
                <td>{row.city || "—"}</td>
                <td>{row.source}</td>
                <td>{row.category || "—"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>

      <div className="pager">
        <button className="ghost" type="button" disabled={!previous} onClick={() => setPage((p) => Math.max(1, p - 1))}>
          Previous
        </button>
        <span>Page {page}</span>
        <button className="ghost" type="button" disabled={!next} onClick={() => setPage((p) => p + 1)}>
          Next
        </button>
      </div>

      {selected ? (
        <>
          <div className="drawer-back" onClick={() => setSelected(null)} />
          <aside className="drawer">
            <h2 className="phone">{selected.phone}</h2>
            <dl className="dl">
              <dt>Business</dt>
              <dd>{selected.business}</dd>
              <dt>Address</dt>
              <dd>
                {[selected.address, selected.city, selected.state, selected.postal_code]
                  .filter(Boolean)
                  .join(", ") || "—"}
              </dd>
              <dt>State</dt>
              <dd>{selected.state || "—"}</dd>
              <dt>Source</dt>
              <dd>{selected.source}</dd>
              <dt>Category</dt>
              <dd>{selected.category || "—"}</dd>
              <dt>Line type</dt>
              <dd>{selected.line_type || "Not checked yet"}</dd>
              <dt>First seen</dt>
              <dd>{selected.first_seen_at ? new Date(selected.first_seen_at).toLocaleString() : "—"}</dd>
              <dt>Last seen</dt>
              <dd>{selected.last_seen_at ? new Date(selected.last_seen_at).toLocaleString() : "—"}</dd>
              {selected.source_url ? (
                <>
                  <dt>Listing</dt>
                  <dd>
                    <a href={selected.source_url} target="_blank" rel="noreferrer">
                      Open original
                    </a>
                  </dd>
                </>
              ) : null}
            </dl>
            <button className="ghost" type="button" style={{ marginTop: 20 }} onClick={() => setSelected(null)}>
              Close
            </button>
          </aside>
        </>
      ) : null}
    </AppShell>
  );
}
