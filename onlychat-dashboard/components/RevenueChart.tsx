export interface ChartPoint {
  date: string;
  totalUsd: number;
  isFinal: boolean;
}

function formatDayLabel(date: string) {
  const d = new Date(`${date}T00:00:00`);
  return d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
}

export function RevenueChart({ data }: { data: ChartPoint[] }) {
  const max = Math.max(1, ...data.map((d) => d.totalUsd));

  return (
    <div className="rounded-2xl border p-6" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
      <h2 className="font-bold mb-6">Revenu Telegram par jour (USD)</h2>
      <div className="flex items-end gap-2 h-48">
        {data.map((d, i) => (
          <div key={d.date} className="flex-1 flex flex-col items-center gap-1 group relative">
            <div
              className="w-full rounded-t-sm transition-all hover:opacity-80"
              style={{
                height: `${(d.totalUsd / max) * 100}%`,
                minHeight: d.totalUsd > 0 ? "2px" : "0",
                background: !d.isFinal
                  ? "linear-gradient(180deg,#a855f7,#7c3aed)"
                  : "linear-gradient(180deg,rgba(168,85,247,0.4),rgba(124,58,237,0.2))",
              }}
              title={`${d.date}: $${d.totalUsd.toFixed(2)}`}
            />
            {i % Math.ceil(data.length / 8 || 1) === 0 && (
              <span className="text-[10px] whitespace-nowrap" style={{ color: "#4b5563" }}>
                {formatDayLabel(d.date)}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
