const BASE =
  process.env.NEXT_PUBLIC_WPILOT_API ?? "http://localhost:8000";

export interface Shift {
  shift_id: string;
  date: string;
  window: string;
  role: string;
  slots_needed: number;
  slots_filled: number;
  gap: number;
  location: string;
  eligibility: string[];
  status: "covered" | "open";
}

export interface Receipt {
  id: number;
  created_at: string;
  campaign_id: string;
  kind: string;
  detail: string;
}

export interface Campaign {
  campaign_id: string;
  shift_id: string;
  outcome: "FILLED" | "ESCALATED";
  accepted_by: string;
  needs_review: boolean;
  reason: string;
  asked: string[];
  receipts: Receipt[];
}

export interface InboxMsg {
  message_id: string;
  to: string;
  body: string;
  meta: Record<string, string>;
  reply: string | null;
}

export interface Offer {
  message_id: string;
  body: string;
  meta: Record<string, string>;
  shift: {
    shift_id: string;
    date: string;
    window: string;
    role: string;
    location: string;
  } | null;
  reply: string | null;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${path}: ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  shifts: () => req<Shift[]>("/api/shifts"),
  campaigns: () => req<Campaign[]>("/api/campaigns"),
  runCampaign: (shift_id: string, reply_timeout_seconds = 60) =>
    req<Campaign>("/api/campaigns", {
      method: "POST",
      body: JSON.stringify({ shift_id, reply_timeout_seconds }),
    }),
  inbox: () => req<InboxMsg[]>("/api/inbox"),
  reply: (message_id: string, body: string) =>
    req<{ ok: boolean }>(
      `/api/inbox/reply?message_id=${encodeURIComponent(message_id)}`,
      { method: "POST", body: JSON.stringify({ body }) }
    ),
  offer: (message_id: string) =>
    req<Offer>(`/api/offers/${encodeURIComponent(message_id)}`),
  answerOffer: (message_id: string, answer: string) =>
    req<{ ok: boolean }>(`/api/offers/${encodeURIComponent(message_id)}/answer`, {
      method: "POST",
      body: JSON.stringify({ body: answer }),
    }),
  reset: () => req<{ ok: boolean }>("/api/demo/reset", { method: "POST" }),
};
