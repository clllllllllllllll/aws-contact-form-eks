"""Read-only account, capacity, and version checks before workload provisioning."""

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

ACCOUNT = "203888389134"
REGION = "ap-southeast-1"
STANDARD_QUOTA = "L-1216C47A"
NODE_TYPE = "t3.medium"
RELAY_TYPE = "t3.micro"
DB_CLASS = "db.t4g.small"
DB_MAJOR = "16"
STANDARD_FAMILY = re.compile(r"^[acdhimrtz][0-9]")
AMI_ID = re.compile(r"^ami-[0-9a-f]{8,17}$")
EKS_MINOR = re.compile(r"^1\.[0-9]+$")
NODE_RELEASE = re.compile(r"^(1\.[0-9]+)\.[0-9]+-([0-9]{8})$")
ADDONS = {"vpc_cni": "vpc-cni", "kube_proxy": "kube-proxy", "coredns": "coredns"}
DEFAULT_VERIFIED_FILE = Path(".local/verified-workload.tfvars.json")


class Blocked(RuntimeError):
    """A verified prerequisite is not met."""


class Incomplete(RuntimeError):
    """A required read or response is missing or cannot be interpreted."""


def require(condition, message):
    if not condition:
        raise Blocked(message)


def pages(client, operation, **arguments):
    return client.get_paginator(operation).paginate(**arguments)


def load_versions(path):
    values = json.loads(Path(path).read_text())
    if not isinstance(values, dict):
        raise Blocked("Version input must be a JSON object.")
    for name in ("kubernetes_version", "node_release_version", "relay_ami_id"):
        value = values.get(name)
        require(isinstance(value, str) and bool(value.strip()) and not value.startswith("REPLACE"),
                f"Choose a verified {name} before running preflight.")
    require(bool(EKS_MINOR.fullmatch(values["kubernetes_version"])),
            "kubernetes_version must be an EKS minor such as 1.xx.")
    release_match = NODE_RELEASE.fullmatch(values["node_release_version"])
    require(bool(release_match) and release_match.group(1) == values["kubernetes_version"],
            "node_release_version must match the selected EKS minor and include its release date.")
    require(bool(AMI_ID.fullmatch(values["relay_ami_id"])), "relay_ami_id must be an AMI ID.")
    addon_versions = values.get("addon_versions")
    require(isinstance(addon_versions, dict) and set(addon_versions) == set(ADDONS),
            "Supply exact vpc_cni, kube_proxy, and coredns addon versions.")
    for name, value in addon_versions.items():
        require(isinstance(value, str) and bool(value.strip()) and not value.startswith("REPLACE"),
                f"Choose a verified {name} add-on version.")
    has_ami = "node_ami_id" in values
    has_version = "node_ssm_parameter_version" in values
    require(has_ami == has_version,
            "Supply both node_ami_id and node_ssm_parameter_version for a frozen node release.")
    if has_ami:
        require(isinstance(values["node_ami_id"], str)
                and bool(AMI_ID.fullmatch(values["node_ami_id"])),
                "node_ami_id must be an AMI ID.")
        require(type(values["node_ssm_parameter_version"]) is int
                and values["node_ssm_parameter_version"] > 0,
                "node_ssm_parameter_version must be a positive integer.")
    selected = {name: values[name] for name in (
        "kubernetes_version", "addon_versions", "node_release_version", "relay_ami_id"
    )}
    if has_ami:
        selected.update(node_ami_id=values["node_ami_id"],
                        node_ssm_parameter_version=values["node_ssm_parameter_version"])
    return selected


def read_existing_versions(path):
    if path.is_symlink():
        raise Blocked("Verified version output must not be a symbolic link.")
    if not path.exists():
        return None
    existing = json.loads(path.read_text())
    if not isinstance(existing, dict):
        raise Blocked("Existing verified version file is not a JSON object.")
    return existing


def preserve_existing_pins(path, versions):
    existing = read_existing_versions(path)
    if existing is None:
        return
    for name, value in versions.items():
        require(existing.get(name) == value,
                "Existing verified pins differ; choose a new --verified-file path.")


