"""Publish a committed app tree once to ECR, then return its immutable digest."""

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

REGION = "ap-southeast-1"
ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True, capture_output=True,
    ).stdout.strip()


def image_tag():
    if git("status", "--porcelain", "--", "app"):
        raise RuntimeError("Commit app changes before publishing an image")
    return git("rev-parse", "--short=12", "HEAD:app")


def image_digest(client, repository, tag):
    try:
        result = client.describe_images(
            repositoryName=repository,
            imageIds=[{"imageTag": tag}],
        )
        return result["imageDetails"][0]["imageDigest"]
    except client.exceptions.ImageNotFoundException:
        return None


def publish(client, repository_url, tag):
    repository = repository_url.split("/", 1)[1]
    current = image_digest(client, repository, tag)
    if current:
        return current, False

    registry = repository_url.split("/", 1)[0]
    full_tag = f"{repository_url}:{tag}"
    token = client.get_authorization_token()["authorizationData"][0]["authorizationToken"]
    username, password = base64.b64decode(token).decode("utf-8").split(":", 1)
    with tempfile.TemporaryDirectory(prefix="contact-form-docker-") as docker_config:
        environment = os.environ.copy()
        environment["DOCKER_CONFIG"] = docker_config
        subprocess.run(
            ["docker", "login", "--username", username, "--password-stdin", registry],
            input=password, text=True, env=environment,
            stdout=subprocess.DEVNULL, check=True,
        )
        subprocess.run(
            ["docker", "build", "--tag", full_tag, str(ROOT / "app")],
            env=environment, stdout=sys.stderr, stderr=sys.stderr, check=True,
        )
        subprocess.run(
            ["docker", "push", full_tag],
            env=environment, stdout=sys.stderr, stderr=sys.stderr, check=True,
        )

    for _ in range(12):
        current = image_digest(client, repository, tag)
        if current:
            return current, True
        time.sleep(5)
    raise RuntimeError("ECR did not return a digest after the image push")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "contact-form-deployer"))
    args = parser.parse_args()
    if not args.repository_url.startswith("203888389134.dkr.ecr.ap-southeast-1.amazonaws.com/"):
        parser.error("Repository URL is outside the approved account or region")
    session = boto3.Session(profile_name=args.profile, region_name=REGION)
    digest, changed = publish(session.client("ecr"), args.repository_url, image_tag())
    print(json.dumps({
        "image_uri": f"{args.repository_url}@{digest}",
        "published": changed,
    }))


if __name__ == "__main__":
    try:
        main()
    except (ClientError, OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as error:
        print(f"Image publish failed: {error}", file=sys.stderr)
        sys.exit(1)
