"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageCircle, LayoutDashboard, Users, BarChart3,
  Settings, LogOut, Bell, Zap, MessagesSquare, Brain, Bot, CreditCard, ShieldCheck, DollarSign, BookOpen
} from "lucide-react";
import { createClient } from "@/lib/supabase-browser";
import { useEffect, useState } from "react";

const nav = [
  { href: "/dashboard", label: "Vue d'ensemble", icon: LayoutDashboard },
  { href: "/dashboard/creators", label: "Mes créateurs", icon: Users },
  { href: "/dashboard/conversations", label: "Conversations", icon: MessagesSquare },
  { href: "/dashboard/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/dashboard/billing", label: "Facturation", icon: CreditCard },
  { href: "/dashboard/bot-docs", label: "Doc du bot", icon: BookOpen },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [isAdmin, setIsAdmin] = useState(false);
  const [balance, setBalance] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/billing").then(r => r.ok ? r.json() : null).then(d => {
      if (d?.isAdmin) setIsAdmin(true);
      if (d?.billing?.balance !== undefined) setBalance(d.billing.balance);
    }).catch(() => {});
  }, []);

  const handleLogout = async () => {
    const supabase = createClient();
    await supabase.auth.signOut();
    window.location.href = "/login";
  };

  return (
    <aside className="w-64 flex-shrink-0 flex flex-col border-r"
      style={{ background: "#0d0d14", borderColor: "#1e1e2e", minHeight: "100vh" }}>
      {/* Logo */}
      <div className="px-6 py-5 border-b" style={{ borderColor: "#1e1e2e" }}>
        <Link href="/" className="flex items-center gap-2">
          {/* Logo dollar ailé */}
          <svg width="36" height="36" viewBox="0 0 88 88" style={{ flexShrink: 0 }}>
            <path d="M8,44 C8,32 18,22 30,26 C24,32 22,38 24,44 C22,50 24,56 30,62 C18,66 8,56 8,44 Z" fill="#f59e0b" opacity="0.6"/>
            <path d="M80,44 C80,32 70,22 58,26 C64,32 66,38 64,44 C66,50 64,56 58,62 C70,66 80,56 80,44 Z" fill="#f59e0b" opacity="0.6"/>
            <circle cx="44" cy="44" r="22" fill="#0d0d14" stroke="#f59e0b" strokeWidth="2.5"/>
            <text x="33" y="56" fontSize="30" fill="#f59e0b" fontFamily="monospace" fontWeight="900">$</text>
          </svg>
          <span style={{ fontSize: "18px", fontWeight: 800, letterSpacing: "-0.5px", color: "#fff" }}>
            Puls<span style={{ color: "#f59e0b" }}>Chat</span>
            <span style={{ background: "#f59e0b", color: "#0d0d14", fontSize: "8px", fontWeight: 900, padding: "2px 5px", borderRadius: "4px", marginLeft: "5px", verticalAlign: "middle", position: "relative", top: "-1px" }}>AI</span>
          </span>
        </Link>
      </div>

      {/* Status IA */}
      <div className="px-4 py-4 border-b" style={{ borderColor: "#1e1e2e" }}>
        <div className="flex items-center justify-between px-3 py-2.5 rounded-xl"
          style={{ background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.2)" }}>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: "#10b981" }} />
            <span className="text-xs font-medium" style={{ color: "#10b981" }}>IA Active</span>
          </div>
          <Zap size={12} style={{ color: "#10b981" }} />
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-4 py-4 space-y-1">
        {nav.map(({ href, label, icon: Icon }) => {
          const active = pathname === href;
          return (
            <Link key={href} href={href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all"
              style={{
                background: active ? "rgba(168,85,247,0.12)" : "transparent",
                color: active ? "#a855f7" : "#6b7280",
                borderLeft: active ? "2px solid #a855f7" : "2px solid transparent",
              }}>
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>

      {/* Solde */}
      {balance !== null && (
        <div className="px-4 pb-2">
          <Link href="/dashboard/billing"
            className="flex items-center justify-between px-3 py-2.5 rounded-xl transition-all hover:bg-white/5"
            style={{ background: "rgba(16,185,129,0.06)", border: "1px solid rgba(16,185,129,0.15)" }}>
            <div className="flex items-center gap-2">
              <DollarSign size={14} style={{ color: "#10b981" }} />
              <span className="text-xs font-medium" style={{ color: "#10b981" }}>Solde</span>
            </div>
            <span className="text-sm font-black" style={{ color: "#10b981" }}>${balance.toFixed(2)}</span>
          </Link>
        </div>
      )}

      {/* Bottom */}
      <div className="px-4 py-4 border-t space-y-1" style={{ borderColor: "#1e1e2e" }}>
        {isAdmin && (
          <Link href="/dashboard/admin"
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all"
            style={{ color: "#a855f7", background: "rgba(168,85,247,0.08)" }}>
            <ShieldCheck size={16} />
            Admin
          </Link>
        )}
        <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all hover:bg-white/5"
          style={{ color: "#6b7280" }}>
          <Bell size={16} />
          Alertes Telegram
        </button>
        <button onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-all hover:bg-white/5"
          style={{ color: "#6b7280" }}>
          <LogOut size={16} />
          Déconnexion
        </button>
      </div>
    </aside>
  );
}
