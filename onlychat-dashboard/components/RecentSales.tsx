import { SaleRecord } from "@/lib/types";

export function RecentSales({ sales }: { sales: SaleRecord[] }) {
  return (
    <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
      <h2 className="font-bold mb-4">Ventes récentes</h2>
      {sales.length === 0 ? (
        <p className="text-sm" style={{ color: "#6b7280" }}>Aucune vente récente</p>
      ) : (
        <div className="space-y-3">
          {sales.slice(0, 15).map((s, i) => (
            <div key={`${s.date}-${i}`} className="flex items-center justify-between text-sm">
              <div>
                <div className="font-medium">{s.label || "Vente"}</div>
                <div className="text-xs" style={{ color: "#6b7280" }}>
                  {new Date(s.date).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}
                </div>
              </div>
              <span className="font-bold" style={{ color: "#10b981" }}>+${s.amount.toFixed(2)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
