import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Taigi Flow – Admin",
};

const NAV = [
  { href: "/agents", label: "Agent 人格" },
  { href: "/dictionary", label: "發音字典" },
  { href: "/sessions", label: "對話日誌" },
  { href: "/monitor", label: "監控" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-TW">
      <body className="flex min-h-screen bg-gray-50 text-gray-900">
        <aside className="w-52 shrink-0 bg-gray-900 text-gray-100 flex flex-col">
          <div className="px-4 py-5 text-lg font-bold border-b border-gray-700">
            Taigi Flow
          </div>
          <nav className="flex-1 px-2 py-4 space-y-1">
            {NAV.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className="block px-3 py-2 rounded text-sm hover:bg-gray-700 transition-colors"
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </aside>
        <main className="flex-1 p-8 min-w-0">{children}</main>
      </body>
    </html>
  );
}
