"""Server API tests (FastAPI TestClient, scripted instant replies)."""

from fastapi.testclient import TestClient

from wpilot.server import STATE, app

client = TestClient(app)


def setup_function(_):
    STATE.reset()
    # Instant answers so campaigns resolve without waiting.
    STATE.channel.scripted_replies = {
        "+15550001001": "YES",  # Maya accepts
        "+15550001008": "NO",
    }


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_shifts_and_gaps():
    shifts = {s["shift_id"]: s for s in client.get("/api/shifts").json()}
    assert shifts["S1"]["gap"] == 1 and shifts["S1"]["status"] == "open"
    assert shifts["S2"]["status"] == "covered"


def test_full_campaign_flow():
    r = client.post("/api/campaigns", json={"shift_id": "S1"})
    assert r.status_code == 201
    body = r.json()
    assert body["outcome"] == "FILLED" and body["accepted_by"] == "V1"
    assert any(x["kind"] == "slot_filled" for x in body["receipts"])
    # Roster write-back visible on shifts endpoint.
    shifts = {s["shift_id"]: s for s in client.get("/api/shifts").json()}
    assert shifts["S1"]["status"] == "covered"
    # Inbox shows the offer + recorded reply.
    inbox = client.get("/api/inbox").json()
    assert len(inbox) == 1 and inbox[0]["reply"] == "YES"


def test_offer_answer_flow():
    r = client.post("/api/campaigns", json={"shift_id": "S1"})
    msg_id = client.get("/api/inbox").json()[0]["message_id"]
    offer = client.get(f"/api/offers/{msg_id}").json()
    assert offer["shift"]["shift_id"] == "S1"
    assert offer["reply"] == "YES"
    assert r.json()["campaign_id"] in [
        c["campaign_id"] for c in client.get("/api/campaigns").json()
    ]


def test_unknown_shift_404():
    r = client.post("/api/campaigns", json={"shift_id": "NOPE"})
    assert r.status_code == 404


def test_reset_restores_gaps():
    client.post("/api/campaigns", json={"shift_id": "S1"})
    assert client.post("/api/demo/reset").status_code == 200
    shifts = {s["shift_id"]: s for s in client.get("/api/shifts").json()}
    assert shifts["S1"]["gap"] == 1
    assert client.get("/api/inbox").json() == []
