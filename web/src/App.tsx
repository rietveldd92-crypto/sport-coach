import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AUTH_LOST_EVENT, getAuthStatus, isUnavailable } from "./api/client";
import Spinner from "./components/Spinner";
import TabBar from "./components/TabBar";
import Login from "./screens/Login";
import Today from "./screens/Today";
import Week from "./screens/Week";

// Season + Jij dragen recharts mee — lazy zodat Today licht blijft.
const Season = lazy(() => import("./screens/Season"));
const You = lazy(() => import("./screens/You"));

type AuthState = "checking" | "in" | "out";

export default function App() {
  const [auth, setAuth] = useState<AuthState>("checking");

  const check = useCallback(async () => {
    try {
      const status = await getAuthStatus();
      setAuth(status.authenticated ? "in" : "out");
    } catch (err) {
      // Offline: de app draait op de SW-cache. Wie geen sessie heeft komt
      // toch niet binnen, dus laat 'm door naar de gecachete schermen in
      // plaats van een inlogscherm dat zonder server tóch niet werkt.
      setAuth(isUnavailable(err) ? "in" : "out");
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  useEffect(() => {
    const onAuthLost = () => setAuth("out");
    window.addEventListener(AUTH_LOST_EVENT, onAuthLost);
    return () => window.removeEventListener(AUTH_LOST_EVENT, onAuthLost);
  }, []);

  if (auth === "checking") {
    return (
      <div className="min-h-dvh bg-bg text-ink">
        <Spinner label="Laden…" />
      </div>
    );
  }

  if (auth === "out") {
    return <Login onSuccess={() => setAuth("in")} />;
  }

  return (
    <div className="min-h-dvh bg-bg text-ink">
      <main className="mx-auto max-w-[480px] px-5 pb-28 pt-4">
        <Suspense fallback={<Spinner label="Laden…" />}>
          <Routes>
            <Route path="/" element={<Today />} />
            <Route path="/week" element={<Week />} />
            <Route path="/season" element={<Season />} />
            <Route path="/jij" element={<You />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </main>
      <TabBar />
    </div>
  );
}
