"use client";

import { useCallback, useEffect, useState } from "react";
import { api, type Campaign, type Receipt, type Shift } from "../lib/api";

function ShiftCard({
  shift,
  onRun,
  busy,
}: {
  shift: Shift;
  onRun: (id: string) => void;
  busy: boolean;
}) {
  return (
    <div className="card">
      <div className="row">
        <div>
          <h3>
            {shift.date} · {shift.window} — {shift.role}
          </h3>
          <div className="meta">
            {shift.location} · {shift.slots_filled}/{shift.slots_needed} filled
            {shift.eligibility.length > 0 &&
              ` · requires ${shift.eligibility.join(", ")}`}
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span className={`pill ${shift.status}`}>{shift.status}</span>
          {shift.status === "open" && (
            <button disabled={busy} onClick={() => onRun(shift.shift_id)}>
              {busy ? "Working…" : "Fill it"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ConsolePage() {
  const [shifts, setShifts] = useState<Shift[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setError("");
      const [s, c, r] = await Promise.all([
        api.shifts(),
        api.campaigns(),
        api.receipts(),
      ]);
      setShifts(s);
      setCampaigns(c);
      setReceipts(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function run(shift_id: string) {
    setBusy(true);
    setError("");
    try {
      await api.runCampaign(shift_id, 300);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function undo(campaign_id: string, shift_id: string) {
    setError("");
    try {
      await api.undo(campaign_id, shift_id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const needsYou = campaigns.filter(
    (c) => c.outcome === "ESCALATED" || c.needs_review
  );

  const campaignIds = new Set(campaigns.map((c) => c.campaign_id));
  const agentReceipts = receipts.filter(
    (r) => r.campaign_id && !campaignIds.has(r.campaign_id)
  );

  return (
    <main>
      <header className="top">
        <h1>wpilot</h1>
        <nav>
          <a href="/demo">Demo console</a>
        </nav>
      </header>
      <p className="sub">
        Harbor Pantry · wpilot works the phone tree. You only hear from it when
        a human needs to decide.
      </p>
      {error && <div className="error">{error}</div>}

      {needsYou.length > 0 && (
        <>
          <div className="section-title">Needs you</div>
          {needsYou.map((c) => (
            <div className="card" key={c.campaign_id}>
              <div className="row">
                <div>
                  <h3>
                    {c.shift_id} — {c.reason}
                  </h3>
                  <div className="meta">
                    Asked {c.asked.length} volunteer{c.asked.length === 1 ? "" : "s"}
                    {c.accepted_by && ` · accepted by ${c.accepted_by}`}
                  </div>
                </div>
                <span className={`pill ${c.needs_review ? "review" : "escalated"}`}>
                  {c.needs_review ? "review" : "escalated"}
                </span>
              </div>
            </div>
          ))}
        </>
      )}

      <div className="section-title">Today&apos;s shifts</div>
      {shifts.map((s) => (
        <ShiftCard key={s.shift_id} shift={s} onRun={run} busy={busy} />
      ))}

      <div className="section-title">Activity — every action, receipted</div>
      {campaigns.length === 0 && agentReceipts.length === 0 && (
        <p className="empty">
          Nothing yet. Tap “Fill it” on an open shift and watch wpilot work.
        </p>
      )}
      {agentReceipts.length > 0 && (
        <div className="card">
          <div className="row">
            <div>
              <h3>{agentReceipts[0].campaign_id} — live agent run</h3>
              <div className="meta">
                Strands loop on Bedrock · {agentReceipts.length} receipts
              </div>
            </div>
            <span className="pill covered">agent</span>
          </div>
          <details open>
            <summary className="meta">
              Receipts ({agentReceipts.length})
            </summary>
            <ul className="receipts">
              {agentReceipts.map((r) => (
                <li key={r.id}>
                  [{r.kind}] {r.detail}
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}
      {[...campaigns].reverse().map((c) => (
        <div className="card" key={c.campaign_id}>
          <div className="row">
            <div>
              <h3>
                {c.shift_id} — {c.reason}
              </h3>
              <div className="meta">
                {c.campaign_id} · asked: {c.asked.join(", ") || "nobody"}
              </div>
            </div>
            <span
              className={`pill ${c.outcome === "FILLED" ? "filled" : "escalated"}`}
            >
              {c.outcome.toLowerCase()}
            </span>
          </div>
          {c.outcome === "FILLED" && (
            <button
              style={{ marginTop: 8 }}
              onClick={() => undo(c.campaign_id, c.shift_id)}
              title="Revert this booking (snapshot undo, fully receipted)"
            >
              Undo booking
            </button>
          )}
          <details>
            <summary className="meta">Receipts ({c.receipts.length})</summary>
            <ul className="receipts">
              {c.receipts.map((r) => (
                <li key={r.id}>
                  [{r.kind}] {r.detail}
                </li>
              ))}
            </ul>
          </details>
        </div>
      ))}
    </main>
  );
}
