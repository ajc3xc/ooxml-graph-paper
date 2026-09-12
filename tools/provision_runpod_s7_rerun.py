#!/usr/bin/env python3
"""
Provision a RunPod CPU-only pod for a full, clean, single-environment re-run
of the PAPER-S7 equation/table_structural/caption benchmark (both arms, all
26 documents per family), so the reported timings aren't a mix of the local
Windows host's own shared-host contention (a concurrent SLAM training job,
plus other concurrent Claude Code sessions) and whatever the remote box looks
like -- one environment, start to finish.

Adapted from the proven pattern in a sibling project's
provision_runpod_caduceus.py (RUNPOD_KEY bearer auth against RunPod's REST
API, https://rest.runpod.io/v1/pods, no SDK) per that script's own handoff
instruction to copy rather than edit in place. Differs from that GPU script
in exactly one structural way: computeType="CPU" plus cpuFlavorIds/vcpuCount
instead of gpuTypeIds/gpuCount -- confirmed via RunPod's live OpenAPI schema
(https://rest.runpod.io/v1/openapi.json), since no GPU fields apply here and
this workload (LibreOffice headless rendering + a Python/Node harness, no
ML training) has no GPU use at all.

Still uses the RunPod-published runpod/pytorch image (not a lighter generic
Ubuntu image) specifically because the sibling project's handoff documents a
real, confirmed failure mode: a bare python:3.11 image has no SSH server at
all, because only RunPod-published images bundle the PUBLIC_KEY-triggered
SSH bootstrap. We don't need PyTorch itself -- the extra image-pull time is
a deliberate, small, one-time cost traded against a repeat of that same
no-SSH-access failure on a task where re-diagnosing it would cost far more.

Requires: pip install requests python-dotenv
Reads RUNPOD_KEY from a local .env -- checked in this repo root first, then
falling back to the sibling dnabert-error-correction project's .env (where
the key already lives from an earlier task) so the key never has to be
retyped, read aloud, or copy-pasted through this conversation. The key is
never printed, logged, or passed on the command line, in either script.

Usage:
    python provision_runpod_s7_rerun.py --dry-run   # print the request payload, create nothing
    python provision_runpod_s7_rerun.py             # actually create the pod (COSTS MONEY)
"""
import argparse
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

# CPU-only pod: computeType="CPU" makes gpuTypeIds/gpuCount/minRAMPerGPU/etc
# irrelevant (RunPod ignores them per the OpenAPI schema's own description).
COMPUTE_TYPE = "CPU"
CPU_FLAVOR_IDS = ["cpu3c"]  # "compute-optimized" flavor (1:2 vCPU:RAM ratio) --
                             # this workload is LibreOffice conversions + a Python/
                             # Node harness process, not memory-hungry; a "c" (compute)
                             # flavor over "g"/"m" (general/memory) matches that shape.
VCPU_COUNT_PRIMARY = 4        # matches the harness's local --max-workers=4 so chains can
                              # actually parallelize instead of re-creating the resource
                              # contention this re-run exists to eliminate.
VCPU_COUNT_FALLBACK = 2       # user's explicit fallback if 4 isn't available at this flavor/
                              # region right now -- tried automatically on a capacity/
                              # availability error from the create call, not a silent default.
CLOUD_TYPE = "SECURE"        # non-spot/persistent, same rationale as the GPU script:
                              # avoids a spot pod being reclaimed mid-run.
DOCKER_IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"  # proven SSH
                                                                              # bootstrap;
                                                                              # CUDA/PyTorch
                                                                              # bits are
                                                                              # simply unused
                                                                              # on a CPU pod.
CONTAINER_DISK_GB = 20
VOLUME_MOUNT_PATH = "/workspace"
SSH_PUBLIC_KEY_PATH = Path.home() / ".ssh" / "id_ed25519.pub"

