import { useEffect, useState } from "react";

export function useOnline(): boolean {
  const [online, setOnline] = useState(() => navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return online;
}

/** Amberkleurige balk: cached data, geen verse verbinding. */
export default function OfflineBanner({ show, reason }: { show: boolean; reason?: string }) {
  if (!show) return null;
  return (
    <div className="mb-4 flex items-center gap-2.5 rounded-xl border border-warning/40 bg-warning/10 px-3.5 py-2.5 text-[0.8rem] text-warning">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M1.5 8.5a14 14 0 0 1 21 0M5 12.5a9 9 0 0 1 14 0M8.5 16.5a4 4 0 0 1 7 0" opacity="0.45" />
        <path d="M12 20.2h.01" />
        <path d="M3 3l18 18" />
      </svg>
      <span>{reason ?? "Offline — je ziet de laatst opgehaalde data."}</span>
    </div>
  );
}
