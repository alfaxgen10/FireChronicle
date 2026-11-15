"""Regression tests for ``pipeline.ingest.resolve_manifest_path`` hardening."""

import os
import shutil
import sys
from pathlib import Path

import pytest

import pipeline.ingest as ingest
from pipeline.config import SENSOR_MODIS, SENSOR_VIIRS

VALID = "data/raw/modis/archive/fire_archive_M-C61_849850.csv"


@pytest.fixture
def repo(tmp_path):
    """A minimal repository containing one raw source file."""
    root = tmp_path / "repo"
    source = root.joinpath(*VALID.split("/"))
    source.parent.mkdir(parents=True)
    source.write_bytes(b"latitude,longitude\n")
    return root


def _link_directory(link: Path, target: Path) -> None:
    """Create a directory symlink, or a Windows junction if symlinks need privileges."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    if sys.platform == "win32":
        try:
            import _winapi
            _winapi.CreateJunction(str(target), str(link))
            return
        except (ImportError, AttributeError, OSError):
            pass
    pytest.skip("platform does not permit creating a directory link")


# --- valid paths -------------------------------------------------------------

def test_accepts_valid_relative_path(repo):
    resolved = ingest.resolve_manifest_path(VALID, project_root=repo, require_file=True)
    assert resolved == repo.joinpath(*VALID.split("/"))
    assert resolved.is_file()


def test_accepts_valid_path_whose_file_is_absent(repo):
    # Raw data are not distributed, so a clone may lack the file; syntax still resolves.
    missing = "data/raw/viirs/nrt/fire_nrt_J1V-C2_849851.csv"
    assert ingest.resolve_manifest_path(missing, project_root=repo) == repo.joinpath(*missing.split("/"))


def test_relocated_repository_still_resolves(repo, tmp_path):
    moved = tmp_path / "moved" / "elsewhere" / "repo"
    shutil.copytree(repo, moved)
    shutil.rmtree(repo)
    resolved = ingest.resolve_manifest_path(VALID, project_root=moved, require_file=True)
    assert resolved.is_file()
    assert resolved.resolve().is_relative_to(moved.resolve())


@pytest.mark.parametrize("sensor,subdir", [(SENSOR_MODIS, "modis"), (SENSOR_VIIRS, "viirs")])
def test_writer_output_is_accepted_by_resolver(repo, sensor, subdir):
    sensor_dir = repo / "data" / "raw" / subdir
    path = sensor_dir / "archive" / "fire_archive_X_1.csv"
    recorded = ingest.portable_source_path(path, sensor_dir, sensor)
    assert ingest.resolve_manifest_path(recorded, project_root=repo) == path


# --- rejected stored forms ----------------------------------------------------

@pytest.mark.parametrize("bad", ["", None, 123])
def test_rejects_empty_or_non_string(repo, bad):
    with pytest.raises(ValueError):
        ingest.resolve_manifest_path(bad, project_root=repo)


@pytest.mark.parametrize("bad", [
    "C:/Users/someone/x.csv",
    "C:\\Users\\someone\\x.csv",
    "c:/x.csv",
    "C:data/raw/x.csv",          # drive-relative
    "C:",
    "data/C:/x.csv",             # drive segment mid-path
    "\\\\?\\C:\\x.csv",          # extended-length
    "file:///etc/passwd",
    "data/raw/x.csv:stream",     # NTFS alternate data stream
])
def test_rejects_drive_prefixes_and_colons(repo, bad):
    with pytest.raises(ValueError):
        ingest.resolve_manifest_path(bad, project_root=repo)


@pytest.mark.parametrize("bad", ["/home/someone/x.csv", "/data/raw/x.csv", "//server/share/x.csv"])
def test_rejects_posix_absolute(repo, bad):
    with pytest.raises(ValueError):
        ingest.resolve_manifest_path(bad, project_root=repo)


@pytest.mark.parametrize("bad", [
    "data\\raw\\modis\\x.csv",
    "data/raw\\modis/x.csv",
    "\\x.csv",
    "\\\\server\\share\\x.csv",
])
def test_rejects_backslashes(repo, bad):
    with pytest.raises(ValueError):
        ingest.resolve_manifest_path(bad, project_root=repo)


@pytest.mark.parametrize("bad", [
    "../outside.csv",
    "data/raw/../../outside.csv",
    "data/..",
    "..",
    "./data/raw/x.csv",
    "data/./raw/x.csv",
    "data//raw/x.csv",
    "data/raw/",
])
def test_rejects_traversal_and_non_canonical_segments(repo, bad):
    with pytest.raises(ValueError):
        ingest.resolve_manifest_path(bad, project_root=repo)


def test_rejects_control_characters(repo):
    with pytest.raises(ValueError):
        ingest.resolve_manifest_path("data/raw/x\x00.csv", project_root=repo)


# --- filesystem checks --------------------------------------------------------

def test_rejects_directory_target(repo):
    with pytest.raises(ValueError, match="directory"):
        ingest.resolve_manifest_path("data/raw/modis/archive", project_root=repo)


def test_require_file_rejects_missing_file(repo):
    with pytest.raises(ValueError, match="not found"):
        ingest.resolve_manifest_path(
            "data/raw/modis/archive/missing.csv", project_root=repo, require_file=True
        )


def test_rejects_symlink_escaping_repository(repo, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.csv").write_bytes(b"s")
    _link_directory(repo / "data" / "raw" / "escape", outside)

    with pytest.raises(ValueError, match="outside the repository"):
        ingest.resolve_manifest_path("data/raw/escape/secret.csv", project_root=repo)


def test_accepts_symlink_that_stays_inside_repository(repo):
    _link_directory(repo / "data" / "raw" / "alias", repo / "data" / "raw" / "modis")
    resolved = ingest.resolve_manifest_path(
        "data/raw/alias/archive/fire_archive_M-C61_849850.csv",
        project_root=repo,
        require_file=True,
    )
    assert resolved.is_file()
