import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "wpilot — volunteer shift backfill",
  description:
    "When a shift goes short, wpilot works the phone tree and only interrupts the coordinator when a human needs to decide.",
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
