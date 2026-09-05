"use client";

import { use, useCallback, useEffect, useState } from "react";
import { api, type Offer } from "../../../lib/api";

export default function ConfirmPage({
  params,
}: {
  params: Promise<{ messageId: string }>;
}) {
  const { messageId } = use(params);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setOffer(await api.offer(messageId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [messageId]);

  useEffect(() => {
    load();
  }, [load]);

  async function answer(body: string) {
    try {
      await api.answerOffer(messageId, body);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <main className="confirm-wrap">
      <h1>wpilot</h1>
      {error && <div className="error">{error}</div>}
      {!offer && !error && <p className="meta">Loading your shift…</p>}
      {offer && (
        <div className="card" style={{ textAlign: "left" }}>
          <h3>Can you cover this shift?</h3>
          <p>{offer.body}</p>
          {offer.shift && (
            <p className="meta">
              {offer.shift.date} · {offer.shift.window} · {offer.shift.role} ·{" "}
              {offer.shift.location}
            </p>
          )}
          {offer.reply ? (
            <p className="big">
              {offer.reply === "YES"
                ? "✓ You're on the roster. See you there!"
                : "No problem — thanks for letting us know!"}
            </p>
          ) : (
            <div className="tap-row">
              <button className="primary" onClick={() => answer("YES")}>
                Accept
              </button>
              <button onClick={() => answer("NO")}>Decline</button>
            </div>
          )}
        </div>
      )}
      <p className="meta">No account needed. This link is single-use.</p>
    </main>
  );
}
