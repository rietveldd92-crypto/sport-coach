import { useEffect } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

export default function BottomSheet({ open, onClose, title, children }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  // Portal naar <body>: de rise-in animatie laat (fill-mode: both) een
  // permanente transform op secties achter, en een transformed ancestor
  // wordt de containing block voor position:fixed. Zonder portal rendert
  // een sheet die binnen zo'n sectie wordt geopend buiten beeld.
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center">
      <button
        aria-label="Sluiten"
        className="sheet-backdrop absolute inset-0 bg-black/60"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        className="sheet-panel relative max-h-[88dvh] w-full max-w-[480px] overflow-y-auto rounded-t-3xl border-t border-line-strong bg-raised px-5 pt-3"
        style={{ paddingBottom: "calc(env(safe-area-inset-bottom) + 1.5rem)" }}
      >
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-line-strong" />
        {title && (
          <h2 className="font-display mb-4 text-xl font-semibold">{title}</h2>
        )}
        {children}
      </div>
    </div>,
    document.body,
  );
}
