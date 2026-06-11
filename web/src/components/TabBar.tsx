import { NavLink } from "react-router-dom";

const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

function IconToday() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" {...STROKE}>
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M18.4 5.6l-1.6 1.6M7.2 16.8l-1.6 1.6" />
    </svg>
  );
}

function IconWeek() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" {...STROKE}>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2.5" />
      <path d="M3.5 9.8h17M8 3.2V6.5M16 3.2V6.5" />
    </svg>
  );
}

function IconSeason() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" {...STROKE}>
      <path d="M3 19.5 9 9l4 6 3.5-5.5L21 19.5Z" />
      <path d="M16.5 4.5v4M16.5 4.5h3.5l-1 1.5 1 1.5h-3.5" />
    </svg>
  );
}

function IconYou() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" {...STROKE}>
      <circle cx="12" cy="8" r="3.6" />
      <path d="M5 20.2c.8-4 3.6-5.8 7-5.8s6.2 1.8 7 5.8" />
    </svg>
  );
}

const TABS = [
  { to: "/", label: "Today", icon: <IconToday /> },
  { to: "/week", label: "Week", icon: <IconWeek /> },
  { to: "/season", label: "Season", icon: <IconSeason /> },
  { to: "/jij", label: "Jij", icon: <IconYou /> },
];

export default function TabBar() {
  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-raised/90 backdrop-blur-lg"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      <div className="mx-auto flex max-w-[480px]">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.to === "/"}
            className={({ isActive }) =>
              `flex flex-1 flex-col items-center gap-1 pb-2.5 pt-3 text-[0.66rem] font-medium tracking-wide transition-colors ${
                isActive ? "text-accent" : "text-dim hover:text-muted"
              }`
            }
          >
            {({ isActive }) => (
              <>
                {tab.icon}
                <span>{tab.label}</span>
                <span
                  className={`h-1 w-1 rounded-full transition-opacity ${
                    isActive ? "bg-accent opacity-100" : "opacity-0"
                  }`}
                />
              </>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
