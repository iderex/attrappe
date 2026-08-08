"""Build the distribution twice and refuse if the two disagree.

    python tools/build_distribution.py

The artefacts a release publishes have to be traceable to a commit, and the
cheapest checkable form of that is the narrow one: two builds of the same commit
produce archives with identical content. Nothing here claims the stronger
property, that a build on another machine or in another year produces the same
bytes, and that claim is not made anywhere else either.

Content rather than bytes. A wheel and a source distribution are zip and tar
archives, and an archive records a modification time per member, so two builds
made a second apart differ in bytes while carrying the same files. The comparison
is therefore over the extracted trees: every member's path and the hash of its
contents.

`dist/` is left holding the first build, which is what the release path uploads.
The second goes somewhere temporary and is thrown away.
"""

import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def build(into: Path) -> bool:
    command = [sys.executable, "-m", "build", "--outdir", str(into)]
    print(f"  $ python -m build --outdir {into.name}")
    return subprocess.run(command, cwd=ROOT, check=False).returncode == 0


def content(archive: Path) -> dict[str, str]:
    """Every member of the archive as path to hash of its contents.

    The member's own path is kept and everything else the archive records about
    it is dropped: the modification time is what makes two builds differ, and it
    is not part of what the artefact is.
    """
    entries: dict[str, str] = {}
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                if member.is_dir():
                    continue
                entries[member.filename] = hashlib.sha256(bundle.read(member)).hexdigest()
        return entries

    with tarfile.open(archive) as tarball:
        for entry in tarball.getmembers():
            if not entry.isfile():
                continue
            handle = tarball.extractfile(entry)
            if handle is None:
                continue
            entries[entry.name] = hashlib.sha256(handle.read()).hexdigest()
    return entries


def compare(first: Path, second: Path) -> list[str]:
    problems: list[str] = []
    left = sorted(path.name for path in first.iterdir() if path.is_file())
    right = sorted(path.name for path in second.iterdir() if path.is_file())
    if not left:
        return ["the build produced no artefact at all"]
    if left != right:
        return [f"the two builds produced different files: {left} against {right}"]

    for name in left:
        one, two = content(first / name), content(second / name)
        if one == two:
            print(f"    {name}: {len(one)} member(s), identical in both builds")
            continue
        differing = sorted(key for key in set(one) | set(two) if one.get(key) != two.get(key))
        problems.append(f"{name} differs between two builds of one commit: {', '.join(differing)}")
    return problems


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    with tempfile.TemporaryDirectory() as temporary:
        second = Path(temporary) / "dist"
        second.mkdir()
        if not build(DIST) or not build(second):
            print("\n  refused: the build did not finish")
            return 1
        problems = compare(DIST, second)

    if problems:
        print("\n  refused:")
        for problem in problems:
            print(f"    {problem}")
        return 1
    print(f"  two builds of this commit agree, and {DIST.name}/ holds the first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
