"""Mirror official ok-ww releases into this repository with the character code patch.

For every version tag in UPSTREAM_URL that is >= MIN_VERSION and missing here:
  fetch it, run tools/apply_charcode.py on its files, commit the result as a
  standalone (parentless) commit, and push a tag with the same name.

The PyAppify launcher only installs version tags, so the tags are what users get.
The `release` branch is moved to the newest tag so the code can be browsed on GitHub.

Environment:
  UPSTREAM_URL  official update repository (default ok-oldking/ok-ww-update)
  SELF_GIT_URL  URL written into pyappify.yml git_url (this repository)
  MIN_VERSION   oldest version to mirror (default v3.8.13)
  DRY_RUN=1     build and verify but do not push
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import io
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "https://github.com/ok-oldking/ok-ww-update.git")
SELF_GIT_URL = os.environ["SELF_GIT_URL"]
MIN_VERSION = os.environ.get("MIN_VERSION", "v3.8.13")
DRY_RUN = os.environ.get("DRY_RUN") == "1"
BUILD_DIR = ROOT / ".build"
TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


# Release files must keep upstream's exact bytes (many are CRLF): no line-ending conversion.
GIT = ["git", "-c", "core.autocrlf=false", "-c", "core.safecrlf=false", "-c", "core.eol=lf"]

# The only paths apply_charcode.py may change. Anything else differing from upstream aborts the tag.
EXPECTED_CHANGES = re.compile(
    r"^(config\.py|pyappify\.yml|src/char/CharFactory\.py|src/char/CustomCharLoader\.py"
    r"|src/task/BaseCombatTask\.py|src/gui/CharacterCodeTab\.py|i18n/[^/]+/LC_MESSAGES/ok\.(po|mo))$")


def git(*args, input=None, env=None, capture=True):
    result = subprocess.run([*GIT, *args], cwd=ROOT, input=input, env=env,
                            capture_output=capture, check=False)
    if result.returncode != 0:
        err = result.stderr.decode(errors="replace") if capture else ""
        raise RuntimeError(f"git {' '.join(args)} failed: {err.strip()}")
    return result.stdout.decode().strip() if capture else ""


def version_key(tag):
    """Semver precedence: a release sorts after its pre-releases."""
    m = TAG_RE.match(tag)
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    pre_key = (1,) if pre is None else (0, *[(0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split(".")])
    return (int(major), int(minor), int(patch), pre_key)


def remote_tags(url):
    out = git("ls-remote", "--tags", url)
    tags = {}
    for line in out.splitlines():
        sha, ref = line.split("\t")
        name = ref.removeprefix("refs/tags/")
        if name.endswith("^{}"):
            tags[name[:-3]] = sha  # peeled commit of an annotated tag wins
        else:
            tags.setdefault(name, sha)
    return tags


def build_release(tag, upstream_sha):
    git("fetch", "--quiet", "--no-tags", "--depth", "1", UPSTREAM_URL, f"refs/tags/{tag}:refs/upstream/{tag}")
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir()
    archive = subprocess.run([*GIT, "archive", f"refs/upstream/{tag}"], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(BUILD_DIR, filter="tar")
    patch = subprocess.run([sys.executable, str(ROOT / "tools/apply_charcode.py"), str(BUILD_DIR), SELF_GIT_URL])
    if patch.returncode != 0:
        raise RuntimeError(f"apply_charcode.py failed for {tag}")

    env = dict(os.environ, GIT_INDEX_FILE=str(ROOT / ".git/charcode-index"))
    pathlib.Path(env["GIT_INDEX_FILE"]).unlink(missing_ok=True)
    git(f"--work-tree={BUILD_DIR}", "add", "--all", "--force", ".", env=env)
    tree = git("write-tree", env=env)
    message = (f"ok-ww {tag} + character code\n\n"
               f"Official release: {UPSTREAM_URL} {tag} ({upstream_sha})\n"
               f"Patched by tools/apply_charcode.py")
    commit = git("commit-tree", tree, "-m", message)
    shutil.rmtree(BUILD_DIR)
    changed = git("diff-tree", "-r", "--name-only", f"refs/upstream/{tag}", commit).splitlines()
    unexpected = [p for p in changed if not EXPECTED_CHANGES.match(p)]
    if unexpected:
        raise RuntimeError(f"{tag}: files changed outside the patch: {unexpected}")
    print(f"{tag}: {len(changed)} files differ from upstream, all expected")
    return commit


def main():
    min_key = version_key(MIN_VERSION)
    upstream = {t: s for t, s in remote_tags(UPSTREAM_URL).items() if version_key(t)}
    own = remote_tags("origin")
    todo = sorted((t for t in upstream if t not in own and version_key(t) >= min_key), key=version_key)
    print(f"upstream versions >= {MIN_VERSION}: {sorted((t for t in upstream if version_key(t) >= min_key), key=version_key)}")
    print(f"to build: {todo or 'nothing'}")

    built, failed = {}, []
    for tag in todo:
        print(f"::group::{tag}")
        try:
            commit = build_release(tag, upstream[tag])
            git("tag", "-f", tag, commit)
            if not DRY_RUN:
                git("push", "origin", f"refs/tags/{tag}", capture=False)
            built[tag] = commit
            print(f"{tag} -> {commit}")
        except Exception as e:
            print(f"::error title={tag} patch failed::{e}")
            failed.append(tag)
        print("::endgroup::")

    all_own = {**{t: s for t, s in own.items() if version_key(t)}, **built}
    if built and not DRY_RUN:
        newest = max(all_own, key=version_key)
        git("fetch", "--quiet", "--no-tags", "--depth", "1", "origin", f"refs/tags/{newest}")
        git("push", "--force", "origin", f"{all_own[newest]}:refs/heads/release", capture=False)
        print(f"release branch -> {newest}")

    status = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "upstream": UPSTREAM_URL,
        "built": sorted(built, key=version_key),
        "failed": failed,
        "latest": max(all_own, key=version_key) if all_own else None,
    }
    (ROOT / ".sync-result.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))
    if failed:
        sys.exit(f"failed to patch: {', '.join(failed)}")


if __name__ == "__main__":
    main()
