import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Taigi Flow – Playground",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW">
      <body>{children}</body>
    </html>
  );
}
