import "./globals.css";

export const metadata = {
  title: "AI Research Assistant",
  description: "Intelligent research with interactive guidance using LangGraph",
};

// Mobile: use the real device width, allow pinch-zoom (a11y), tint the chrome.
export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#4f46e5",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
