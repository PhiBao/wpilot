# Deploy runbook — the steps only you can click

## 0. Status (live)

- UI: https://wpilot-ui.vercel.app (Vercel, points at AWS API)
- API: https://fpxyvjfpc5.us-east-1.awsapprunner.com (App Runner, us-east-1)
- ECR: `381492277789.dkr.ecr.us-east-1.amazonaws.com/wpilot-api:apprunner`
- AgentCore runtime: **blocked on AWS-side quota** (`maxAgents limit exceeded`
  with 0 runtimes = quota is 0). Fix: Service Quotas console → *Amazon
  Bedrock AgentCore* → request increase of agent runtimes (or Support Center
  case). Do this ASAP — approval can take days. Script ready:
  `AWS_PROFILE=wpilot python deploy/agentcore_deploy.py` (role + runtime +
  wait + smoke invoke). Arm64 image already in ECR (`wpilot-agent:agentcore`).
- Bedrock data plane (verified Sep 6): control plane OK (models ACTIVE),
  but **InvokeModel returns `Operation not allowed` on every model/region** —
  account-verification guardrail, same root cause as quota 0. IAM is fine;
  regions won't help. Plan: run the live Strands loop on Anthropic/OpenAI
  (Strands is model-portable; swap-back is config-only), keys via App Runner
  env + local `.env`. Bearer-token "mantle" endpoint not needed — SigV4 path
  is already authorized.
- SES sender `kiter0211@gmail.com`: verification email sent — click the link
- AWS credits: request by **Sep 11, 12pm PT** (form in Devpost Resources tab)

## 1. Fly.io fallback (only if AWS has issues)

`fly.toml` targets app `wpilot-api` → https://wpilot-api.fly.dev :

```bash
cd /home/kiter/agentsforhumans
fly auth login
fly launch --no-deploy   # accept app name wpilot-api, region iad, no postgres/redis
fly deploy               # builds Dockerfile.api, one warm 512MB machine
```

Why warm (`auto_stop_machines = "off"`): the demo keeps roster + inbox in
memory so judge clicks share state. Costs pennies for two weeks; scale to
zero after judging (`fly scale count 0`).

## 2. Point the UI at the API (~2 min)

```bash
cd wpilot-ui
printf 'https://wpilot-api.fly.dev' | vercel env add NEXT_PUBLIC_WPILOT_API production --force
vercel --prod --yes
```

Then open https://wpilot-ui.vercel.app/demo and run the video-script flow once.

## 3. AWS follow-ups (your account + credits)

- **AgentCore (judging boost):** `pip install bedrock-agentcore`, wrap
  `wpilot-agent/src/wpilot/agent.py:build_agent` with `@app.entrypoint`,
  `agentcore deploy`. The `/api/agent/*` paths already exercise this loop.
- **SES real email:** verify one sender identity (sandbox), set
  `WPILOT_SES_SENDER`, implement `SesChannel` beside `InteractiveChannel`.
- **EventBridge:** hourly `POST /api/campaigns` per open shift (scan first via
  `GET /api/shifts`, only run where `gap > 0`).

## 4. Submit (before Sep 14, 5pm PDT)

1. Upload the recorded demo video (≤5 min, YouTube/Vimeo public) — upload-ready
   file and storyboard live outside git in `~/wpilot-media/`
2. Paste the submission text into Devpost; link repo + live demo URLs
3. Publish 2 builder.aws posts (+0.4 bonus)
4. Submit early (Sep 13) — code freezes, video can be re-recorded
