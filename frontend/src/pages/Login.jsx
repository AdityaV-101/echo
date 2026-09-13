import { useState } from "react";
import Mascot from "../components/Mascot";
import FloatingDecor from "../components/FloatingDecor";
import Doodles from "../components/Doodles";
import { useApp } from "../lib/AppContext";

export default function Login() {
  const { doLogin, error, loading } = useApp();
  const [id, setId] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmed = id.trim();
    if (!trimmed) return;
    await doLogin(trimmed);
  };

  return (
    <div className="screen screen-login">
      <FloatingDecor variant="login" />
      <Doodles variant="login" />
      <div className="login-card">
        <Mascot state="idle" size={140} />
        <h1 className="app-title">Echo</h1>
        <p className="app-subtitle">Meet Echo! Practice sounds. Play games. Get better every day!</p>
        <form onSubmit={handleSubmit} className="login-form">
          <label htmlFor="user-id" className="login-label">
            Enter your name or ID
          </label>
          <input
            id="user-id"
            className="login-input"
            type="text"
            value={id}
            onChange={(e) => setId(e.target.value)}
            placeholder="e.g. Jamie"
            autoFocus
          />
          <button type="submit" className="btn btn-primary btn-large" disabled={loading || !id.trim()}>
            {loading ? "Loading..." : "Start"}
          </button>
        </form>
        {error && <p className="error-text">{error}</p>}
      </div>
    </div>
  );
}
