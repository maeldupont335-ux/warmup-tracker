"use client";
import { useState, useEffect } from "react";
import { MessageCircle, RefreshCw, Send, User, Bot } from "lucide-react";

interface Conversation {
  id: string;
  platform: string;
  fan_id: string;
  fan_username: string | null;
  total_revenue: number;
  updated_at: string;
}

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export default function ConversationsPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [msgLoading, setMsgLoading] = useState(false);

  const fetchConversations = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/conversations");
      const data = await res.json();
      setConversations(data.conversations ?? []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const fetchMessages = async (id: string) => {
    setMsgLoading(true);
    try {
      const res = await fetch(`/api/conversations?id=${id}`);
      const data = await res.json();
      setMessages(data.messages ?? []);
    } catch { /* ignore */ }
    finally { setMsgLoading(false); }
  };

  useEffect(() => { fetchConversations(); }, []);
  useEffect(() => { if (selected) fetchMessages(selected); }, [selected]);

  const selectedConv = conversations.find(c => c.id === selected);

  return (
    <div className="flex h-full" style={{ color: "#fff", minHeight: "calc(100vh - 0px)" }}>
      {/* Liste conversations */}
      <div className="w-80 flex-shrink-0 border-r flex flex-col" style={{ borderColor: "#1e1e2e" }}>
        <div className="p-5 border-b flex items-center justify-between" style={{ borderColor: "#1e1e2e" }}>
          <h1 className="font-black text-lg">Conversations</h1>
          <button onClick={fetchConversations} className="p-1.5 rounded-lg hover:bg-white/5 transition-all" style={{ color: "#6b7280" }}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-6 text-center text-sm" style={{ color: "#6b7280" }}>Chargement...</div>
          ) : conversations.length === 0 ? (
            <div className="p-6 text-center">
              <MessageCircle size={32} className="mx-auto mb-3 opacity-20" />
              <p className="text-sm" style={{ color: "#6b7280" }}>Aucune conversation pour l&apos;instant</p>
              <p className="text-xs mt-1" style={{ color: "#4b5563" }}>Les fans apparaîtront ici dès qu&apos;ils écrivent via Telegram</p>
            </div>
          ) : (
            conversations.map((c) => (
              <button key={c.id} onClick={() => setSelected(c.id)}
                className="w-full text-left px-4 py-3 border-b transition-all hover:bg-white/3"
                style={{
                  borderColor: "#1e1e2e",
                  background: selected === c.id ? "rgba(168,85,247,0.08)" : "transparent",
                  borderLeft: selected === c.id ? "3px solid #a855f7" : "3px solid transparent",
                }}>
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                    style={{ background: "rgba(168,85,247,0.15)", color: "#a855f7" }}>
                    {(c.fan_username?.[0] ?? "?").toUpperCase()}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{c.fan_username ?? c.fan_id}</div>
                    <div className="text-xs" style={{ color: "#6b7280" }}>{c.platform}</div>
                  </div>
                  {c.total_revenue > 0 && (
                    <span className="text-xs font-bold" style={{ color: "#10b981" }}>€{c.total_revenue}</span>
                  )}
                </div>
                <div className="text-xs" style={{ color: "#4b5563" }}>
                  {new Date(c.updated_at).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 flex flex-col">
        {!selected ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Send size={40} className="mx-auto mb-4 opacity-10" />
              <p style={{ color: "#6b7280" }}>Sélectionne une conversation</p>
            </div>
          </div>
        ) : (
          <>
            {/* Header conv */}
            <div className="p-4 border-b flex items-center gap-3" style={{ borderColor: "#1e1e2e" }}>
              <div className="w-9 h-9 rounded-full flex items-center justify-center font-bold"
                style={{ background: "rgba(168,85,247,0.15)", color: "#a855f7" }}>
                {(selectedConv?.fan_username?.[0] ?? "?").toUpperCase()}
              </div>
              <div>
                <div className="font-semibold">{selectedConv?.fan_username ?? selectedConv?.fan_id}</div>
                <div className="text-xs" style={{ color: "#6b7280" }}>{selectedConv?.platform} · {messages.length} messages</div>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-5 space-y-3">
              {msgLoading ? (
                <div className="text-center py-10 text-sm" style={{ color: "#6b7280" }}>Chargement...</div>
              ) : messages.map((m) => (
                <div key={m.id} className={`flex gap-2 ${m.role === "assistant" ? "flex-row-reverse" : ""}`}>
                  <div className="w-7 h-7 rounded-full flex-shrink-0 flex items-center justify-center"
                    style={{ background: m.role === "assistant" ? "rgba(168,85,247,0.2)" : "rgba(75,85,99,0.3)" }}>
                    {m.role === "assistant" ? <Bot size={13} style={{ color: "#a855f7" }} /> : <User size={13} style={{ color: "#9ca3af" }} />}
                  </div>
                  <div className={`max-w-sm px-3 py-2 rounded-2xl text-sm leading-relaxed ${m.role === "assistant" ? "rounded-tr-sm" : "rounded-tl-sm"}`}
                    style={{
                      background: m.role === "assistant" ? "rgba(168,85,247,0.12)" : "#1e1e2e",
                      color: "#d1d5db",
                      border: m.role === "assistant" ? "1px solid rgba(168,85,247,0.2)" : "1px solid #2a2a3e",
                    }}>
                    {m.content}
                    <div className="text-xs mt-1" style={{ color: "#4b5563" }}>
                      {new Date(m.created_at).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
