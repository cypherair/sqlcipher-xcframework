#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import plistlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_LIBRARIES = {
    "ios-arm64_arm64e": {
        "platform": "ios",
        "variant": None,
        "architectures": ["arm64", "arm64e"],
    },
    "macos-arm64_arm64e": {
        "platform": "macos",
        "variant": None,
        "architectures": ["arm64", "arm64e"],
    },
    "xros-arm64_arm64e": {
        "platform": "xros",
        "variant": None,
        "architectures": ["arm64", "arm64e"],
    },
    "ios-arm64-simulator": {
        "platform": "ios",
        "variant": "simulator",
        "architectures": ["arm64"],
    },
    "xros-arm64-simulator": {
        "platform": "xros",
        "variant": "simulator",
        "architectures": ["arm64"],
    },
}

REQUIRED_HEADERS = ["SQLCipher.h", "sqlite3.h", "sqlite3ext.h", "sqlite3session.h", "module.modulemap"]
COMPILE_OPTIONS = ["SQLITE_HAS_CODEC", "SQLITE_TEMP_STORE=2"]
LINK_FRAMEWORKS = ["Security", "CoreFoundation", "Foundation"]
CFLAGS = [
    "-DNDEBUG",
    "-DSQLCIPHER_CRYPTO_CC",
    "-DSQLITE_HAS_CODEC",
    "-DSQLITE_TEMP_STORE=2",
    "-DSQLITE_THREADSAFE=1",
    "-DSQLITE_EXTRA_INIT=sqlcipher_extra_init",
    "-DSQLITE_EXTRA_SHUTDOWN=sqlcipher_extra_shutdown",
]


