import type { ReactNode } from "react";

export const metadata = {
  title: "CopilotKit × AG-UI Example",
  description: "Drive the template's human-in-the-loop agent from CopilotKit via AG-UI.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0 }}>{children}</body>
    </html>
  );
}
