import { LucideIcon } from "lucide-react";

export function SummaryCard({
  label,
  value,
  icon: Icon,
  color = "#a855f7",
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  color?: string;
}) {
  return (
    <div className="p-5 rounded-2xl border" style={{ background: "#111118", borderColor: "#1e1e2e" }}>
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs" style={{ color: "#6b7280" }}>{label}</span>
        <Icon size={15} style={{ color }} />
      </div>
      <div className="text-2xl font-black">{value}</div>
    </div>
  );
}
