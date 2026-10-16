import "./globals.css";

export const metadata = {
  title: "Repo Steward",
  description: "A maintainer agent for GitHub repositories that asks before anything public happens.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#faf8f3",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-[100dvh]">{children}</body>
    </html>
  );
}
