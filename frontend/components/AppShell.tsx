"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, clearSessionCache } from "@/lib/api";

const LINKS = [
  { href: "/scraper", label: "Scraper" },
  { href: "/numbers", label: "Numbers" },
  { href: "/usage", label: "Usage" },
  { href: "/keys", label: "Keys" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [ready, setReady] = useState(false);
  const [bootError, setBootError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      setBootError(
        "The server is busy or offline. Redirecting to sign in — try again in a moment.",
      );
      window.setTimeout(() => {
        if (!cancelled) router.replace("/login");
      }, 2500);
    }, 12_000);

    api
      .me()
      .then((user) => {
        if (cancelled) return;
        window.clearTimeout(timer);
        setUsername(user.username);
        setReady(true);
        setBootError("");
      })
      .catch(() => {
        if (cancelled) return;
        window.clearTimeout(timer);
        router.replace("/login");
      });

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [router]);

  async function signOut() {
    try {
      await api.logout();
    } finally {
      clearSessionCache();
      router.replace("/login");
    }
  }

  if (!ready) {
    return (
      <div className="main">
        <p className="lede">Opening Phone Desk…</p>
        {bootError ? <div className="banner">{bootError}</div> : null}
      </div>
    );
  }

  return (
    <div className="desk">
      <aside className="spine">
        <p className="built-by">
          <span className="built-by-label">Built by</span>
          <span className="built-by-name">Izaan Bin Mujeeb</span>
        </p>
        <div className="brand">
          Phone Desk
          <span>US business numbers</span>
        </div>
        <nav className="nav">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              prefetch
              className={pathname === link.href ? "active" : ""}
            >
              {link.label}
            </Link>
          ))}
        </nav>
        <div className="spine-foot">
          <span>Signed in as {username}</span>
          <button type="button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
