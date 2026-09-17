"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, clearCsrf } from "@/lib/api";

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

  useEffect(() => {
    api
      .me()
      .then((user) => {
        setUsername(user.username);
        setReady(true);
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          router.replace("/login");
          return;
        }
        router.replace("/login");
      });
  }, [router]);

  async function signOut() {
    try {
      await api.logout();
    } finally {
      clearCsrf();
      router.replace("/login");
    }
  }

  if (!ready) {
    return (
      <div className="main">
        <p className="lede">Opening Phone Desk…</p>
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
