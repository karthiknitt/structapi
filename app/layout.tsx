import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StructAgent",
  description: "StructAgent — IS-code structural design agent",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
