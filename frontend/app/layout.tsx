import "./globals.css";

export const metadata = {
  title: "Mission Control",
  description: "A personal agent that gets real-life jobs done — and asks before anything that matters.",
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
