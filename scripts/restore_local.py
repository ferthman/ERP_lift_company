import argparse
import json
import shutil
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_NAME = "lift_crm.db"
UPLOADS_DIR_NAME = "uploads"
ARCHIVE_EXPORT_PATTERNS = ("archive*.xlsx", "*export*.xlsx", "*export*.csv")


def archive_export_files(backup_dir):
    files = set()
    for pattern in ARCHIVE_EXPORT_PATTERNS:
        files.update(path for path in backup_dir.glob(pattern) if path.is_file())
    return sorted(files)


def load_manifest(backup_dir):
    manifest_path = backup_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def planned_restores(backup_dir, root):
    restores = []
    db_backup = backup_dir / DB_NAME
    if db_backup.exists():
        restores.append((db_backup, root / DB_NAME, "file"))

    uploads_backup = backup_dir / UPLOADS_DIR_NAME
    if uploads_backup.exists() and uploads_backup.is_dir():
        restores.append((uploads_backup, root / UPLOADS_DIR_NAME, "directory"))

    for backup_file in archive_export_files(backup_dir):
        restores.append((backup_file, root / backup_file.name, "file"))

    return restores


def existing_restore_targets(restores):
    return [target for _, target, _ in restores if target.exists()]


def restore_backup(backup_dir, root=ROOT_DIR, force=False):
    backup_dir = Path(backup_dir).resolve()
    root = Path(root).resolve()
    if not backup_dir.exists() or not backup_dir.is_dir():
        raise FileNotFoundError(f"Backup folder not found: {backup_dir}")

    manifest = load_manifest(backup_dir)
    restores = planned_restores(backup_dir, root)
    if not restores:
        raise RuntimeError(f"No restorable local data found in backup: {backup_dir}")

    existing_targets = existing_restore_targets(restores)
    if existing_targets and not force:
        targets = ", ".join(str(path) for path in existing_targets)
        raise RuntimeError(
            "Refusing to overwrite current local data without --force. "
            f"Existing targets: {targets}"
        )

    root.mkdir(parents=True, exist_ok=True)
    restored = []
    for source, target, kind in restores:
        if kind == "directory":
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        restored.append(
            {
                "source": source.relative_to(backup_dir).as_posix(),
                "target": str(target),
                "type": kind,
            }
        )

    return {
        "backup_dir": str(backup_dir),
        "root": str(root),
        "manifest": manifest,
        "restored": restored,
    }


def print_summary(result):
    print(f"Restored backup: {result['backup_dir']}")
    print(f"Restore target: {result['root']}")
    print(f"Restored items: {len(result['restored'])}")
    for item in result["restored"]:
        print(f"- {item['source']} -> {item['target']}")
    print("WARNING: Restart the Flask app after restoring local data.")
    print("Verify by starting the app, logging in, checking tickets/assets, uploads, and archive export.")


def parse_args():
    parser = argparse.ArgumentParser(description="Restore a local Lift CRM backup.")
    parser.add_argument("backup_folder", help="Path to a backup folder created by scripts/backup_local.py.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing local lift_crm.db, uploads/, and archive/export files.",
    )
    parser.add_argument(
        "--root",
        default=str(ROOT_DIR),
        help="Project root to restore into. Defaults to the repository root.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = restore_backup(args.backup_folder, root=args.root, force=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}")
        print("Restore aborted. Re-run with --force only after creating a fresh backup of current data.")
        raise SystemExit(1) from exc
    print_summary(result)


if __name__ == "__main__":
    main()
