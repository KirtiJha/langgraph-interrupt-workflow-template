import "./globals.css";
import { THEME_SCRIPT } from "../lib/themeScript";

export const metadata = {
  title: "Repo Steward",
  description: "A maintainer agent for GitHub repositories that asks before anything public happens.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#faf8f3" },
    { media: "(prefers-color-scheme: dark)", color: "#0f0d0b" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-[100dvh]">{children}</body>
    </html>
  );
}
