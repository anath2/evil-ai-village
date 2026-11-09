#!/usr/bin/env python3
"""Upload village experiment data to a HuggingFace **dataset** repo.

The repo stays small (code + curated summaries). Raw run artifacts (boards,
per-agent transcripts, social graphs, logs) are gitignored locally, so this
script is how they leave the machine: push them to the Hub instead of keeping
them on disk.

Examples
--------
Upload one report directory under ``experiments/<name>/``::

    python scripts/upload_to_hf.py reports/experiment-2026-11-08-hardened \
        --repo-id <user>/evil-ai-village

Upload every report directory (each becomes its own ``experiments/<name>/``)::

    python scripts/upload_to_hf.py reports --all-reports \
        --repo-id <user>/evil-ai-village

Dry run (manifest + secret scan, no network writes)::

    python scripts/upload_to_hf.py reports/experiment-2026-11-08-hardened \
        --repo-id <user>/evil-ai-village --dry-run

The token is read from ``--token``, ``$HF_TOKEN`` or ``$HUGGINGFACE_TOKEN``
(``.env`` is loaded automatically when present).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:  # optional dependency
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - dotenv is a core dep in practice
    load_dotenv = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Secret scanning
# ---------------------------------------------------------------------------
# High-confidence credential patterns. Anything matching these blocks upload
# unless --allow-secrets is passed. Keep this strict: a false positive is a
# warning we can override, a false negative leaks a key.
SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsk-or-[A-Za-z0-9_-]{20,}"), "OpenRouter key"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"), "Anthropic key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{32,}"), "OpenAI-style key"),
    (re.compile(r"\bhf_[A-Za-z0-9]{20,}"), "HuggingFace token"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "GitHub token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
]

TEXT_SUFFIXES = {
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".yaml",
    ".yml",
    ".py",
    ".sh",
    ".csv",
    ".tsv",
    ".log",
}
MAX_SCAN_BYTES = 64 * 1024 * 1024  # skip anything bigger than 64 MiB

DEFAULT_IGNORE = [
    ".env",
    "*.env",
    "*.pyc",
    "__pycache__/*",
    ".venv/*",
    "*.egg-info/*",
    ".git/*",
    ".DS_Store",
]


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f}PB"


def collect_files(
    path: Path, allow: list[str] | None = None, ignore: list[str] | None = None
) -> list[Path]:
    """Return regular files under *path*, filtered by glob patterns."""
    import fnmatch

    if path.is_file():
        candidates = [path]
        base = path.parent
    else:
        candidates = sorted(p for p in path.rglob("*") if p.is_file())
        base = path

    allow = allow or []
    ignore = ignore or []

    def matches(rel: str, patterns: list[str]) -> bool:
        for pat in patterns:
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, f"*/{pat}"):
                return True
            # directory-style patterns like "logs/" match the prefix
            if pat.endswith("/") and (rel == pat[:-1] or rel.startswith(pat)):
                return True
        return False

    out: list[Path] = []
    for f in candidates:
        rel = str(f.relative_to(base))
        if ignore and matches(rel, ignore):
            continue
        if allow and not matches(rel, allow):
            continue
        out.append(f)
    return out


def scan_secrets(files: list[Path], base: Path) -> list[dict[str, str]]:
    """Return a list of {file, kind} for files containing credential patterns."""
    hits: list[dict[str, str]] = []
    for f in files:
        if f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if f.stat().st_size > MAX_SCAN_BYTES:
                continue
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for pat, kind in SECRET_PATTERNS:
            if pat.search(text):
                hits.append({"file": str(f.relative_to(base)), "kind": kind})
                break
    return hits


# ---------------------------------------------------------------------------
# Dataset card
# ---------------------------------------------------------------------------
def _yaml_frontmatter(fm: dict) -> list[str]:
    """Render a simple YAML frontmatter block (no yaml dependency)."""
    parts = ["---"]
    for key, value in fm.items():
        if isinstance(value, list) and value and isinstance(value[0], str):
            parts.append(f"{key}:")
            for item in value:
                parts.append(f"  - {item}")
        else:
            parts.append(f"{key}: {value}")
    parts.append("---")
    return parts


def build_card(
    name: str,
    source: Path,
    repo_id: str,
    title: str | None,
    extra: dict | None = None,
) -> str:
    metrics: dict = {}
    metrics_path = source / "metrics.json"
    if metrics_path.is_file():
        try:
            metrics = json.loads(metrics_path.read_text())
        except Exception:
            metrics = {}

    readme = source / "README.md"
    summary = ""
    if readme.is_file():
        # Take the first paragraph-ish block, skip headings/frontmatter.
        lines = []
        for line in readme.read_text(errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("---"):
                if lines:
                    break
                continue
            lines.append(s)
        summary = " ".join(lines)[:1200]

    title = title or f"Evil AI Village — {name}"
    fm = {
        "license": "apache-2.0",
        "tags": [
            "ai-agents",
            "multi-agent",
            "social-simulation",
            "cybersecurity",
            "agent-societies",
        ],
        "pretty_name": title,
    }
    parts = _yaml_frontmatter(fm)
    parts.append("")
    parts.append(f"# {title}")
    parts.append("")
    if summary:
        parts.append(summary)
        parts.append("")
    parts.append(f"**Source directory:** `{source}`")
    parts.append(f"**Uploaded to:** `{repo_id}`")
    parts.append("")
    if metrics:
        parts.append("## Metrics")
        parts.append("")
        parts.append("```json")
        parts.append(json.dumps(metrics, indent=2, sort_keys=True))
        parts.append("```")
        parts.append("")
    if extra:
        parts.append("## Run metadata")
        parts.append("")
        parts.append("```json")
        parts.append(json.dumps(extra, indent=2, sort_keys=True))
        parts.append("```")
        parts.append("")
    parts.append("## Layout")
    parts.append("")
    parts.append(f"- `experiments/{name}/` — raw board, transcripts, graphs, metrics.")
    parts.append("")
    parts.append(
        "Generated by `scripts/upload_to_hf.py` in "
        "[evil-ai-village](https://github.com/anath2/evil-ai-village)."
    )
    parts.append("")
    return "\n".join(parts)


def _read_experiment(path: Path) -> dict:
    """Compact summary of one experiment directory."""
    metrics: dict = {}
    mp = path / "metrics.json"
    if mp.is_file():
        try:
            metrics = json.loads(mp.read_text())
        except Exception:
            pass
    summary = ""
    readme = path / "README.md"
    if readme.is_file():
        lines = []
        for line in readme.read_text(errors="ignore").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("---"):
                if lines:
                    break
                continue
            lines.append(s)
        summary = " ".join(lines)[:600]
    return {"name": path.name, "metrics": metrics, "summary": summary}


def build_dataset_card(
    experiments: list[dict],
    repo_id: str,
    title: str = "Evil AI Village",
) -> str:
    """Build a repo-wide card listing every experiment."""
    fm = {
        "license": "apache-2.0",
        "tags": [
            "ai-agents",
            "multi-agent",
            "social-simulation",
            "cybersecurity",
            "agent-societies",
        ],
        "pretty_name": title,
    }
    parts = _yaml_frontmatter(fm)
    parts.append("")
    parts.append(f"# {title}")
    parts.append("")
    parts.append(
        "Raw artifacts from multi-agent society experiments in "
        "[evil-ai-village](https://github.com/anath2/evil-ai-village): "
        "agents on a shared message board, a shared task, and a hardened "
        "verifier. Each experiment directory holds the board, per-agent "
        "transcripts, the social graph, and metrics."
    )
    parts.append("")
    parts.append("## Experiments")
    parts.append("")
    for exp in experiments:
        name = exp["name"]
        m = exp.get("metrics") or {}
        parts.append(f"### `{name}`")
        parts.append("")
        if exp.get("summary"):
            parts.append(exp["summary"])
            parts.append("")
        keys = [
            "agents", "completion_rate", "error_rate", "turn_yield",
            "solved", "cost_usd", "largest_coalition", "isolate_rate",
            "board_density", "participation_rate", "sandbox_lost",
        ]
        row = {k: m[k] for k in keys if k in m}
        if row:
            parts.append("```json")
            parts.append(json.dumps(row, indent=2, sort_keys=True))
            parts.append("```")
            parts.append("")
        parts.append(f"Artifacts: `experiments/{name}/`")
        parts.append("")
    parts.append("## Layout")
    parts.append("")
    parts.append(
        "`experiments/<name>/` — board.jsonl, logs/, social_graph.json, "
        "social_report.md, metrics.json, README.md."
    )
    parts.append("")
    parts.append("Generated by `scripts/upload_to_hf.py`.")
    parts.append("")
    return "\n".join(parts)


def write_dataset_card(
    api,
    repo_id: str,
    experiments: list[dict],
    title: str = "Evil AI Village",
    token: str | None = None,
) -> None:
    card = build_dataset_card(experiments, repo_id, title=title)
    api.upload_file(
        path_or_fileobj=card.encode(),
        path_in_repo="README.md",
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Add dataset card",
        token=token,
    )
    print("[hf] dataset card written to README.md")


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def _token(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for var in ("HF_TOKEN", "HUGGINGFACE_TOKEN", "HUGGING_FACE_HUB_TOKEN"):
        val = os.environ.get(var)
        if val:
            return val.strip()
    return None


def _repo_has_root_readme(api, repo_id: str) -> bool:
    try:
        files = api.list_repo_files(repo_id=repo_id, repo_type="dataset")
    except Exception:
        return False
    return "README.md" in files


def upload(
    source: Path,
    repo_id: str,
    *,
    private: bool = False,
    token: str | None = None,
    path_in_repo: str | None = None,
    message: str | None = None,
    allow: list[str] | None = None,
    ignore: list[str] | None = None,
    allow_secrets: bool = False,
    card: bool = True,
    force_card: bool = False,
    title: str | None = None,
    dry_run: bool = False,
) -> dict:
    base = source if source.is_dir() else source.parent
    name = source.name if source.is_dir() else source.stem
    files = collect_files(source, allow=allow, ignore=ignore)
    total = sum(f.stat().st_size for f in files)
    secret_hits = scan_secrets(files, base)

    report = {
        "source": str(source),
        "repo_id": repo_id,
        "name": name,
        "path_in_repo": path_in_repo or f"experiments/{name}",
        "files": len(files),
        "bytes": total,
        "secret_hits": secret_hits,
        "dry_run": dry_run,
    }

    if secret_hits and not allow_secrets:
        print("REFUSING to upload: possible credentials found.", file=sys.stderr)
        for hit in secret_hits:
            print(f"  - {hit['file']}: {hit['kind']}", file=sys.stderr)
        print("Re-run with --allow-secrets to override.", file=sys.stderr)
        report["status"] = "blocked"
        return report

    if dry_run:
        print(f"[dry-run] repo   : {repo_id} (dataset, private={private})")
        print(f"[dry-run] source : {source}")
        print(f"[dry-run] target : {report['path_in_repo']}/")
        print(f"[dry-run] files  : {len(files)} ({_human(total)})")
        for f in files[:40]:
            print(f"          {f.relative_to(base)}  ({_human(f.stat().st_size)})")
        if len(files) > 40:
            print(f"          ... and {len(files) - 40} more")
        if secret_hits:
            print(f"[dry-run] secret scan: {len(secret_hits)} hit(s) (overridden)")
        else:
            print("[dry-run] secret scan: clean")
        report["status"] = "dry-run"
        return report

    tok = _token(token)
    if not tok:
        print(
            "No HuggingFace token. Set HF_TOKEN (or --token). "
            "Create one at https://huggingface.co/settings/tokens",
            file=sys.stderr,
        )
        report["status"] = "no-token"
        return report

    from huggingface_hub import HfApi

    api = HfApi(token=tok)
    api.create_repo(
        repo_id=repo_id,
        repo_type="dataset",
        private=private,
        exist_ok=True,
    )
    print(f"[hf] repo ready: {repo_id} (dataset)")

    commit = api.upload_folder(
        folder_path=str(source),
        path_in_repo=report["path_in_repo"],
        repo_id=repo_id,
        repo_type="dataset",
        commit_message=message or f"Add {name}",
        ignore_patterns=DEFAULT_IGNORE + list(ignore or []),
        allow_patterns=allow or None,
        token=tok,
    )
    report["commit"] = getattr(commit, "commit_url", None) or str(commit)
    print(f"[hf] uploaded {len(files)} files ({_human(total)}) -> {report['path_in_repo']}/")
    print(f"[hf] commit: {report['commit']}")

    if card and (force_card or not _repo_has_root_readme(api, repo_id)):
        card_md = build_card(
            name=name,
            source=source if source.is_dir() else base,
            repo_id=repo_id,
            title=title,
            extra={"source": str(source), "path_in_repo": report["path_in_repo"]},
        )
        api.upload_file(
            path_or_fileobj=card_md.encode(),
            path_in_repo="README.md",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message="Add dataset card",
            token=tok,
        )
        print("[hf] dataset card written to README.md")

    report["status"] = "uploaded"
    return report


# ---------------------------------------------------------------------------
# Token diagnostics
# ---------------------------------------------------------------------------
def check_token(token: str | None = None) -> int:
    """Print who the token is and whether it can create/upload datasets."""
    tok = _token(token)
    if not tok:
        print("No HuggingFace token. Set HF_TOKEN in .env (or --token).", file=sys.stderr)
        return 1
    from huggingface_hub import HfApi

    try:
        me = HfApi(token=tok).whoami()
    except Exception as exc:
        print(f"auth FAILED: {exc}", file=sys.stderr)
        return 1

    auth = me.get("auth") or {}
    at = auth.get("accessToken") or {}
    fg = at.get("fineGrained") or {}
    perms: set[str] = set(fg.get("global") or [])
    for scope in fg.get("scoped") or []:
        perms.update(scope.get("permissions") or [])

    print(f"user      : {me.get('name')} ({me.get('type')})")
    print(f"token     : {at.get('displayName') or '(unknown)'}")
    print(f"role      : {at.get('role') or '(classic/unknown)'}")
    print(f"permissions: {sorted(perms) or '(none listed)'}")

    role = (at.get("role") or "").lower()
    can_write = (
        role == "write"
        or "repo.content.write" in perms
        or "repo.create" in perms
    )
    print(f"can upload: {'YES' if can_write else 'NO'}")
    if not can_write:
        print(
            "  -> create a token with write access at "
            "https://huggingface.co/settings/tokens"
            " (fine-grained: repo.create + repo.content.write + repo.delete)",
            file=sys.stderr,
        )
    return 0 if can_write else 2


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------
def smoke_test(
    repo_id: str | None = None,
    token: str | None = None,
    private: bool = True,
) -> int:
    """End-to-end check: create a temp private repo, upload, verify, delete.

    Confirms the token, repo creation, upload, and listing all work without
    touching the real dataset repo or leaving anything behind.
    """
    import tempfile
    import time

    from huggingface_hub import HfApi

    tok = _token(token)
    if not tok:
        print("No HuggingFace token. Set HF_TOKEN in .env (or --token).", file=sys.stderr)
        return 1

    api = HfApi(token=tok)
    try:
        me = api.whoami()
    except Exception as exc:
        print(f"[smoke] auth FAILED: {exc}", file=sys.stderr)
        return 1
    user = me.get("name")
    print(f"[smoke] auth OK: {user}")

    repo = repo_id or f"{user}/evil-ai-village-smoke-{int(time.time())}"
    print(f"[smoke] repo: {repo} (private={private})")

    tmp = Path(tempfile.mkdtemp(prefix="village-smoke-"))
    try:
        (tmp / "README.md").write_text("# smoke test\n\nTemporary upload check.\n")
        (tmp / "metrics.json").write_text(
            json.dumps({"smoke": True, "ts": time.time()})
        )
        api.create_repo(repo_id=repo, repo_type="dataset", private=private, exist_ok=True)
        print("[smoke] repo created/ready")
        commit = api.upload_folder(
            folder_path=str(tmp),
            repo_id=repo,
            repo_type="dataset",
            commit_message="smoke test",
        )
        print(f"[smoke] uploaded: {getattr(commit, 'commit_url', commit)}")
        files = sorted(api.list_repo_files(repo_id=repo, repo_type="dataset"))
        print(f"[smoke] files in repo: {files}")
        ok = "README.md" in files and "metrics.json" in files
        print(f"[smoke] verify: {'PASS' if ok else 'FAIL'}")
        return 0 if ok else 1
    except Exception as exc:
        msg = str(exc)
        print(f"[smoke] FAILED: {msg}", file=sys.stderr)
        if "403" in msg or "permission" in msg.lower():
            print(
                "[smoke] hint: this token looks read-only. Create a write token "
                "(fine-grained: repo.create + repo.content.write + repo.delete) "
                "at https://huggingface.co/settings/tokens",
                file=sys.stderr,
            )
        return 1
    finally:
        try:
            api.delete_repo(repo_id=repo, repo_type="dataset")
            print(f"[smoke] deleted {repo}")
        except Exception as exc:  # pragma: no cover
            print(f"[smoke] cleanup failed ({repo}): {exc}", file=sys.stderr)
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Upload village experiment data to a HuggingFace dataset repo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("path", nargs="?", help="File or directory to upload.")
    ap.add_argument("--repo-id", default=None, help="Dataset repo, e.g. user/evil-ai-village")
    ap.add_argument("--smoke-test", action="store_true",
                    help="Create a temp private repo, upload a tiny payload, verify, delete.")
    ap.add_argument("--check-token", action="store_true",
                    help="Print the token's identity and upload permissions, then exit.")
    ap.add_argument("--all-reports", action="store_true",
                    help="Upload every subdirectory of PATH as its own experiment.")
    ap.add_argument("--private", action="store_true", help="Create the repo as private.")
    ap.add_argument("--token", default=None, help="HF token (default: $HF_TOKEN).")
    ap.add_argument("--path-in-repo", default=None,
                    help="Target directory inside the repo (default: experiments/<name>).")
    ap.add_argument("--message", default=None, help="Commit message.")
    ap.add_argument("--include", action="append", default=None, help="Glob(s) to include.")
    ap.add_argument("--exclude", action="append", default=None, help="Glob(s) to exclude.")
    ap.add_argument("--allow-secrets", action="store_true",
                    help="Upload even if credential-like strings are found.")
    ap.add_argument("--no-card", action="store_true", help="Do not write a dataset card.")
    ap.add_argument("--force-card", action="store_true",
                    help="Rewrite the dataset card even if the repo already has a README.md.")
    ap.add_argument("--title", default=None, help="Dataset card title.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Show manifest + secret scan; make no network writes.")
    ap.add_argument("--json", action="store_true", help="Print the report as JSON.")
    args = ap.parse_args(argv)

    if load_dotenv:
        load_dotenv()

    if args.check_token:
        return check_token(token=args.token)

    if args.smoke_test:
        return smoke_test(repo_id=args.repo_id, token=args.token)

    if not args.path:
        ap.error("path is required unless --smoke-test is used")
    if not args.repo_id:
        ap.error("--repo-id is required unless --smoke-test is used")

    source = Path(args.path).expanduser().resolve()
    if not source.exists():
        print(f"Path not found: {source}", file=sys.stderr)
        return 2

    targets: list[Path]
    if args.all_reports:
        if not source.is_dir():
            print("--all-reports requires a directory.", file=sys.stderr)
            return 2
        targets = sorted(p for p in source.iterdir() if p.is_dir())
        if not targets:
            print(f"No subdirectories under {source}", file=sys.stderr)
            return 2
    else:
        targets = [source]

    reports = []
    failed = False
    for target in targets:
        try:
            rep = upload(
                target,
                args.repo_id,
                private=args.private,
                token=args.token,
                path_in_repo=args.path_in_repo if len(targets) == 1 else None,
                message=args.message,
                allow=args.include,
                ignore=args.exclude,
                allow_secrets=args.allow_secrets,
                card=not args.no_card and not args.all_reports,
                force_card=args.force_card,
                title=args.title,
                dry_run=args.dry_run,
            )
        except Exception as exc:  # network / auth errors
            print(f"[hf] upload failed for {target}: {exc}", file=sys.stderr)
            rep = {"source": str(target), "status": "error", "error": str(exc)}
            failed = True
        reports.append(rep)

    if args.all_reports and not args.no_card and not args.dry_run:
        tok = _token(args.token)
        if tok:
            from huggingface_hub import HfApi

            api = HfApi(token=tok)
            exps = [_read_experiment(t) for t in targets]
            try:
                write_dataset_card(
                    api,
                    args.repo_id,
                    exps,
                    title=args.title or "Evil AI Village",
                    token=tok,
                )
            except Exception as exc:  # non-fatal
                print(f"[hf] dataset card failed: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        print()
        print("Summary")
        print("-------")
        for rep in reports:
            print(
                f"  {rep.get('status', '?'):9s}  {rep.get('name', '?'):40s}  "
                f"{rep.get('files', 0):4d} files  {_human(rep.get('bytes', 0))}"
            )
        print(f"  repo: https://huggingface.co/datasets/{args.repo_id}")

    if any(rep.get("status") in ("blocked", "no-token", "error") for rep in reports):
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