def save_verified_versions(path, versions):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = read_existing_versions(path)
    if existing is not None:
        require(existing == versions, "Existing verified pins differ; choose a new --verified-file path.")
        require(stat.S_IMODE(path.stat().st_mode) == 0o600,
                "Existing verified file must have mode 600 before reuse.")
        return
    descriptor, temporary_name = tempfile.mkstemp(prefix=".verified-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(versions, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary_name, 0o600)
        try:
            os.link(temporary_name, path)
        except FileExistsError:
            existing = read_existing_versions(path)
            require(existing == versions, "Existing verified pins differ; choose a new --verified-file path.")
            require(stat.S_IMODE(path.stat().st_mode) == 0o600,
                    "Existing verified file must have mode 600 before reuse.")
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def selected_zones(ec2):
    response = ec2.describe_availability_zones(Filters=[{"Name": "state", "Values": ["available"]}])
    names = sorted({
        zone["ZoneName"] for zone in response["AvailabilityZones"]
        if zone.get("State") == "available"
        and zone.get("ZoneType", "availability-zone") == "availability-zone"
    })
    require(len(names) >= 2, "Fewer than two standard Availability Zones are available.")
    return names[:2]


def instance_vcpus(ec2, instance_types):
    result = {}
    types = sorted(instance_types)
    for start in range(0, len(types), 100):
        for page in pages(ec2, "describe_instance_types", InstanceTypes=types[start:start + 100]):
            for item in page["InstanceTypes"]:
                result[item["InstanceType"]] = item["VCpuInfo"]["DefaultVCpus"]
    if set(result) != set(types) or any(not isinstance(value, int) or value <= 0 for value in result.values()):
        raise Incomplete("EC2 instance type vCPU inventory is missing or invalid.")
    return result


def standard_capacity(ec2, quotas, require_update_headroom=False):
    active = []
    for page in pages(ec2, "describe_instances", Filters=[
        {"Name": "instance-state-name", "Values": ["pending", "running"]},
    ]):
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                lifecycle = instance.get("InstanceLifecycle")
                if lifecycle == "spot":
                    continue
                if lifecycle is not None:
                    raise Incomplete(f"Unclassified EC2 instance lifecycle: {lifecycle}.")
                if STANDARD_FAMILY.match(instance["InstanceType"]):
                    active.append(instance["InstanceType"])

    vcpus = instance_vcpus(ec2, set(active) | {NODE_TYPE, RELAY_TYPE})
    require(vcpus[NODE_TYPE] == 2 and vcpus[RELAY_TYPE] == 2,
            "Approved t3 worker/relay sizes no longer match the six-vCPU allowance.")
    running = sum(vcpus[instance_type] for instance_type in active)
    applied = quotas.get_service_quota(ServiceCode="ec2", QuotaCode=STANDARD_QUOTA)["Quota"]["Value"]
    if not isinstance(applied, (int, float)) or applied <= 0:
        raise Incomplete("Applied Standard On-Demand EC2 quota was not returned.")

    base = 2 * vcpus[NODE_TYPE] + vcpus[RELAY_TYPE]
    # Each single-AZ node group can add max(2 * AZ count, maxUnavailable) nodes.
    extra_per_group = max(2 * 1, 1)
    simultaneous_peak = base + 2 * extra_per_group * vcpus[NODE_TYPE]
    remaining = applied - running
    require(remaining >= base,
            f"Applied Standard quota has {remaining:g} free vCPUs; new base needs {base}.")
    if require_update_headroom:
        require(remaining >= simultaneous_peak,
                f"Applied Standard quota has {remaining:g} free vCPUs; simultaneous node updates may need {simultaneous_peak}.")
    return {
        "applied_vcpus": applied,
        "running_on_demand_standard_vcpus": running,
        "free_vcpus_before_provisioning": remaining,
        "new_base_vcpus": base,
        "new_simultaneous_update_peak_vcpus": simultaneous_peak,
        "simultaneous_update_headroom_ready": remaining >= simultaneous_peak,
    }


def check_eks(eks, versions):
    minor = versions["kubernetes_version"]
    listed = [
        item
        for page in pages(eks, "describe_cluster_versions", clusterVersions=[minor])
        for item in page["clusterVersions"]
        if item.get("clusterVersion") == minor
    ]
    require(any(item.get("versionStatus") == "STANDARD_SUPPORT" for item in listed),
            f"EKS {minor} is not confirmed in standard support in {REGION}.")

    selected = {}
    for variable_name, addon_name in ADDONS.items():
        pin = versions["addon_versions"][variable_name]
        matches = [
            release
            for page in pages(eks, "describe_addon_versions", addonName=addon_name, kubernetesVersion=minor)
            for addon in page["addons"] if addon.get("addonName") == addon_name
            for release in addon["addonVersions"]
            if release.get("addonVersion") == pin
            and any(item.get("clusterVersion") == minor for item in release.get("compatibilities", []))
        ]
        require(bool(matches), f"Pinned {addon_name} {pin} is not confirmed compatible with EKS {minor}.")
        selected[addon_name] = pin
    return {"kubernetes_version": minor, "addon_versions": selected}


def check_rds(rds):
    options = [
        item
        for page in pages(rds, "describe_orderable_db_instance_options",
                          Engine="postgres", DBInstanceClass=DB_CLASS, Vpc=True)
        for item in page["OrderableDBInstanceOptions"]
        if item.get("DBInstanceClass") == DB_CLASS
        and item.get("EngineVersion", "").split(".")[0] == DB_MAJOR
        and item.get("MultiAZCapable") is True
        and item.get("Vpc") is True
    ]
    require(bool(options), f"Multi-AZ PostgreSQL {DB_MAJOR} on {DB_CLASS} is not orderable in {REGION}.")
    return {"instance_class": DB_CLASS, "engine_major": DB_MAJOR,
            "orderable_multi_az_minor_versions": sorted({item["EngineVersion"] for item in options})}


def amazon_image(ec2, image_id, name_fragment):
    images = ec2.describe_images(ImageIds=[image_id], Owners=["amazon"])["Images"]
    require(len(images) == 1, f"Amazon-owned AMI {image_id} is unavailable in {REGION}.")
    image = images[0]
    require(image.get("ImageId") == image_id and image.get("State") == "available"
            and image.get("Architecture") == "x86_64"
            and image.get("RootDeviceType") == "ebs"
            and name_fragment in image.get("Name", ""),
            f"AMI {image_id} does not match the required available x86_64 image.")
    return {"image_id": image_id, "name": image["Name"]}


def check_amis(ec2, ssm, versions):
    minor = versions["kubernetes_version"]
    base_path = f"/aws/service/eks/optimized-ami/{minor}/amazon-linux-2023/x86_64/standard"
    recommended_path = f"{base_path}/recommended"
    recommended_response = ssm.get_parameter(Name=recommended_path)["Parameter"]
    recommended = json.loads(recommended_response["Value"])
    selected_response = recommended_response
    if "node_ssm_parameter_version" in versions:
        selected_response = ssm.get_parameter(
            Name=f"{recommended_path}:{versions['node_ssm_parameter_version']}"
        )["Parameter"]
        require(selected_response["Version"] == versions["node_ssm_parameter_version"],
                "The selected SSM parameter version differs from the requested version.")
    selected = json.loads(selected_response["Value"])
    release = versions["node_release_version"]
    require(selected["release_version"] == release,
            "The selected SSM parameter version does not match the pinned node release.")
    node_image_id = selected["image_id"]
    if "node_ami_id" in versions:
        require(node_image_id == versions["node_ami_id"],
                "The selected SSM parameter version does not match the pinned node AMI.")
    release_date = NODE_RELEASE.fullmatch(release).group(2)
    image_name = f"amazon-eks-node-al2023-x86_64-standard-{minor}-v{release_date}"
    require(selected["image_name"] == image_name,
            "The selected SSM image name does not match the AL2023 build and EKS minor.")
    node = amazon_image(ec2, node_image_id, image_name)
    require(node["name"] == image_name, "The selected node AMI name does not match its release.")
    relay = amazon_image(ec2, versions["relay_ami_id"], "al2023-ami-")
    return {"node_release_version": release, "node_ami": node, "relay_ami": relay,
            "node_ssm_parameter_version": selected_response["Version"],
            "recommended_node_release_version": recommended["release_version"],
            "recommendation_drift": recommended["release_version"] != release}


def collect(session, versions, require_update_headroom=False):
    require(session.region_name == REGION, f"Use only {REGION} for this deployment.")
    identity = session.client("sts").get_caller_identity()
    require(identity["Account"] == ACCOUNT and not identity["Arn"].endswith(":root"),
            "Use the authorized non-root principal in the approved account.")

    ec2 = session.client("ec2")
    quotas = session.client("service-quotas")
    zones = selected_zones(ec2)
    capacity = standard_capacity(ec2, quotas, require_update_headroom)
    eks = check_eks(session.client("eks"), versions)
    rds = check_rds(session.client("rds"))
    amis = check_amis(ec2, session.client("ssm"), versions)
    return {
        "status": "READY",
        "account": ACCOUNT,
        "region": REGION,
        "principal": identity["Arn"],
        "selected_zones": zones,
        "standard_capacity": capacity,
        "eks": eks,
        "rds": rds,
        "amis": amis,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=os.environ.get("AWS_PROFILE", "contact-form-deployer"))
    parser.add_argument("--versions-file", required=True, type=Path)
    parser.add_argument("--verified-file", default=DEFAULT_VERIFIED_FILE, type=Path)
    parser.add_argument("--require-update-headroom", action="store_true")
    args = parser.parse_args()
    try:
        require(args.versions_file.resolve() != args.verified_file.resolve(),
                "Use a separate candidate file; the verified file is an output.")
        versions = load_versions(args.versions_file)
        preserve_existing_pins(args.verified_file, versions)
        session = boto3.Session(profile_name=args.profile, region_name=REGION)
        report = collect(session, versions, args.require_update_headroom)
        verified = dict(versions,
                        node_ami_id=report["amis"]["node_ami"]["image_id"],
                        node_ssm_parameter_version=report["amis"]["node_ssm_parameter_version"])
        save_verified_versions(args.verified_file, verified)
        report["verified_versions_file"] = str(args.verified_file.resolve())
        code = 0
    except Blocked as error:
        report, code = {"status": "BLOCKED", "reason": str(error)}, 2
    except (BotoCoreError, ClientError, Incomplete, KeyError, ValueError, OSError, TypeError,
            IndexError, AttributeError, UnicodeError) as error:
        report, code = {"status": "INCOMPLETE", "reason": str(error)}, 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
