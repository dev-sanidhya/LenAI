import { useState } from "react";
import { useAuth } from "../contexts/AuthContext";
import toast from "react-hot-toast";
import { Loader2, Lock } from "lucide-react";

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
      toast.success("Authenticated");
    } catch {
      toast.error("Invalid API key");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="card p-8 w-full max-w-sm">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-9 h-9 bg-brand-500 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold">L</span>
          </div>
          <div>
            <p className="font-semibold text-gray-900">LenAI</p>
            <p className="text-xs text-gray-500">Pricing Intelligence</p>
          </div>
        </div>

        <h1 className="text-lg font-semibold text-gray-900 mb-1">Sign in</h1>
        <p className="text-sm text-gray-500 mb-6">
          Enter your API key. It is exchanged for a short-lived token and never stored.
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
            <div className="relative">
              <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="password"
                autoComplete="current-password"
                className="w-full border border-gray-300 rounded-lg pl-9 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
                placeholder="your-api-key"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
          </div>
          <button type="submit" disabled={loading || !apiKey.trim()} className="btn-primary w-full justify-center">
            {loading ? <Loader2 size={16} className="animate-spin" /> : null}
            {loading ? "Authenticating..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
