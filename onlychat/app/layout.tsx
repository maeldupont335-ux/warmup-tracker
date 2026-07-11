import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PulsChat AI — Automatise tes revenus",
  description: "IA ultra-humaine qui gère tes chats 24/7, vend du PPV et booste tes revenus.",
  icons: {
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 88 88'><rect width='88' height='88' rx='18' fill='%230a0a14'/><path d='M8,44 C8,32 18,22 30,26 C24,32 22,38 24,44 C22,50 24,56 30,62 C18,66 8,56 8,44 Z' fill='%23f59e0b' opacity='0.7'/><path d='M80,44 C80,32 70,22 58,26 C64,32 66,38 64,44 C66,50 64,56 58,62 C70,66 80,56 80,44 Z' fill='%23f59e0b' opacity='0.7'/><circle cx='44' cy='44' r='22' fill='%230a0a14' stroke='%23f59e0b' stroke-width='3'/><text x='33' y='56' font-size='30' fill='%23f59e0b' font-family='monospace' font-weight='900'>$</text></svg>",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr" className="h-full">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
