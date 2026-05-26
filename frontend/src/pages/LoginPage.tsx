import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import toast from "react-hot-toast";
import { ArrowRight, Loader2, LockKeyhole, ShieldCheck, Sparkles } from "lucide-react";

export default function LoginPage() {
  const { login } = useAuth();
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) return;
    setLoading(true);
    try {
      await login(apiKey.trim());
      toast.success("Workspace unlocked");
    } catch {
      toast.error("Invalid API key");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="grid w-full max-w-6xl gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <section className="panel overflow-hidden p-8 md:p-10">
          <div className="eyebrow">Production-Ready Pricing Intelligence</div>
          <h1 className="headline mt-4 max-w-3xl">
            Analyst infrastructure for pricing decisions that need evidence, controls, and exportable audit history.
          </h1>
          <p className="mt-5 max-w-2xl text-base leading-7 body-muted">
            LenAI combines local model inference, SQL-safe data reasoning, document retrieval, and action logging
            into a single operating console for pricing teams.
          </p>

          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {[
              {
                title: "Traceable by default",
                body: "Every recommendation captures SQL, retrieval evidence, model provenance, and analyst action.",
              },
              {
                title: "Tenant-scoped workflows",
                body: "JWT-based access, scoped assets, and retrieval filters keep the working set isolated.",
              },
              {
                title: "Built for review",
                body: "Structured outputs and exportable records fit committee review, not just chat interactions.",
              },
            ].map((item) => (
              <div key={item.title} className="panel-subtle p-5">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-2xl bg-white/[0.04] text-sky-200">
                  <Sparkles size={16} />
                </div>
                <h2 className="text-base font-semibold text-white">{item.title}</h2>
                <p className="mt-2 text-sm leading-6 body-muted">{item.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="panel p-8 md:p-10">
          <div className="mb-8 flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-sky-400 via-blue-500 to-cyan-300 shadow-[0_18px_50px_rgba(31,122,224,0.35)]">
              <span className="text-lg font-bold text-slate-950">L</span>
            </div>
            <div>
              <div className="text-lg font-semibold text-white">Secure Workspace Access</div>
              <div className="text-sm body-muted">Exchange tenant API key for a short-lived session token.</div>
            </div>
          </div>

          <div className="mb-6 rounded-[24px] border border-emerald-400/12 bg-emerald-400/6 p-4 text-sm text-slate-200">
            <div className="mb-2 flex items-center gap-2 font-medium text-emerald-200">
              <ShieldCheck size={16} />
              Session security model
            </div>
            <p className="leading-6 body-muted">
              The raw API key is exchanged once for a JWT and is not persisted in browser storage. Session state is
              memory-only and is cleared on refresh or 401.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-slate-200">Tenant API Key</label>
              <div className="relative">
                <LockKeyhole size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  type="password"
                  autoComplete="current-password"
                  className="input pl-11"
                  placeholder="Enter API key"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </div>
            </div>

            <button type="submit" disabled={loading || !apiKey.trim()} className="btn-primary w-full">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
              {loading ? "Authorizing workspace..." : "Enter workspace"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
