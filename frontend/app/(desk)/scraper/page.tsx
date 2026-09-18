"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { startVisiblePoll } from "@/lib/polling";
import type { Alert, ScraperStatus } from "@/lib/types";

function formatWhen(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function ChipList({
  label,
  items,
  draft,
  placeholder,
  onDraftChange,
  onAdd,
  onRemove,
}: {
  label: string;
  items: string[];
  draft: string;
  placeholder: string;
  onDraftChange: (value: string) => void;
  onAdd: () => void;
  onRemove: (value: string) => void;
}) {
  return (
    <div className="filter-block">
      <h3>{label}</h3>
      <div className="chips">
        {items.length === 0 ? <span className="hint">None yet</span> : null}
        {items.map((item) => (
          <span className="chip" key={item}>
            {item}
            <button type="button" aria-label={`Remove ${item}`} onClick={() => onRemove(item)}>
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="key-row">
        <input
          type="text"
          value={draft}
          placeholder={placeholder}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              onAdd();
            }
          }}
        />
        <button type="button" className="save" onClick={onAdd}>
          Add
        </button>
      </div>
    </div>
  );
}

export default function ScraperPage() {
  const [status, setStatus] = useState<ScraperStatus | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [savingFilters, setSavingFilters] = useState(false);
  const [filterMessage, setFilterMessage] = useState("");
  const [cities, setCities] = useState<string[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [cityDraft, setCityDraft] = useState("");
  const [categoryDraft, setCategoryDraft] = useState("");
  const dirtyRef = useRef(false);
  const runningRef = useRef(false);
  const alertAtRef = useRef(0);

  const applyStatus = useCallback((next: ScraperStatus, forceFilters = false) => {
    setStatus(next);
    runningRef.current = Boolean(next.running);
    if (forceFilters || !dirtyRef.current) {
      setCities(next.cities || []);
      setCategories(next.categories || []);
    }
  }, []);

  useEffect(() => {
    let first = true;
    return startVisiblePoll(
      async () => {
        try {
          const next = await api.scraperStatus();
          applyStatus(next);
          const now = Date.now();
          if (first || now - alertAtRef.current > 45_000) {
            const alertPayload = await api.alerts();
            setAlerts(alertPayload.alerts);
            alertAtRef.current = now;
          }
          if (first) first = false;
        } catch (err) {
          if (first) {
            setError(
              err instanceof ApiError ? err.message : "Could not load scraper status.",
            );
            first = false;
          }
        }
      },
      () => (runningRef.current ? 4000 : 12_000),
    );
  }, [applyStatus]);

  async function toggle() {
    if (!status) return;
    const stopping = status.running;
    setBusy(true);
    setError("");
    // Optimistic Stop so the UI does not freeze while the API catches up.
    if (stopping) {
      applyStatus({ ...status, running: false });
      runningRef.current = false;
    }
    try {
      const next = stopping ? await api.scraperStop() : await api.scraperStart();
      applyStatus(next);
    } catch (err) {
      if (stopping) {
        // Re-sync from server on failure.
        try {
          applyStatus(await api.scraperStatus());
        } catch {
          /* ignore */
        }
      }
      setError(err instanceof ApiError ? err.message : "Could not change the scraper.");
    } finally {
      setBusy(false);
    }
  }

  function markDirty() {
    dirtyRef.current = true;
    setFilterMessage("");
  }

  function addCity() {
    const name = cityDraft.trim();
    if (!name) return;
    if (cities.some((c) => c.toLowerCase() === name.toLowerCase())) {
      setCityDraft("");
      return;
    }
    markDirty();
    setCities((current) => [...current, name]);
    setCityDraft("");
  }

  function addCategory() {
    const name = categoryDraft.trim().toLowerCase();
    if (!name) return;
    if (categories.includes(name)) {
      setCategoryDraft("");
      return;
    }
    markDirty();
    setCategories((current) => [...current, name]);
    setCategoryDraft("");
  }

  async function saveFilters(event: FormEvent) {
    event.preventDefault();
    if (cities.length === 0 || categories.length === 0) {
      setError("Add at least one city and one business type before saving.");
      return;
    }
    setSavingFilters(true);
    setError("");
    setFilterMessage("");
    try {
      const next = await api.scraperUpdateOrchestration({ cities, categories });
      dirtyRef.current = false;
      applyStatus(next, true);
      setFilterMessage("Filters saved. Collection will use these cities and business types.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save filters.");
    } finally {
      setSavingFilters(false);
    }
  }

  const current = status?.current;

  return (
    <>
      <h1 className="page-title">Scraper</h1>
      <p className="lede">
        Press Start to collect public business numbers city by city. You can
        leave this page — collection keeps running on the server. Press Stop
        when you are done.
      </p>

      {!status?.worker_online || !status?.redis_online ? (
        <div className="banner">
          Phone collection is temporarily unavailable on the server. Please try
          again later, or contact whoever hosts this app if it continues.
        </div>
      ) : null}

      {alerts.map((alert) => (
        <div key={alert.title} className={`banner ${alert.level === "warning" ? "warn" : ""}`}>
          {alert.title}. {alert.detail}{" "}
          <a href={alert.href}>Open {alert.href.replace("/", "") || "page"}</a>
        </div>
      ))}

      {error ? <div className="banner">{error}</div> : null}

      <div className={`panel ${status?.running ? "" : "danger"}`}>
        <div className="switch-row">
          <button
            type="button"
            className={`rocker ${status?.running ? "stop" : ""}`}
            onClick={toggle}
            disabled={
              busy ||
              (!status?.running &&
                (!status?.worker_online || !status?.redis_online))
            }
            title={
              !status?.running &&
              (!status?.worker_online || !status?.redis_online)
                ? "Collection is unavailable until the server is restored"
                : undefined
            }
          >
            {status?.running ? "Stop collecting" : "Start collecting"}
          </button>
          <div>
            <span className={`pulse ${status?.running ? "on" : ""}`} />{" "}
            {status?.running ? "Collecting now" : "Stopped"}
            {status?.running && current?.city ? (
              <div className="hint" style={{ marginTop: 8 }}>
                Working on {current.category || "businesses"} in {current.city}
                {current.source ? ` from ${current.source}` : ""}.
              </div>
            ) : (
              <div className="hint" style={{ marginTop: 8 }}>
                Next up: {status?.next_category || current?.category || "businesses"} in{" "}
                {status?.next_city || current?.city || "the next city"}.
              </div>
            )}
          </div>
        </div>
      </div>

      <form className="panel" style={{ marginTop: 20 }} onSubmit={saveFilters}>
        <h2 style={{ margin: "0 0 8px", fontSize: "1.1rem" }}>What to collect</h2>
        <p className="hint" style={{ marginTop: 0 }}>
          Add US cities and business types. Save to update orchestration — Start
          will rotate through these filters.
        </p>
        <ChipList
          label="Cities"
          items={cities}
          draft={cityDraft}
          placeholder="e.g. Chicago"
          onDraftChange={setCityDraft}
          onAdd={addCity}
          onRemove={(value) => {
            markDirty();
            setCities((current) => current.filter((c) => c !== value));
          }}
        />
        <ChipList
          label="Business types"
          items={categories}
          draft={categoryDraft}
          placeholder="e.g. pharmacy"
          onDraftChange={setCategoryDraft}
          onAdd={addCategory}
          onRemove={(value) => {
            markDirty();
            setCategories((current) => current.filter((c) => c !== value));
          }}
        />
        <div className="key-row" style={{ marginTop: 8 }}>
          <button className="save" type="submit" disabled={savingFilters}>
            {savingFilters ? "Saving…" : "Save filters"}
          </button>
        </div>
        {filterMessage ? <p className="hint">{filterMessage}</p> : null}
      </form>

      <div className="panel" style={{ marginTop: 20 }}>
        <div className="kv">
          <div>
            New numbers this run
            <b>{status?.session_saved ?? 0}</b>
          </div>
          <div>
            Updated numbers
            <b>{status?.session_updated ?? 0}</b>
          </div>
          <div>
            Started
            <b style={{ fontSize: "1rem" }}>{formatWhen(status?.session_started_at ?? null)}</b>
          </div>
        </div>
        {status?.last_error ? (
          <p className="error" style={{ marginTop: 16 }}>
            Last problem: {status.last_error}
          </p>
        ) : null}
        {status?.detail ? <p className="hint">{status.detail}</p> : null}
      </div>

      <div className="panel" style={{ marginTop: 20 }}>
        <h2 style={{ margin: "0 0 12px", fontSize: "1.1rem" }}>Recent collection</h2>
        {(status?.recent_runs || []).length === 0 ? (
          <p className="hint">Nothing collected yet. Press Start.</p>
        ) : (
          <table className="ledger">
            <thead>
              <tr>
                <th>When</th>
                <th>Place</th>
                <th>Source</th>
                <th>New</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {status?.recent_runs.map((run) => (
                <tr key={`${run.id}-${run.started_at}`}>
                  <td>{formatWhen(run.started_at)}</td>
                  <td>
                    {run.city} {run.category}
                  </td>
                  <td>{run.source || "—"}</td>
                  <td>{run.saved}</td>
                  <td>
                    {run.status === "success"
                      ? "Saved"
                      : run.status === "failed"
                        ? "Failed"
                        : "Skipped"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
