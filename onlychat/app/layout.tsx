import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulsChat AI — Automatise tes revenus",
  description: "IA ultra-humaine qui gère tes chats 24/7, vend du PPV et booste tes revenus.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className="h-full">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
