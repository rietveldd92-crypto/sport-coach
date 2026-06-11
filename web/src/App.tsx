import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Spinner from "./components/Spinner";
import TabBar from "./components/TabBar";
import Today from "./screens/Today";
import Week from "./screens/Week";

// Season + Jij dragen recharts mee — lazy zodat Today licht blijft.
const Season = lazy(() => import("./screens/Season"));
const You = lazy(() => import("./screens/You"));

export default function App() {
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
