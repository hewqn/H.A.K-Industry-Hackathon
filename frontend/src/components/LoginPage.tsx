import { useState, type FormEvent } from "react";
import { login, register } from "../auth";

export default function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const user = String(data.get("username") ?? "").trim();
    const password = String(data.get("password") ?? "");
    setBusy(true);
    setError("");
    try {
      if (mode === "signup") {
        await register(user, password);
      } else {
        await login(user, password);
      }
      onLoggedIn();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Incorrect username or password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit}>
        <header className="login-head">
          <p className="login-title">H.A.K</p>
          <div className="login-tabs" role="tablist" aria-label="Account">
            <button type="button" role="tab" aria-selected={mode === "login"}
              className={mode === "login" ? "active" : ""}
              onClick={() => { setMode("login"); setError(""); }}>
              Log in
            </button>
            <button type="button" role="tab" aria-selected={mode === "signup"}
              className={mode === "signup" ? "active" : ""}
              onClick={() => { setMode("signup"); setError(""); }}>
              Sign up
            </button>
          </div>
        </header>
        <label>
          Username
          <input name="username" autoComplete="username" minLength={3} required autoFocus disabled={busy} />
        </label>
        <label>
          Password
          <input name="password" type="password" autoComplete={mode === "signup" ? "new-password" : "current-password"}
            minLength={8} required disabled={busy} />
        </label>
        {error && <p className="login-error" role="alert">{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? (mode === "signup" ? "Creating account…" : "Signing in…") : mode === "signup" ? "Create account" : "Log in"}
        </button>
      </form>
    </div>
  );
}
