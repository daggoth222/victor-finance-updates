"""Publish only a reviewed binary candidate whose independent artifact digest is fixed.

The short-lived input URL grants access only to the binary being made public. It is
removed after publication. No cross-repository token, private key or account data.
"""

import base64
import hashlib
import io
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

REPO = os.environ["GH_REPOSITORY"]
if REPO != "daggoth222/victor-finance-updates":
    raise SystemExit("Unexpected distribution repository")
API = "https://api.github.com/repos/" + REPO
TOKEN = os.environ["GH_TOKEN"]
PACKAGE = "VICTOR-Finance-Windows-x64.zip"
LIMIT = 128 * 1024 * 1024


def api(path, payload=None, method=None, *, binary=None, upload=False):
    raw = (
        binary
        if binary is not None
        else json.dumps(payload).encode()
        if payload is not None
        else None
    )
    url = "https://uploads.github.com/repos/" + REPO + path if upload else API + path
    request = urllib.request.Request(
        url,
        data=raw,
        method=method,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/octet-stream"
            if binary is not None
            else "application/json",
            "User-Agent": "VICTOR-Finance-release-publisher",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def bounded_download(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("HTTPS download required")
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent": "VICTOR-Finance-release-verifier"}),
        timeout=120,
    ) as response:
        data = io.BytesIO()
        while chunk := response.read(1024 * 1024):
            if data.tell() + len(chunk) > LIMIT:
                raise ValueError("Package exceeds limit")
            data.write(chunk)
        return data.getvalue()


def contents(path):
    item = api("/contents/" + path + "?ref=main")
    return item, json.loads(base64.b64decode(item["content"]))


def main():
    request_path = Path("release-request.json")
    if not request_path.exists():
        print("No release request")
        return
    request = json.loads(request_path.read_text())
    if request.get("state") != "pending":
        print("No pending release")
        return
    version = request["version"]
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Invalid version")
    if not re.fullmatch("[0-9a-f]{40}", request["source_sha"]) or not re.fullmatch(
        "[0-9a-f]{64}", request["artifact_sha256"]
    ):
        raise ValueError("Invalid candidate identity")
    location = urllib.parse.urlsplit(request["artifact_url"])
    if not location.hostname or not location.hostname.endswith(
        (".oaiusercontent.com", ".blob.core.windows.net")
    ):
        raise ValueError("Unexpected candidate storage")
    original_request, current_request = contents("release-request.json")
    if current_request != request:
        raise ValueError("Release request changed")
    channel_file, channel = contents("channels/stable.json")
    current = channel.get("release")
    if current and tuple(map(int, current["version"].split("."))) >= tuple(
        map(int, version.split("."))
    ):
        raise ValueError("Channel must advance; no overwrite or downgrade")
    raw = bounded_download(request["artifact_url"])
    if hashlib.sha256(raw).hexdigest() != request["artifact_sha256"]:
        raise ValueError("Candidate artifact digest mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        if set(outer.namelist()) != {PACKAGE, "stable.json", "SHA256SUMS.txt"}:
            raise ValueError("Unexpected candidate files")
        if any(item.file_size > LIMIT for item in outer.infolist()):
            raise ValueError("Candidate member exceeds limit")
        package = outer.read(PACKAGE)
        stable_raw = outer.read("stable.json")
        sums = outer.read("SHA256SUMS.txt")
    manifest = json.loads(stable_raw)
    release = manifest["release"]
    expected_url = "https://github.com/" + REPO + "/releases/download/v" + version + "/" + PACKAGE
    if (
        manifest.get("schema") != 1
        or manifest.get("channel") != "stable"
        or release["version"] != version
        or release["platform"] != "windows-x64"
        or release["url"] != expected_url
    ):
        raise ValueError("Candidate manifest identity mismatch")
    package_hash = hashlib.sha256(package).hexdigest()
    if (
        release["sha256"] != package_hash
        or release["size"] != len(package)
        or len(package) > LIMIT
        or sums.decode().strip() != package_hash + "  " + PACKAGE
    ):
        raise ValueError("Package checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(package)) as bundle:
        for item in bundle.infolist():
            path = PurePosixPath(item.filename)
            if (
                not item.filename.startswith("VICTORFinance/")
                or ".." in path.parts
                or path.is_absolute()
                or path.suffix.lower() in (".sqlite", ".sqlite3", ".db", ".pem", ".key")
                or path.name.startswith(".env")
            ):
                raise ValueError("Unexpected private data or archive path")
        meta = json.loads(
            bundle.read("VICTORFinance/engine/_internal/trading_ai/windows-build.json")
        )
        if (
            meta["version"] != version
            or meta["source_sha"] != request["source_sha"]
            or meta["live_enabled"] is not False
        ):
            raise ValueError("Embedded build identity mismatch")
        expected = {}
        for line in bundle.read("VICTORFinance/SHA256SUMS.txt").decode().splitlines():
            checksum, name = line.split("  ", 1)
            if name in expected:
                raise ValueError("Duplicate integrity member")
            expected[name] = checksum
        actual = {
            i.filename.removeprefix("VICTORFinance/"): hashlib.sha256(bundle.read(i)).hexdigest()
            for i in bundle.infolist()
            if not i.is_dir() and i.filename != "VICTORFinance/SHA256SUMS.txt"
        }
        if expected != actual:
            raise ValueError("Bundle integrity mismatch")
    # Resume only an identical verified publication; never replace release assets.
    proof = "Source: " + request["source_sha"] + "\nSHA-256: " + package_hash
    try:
        created = api("/releases/tags/v" + version)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        created = None
    if created and proof not in created.get("body", ""):
        raise ValueError("Existing release has a different build identity; refusing overwrite")
    if created is None:
        created = api(
            "/releases",
            dict(
                tag_name="v" + version,
                target_commitish="main",
                name="VICTOR Finance " + version,
                body=release["notes"]
                + "\n\nWindows x64. Paquet portable vérifié; installation manuelle après téléchargement depuis VF. Signature éditeur reportée.\n\n"
                + proof,
                draft=True,
                prerelease=False,
            ),
            method="POST",
        )
    rid = created["id"]
    assets = {asset["name"]: asset for asset in created.get("assets", [])}
    for name, data in ((PACKAGE, package), ("SHA256SUMS.txt", sums)):
        if name in assets:
            if assets[name].get("digest") != "sha256:" + hashlib.sha256(data).hexdigest():
                raise ValueError("Existing release asset differs; refusing overwrite")
        elif created.get("draft", True):
            api(
                "/releases/" + str(rid) + "/assets?name=" + urllib.parse.quote(name),
                binary=data,
                method="POST",
                upload=True,
            )
        else:
            raise ValueError("Published release missing verified asset")
    _, latest_request = contents("release-request.json")
    if latest_request != request:
        raise ValueError("Request changed; verified draft left unpublished")
    if created.get("draft", True):
        api("/releases/" + str(rid), dict(draft=False), method="PATCH")
    for attempt in range(6):
        try:
            public = bounded_download(expected_url)
            if hashlib.sha256(public).hexdigest() != package_hash:
                raise ValueError("Public package digest mismatch")
            break
        except urllib.error.HTTPError:
            if attempt == 5:
                raise
            time.sleep(3)
    # Channel is activated only after a verified anonymous public download.
    api(
        "/contents/channels/stable.json",
        dict(
            message="Activate verified VF " + version + " [skip ci]",
            sha=channel_file["sha"],
            branch="main",
            content=base64.b64encode(stable_raw).decode(),
        ),
        method="PUT",
    )
    sanitized = dict(
        state="published",
        version=version,
        source_sha=request["source_sha"],
        package_sha256=package_hash,
        release_url="https://github.com/" + REPO + "/releases/tag/v" + version,
    )
    api(
        "/contents/release-request.json",
        dict(
            message="Record publication and remove temporary download URL [skip ci]",
            sha=original_request["sha"],
            branch="main",
            content=base64.b64encode((json.dumps(sanitized, indent=2) + "\n").encode()).decode(),
        ),
        method="PUT",
    )
    print("Published and verified VF " + version + "; stable channel activated")


if __name__ == "__main__":
    main()
