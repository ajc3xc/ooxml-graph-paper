#!/usr/bin/env python3
"""PAPER-S7 multi-anchor extension: provision a RunPod CPU-only pod for the
equation/caption/section_reorder N-growth run, reusing an existing network
volume instead of creating a new one.

Adapted from provision_runpod_s7_rerun.py (copy-not-edit-in-place, per that
script's own inherited handoff instruction). Differs in exactly one way:
that script's fresh-network-volume creation hit RunPod's real, documented
constraint ("You must have at least $5 in your account to create a network
volume") when the account balance was below $5 -- confirmed via the actual
API error body, not assumed. Per explicit user instruction (2026-09-19,
"just use the current pre-existing 60gb volume just for now"), this script
instead attaches the account's existing "sam31-annotator-permavol" volume
(id 2tu2wtzof7, 60GB, pinned to datacenter US-IL-1 -- confirmed via GET
/networkvolumes) rather than creating a new one, which has no $5-minimum
gate (only volume *creation* does; attaching an existing one to a new pod
is billed as ordinary compute, same $0.12/hr cpu3c rate as before).

This volume belongs to an unrelated prior project (a SAM/segmentation
annotation tool). Nothing on it is touched, moved, or deleted -- this
project's own data is written under a clearly separate, namespaced
subdirectory (/workspace/ooxml-graph-paper/) so the two projects' files
never collide.

Because the volume is pinned to US-IL-1, not EU-RO-1 (where the original
S7 confirmatory re-run's own fresh volume landed), dataCenterIds is set to
US-IL-1 here -- a network volume's datacenter pin constrains which
datacenter any pod using it can schedule into, per RunPod's own scheduling
rule (same rule the original script's own comments already document).

Usage:
    python provision_runpod_multi_anchor_extension.py --dry-run   # print the payload, create nothing
    python provision_runpod_multi_anchor_extension.py             # actually create the pod (COSTS MONEY)
"""
import json
import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
FALLBACK_ENV_PATH = Path(r"C:\Users\13144\Documents\dnabert-error-correction\.env")


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv(REPO_ROOT / ".env")
load_dotenv(FALLBACK_ENV_PATH)

RUNPOD_API_BASE = "https://rest.runpod.io/v1"

EXISTING_VOLUME_ID = "2tu2wtzof7"  # "sam31-annotator-permavol", 60GB, US-IL-1 -- confirmed live via GET /networkvolumes, 2026-09-19
EXISTING_VOLUME_DATACENTER = "US-IL-1"

COMPUTE_TYPE = "CPU"
CPU_FLAVOR_IDS = ["cpu3c"]
VCPU_COUNT_PRIMARY = 4
VCPU_COUNT_FALLBACK = 2
CLOUD_TYPE = "SECURE"
DOCKER_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"
CONTAINER_DISK_GB = 20
VOLUME_MOUNT_PATH = "/workspace"
SSH_PUBLIC_KEY_PATH = Path.home() / ".ssh" / "id_ed25519.pub"


def build_payload(vcpu_count: int) -> dict:
    ssh_pub_key = SSH_PUBLIC_KEY_PATH.read_text().strip() if SSH_PUBLIC_KEY_PATH.exists() else ""
    if not ssh_pub_key:
        print(f"WARNING: no SSH public key found at {SSH_PUBLIC_KEY_PATH} -- "
              "you'll only be able to reach the pod via RunPod's web terminal, not ssh.", file=sys.stderr)

    return {
        "name": "paper-s7-multi-anchor-extension",
        "imageName": DOCKER_IMAGE,
        "computeType": COMPUTE_TYPE,
        "cpuFlavorIds": CPU_FLAVOR_IDS,
        "vcpuCount": vcpu_count,
        "cloudType": CLOUD_TYPE,
        "containerDiskInGb": CONTAINER_DISK_GB,
        "networkVolumeId": EXISTING_VOLUME_ID,
        "volumeMountPath": VOLUME_MOUNT_PATH,
        "dataCenterIds": [EXISTING_VOLUME_DATACENTER],
        "ports": ["22/tcp"],
        "env": {"PUBLIC_KEY": ssh_pub_key},
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("RUNPOD_KEY")
    if not api_key:
        sys.exit("RUNPOD_KEY not found in .env -- aborting. Never pass it on the command line.")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if args.dry_run:
        print("=== DRY RUN -- no pod created ===")
        print(json.dumps(build_payload(VCPU_COUNT_PRIMARY), indent=2))
        return

    pod = None
    for vcpu_count in (VCPU_COUNT_PRIMARY, VCPU_COUNT_FALLBACK):
        payload = build_payload(vcpu_count)
        resp = requests.post(f"{RUNPOD_API_BASE}/pods", headers=headers, json=payload, timeout=60)
        if resp.status_code < 300:
            pod = resp.json()
            break
        print(f"vcpuCount={vcpu_count} failed ({resp.status_code}): {resp.text}", file=sys.stderr)
        if vcpu_count == VCPU_COUNT_PRIMARY:
            print(f"Retrying with the fallback vcpuCount={VCPU_COUNT_FALLBACK}...", file=sys.stderr)
    if pod is None:
        sys.exit(f"Pod creation failed at both vcpuCount={VCPU_COUNT_PRIMARY} and "
                  f"vcpuCount={VCPU_COUNT_FALLBACK} -- see errors above.")

    print(json.dumps(pod, indent=2))
    print(f"\nPod id: {pod.get('id')}")
    print(f"vCPUs: {pod.get('vcpuCount')}  |  costPerHr: {pod.get('costPerHr')}")


if __name__ == "__main__":
    main()
