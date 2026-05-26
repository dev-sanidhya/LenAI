import { Outlet, NavLink, useLocation } from "react-router-dom";
import {
  Activity,
  ClipboardList,
  Database,
  MessageSquareQuote,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import clsx from "clsx";

const navItems = [
  { to: "/dashboard", label: "Data Workspace", icon: Database, hint: "Ingestion, readiness, and source governance" },
  { to: "/query", label: "Decision Studio", icon: MessageSquareQuote, hint: "Ask pricing questions and review evidence" },
  { to: "/audit", label: "Audit Ledger", icon: ClipboardList, hint: "Trace recommendations, actions, and exports" },
];

export default function Layout() {
  const location = useLocation();

  return (
    <div className="app-shell">
      <div className="shell-grid">
        <aside className="hidden w-[320px] shrink-0 border-r border-white/5 px-6 py-8 xl:block">
          <div className="panel h-full px-6 py-7">
            <div className="mb-10">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 via-blue-500 to-cyan-300 shadow-[0_18px_50px_rgba(31,122,224,0.35)]">
                <span className="text-lg font-bold text-slate-950">L</span>
              </div>
              <div className="eyebrow">Production Workspace</div>
              <h1 className="mt-3 text-3xl font-bold text-white">LenAI</h1>
              <p className="mt-2 text-sm leading-6 body-muted">
                Pricing intelligence for analyst teams that need auditable recommendations, controlled data access,
                and production-ready decision traceability.
              </p>
            </div>

            <nav className="space-y-2">
              {navItems.map(({ to, label, icon: Icon, hint }) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    clsx(
                      "nav-chip",
                      isActive
                        ? "bg-white/[0.08] text-white shadow-[inset_0_0_0_1px_rgba(91,181,255,0.28)]"
                        : "text-slate-300 hover:bg-white/[0.04] hover:text-white"
                    )
                  }
                >
                  <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-white/[0.04]">
                    <Icon size={18} />
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate">{label}</span>
                    <span className="mt-1 block text-xs text-slate-400">{hint}</span>
                  </span>
                </NavLink>
              ))}
            </nav>

            <div className="mt-10 rounded-[26px] border border-sky-400/10 bg-gradient-to-br from-sky-400/10 via-transparent to-emerald-400/10 p-5">
              <div className="mb-3 flex items-center gap-2 text-sky-200">
                <ShieldCheck size={16} />
                <span className="text-sm font-semibold">Analyst Controls</span>
              </div>
              <ul className="space-y-3 text-sm text-slate-300">
                <li className="flex gap-3">
                  <Sparkles size={15} className="mt-0.5 text-cyan-300" />
                  <span>Structured outputs with explicit confidence and reasoning trace.</span>
                </li>
                <li className="flex gap-3">
                  <Activity size={15} className="mt-0.5 text-emerald-300" />
                  <span>Hybrid evidence path across SQL and document retrieval.</span>
                </li>
              </ul>
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b border-white/5 bg-[#07111fcc] px-4 py-4 backdrop-blur xl:px-8">
            <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
              <div className="xl:hidden">
                <div className="text-sm font-semibold text-white">LenAI</div>
                <div className="text-xs body-muted">Pricing Intelligence</div>
              </div>
              <div className="hidden xl:block">
                <div className="eyebrow">
                  {location.pathname.includes("dashboard")
                    ? "Source Control"
                    : location.pathname.includes("query")
                      ? "Decision Flow"
                      : "Review and Export"}
                </div>
                <div className="mt-1 text-sm body-muted">
                  {location.pathname.includes("dashboard")
                    ? "Prepare governed data and document context before querying."
                    : location.pathname.includes("query")
                      ? "Compose analyst questions, review evidence, and record actions."
                      : "Inspect immutable recommendation history and export records."}
                </div>
              </div>

              <nav className="flex items-center gap-2">
                {navItems.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    className={({ isActive }) =>
                      clsx(
                        "inline-flex items-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-medium transition-colors",
                        isActive
                          ? "bg-sky-400/10 text-sky-100 shadow-[inset_0_0_0_1px_rgba(91,181,255,0.28)]"
                          : "text-slate-300 hover:bg-white/[0.04] hover:text-white"
                      )
                    }
                  >
                    <Icon size={16} />
                    <span className="hidden sm:inline">{label.replace(" Workspace", "").replace(" Studio", "").replace(" Ledger", "")}</span>
                  </NavLink>
                ))}
              </nav>
            </div>
          </header>

          <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col px-4 py-8 xl:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
