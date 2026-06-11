export default function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-3 py-16 text-muted">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-line-strong border-t-accent" />
      {label && <span className="text-sm">{label}</span>}
    </div>
  );
}
