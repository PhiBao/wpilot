"""Deploy wpilot agent to Bedrock AgentCore Runtime (idempotent-ish).

Usage (venv active, AWS_PROFILE=wpilot):
    python deploy/agentcore_deploy.py            # create role + runtime, wait READY
    python deploy/agentcore_deploy.py --invoke "List open gaps"
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import boto3

REGION = "us-east-1"
ACCOUNT = "381492277789"
ROLE_NAME = "wpilot-agentcore-exec"
RUNTIME_NAME = "wpilot_agent"  # AgentCore names: [a-zA-Z][a-zA-Z0-9_]{0,47}
IMAGE = f"{ACCOUNT}.dkr.ecr.{REGION}.amazonaws.com/wpilot-agent:agentcore"

TRUST = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "bedrock-agentcore.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
}

EXEC_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Effect": "Allow",
         "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
         "Resource": "*"},
        {"Effect": "Allow",
         "Action": ["logs:CreateLogGroup", "logs:CreateLogStream",
                    "logs:PutLogEvents", "logs:DescribeLogStreams"],
         "Resource": "*"},
        {"Effect": "Allow",
         "Action": ["ecr:GetAuthorizationToken", "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"],
         "Resource": "*"},
    ],
}


def ensure_role(iam) -> str:
    try:
        arn = iam.get_role(RoleName=ROLE_NAME)["Role"]["Arn"]
        print("role exists:", arn)
        return arn
    except iam.exceptions.NoSuchEntityException:
        pass
    arn = iam.create_role(RoleName=ROLE_NAME,
                          AssumeRolePolicyDocument=json.dumps(TRUST))["Role"]["Arn"]
    iam.put_role_policy(RoleName=ROLE_NAME, PolicyName="wpilot-agentcore-exec",
                        PolicyDocument=json.dumps(EXEC_POLICY))
    print("role created:", arn)
    time.sleep(15)  # IAM propagation
    return arn


def find_runtime(control):
    token = None
    while True:
        kw = {"maxResults": 50}
        if token:
            kw["nextToken"] = token
        page = control.list_agent_runtimes(**kw)
        for r in page.get("agentRuntimes", []):
            if r["agentRuntimeName"] == RUNTIME_NAME:
                return r["agentRuntimeArn"]
        token = page.get("nextToken")
        if not token:
            return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--invoke", default=None)
    args = ap.parse_args()

    iam = boto3.client("iam", region_name=REGION)
    control = boto3.client("bedrock-agentcore-control", region_name=REGION)
    role_arn = ensure_role(iam)

    arn = find_runtime(control)
    if not arn:
        print("creating runtime", RUNTIME_NAME)
        resp = control.create_agent_runtime(
            agentRuntimeName=RUNTIME_NAME,
            agentRuntimeArtifact={"containerConfiguration": {"containerUri": IMAGE}},
            networkConfiguration={"networkMode": "PUBLIC"},
            roleArn=role_arn,
        )
        arn = resp["agentRuntimeArn"]
    print("runtime:", arn)

    for _ in range(40):
        desc = control.get_agent_runtime(agentRuntimeArn=arn)
        status = desc.get("status") or desc.get("agentRuntime", {}).get("status")
        print("status:", status)
        if status in ("READY", "ACTIVE"):
            break
        if status in ("CREATE_FAILED", "DELETE_FAILED", "FAILED"):
            print(json.dumps(desc, indent=1, default=str))
            return 1
        time.sleep(20)

    with open("deploy/agentcore_runtime.json", "w") as f:
        json.dump({"agentRuntimeArn": arn, "region": REGION}, f, indent=1)
    print("saved deploy/agentcore_runtime.json")

    if args.invoke:
        rt = boto3.client("bedrock-agentcore", region_name=REGION)
        resp = rt.invoke_agent_runtime(
            agentRuntimeArn=arn,
            runtimeSessionId="wpilot-smoke-00000000000000000001",
            payload=json.dumps({"prompt": args.invoke}).encode(),
        )
        print(resp["response"].read().decode()[:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
