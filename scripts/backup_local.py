import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKUPS_DIR_NAME = "backups"
DB_NAME = "lift_crm.db"
UPLOADS_DIR_NAME = "uploads"
ARCHIVE_EXPORT_PATTERNS = ("archive*.xlsx", "*export*.xlsx", "*export*.csv")


def utc_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def relative_to_root(path, root):
    return path.relative_to(root).as_posix()


def file_size(path):
    return path.stat().st_size


def copy_file(source, destination, root, manifest):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    manifest["copied"].append(
        {
            "source": relative_to_root(source, root),
            "backup_path": destination.relative_to(manifest["_backup_dir"]).as_posix(),
            "type": "file",
            "size_bytes": file_size(destination),
        }
    )


def copy_directory(source, destination, root, manifest):
    destination.mkdir(parents=True, exist_ok=True)
    manifest["copied"].append(
        {
            "source": relative_to_root(source, root),
            "backup_path": destination.relative_to(manifest["_backup_dir"]).as_posix(),
            "type": "directory",
            "size_bytes": sum(file_size(path) for path in source.rglob("*") if path.is_file()),
        }
    )
    for file_path in sorted(path for path in source.rglob("*") if path.is_file()):
        relative_path = file_path.relative_to(source)
        copy_file(file_path, destination / relative_path, root, manifest)


def archive_export_files(root):
    files = set()
    for pattern in ARCHIVE_EXPORT_PATTERNS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(files)


def create_backup(root=ROOT_DIR, timestamp=None):
    root = Path(root).resolve()
    backup_root = root / BACKUPS_DIR_NAME
    backup_name = timestamp or utc_timestamp()
    backup_dir = backup_root / backup_name
    counter = 1
    while backup_dir.exists():
        backup_dir = backup_root / f"{backup_name}-{counter}"
        counter += 1
    backup_dir.mkdir(parents=True)

    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "backup_name": backup_dir.name,
        "source_root": str(root),
        "copied": [],
        "warnings": [],
        "_backup_dir": backup_dir,
    }

    db_path = root / DB_NAME
    if db_path.exists():
        copy_file(db_path, backup_dir / DB_NAME, root, manifest)
    else:
        manifest["warnings"].append(f"{DB_NAME} not found; database was not backed up.")

    uploads_path = root / UPLOADS_DIR_NAME
    if uploads_path.exists() and uploads_path.is_dir():
        copy_directory(uploads_path, backup_dir / UPLOADS_DIR_NAME, root, manifest)
    else:
        manifest["warnings"].append(f"{UPLOADS_DIR_NAME}/ not found; uploads were not backed up.")

    export_files = archive_export_files(root)
    if export_files:
        for source in export_files:
            copy_file(source, backup_dir / source.name, root, manifest)
    else:
        manifest["warnings"].append("No archive/export files found; archive exports were not backed up.")

    manifest_path = backup_dir / "manifest.json"
    serializable_manifest = {key: value for key, value in manifest.items() if not key.startswith("_")}
    manifest_path.write_text(json.dumps(serializable_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return backup_dir, serializable_manifest


def print_summary(backup_dir, manifest):
    print(f"Backup created: {backup_dir}")
    print(f"Copied files: {len(manifest['copied'])}")
    for warning in manifest["warnings"]:
        print(f"WARNING: {warning}")
    print(f"Manifest: {backup_dir / 'manifest.json'}")


def parse_args():
    parser = argparse.ArgumentParser(description="Create a local Lift CRM backup.")
    parser.add_argument(
        "--root",
        default=str(ROOT_DIR),
        help="Project root to back up. Defaults to the repository root.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    backup_dir, manifest = create_backup(root=args.root)
    print_summary(backup_dir, manifest)


if __name__ == "__main__":
    main()
