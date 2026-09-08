"""Set App Runner runtime env (model key) without redeploying code.

Reads BEDROCK_SERVICE_SECRET + WPILOT_MODEL_ID from repo .env (never committed,
never printed) and updates the service in place (triggers a deployment).

Usage: AWS_PROFILE=wpilot python deploy/apprunner_env.py
"""

from __future__ import annotations

from pathlib import Path

import boto3

REGION = "us-east-1"
SERVICE_ARN = (
    "arn:aws:apprunner:us-east-1:381492277789:service/"
    "wpilot-api/c35510a610b5462ebc9fe9aa5bcb0e99"
)
IMAGE = "381492277789.dkr.ecr.us-east-1.amazonaws.com/wpilot-api:apprunner"
ACCESS_ROLE = "arn:aws:iam::381492277789:role/wpilot-apprunner-ecr"


def read_dotenv() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (Path(__file__).resolve().parent.parent / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def main() -> None:
    env = read_dotenv()
    runtime_env = {}
    if env.get("BEDROCK_SERVICE_SECRET"):
        runtime_env["BEDROCK_SERVICE_SECRET"] = env["BEDROCK_SERVICE_SECRET"]
    if env.get("WPILOT_MODEL_ID"):
        runtime_env["WPILOT_MODEL_ID"] = env["WPILOT_MODEL_ID"]
    print("setting keys:", sorted(runtime_env))
    apprunner = boto3.client("apprunner", region_name=REGION)
    op = apprunner.update_service(
        ServiceArn=SERVICE_ARN,
        SourceConfiguration={
            "ImageRepository": {
                "ImageIdentifier": IMAGE,
                "ImageRepositoryType": "ECR",
                "ImageConfiguration": {
                    "Port": "8000",
                    "RuntimeEnvironmentVariables": runtime_env,
                },
            },
            "AuthenticationConfiguration": {"AccessRoleArn": ACCESS_ROLE},
            "AutoDeploymentsEnabled": False,
        },
    )
    print("operation:", op["OperationId"])


if __name__ == "__main__":
    main()