# A first real pod (id vgl49wk761hf0t, terminated) came back with volumeInGb: 0
# despite requesting 40 -- RunPod's inline "Pod volume" field silently does not
# provision anything for computeType=CPU right now (confirmed empirically, not
# just a docs gap). The explicit, independently-verifiable alternative is a
# standalone network volume (its own resource, listed via GET /networkvolumes)
# attached by networkVolumeId. It's datacenter-pinned at creation, so the pod's
# dataCenterIds must be constrained to match, or scheduling will fail.
NETWORK_VOLUME_NAME = "paper-s7-clean-rerun-vol"
NETWORK_VOLUME_SIZE_GB = 40  # corpus + both repos + LibreOffice + node_modules + run
                               # outputs/checkpoints for 3 families x 2 arms x 26 docs;
                               # generous headroom since this is the one thing that must
                               # survive a pod restart.
NETWORK_VOLUME_DATACENTER = "EU-RO-1"  # where the (terminated) test pod actually landed;
                                          # confirmed available for this account/flavor.


def ensure_network_volume(headers: dict, create: bool) -> str:
    """Return the id of the persistent network volume, reusing one by name if it
    already exists. With create=False (dry-run), never calls POST -- a network
    volume bills storage from the moment it exists, dry-run must stay free."""
    resp = requests.get(f"{RUNPOD_API_BASE}/networkvolumes", headers=headers, timeout=30)
    resp.raise_for_status()
    for vol in resp.json():
        if vol.get("name") == NETWORK_VOLUME_NAME:
            return vol["id"]

    if not create:
        return "<to-be-created-on-real-run>"

    resp = requests.post(
        f"{RUNPOD_API_BASE}/networkvolumes",
        headers=headers,
        json={"name": NETWORK_VOLUME_NAME, "size": NETWORK_VOLUME_SIZE_GB, "dataCenterId": NETWORK_VOLUME_DATACENTER},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def build_payload(vcpu_count: int, network_volume_id: str) -> dict:
    ssh_pub_key = SSH_PUBLIC_KEY_PATH.read_text().strip() if SSH_PUBLIC_KEY_PATH.exists() else ""
    if not ssh_pub_key:
        print(f"WARNING: no SSH public key found at {SSH_PUBLIC_KEY_PATH} -- "
              "you'll only be able to reach the pod via RunPod's web terminal, not ssh.", file=sys.stderr)

    payload = {
        "name": "paper-s7-clean-rerun",
        "imageName": DOCKER_IMAGE,
        "computeType": COMPUTE_TYPE,
        "cpuFlavorIds": CPU_FLAVOR_IDS,
        "vcpuCount": vcpu_count,
        "cloudType": CLOUD_TYPE,
        "containerDiskInGb": CONTAINER_DISK_GB,
        "networkVolumeId": network_volume_id,
        "volumeMountPath": VOLUME_MOUNT_PATH,
        "dataCenterIds": [NETWORK_VOLUME_DATACENTER],
        "ports": ["22/tcp"],
        "env": {"PUBLIC_KEY": ssh_pub_key},
    }
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print the request payload without creating a pod")
    args = parser.parse_args()

    api_key = os.environ.get("RUNPOD_KEY")
    if not api_key:
        sys.exit("RUNPOD_KEY not found in .env (checked repo root and the dnabert-error-correction "
                  "fallback) -- aborting. Never pass it on the command line.")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if args.dry_run:
        volume_id = ensure_network_volume(headers, create=False)
        print("=== DRY RUN -- no pod created, no network volume created ===")
        print(json.dumps(build_payload(VCPU_COUNT_PRIMARY, volume_id), indent=2))
        return

    volume_id = ensure_network_volume(headers, create=True)
    print(f"Network volume ready: {volume_id} ({NETWORK_VOLUME_SIZE_GB}GB in {NETWORK_VOLUME_DATACENTER})")

    pod = None
    for vcpu_count in (VCPU_COUNT_PRIMARY, VCPU_COUNT_FALLBACK):
        payload = build_payload(vcpu_count, volume_id)
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
    print("Check the RunPod dashboard's Connect tab for the SSH host:port, "
          "or query GET /pods/{id} for the runtime/ports info once it's RUNNING.")


if __name__ == "__main__":
    main()
