export function DateRangePicker({
  start,
  end,
  onChange,
}: {
  start: string;
  end: string;
  onChange: (start: string, end: string) => void;
}) {
  return (
    <div className="flex items-center gap-2 p-1 rounded-xl" style={{ background: "#111118", border: "1px solid #1e1e2e" }}>
      <input
        type="date"
        value={start}
        max={end}
        onChange={(e) => onChange(e.target.value, end)}
        className="bg-transparent text-sm px-2 py-1 rounded-lg outline-none"
        style={{ color: "#fff" }}
      />
      <span style={{ color: "#4b5563" }}>→</span>
      <input
        type="date"
        value={end}
        min={start}
        max={new Date().toISOString().slice(0, 10)}
        onChange={(e) => onChange(start, e.target.value)}
        className="bg-transparent text-sm px-2 py-1 rounded-lg outline-none"
        style={{ color: "#fff" }}
      />
    </div>
  );
}
