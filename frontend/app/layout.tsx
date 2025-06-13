import "./globals.css";

export const metadata = {
  title: "AI Research Assistant",
  description: "Intelligent research with interactive guidance using LangGraph",
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
