"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { startVisiblePoll } from "@/lib/polling";
import type { UsagePayload } from "@/lib/types";

export default function UsagePage() {
  const [data, setData] = useState<UsagePayload | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let first = true;
    return startVisiblePoll(
      async () => {
        try {
          const payload = await api.usage();
          setData(payload);
          if (first) first = false;
        } catch (err) {
          if (first) {
            setError(err instanceof ApiError ? err.message : "Could not load usage.");
            first = false;
          }
        }
      },
      () => 45_000,
    );
  }, []);

  return (
    <>
      <h1 className="page-title">Usage</h1>
      <p className="lede">
        Each source has a limited number of free lookups. The filled bar is how
        much you have already used. When a bar is full, add a new key.
      </p>
      {error ? <div className="banner">{error}</div> : null}

      {data?.alerts.map((alert) => (
        <div key={alert.title} className={`banner ${alert.level === "warning" ? "warn" : ""}`}>
          {alert.title}. {alert.detail} <Link href={alert.href}>Go there</Link>
        </div>
      ))}

      <div className="kv" style={{ marginBottom: 24 }}>
        <div>
          Numbers on file
          <b>{data?.phone_total ?? 0}</b>
        </div>
        <div>
          New in the last day
          <b>{data?.harvest_24h.saved ?? 0}</b>
        </div>
        <div>
          New this week
          <b>{data?.harvest_7d.saved ?? 0}</b>
        </div>
      </div>

      <div className="stack">
        {data?.sources.map((source) => {
          const used = source.used_percent ?? 0;
          const meterClass =
            source.quota_status === "exhausted"
              ? "meter out"
              : source.quota_status === "low"
                ? "meter low"
                : "meter";
          return (
            <section className="panel" key={source.slug}>
              <h2 style={{ margin: 0, fontSize: "1.2rem" }}>{source.name}</h2>
              <p className="hint" style={{ margin: "6px 0 0" }}>
                {source.quota_status_label}
                {source.needs_key && !source.has_key ? " · Missing key" : ""}
              </p>
              {source.max != null ? (
                <div className={meterClass}>
                  <span style={{ width: `${Math.min(100, used)}%` }} />
                </div>
              ) : (
                <div className="meter">
                  <span style={{ width: "8%" }} />
                </div>
              )}
              <p style={{ margin: 0 }}>{source.plain_english}</p>
              {source.quota_status === "exhausted" || (source.needs_key && !source.has_key) ? (
                <p>
                  <Link href="/keys">Add a key</Link>
                </p>
              ) : null}
            </section>
          );
        })}
      </div>
    </>
  );
}
