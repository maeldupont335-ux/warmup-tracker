import { RefreshCw } from "lucide-react";

export function RefreshButton({ loading, onClick }: { loading: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all disabled:opacity-60"
      style={{ background: "linear-gradient(135deg,#a855f7,#7c3aed)", color: "#fff" }}
    >
      <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
      {loading ? "Actualisation..." : "Actualiser"}
    </button>
  );
}
