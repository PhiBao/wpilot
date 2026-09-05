"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type InboxMsg, type Shift } from "../../lib/api";

export default function DemoPage() {
  const [inbox, setInbox] = useState<InboxMsg[]>([]);
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [error, setError] = useState("");
  const [working, setWorking] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [m, s] = await Promise.all([api.inbox(), api.shifts()]);
      setInbox(m);
      setShifts(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [load]);

  async function trigger(shift_id: string) {
    setWorking(shift_id);
    setError("");
    try {
      await api.runCampaign(shift_id, 45);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setWorking(null);
    }
  }

  async function tap(message_id: string, body: string) {
    try {
      await api.reply(message_id, body);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const open = shifts.filter((s) => s.status === "open");

  return (
    <main className="wide">
      <header className="top">
        <h1>wpilot · demo console</h1>
        <nav>
          <a href="/">Coordinator view</a>
        </nav>
      </header>
      <p className="sub">
        Left: the simulated volunteer phone. Right: the org. Trigger a
        cancellation, then answer the texts live as the volunteer would. Every
        sent text below is real engine behavior against a simulated channel —
        nothing is scripted.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="demo-grid">
        <div>
          <div className="section-title">Volunteer phone (simulated SMS)</div>
          <div className="phone">
            {inbox.length === 0 && (
              <div className="bubble">
                <div className="from">wpilot</div>
                No texts yet. Trigger a cancellation on the right.
              </div>
            )}
            {inbox.map((m) => (
              <div className="bubble" key={m.message_id}>
                <div className="from">
                  wpilot → {m.meta.first_name ?? m.to}
                </div>
                <div>{m.body}</div>
                {m.reply ? (
                  <div
                    className={`reply ${m.reply === "YES" ? "yes" : ""}`}
                  >
                    You replied: {m.reply}
                  </div>
                ) : (
                  <>
                    <div className="reply pending">Waiting for reply…</div>
                    <div className="tap-row">
                      <button onClick={() => tap(m.message_id, "YES")}>
                        YES
                      </button>
                      <button onClick={() => tap(m.message_id, "NO")}>
                        NO
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="section-title">Org — trigger a cancellation</div>
          {open.length === 0 && (
            <p className="empty">
              All shifts covered. Reset the demo to run it again.
            </p>
          )}
          {open.map((s) => (
            <div className="card" key={s.shift_id}>
              <div className="row">
                <div>
                  <h3>
                    {s.date} · {s.window} — {s.role}
                  </h3>
                  <div className="meta">
                    {s.slots_filled}/{s.slots_needed} filled · {s.location}
                  </div>
                </div>
                <button
                  className="primary"
                  disabled={working !== null}
                  onClick={() => trigger(s.shift_id)}
                >
                  {working === s.shift_id ? "Running…" : "Someone cancelled — fill it"}
                </button>
              </div>
            </div>
          ))}
          <div className="section-title">Demo controls</div>
          <div className="card">
            <div className="row">
              <span className="meta">Reseed the org, clear inbox + receipts</span>
              <button
                className="danger"
                onClick={() => api.reset().then(load).catch((e) => setError(String(e)))}
              >
                Reset demo
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
