"use client";

import { FormEvent, useEffect, useState } from "react";
import AppShell from "@/components/AppShell";
import { api, ApiError } from "@/lib/api";
import type { KeyCard } from "@/lib/types";

export default function KeysPage() {
  const [cards, setCards] = useState<KeyCard[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [messages, setMessages] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string>("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .keys()
      .then((payload) => setCards(payload.results))
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "Could not load keys.");
      });
  }, []);

  async function save(event: FormEvent, slug: string) {
    event.preventDefault();
    setBusy(slug);
    setErrors((current) => ({ ...current, [slug]: "" }));
    try {
      const card = await api.rotateKey(slug, drafts[slug] || "");
      setCards((current) => current.map((item) => (item.slug === slug ? card : item)));
      setDrafts((current) => ({ ...current, [slug]: "" }));
      setMessages((current) => ({
        ...current,
        [slug]: card.message || "New key saved.",
      }));
    } catch (err) {
      setErrors((current) => ({
        ...current,
        [slug]: err instanceof ApiError ? err.message : "Could not save that key.",
      }));
    } finally {
      setBusy("");
    }
  }

  return (
    <AppShell>
      <h1 className="page-title">Keys</h1>
      <p className="lede">
        When a source runs out of free lookups, open its signup link, create a
        new key, and paste it here. Phone Desk wires it in immediately. You do
        not need to edit any files.
      </p>
      {error ? <div className="banner">{error}</div> : null}

      <div className="key-grid">
        {cards.map((card) => (
          <section className="key-block" key={card.slug}>
            <div className="key-head">
              <h2>{card.name}</h2>
              <span
                className={`connection-badge ${card.connected ? "on" : "off"}`}
              >
                {card.connection_label}
              </span>
            </div>
            <p className="hint">
              {card.needs_key
                ? card.has_key
                  ? `Key on file ending in ${card.key_hint}. ${card.quota_status_label}.`
                  : "No key on file yet."
                : "No key needed."}
            </p>
            <p>{card.plain_english}</p>
            {card.warning ? <p className="banner warn">{card.warning}</p> : null}
            {card.needs_key ? (
              <>
                <ol className="steps">
                  {card.steps.map((step) => (
                    <li key={step}>{step}</li>
                  ))}
                </ol>
                {card.signup_url ? (
                  <p>
                    <a href={card.signup_url} target="_blank" rel="noreferrer">
                      Open {card.name} signup
                    </a>
                  </p>
                ) : null}
                <form className="key-row" onSubmit={(event) => save(event, card.slug)}>
                  <input
                    type="password"
                    autoComplete="off"
                    placeholder="Paste the new API key"
                    value={drafts[card.slug] || ""}
                    onChange={(e) =>
                      setDrafts((current) => ({ ...current, [card.slug]: e.target.value }))
                    }
                  />
                  <button className="save" type="submit" disabled={busy === card.slug}>
                    {busy === card.slug ? "Saving…" : "Save key"}
                  </button>
                </form>
                {errors[card.slug] ? <p className="error">{errors[card.slug]}</p> : null}
                {messages[card.slug] ? <p className="hint">{messages[card.slug]}</p> : null}
              </>
            ) : (
              <ol className="steps">
                {card.steps.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            )}
          </section>
        ))}
      </div>
    </AppShell>
  );
}
