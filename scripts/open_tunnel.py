"""Open an SSM tunnel to the private EKS API and write a local kubeconfig."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ACCOUNT = "203888389134"
REGION = "ap-southeast-1"
ROOT = Path(__file__).resolve().parents[1]


def aws_identity(profile):
    result = subprocess.run(
        ["aws", "sts", "get-caller-identity", "--profile", profile, "--output", "json"],
        capture_output=True, text=True, check=True,
    )
    identity = json.loads(result.stdout)
    if identity["Account"] != ACCOUNT or identity["Arn"].endswith(":root"):
        raise RuntimeError("AWS profile does not match the authorized non-root account")
    return identity


def outputs(profile):
    env = os.environ.copy()
    env["AWS_PROFILE"] = profile
    result = subprocess.run(
        ["terraform", f"-chdir={ROOT / 'terraform' / 'workload'}", "output", "-json"],
        env=env, capture_output=True, text=True, check=True,
    )
    values = json.loads(result.stdout)
    return {key: item["value"] for key, item in values.items()}


def write_kubeconfig(values, profile, port):
    endpoint = urlparse(values["cluster_endpoint"])
    if endpoint.scheme != "https" or not endpoint.hostname:
        raise RuntimeError("Terraform returned an invalid private EKS endpoint")
    name = values["cluster_name"]
    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{
            "name": name,
            "cluster": {
                "server": f"https://127.0.0.1:{port}",
                "tls-server-name": endpoint.hostname,
                "certificate-authority-data": values["cluster_ca_data"],
            },
        }],
        "users": [{
            "name": name,
            "user": {
                "exec": {
                    "apiVersion": "client.authentication.k8s.io/v1beta1",
                    "command": "aws",
                    "args": [
                        "eks", "get-token", "--cluster-name", name,
                        "--region", REGION, "--profile", profile,
                    ],
                },
            },
        }],
        "contexts": [{
            "name": name,
            "context": {"cluster": name, "user": name},
        }],
        "current-context": name,
    }
    directory = ROOT / ".local"
    directory.mkdir(mode=0o700, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory, prefix=".kubeconfig-",
        delete=False,
    ) as temporary:
        json.dump(config, temporary, indent=2)
        temporary.write("\n")
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o600)
    target = directory / "kubeconfig"
    temporary_path.replace(target)
    target.chmod(0o600)
    return target, endpoint.hostname


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "contact-form-deployer"))
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args()
    if not (1024 <= args.port <= 65535):
        parser.error("--port must be between 1024 and 65535")
    if not shutil.which("session-manager-plugin"):
        parser.error("Session Manager plugin is not installed in this WSL environment")
    aws_identity(args.profile)
    values = outputs(args.profile)
    kubeconfig, remote_host = write_kubeconfig(values, args.profile, args.port)
    parameters = {
        "host": [remote_host],
        "portNumber": ["443"],
        "localPortNumber": [str(args.port)],
    }
    command = [
        "aws", "ssm", "start-session",
        "--profile", args.profile, "--region", REGION,
        "--target", values["relay_instance_id"],
        "--document-name", "AWS-StartPortForwardingSessionToRemoteHost",
        "--parameters", json.dumps(parameters),
    ]
    print(f"Kubeconfig: {kubeconfig}", flush=True)
    print(f"In another terminal: export KUBECONFIG={kubeconfig}", flush=True)
    print("The tunnel remains open until Ctrl-C.", flush=True)
    try:
        return subprocess.call(command)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, KeyError, subprocess.CalledProcessError, ValueError, RuntimeError) as error:
        print(f"Tunnel setup failed: {error}", file=sys.stderr)
        sys.exit(1)
