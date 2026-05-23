import json

import pytest

from scripts.backup_local import create_backup
from scripts.restore_local import restore_backup


def write_file(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_backup_copies_db_uploads_and_archive_exports(tmp_path):
    write_file(tmp_path / "lift_crm.db", b"sqlite")
    write_file(tmp_path / "uploads" / "ticket-1" / "photo.jpg", b"photo")
    write_file(tmp_path / "archive.xlsx", b"archive")
    write_file(tmp_path / "assets_export.csv", b"id,name\n")
    write_file(tmp_path / "assets_export.xlsx", b"xlsx")

    backup_dir, manifest = create_backup(root=tmp_path, timestamp="20260523-180000")

    assert (backup_dir / "lift_crm.db").read_bytes() == b"sqlite"
    assert (backup_dir / "uploads" / "ticket-1" / "photo.jpg").read_bytes() == b"photo"
    assert (backup_dir / "archive.xlsx").read_bytes() == b"archive"
    assert (backup_dir / "assets_export.csv").read_bytes() == b"id,name\n"
    assert (backup_dir / "assets_export.xlsx").read_bytes() == b"xlsx"
    assert manifest["warnings"] == []
    copied_sources = {entry["source"] for entry in manifest["copied"]}
    assert "lift_crm.db" in copied_sources
    assert "uploads/ticket-1/photo.jpg" in copied_sources
    assert "archive.xlsx" in copied_sources


def test_backup_succeeds_when_optional_files_are_missing(tmp_path):
    backup_dir, manifest = create_backup(root=tmp_path, timestamp="20260523-180001")

    assert backup_dir.exists()
    assert (backup_dir / "manifest.json").exists()
    assert manifest["copied"] == []
    assert any("lift_crm.db not found" in warning for warning in manifest["warnings"])
    assert any("uploads/ not found" in warning for warning in manifest["warnings"])
    assert any("No archive/export files found" in warning for warning in manifest["warnings"])


def test_backup_writes_manifest_with_sizes(tmp_path):
    write_file(tmp_path / "lift_crm.db", b"12345")

    backup_dir, _ = create_backup(root=tmp_path, timestamp="20260523-180002")
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))

    db_entry = next(entry for entry in manifest["copied"] if entry["source"] == "lift_crm.db")
    assert db_entry["backup_path"] == "lift_crm.db"
    assert db_entry["size_bytes"] == 5
    assert manifest["backup_name"] == "20260523-180002"


def test_restore_refuses_overwrite_without_force(tmp_path):
    source_root = tmp_path / "source"
    restore_root = tmp_path / "restore"
    write_file(source_root / "lift_crm.db", b"backup-db")
    write_file(restore_root / "lift_crm.db", b"current-db")
    backup_dir, _ = create_backup(root=source_root, timestamp="20260523-180003")

    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        restore_backup(backup_dir, root=restore_root)

    assert (restore_root / "lift_crm.db").read_bytes() == b"current-db"


def test_restore_with_force_restores_into_temp_directory(tmp_path):
    source_root = tmp_path / "source"
    restore_root = tmp_path / "restore"
    write_file(source_root / "lift_crm.db", b"backup-db")
    write_file(source_root / "uploads" / "photo.jpg", b"backup-photo")
    write_file(source_root / "archive.xlsx", b"backup-archive")
    write_file(restore_root / "lift_crm.db", b"current-db")
    write_file(restore_root / "uploads" / "old.txt", b"old-upload")
    backup_dir, _ = create_backup(root=source_root, timestamp="20260523-180004")

    result = restore_backup(backup_dir, root=restore_root, force=True)

    assert (restore_root / "lift_crm.db").read_bytes() == b"backup-db"
    assert (restore_root / "uploads" / "photo.jpg").read_bytes() == b"backup-photo"
    assert not (restore_root / "uploads" / "old.txt").exists()
    assert (restore_root / "archive.xlsx").read_bytes() == b"backup-archive"
    restored_sources = {entry["source"] for entry in result["restored"]}
    assert {"lift_crm.db", "uploads", "archive.xlsx"} <= restored_sources