class ValidationError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate CypherAir SQLCipher XCFramework outputs.")
    parser.add_argument("--xcframework", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--source-repository", default="https://github.com/sqlcipher/sqlcipher.git")
    parser.add_argument("--source-tag", default="v4.16.0")
    parser.add_argument("--source-commit", default="e2a6040f2ae5cfff2b3e08eb3320007d93cdf3fc")
    parser.add_argument("--xcframework-zip", type=Path)
    parser.add_argument("--checksum-file", type=Path)
    parser.add_argument("--privacy-manifest", type=Path)
    return parser.parse_args()


def run(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True)
    return completed.stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_plist(path: Path) -> dict:
    with path.open("rb") as handle:
        return plistlib.load(handle)


def validate_xcframework(xcframework: Path) -> list[dict]:
    info_path = xcframework / "Info.plist"
    if not info_path.is_file():
        raise ValidationError(f"XCFramework Info.plist is missing: {info_path}")

    info = load_plist(info_path)
    libraries = info.get("AvailableLibraries")
    if not isinstance(libraries, list):
        raise ValidationError("XCFramework AvailableLibraries is missing or not a list")

    by_identifier = {str(entry.get("LibraryIdentifier")): entry for entry in libraries}
    expected_ids = set(EXPECTED_LIBRARIES)
    actual_ids = set(by_identifier)
    if actual_ids != expected_ids:
        raise ValidationError(f"unexpected library identifiers: actual={sorted(actual_ids)} expected={sorted(expected_ids)}")

    normalized: list[dict] = []
    for identifier, expected in EXPECTED_LIBRARIES.items():
        entry = by_identifier[identifier]
        platform_name = entry.get("SupportedPlatform")
        variant = entry.get("SupportedPlatformVariant")
        architectures = list(entry.get("SupportedArchitectures") or [])
        library_path = entry.get("LibraryPath")
        binary_path = entry.get("BinaryPath")
        headers_path = entry.get("HeadersPath")

        if platform_name != expected["platform"]:
            raise ValidationError(f"{identifier}: platform {platform_name!r} != {expected['platform']!r}")
        if (variant or None) != expected["variant"]:
            raise ValidationError(f"{identifier}: variant {variant!r} != {expected['variant']!r}")
        if architectures != expected["architectures"]:
            raise ValidationError(f"{identifier}: architectures {architectures!r} != {expected['architectures']!r}")
        if library_path != "libSQLCipher.a" or binary_path != "libSQLCipher.a":
            raise ValidationError(f"{identifier}: expected static libSQLCipher.a, got {library_path!r}/{binary_path!r}")
        if headers_path != "Headers":
            raise ValidationError(f"{identifier}: expected Headers path, got {headers_path!r}")

        library = xcframework / identifier / "libSQLCipher.a"
        if not library.is_file():
            raise ValidationError(f"{identifier}: static library is missing: {library}")

        lipo_archs = run(["lipo", "-archs", str(library)]).split()
        if lipo_archs != expected["architectures"]:
            raise ValidationError(f"{identifier}: lipo archs {lipo_archs!r} != {expected['architectures']!r}")

        headers = xcframework / identifier / "Headers"
        for header in REQUIRED_HEADERS:
            if not (headers / header).is_file():
                raise ValidationError(f"{identifier}: required header is missing: {header}")

        normalized.append(
            {
                "identifier": identifier,
                "platform": platform_name,
                "variant": variant,
                "architectures": architectures,
                "libraryPath": library_path,
                "sha256": sha256(library),
            }
        )

    return normalized


def validate_checksum_file(checksum_file: Path, xcframework_zip: Path) -> str:
    if not checksum_file.is_file():
        raise ValidationError(f"checksum file is missing: {checksum_file}")
    if not xcframework_zip.is_file():
        raise ValidationError(f"XCFramework zip is missing: {xcframework_zip}")

    actual = sha256(xcframework_zip)
    text = checksum_file.read_text(encoding="utf-8").strip()
    recorded = text.split()[0] if text else ""
    if recorded != actual:
        raise ValidationError(f"checksum file records {recorded}, expected {actual}")
    if xcframework_zip.name not in text:
        raise ValidationError(f"checksum file must reference {xcframework_zip.name}")
    return actual


def validate_privacy_manifest(path: Path) -> dict:
    if not path.is_file():
        raise ValidationError(f"privacy manifest is missing: {path}")
    payload = load_plist(path)
    if payload.get("NSPrivacyTracking") is not False:
        raise ValidationError("privacy manifest must declare NSPrivacyTracking=false")
    accessed = payload.get("NSPrivacyAccessedAPITypes")
    if not isinstance(accessed, list) or not accessed:
        raise ValidationError("privacy manifest must include accessed API declarations")
    return {"path": str(path), "sha256": sha256(path), "payload": payload}


def smoke_test(xcframework: Path) -> dict:
    host = platform.machine()
    if host not in {"arm64", "arm64e"}:
        return {"status": "skipped", "reason": f"host architecture {host!r} cannot run arm64 smoke binary"}

    identifier = "macos-arm64_arm64e"
    headers = xcframework / identifier / "Headers"
    library = xcframework / identifier / "libSQLCipher.a"

    source = r'''
#include "SQLCipher.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int capture(void *ctx, int argc, char **argv, char **col) {
  (void)argc;
  (void)col;
  snprintf((char *)ctx, 256, "%s", (argv && argv[0]) ? argv[0] : "");
  return 0;
}

static int exec_sql(sqlite3 *db, const char *sql) {
  char *errmsg = NULL;
  int rc = sqlite3_exec(db, sql, NULL, NULL, &errmsg);
  if (rc != SQLITE_OK) {
    fprintf(stderr, "%s -> %s\n", sql, errmsg ? errmsg : "unknown");
    sqlite3_free(errmsg);
  }
  return rc;
}

static int query_value(sqlite3 *db, const char *sql, char *value, size_t value_len) {
  char *errmsg = NULL;
  value[0] = '\0';
  int rc = sqlite3_exec(db, sql, capture, value, &errmsg);
  if (rc != SQLITE_OK) {
    fprintf(stderr, "%s -> %s\n", sql, errmsg ? errmsg : "unknown");
    sqlite3_free(errmsg);
    return rc;
  }
  return value[0] == '\0' ? SQLITE_ERROR : SQLITE_OK;
}

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  const char *path = argv[1];
  const char *good_key = "PRAGMA key = \"x'000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f'\";";
  const char *bad_key = "PRAGMA key = \"x'1f1e1d1c1b1a191817161514131211100f0e0d0c0b0a09080706050403020100'\";";
  sqlite3 *db = NULL;
  char value[256] = {0};

  if (sqlite3_open(":memory:", &db) != SQLITE_OK) return 10;
  if (query_value(db, "PRAGMA cipher_version;", value, sizeof(value)) != SQLITE_OK) return 11;
  if (strncmp(value, "4.16.0", 6) != 0 || strstr(value, "community") == NULL) return 12;
  sqlite3_close(db);

  if (!sqlite3_compileoption_used("SQLITE_HAS_CODEC")) return 13;
  if (!sqlite3_compileoption_used("SQLITE_TEMP_STORE=2")) return 14;

  remove(path);
  if (sqlite3_open(path, &db) != SQLITE_OK) return 20;
  if (exec_sql(db, good_key) != SQLITE_OK) return 21;
  if (exec_sql(db, "CREATE TABLE t(v TEXT);") != SQLITE_OK) return 22;
  if (exec_sql(db, "INSERT INTO t VALUES('hello');") != SQLITE_OK) return 23;
  sqlite3_close(db);

  if (sqlite3_open(path, &db) != SQLITE_OK) return 30;
  if (exec_sql(db, good_key) != SQLITE_OK) return 31;
  if (query_value(db, "SELECT v FROM t;", value, sizeof(value)) != SQLITE_OK) return 32;
  if (strcmp(value, "hello") != 0) return 33;
  sqlite3_close(db);

  if (sqlite3_open(path, &db) != SQLITE_OK) return 40;
  if (exec_sql(db, bad_key) != SQLITE_OK) return 41;
  int wrong_key_rc = query_value(db, "SELECT v FROM t;", value, sizeof(value));
  sqlite3_close(db);
  remove(path);
  if (wrong_key_rc == SQLITE_OK) return 42;

  return 0;
}
'''

    with tempfile.TemporaryDirectory() as temp_name:
        temp_dir = Path(temp_name)
        source_path = temp_dir / "sqlcipher_smoke.c"
        binary_path = temp_dir / "sqlcipher_smoke"
        database_path = temp_dir / "encrypted.db"
        source_path.write_text(source, encoding="utf-8")

        compile_command = [
            "xcrun",
            "clang",
            "-arch",
            "arm64",
            str(source_path),
            str(library),
            "-I",
            str(headers),
            "-DSQLITE_HAS_CODEC",
            "-framework",
            "Security",
            "-framework",
            "CoreFoundation",
            "-framework",
            "Foundation",
            "-o",
            str(binary_path),
        ]
        run(compile_command)
        linkage = run(["otool", "-L", str(binary_path)])
        if "libsqlite3" in linkage:
            raise ValidationError("smoke binary links system libsqlite3")
        run([str(binary_path), str(database_path)])

    return {"status": "passed", "hostArchitecture": host}


def command_output(command: list[str]) -> str:
    try:
        return run(command)
    except subprocess.CalledProcessError as error:
        return (error.stdout or error.stderr or "").strip()


def source_metadata(source_dir: Path | None) -> dict:
    payload: dict[str, object] = {}
    if source_dir is None:
        return payload
    payload["sqlite3C"] = sha256(source_dir / "sqlite3.c")
    payload["sqlite3H"] = sha256(source_dir / "sqlite3.h")
    payload["sqlite3ExtH"] = sha256(source_dir / "sqlite3ext.h")
    payload["sqlite3SessionH"] = sha256(source_dir / "sqlite3session.h")
    version_file = source_dir / "VERSION"
    if version_file.is_file():
        payload["versionFile"] = version_file.read_text(encoding="utf-8").strip()
    return payload


def write_manifest(
    path: Path,
    *,
    args: argparse.Namespace,
    libraries: list[dict],
    zip_sha256: str | None,
    privacy: dict | None,
    smoke: dict,
) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sdk_versions = {
        "iphoneos": command_output(["xcrun", "--sdk", "iphoneos", "--show-sdk-version"]),
        "iphonesimulator": command_output(["xcrun", "--sdk", "iphonesimulator", "--show-sdk-version"]),
        "macosx": command_output(["xcrun", "--sdk", "macosx", "--show-sdk-version"]),
        "xros": command_output(["xcrun", "--sdk", "xros", "--show-sdk-version"]),
        "xrsimulator": command_output(["xcrun", "--sdk", "xrsimulator", "--show-sdk-version"]),
    }
    manifest = {
        "schemaVersion": 1,
        "status": "experimental",
        "generatedAt": generated_at,
        "artifactName": "SQLCipher.xcframework",
        "packageShape": "static-library-xcframework",
        "source": {
            "repository": args.source_repository,
            "tag": args.source_tag,
            "resolvedCommit": args.source_commit,
            **source_metadata(args.source_dir),
        },
        "build": {
            "xcodeVersion": command_output(["xcodebuild", "-version"]),
            "clangVersion": command_output(["xcrun", "clang", "--version"]).splitlines()[0],
            "sdkVersions": sdk_versions,
            "hostMachine": platform.machine(),
            "cflags": CFLAGS,
            "linkFrameworks": LINK_FRAMEWORKS,
        },
        "xcframework": {
            "libraries": libraries,
        },
        "artifacts": {
            "xcframeworkZip": {
                "name": args.xcframework_zip.name if args.xcframework_zip else None,
                "sha256": zip_sha256,
            },
            "checksumFile": {
                "name": args.checksum_file.name if args.checksum_file else None,
                "sha256": sha256(args.checksum_file) if args.checksum_file and args.checksum_file.is_file() else None,
            },
            "privacyManifest": privacy,
        },
        "validation": {
            "compileOptions": COMPILE_OPTIONS,
            "smokeTest": smoke,
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_manifest(path: Path) -> None:
    if not path.is_file():
        raise ValidationError(f"manifest is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") != 1:
        raise ValidationError("manifest schemaVersion must be 1")
    if payload.get("status") != "experimental":
        raise ValidationError("manifest status must be experimental")
    source = payload.get("source") or {}
    if source.get("tag") != "v4.16.0":
        raise ValidationError("manifest source tag must be v4.16.0")
    if source.get("resolvedCommit") != "e2a6040f2ae5cfff2b3e08eb3320007d93cdf3fc":
        raise ValidationError("manifest source commit is not the pinned SQLCipher commit")


def main() -> int:
    args = parse_args()
    try:
        libraries = validate_xcframework(args.xcframework)
        zip_sha = None
        if args.xcframework_zip or args.checksum_file:
            if not args.xcframework_zip or not args.checksum_file:
                raise ValidationError("--xcframework-zip and --checksum-file must be supplied together")
            zip_sha = validate_checksum_file(args.checksum_file, args.xcframework_zip)

        privacy = validate_privacy_manifest(args.privacy_manifest) if args.privacy_manifest else None
        smoke = smoke_test(args.xcframework)

        if args.manifest_out:
            write_manifest(
                args.manifest_out,
                args=args,
                libraries=libraries,
                zip_sha256=zip_sha,
                privacy=privacy,
                smoke=smoke,
            )
            validate_manifest(args.manifest_out)
        if args.manifest:
            validate_manifest(args.manifest)

    except (ValidationError, subprocess.CalledProcessError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print("SQLCipher XCFramework validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

