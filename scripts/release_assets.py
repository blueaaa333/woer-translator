"""Keep public Releases focused on installers; retain checksum compatibility."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

REPO = "blueaaa333/woer-translator"
GUIDE = f"https://github.com/{REPO}/blob/main/docs/MAC_FIRST_RUN.md"
START = "<!-- installer-downloads:start -->"
END = "<!-- installer-downloads:end -->"


def installers(tag):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("Expected a stable release tag, e.g. v0.2.1")
    prefix = f"WoerTranslator-{tag[1:]}"
    return [f"{prefix}-Windows-x64-Setup.exe",
            f"{prefix}-macOS-arm64.dmg", f"{prefix}-macOS-x64.dmg"]


def plan(release, tag):
    required = set(installers(tag))
    if release["tag_name"] != tag or release.get("immutable"):
        raise ValueError("Release tag mismatch or immutable release")
    assets = release["assets"]
    names = [a["name"] for a in assets]
    if len(names) != len(set(names)) or not required.issubset(names):
        raise ValueError("Duplicate assets or missing primary installer; nothing removed")
    prefix = f"WoerTranslator-{tag[1:]}"
    removable = {f"blueaaa333-woer-translator-{tag[1:]}.tgz",
                 f"{prefix}-Mac.html", f"{prefix}-Mac.png",
                 f"{prefix}-Windows-x64-Portable.zip"}
    removable.update(f"{prefix}-{platform}-checks.json"
                     for platform in ("Windows-x64", "macOS-arm64", "macOS-x64"))
    removable.update(f"{prefix}-macOS-{arch}.pkg" for arch in ("arm64", "x64"))
    allowed = required | removable | {"SHA256SUMS.txt"}
    if set(names) - allowed:
        raise ValueError("Unknown release asset; review before removing anything")
    for asset in assets:
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", asset.get("digest") or ""):
            raise ValueError("Missing GitHub SHA-256 digest")
    return [a for a in assets if a["name"] in removable]


def checksums(release, tag):
    plan(release, tag)
    by_name = {a["name"]: a for a in release["assets"]}
    return "".join(f"{by_name[name]['digest'][7:]}  {name}\n"
                   for name in sorted(installers(tag)))


def release_notes(body, tag):
    names = installers(tag)
    body = body.replace("\r\n", "\n")
    body = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\s*",
                  "", body, flags=re.S)
    compatibility = re.search(r"^- macOS 15[^\n]+", body, flags=re.M)
    body = re.sub(r"### 下载选择\n.*?(?=\n### |\Z)", "", body, flags=re.S)
    if compatibility and compatibility.group()[2:] not in body:
        body = body.replace("### 使用说明", compatibility.group()[2:] + "\n\n### 使用说明", 1)
    body = re.sub(r"Release 附带可下载的 HTML 指南.*?重新查看。",
                  "Mac 指南和海报可在仓库中查看，DMG 内也包含离线说明。首次成功打开后的引导可从右上角“··· → Mac 首次运行指南”重新查看。", body)
    poster = r"!\[Mac 首次运行海报\]\([^\n]+\)"
    body = re.sub(poster, "", body)
    base = f"https://github.com/{REPO}/releases/download/{tag}/"
    labels = ["Windows 10 / 11 · 64 位", "Mac · Apple 芯片（M 系列）", "Mac · Intel 芯片"]
    links = ["下载 Windows 安装包", "下载 Mac Apple 芯片版", "下载 Mac Intel 版"]
    rows = "\n".join(f"| {label} | [{text}]({base}{name}) |"
                     for label, text, name in zip(labels, links, names))
    header = (f"{START}\n### 下载安装\n\n| 你的电脑 | 安装包 |\n| --- | --- |\n{rows}\n\n"
              f"Mac：打开 DMG，把 App 拖入 Applications。[首次运行指南]({GUIDE})。\n\n"
              f"[SHA-256 校验文件]({base}SHA256SUMS.txt) 用于核对下载完整性；普通安装无需下载源码。\n{END}\n\n")
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return header + body + "\n"


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True, encoding="utf-8")


def fetch_release(tag):
    return json.loads(gh("api", f"repos/{REPO}/releases/tags/{tag}"))


def archive(tags, directory):
    # Archive before deletion. The workflow uploads this folder before apply runs.
    for tag in tags:
        release = fetch_release(tag)
        obsolete = plan(release, tag)
        target = directory / tag
        target.mkdir(parents=True, exist_ok=True)
        (target / "before.json").write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8")
        for asset in obsolete:
            gh("release", "download", tag, "--repo", REPO, "--pattern", asset["name"], "--dir", str(target), "--clobber")
            with (target / asset["name"]).open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != asset["digest"][7:]:
                raise ValueError("Backup verification failed: " + asset["name"])
        print(f"{tag}: archived and verified {len(obsolete)} auxiliary assets")


def apply(tags, directory):
    # Validate every release before performing the first mutation.
    prepared = []
    for tag in tags:
        before = json.loads((directory / tag / "before.json").read_text(encoding="utf-8"))
        current = fetch_release(tag)
        obsolete = plan(current, tag)
        if release_identity(current) != release_identity(before):
            raise ValueError("Release changed since archive; rerun from archive")
        for asset in obsolete:
            path = directory / tag / asset["name"]
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != asset["digest"][7:]:
                    raise ValueError("Backup no longer matches release")
        prepared.append((tag, current, obsolete))
    for tag, current, obsolete in prepared:
        target = directory / tag
        manifest = target / "SHA256SUMS.txt"
        manifest.write_text(checksums(current, tag), encoding="utf-8", newline="\n")
        gh("release", "upload", tag, str(manifest), "--repo", REPO, "--clobber")
        payload = target / "notes.json"
        payload.write_text(json.dumps({"body": release_notes(current.get("body") or "", tag)}, ensure_ascii=False), encoding="utf-8")
        gh("api", "--method", "PATCH", f"repos/{REPO}/releases/{current['id']}", "--input", str(payload))
        for asset in obsolete:
            gh("api", "--method", "DELETE", f"repos/{REPO}/releases/assets/{asset['id']}")
        final = fetch_release(tag)
        expected = set(installers(tag)) | {"SHA256SUMS.txt"}
        if {a["name"] for a in final["assets"]} != expected:
            raise ValueError("Unexpected final asset list")
        if {a["name"]: a["digest"] for a in final["assets"] if a["name"] in installers(tag)} != {
                a["name"]: a["digest"] for a in current["assets"] if a["name"] in installers(tag)}:
            raise ValueError("Installer digest changed")
        (target / "after.json").write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{tag}: three installers and checksum manifest verified")


def release_identity(release):
    # Download counts and timestamps can change while backup files are downloaded.
    return (release["id"], release["tag_name"], release.get("immutable"), release.get("body"),
            sorted((a["id"], a["name"], a["digest"], a["size"]) for a in release["assets"]))


def stage(version, source, target, notes):
    tag = "v" + version
    names = installers(tag)
    if target.exists():
        raise ValueError("Refusing to mix an existing directory into public assets")
    target.mkdir(parents=True)
    lines = []
    for name in names:
        shutil.copyfile(source / name, target / name)
        with (target / name).open("rb") as stream:
            lines.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {name}\n")
    (target / "SHA256SUMS.txt").write_text("".join(sorted(lines, key=lambda line: line[66:])), encoding="utf-8", newline="\n")
    (target.parent / "release-notes.md").write_text(release_notes(notes.read_text(encoding="utf-8"), tag), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["archive", "apply", "stage"])
    parser.add_argument("--tags", default="v0.2.0 v0.2.1")
    parser.add_argument("--directory", type=Path, default=Path("release-backup"))
    parser.add_argument("--version")
    args = parser.parse_args()
    if args.action == "stage":
        stage(args.version or Path("VERSION").read_text().strip(), Path("release-assets"),
              Path("public-release"), Path("docs/RELEASE_NOTES.md"))
    else:
        tags = args.tags.split()
        if not tags or len(tags) != len(set(tags)):
            parser.error("Provide unique existing release tags")
        for tag in tags:
            installers(tag)
        (archive if args.action == "archive" else apply)(tags, args.directory)


if __name__ == "__main__":
    main()
