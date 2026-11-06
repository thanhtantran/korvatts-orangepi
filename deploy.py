"""Deploy the KorvaTTS web demo to BoxLite Cloud."""

import asyncio
import json
import os
import pathlib
import shutil
import time
import urllib.error
import urllib.request

import boxlite
from boxlite import Boxlite, BoxliteError, BoxliteRestOptions, InboundNetworkSpec, NetworkSpec, OutboundNetworkSpec

ROOT = pathlib.Path(__file__).parent
BUNDLE = ROOT / ".boxlite-deploy"
BOX_NAME = "korvatts-web-demo"
APP_DESTINATION = "/home/boxlite/korvatts-web"
PORT = 8080
SUPERVISOR = [
    "sh", "-c",
    "while true; do "
    "if [ -f /home/boxlite/korvatts-web/web_service.py ]; then "
    "cd /home/boxlite/korvatts-web && "
    "HF_HOME=/home/boxlite/korvatts-hf-cache "
    "KORVATTS_THREADS=2 PYTHONPATH=/home/boxlite/korvatts-web/deps "
    "PORT=8080 python3 -u web_service.py >>/tmp/korvatts.log 2>&1; "
    "fi; sleep 2; done",
]


def api(method: str, path: str, body: dict | None = None) -> dict:
    base = os.environ["BOXLITE_REST_URL"].rstrip("/").removesuffix("/api")
    payload = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(base + path, data=payload, method=method)
    request.add_header("Authorization", f"Bearer {os.environ['BOXLITE_API_KEY']}")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode() or "{}")


def build_bundle() -> pathlib.Path:
    shutil.rmtree(BUNDLE, ignore_errors=True)
    BUNDLE.mkdir()
    for path in ("pyproject.toml", "web_service.py", "LICENSE", "NOTICE"):
        shutil.copy2(ROOT / path, BUNDLE / path)
    shutil.copytree(ROOT / "korvatts", BUNDLE / "korvatts")
    shutil.copytree(ROOT / "web", BUNDLE / "web")
    return BUNDLE


async def find_id(runtime: Boxlite) -> str | None:
    for info in await runtime.list_info():
        if info.name == BOX_NAME:
            return info.id
    return None


async def open_box(runtime: Boxlite) -> boxlite.SimpleBox:
    box_id = await find_id(runtime)
    if box_id:
        box = boxlite.SimpleBox(image="python", runtime=runtime, name=box_id, auto_remove=False, reuse_existing=True)
        await box.start()
        return box
    try:
        box = boxlite.SimpleBox(
            image="python", runtime=runtime, name=BOX_NAME, auto_remove=False, auto_stop=0,
            cpus=2, memory_mib=4096, disk_size_gb=10,
            entrypoint=SUPERVISOR,
            network=NetworkSpec(
                outbound=OutboundNetworkSpec(mode="enabled", allow_net=[]),
                inbound=InboundNetworkSpec(mode="enabled"),
            ),
        )
        await box.start()
        return box
    except (BoxliteError, RuntimeError) as error:
        if "already exists" not in str(error):
            raise
        box_id = await find_id(runtime)
        if not box_id:
            raise
        box = boxlite.SimpleBox(image="python", runtime=runtime, name=box_id, auto_remove=False, reuse_existing=True)
        await box.start()
        return box


async def wait_for_health(box: boxlite.SimpleBox) -> None:
    probe = "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200"
    for _ in range(60):
        result = await box.exec("python3", "-c", probe)
        if result.exit_code == 0:
            return
        await asyncio.sleep(3)
    log = await box.exec("cat", "/tmp/korvatts.log")
    raise RuntimeError(f"KorvaTTS did not become healthy: {log.stdout}")


async def fetch(url: str, suffix: str = "") -> tuple[int, bytes]:
    last = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(url + suffix, timeout=15) as response:
                return response.status, response.read()
        except Exception as error:
            last = error
            await asyncio.sleep(3)
    raise RuntimeError(f"Could not fetch public service: {last}")


async def main() -> None:
    for variable in ("BOXLITE_REST_URL", "BOXLITE_API_KEY"):
        if not os.environ.get(variable):
            raise RuntimeError(f"{variable} is required")
    bundle = build_bundle()
    runtime = Boxlite.rest(BoxliteRestOptions.from_env())
    box = await open_box(runtime)
    reset = await box.exec("sh", "-c", f"rm -rf {APP_DESTINATION} && mkdir -p {APP_DESTINATION}")
    if reset.exit_code != 0:
        raise RuntimeError(reset.stderr)
    await box.copy_in(str(bundle) + "/.", APP_DESTINATION)
    result = await box.exec("sh", "-c", f"test -f {APP_DESTINATION}/web_service.py && test -f {APP_DESTINATION}/web/index.html")
    if result.exit_code != 0:
        raise RuntimeError("App files were not copied to expected paths")
    install = await box.exec(
        "sh", "-c",
        f"cd {APP_DESTINATION} && python3 -m pip install --target {APP_DESTINATION}/deps .",
    )
    if install.exit_code != 0:
        raise RuntimeError(f"KorvaTTS installation failed: {install.stderr}")
    # The supervisor starts before files/dependencies arrive. Restart its child
    # after installing app-local dependencies so Python adds deps/ on startup.
    await box.exec("sh", "-c", 'pkill -f "python3 -u web_service.py" || true')
    await asyncio.sleep(3)
    await wait_for_health(box)

    # User approval is required before running this public-exposure block.
    api("PUT", f"/api/box/{box.id}/labels", {"labels": {"boxlite.io/public": "true"}})
    details = api("GET", f"/api/box/{box.id}")
    if details.get("labels", {}).get("boxlite.io/public") != "true":
        raise RuntimeError("BoxLite did not confirm public label")
    await box.network.update_inbound(InboundNetworkSpec(mode="enabled"))
    tunnel = await box.tunnel(("127.0.0.1", PORT))
    url = tunnel.uri()
    if not url or not tunnel.is_public():
        raise RuntimeError("No public tunnel URL returned")
    status, page = await fetch(url)
    if status != 200 or b"KorvaTTS" not in page:
        raise RuntimeError("Public UI verification failed")
    status, voices = await fetch(url, "/api/voices")
    if status != 200 or b"khanh_vy" not in voices:
        raise RuntimeError("Public voices endpoint verification failed")
    print(url)


if __name__ == "__main__":
    asyncio.run(main())
