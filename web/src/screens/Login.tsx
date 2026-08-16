import { useState, type FormEvent } from "react";
import { ApiError, login } from "../api/client";

/** Inlogscherm. Verschijnt zodra de backend 401 geeft — dus ook als je je
 *  browserdata wist of de app opnieuw installeert. Dat is precies het geval
 *  waarin de oude ?token=-link je met een kapotte app liet zitten. */
export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!password || busy) return;
    setBusy(true);
    setError(null);
    try {
      await login(password);
      setPassword("");
      onSuccess();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Onjuist wachtwoord."
          : err instanceof ApiError && err.status === 429
            ? "Te veel pogingen. Wacht een minuut."
            : err instanceof ApiError && err.status === 0
              ? "Geen verbinding met de server."
              : "Inloggen mislukt. Probeer het opnieuw.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg px-5 text-ink">
      <form onSubmit={submit} className="w-full max-w-[360px]">
        <h1 className="font-display text-3xl">Sport Coach</h1>
        <p className="mt-2 text-sm text-muted">
          Log één keer in; daarna blijft deze app een jaar ingelogd.
        </p>

        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Wachtwoord"
          autoFocus
          autoComplete="current-password"
          aria-label="Wachtwoord"
          aria-invalid={error != null}
          className="mt-6 w-full rounded-xl border border-line bg-raised px-4 py-3
                     text-ink outline-none placeholder:text-dim
                     focus:border-accent"
        />

        {error && (
          <p role="alert" className="mt-3 text-sm text-alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy || !password}
          className="mt-4 w-full rounded-xl bg-accent px-4 py-3 font-medium
                     text-bg transition-colors hover:bg-accent-hover
                     disabled:opacity-40"
        >
          {busy ? "Bezig…" : "Inloggen"}
        </button>
      </form>
    </div>
  );
}
