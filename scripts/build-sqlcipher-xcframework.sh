#!/usr/bin/env bash
# Build CypherAir's experimental SQLCipher XCFramework with Apple arm64e slices.

set -euo pipefail

unset GH_TOKEN GITHUB_TOKEN

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SQLCIPHER_REPOSITORY="${SQLCIPHER_REPOSITORY:-https://github.com/sqlcipher/sqlcipher.git}"
SQLCIPHER_TAG="${SQLCIPHER_TAG:-v4.16.0}"
SQLCIPHER_EXPECTED_COMMIT="${SQLCIPHER_EXPECTED_COMMIT:-e2a6040f2ae5cfff2b3e08eb3320007d93cdf3fc}"

BUILD_DIR="${SQLCIPHER_BUILD_DIR:-$REPO_ROOT/build}"
WORK_DIR="$BUILD_DIR/work"
SOURCE_DIR="$WORK_DIR/sqlcipher"
INCLUDE_DIR="$WORK_DIR/include"

XCFRAMEWORK_NAME="SQLCipher.xcframework"
XCFRAMEWORK_PATH="$BUILD_DIR/$XCFRAMEWORK_NAME"
XCFRAMEWORK_ZIP="$BUILD_DIR/SQLCipher.xcframework.zip"
XCFRAMEWORK_CHECKSUM="$BUILD_DIR/SQLCipher.xcframework.sha256"
MANIFEST_PATH="$BUILD_DIR/SQLCipher.arm64e-build-manifest.json"
PRIVACY_MANIFEST="$BUILD_DIR/SQLCipher-PrivacyInfo.xcprivacy"

CFLAGS=(
    -DNDEBUG
    -DSQLCIPHER_CRYPTO_CC
    -DSQLITE_HAS_CODEC
    -DSQLITE_TEMP_STORE=2
    -DSQLITE_THREADSAFE=1
    -DSQLITE_EXTRA_INIT=sqlcipher_extra_init
    -DSQLITE_EXTRA_SHUTDOWN=sqlcipher_extra_shutdown
)

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "error: missing required command '$1'" >&2
        exit 1
    fi
}

log_step() {
    echo
    echo "[$1] $2"
}

validate_source_identity() {
    if [ -z "$SQLCIPHER_TAG" ] || [ "$SQLCIPHER_TAG" = "latest" ] || [ "$SQLCIPHER_TAG" = "null" ]; then
        echo "error: SQLCIPHER_TAG must be an explicit tag; 'latest' is not allowed" >&2
        exit 1
    fi
    if [ -z "$SQLCIPHER_EXPECTED_COMMIT" ]; then
        echo "error: SQLCIPHER_EXPECTED_COMMIT must not be empty" >&2
        exit 1
    fi
}

fetch_source() {
    log_step source "Fetching SQLCipher $SQLCIPHER_TAG..."

    rm -rf "$WORK_DIR"
    mkdir -p "$SOURCE_DIR"

    git -C "$SOURCE_DIR" init
    git -C "$SOURCE_DIR" remote add origin "$SQLCIPHER_REPOSITORY"
    git -C "$SOURCE_DIR" fetch --depth=1 origin tag "$SQLCIPHER_TAG"

    local resolved_commit
    resolved_commit="$(git -C "$SOURCE_DIR" rev-parse "$SQLCIPHER_TAG^{commit}")"
    if [ "$resolved_commit" != "$SQLCIPHER_EXPECTED_COMMIT" ]; then
        echo "error: SQLCipher $SQLCIPHER_TAG resolved to $resolved_commit, expected $SQLCIPHER_EXPECTED_COMMIT" >&2
        exit 1
    fi

    git -C "$SOURCE_DIR" checkout --detach "$resolved_commit"
}

generate_amalgamation() {
    log_step amalgamation "Generating sqlite3.c/sqlite3.h..."
    (
        cd "$SOURCE_DIR"
        ./configure --with-tempstore=yes
        make sqlite3.c
    )

    for header in sqlite3.h sqlite3ext.h sqlite3session.h; do
        if [ ! -f "$SOURCE_DIR/$header" ]; then
            echo "error: generated header is missing: $header" >&2
            exit 1
        fi
    done
    if [ ! -f "$SOURCE_DIR/sqlite3.c" ]; then
        echo "error: generated sqlite3.c is missing" >&2
        exit 1
    fi
}

prepare_headers() {
    log_step headers "Preparing public headers..."

    rm -rf "$INCLUDE_DIR"
    mkdir -p "$INCLUDE_DIR"
    cp "$SOURCE_DIR/sqlite3.h" "$INCLUDE_DIR/sqlite3.h"
    cp "$SOURCE_DIR/sqlite3ext.h" "$INCLUDE_DIR/sqlite3ext.h"
    cp "$SOURCE_DIR/sqlite3session.h" "$INCLUDE_DIR/sqlite3session.h"

    cat > "$INCLUDE_DIR/SQLCipher.h" <<'HEADER'
#pragma once

#include "sqlite3.h"
HEADER

    cat > "$INCLUDE_DIR/module.modulemap" <<'MODULEMAP'
module SQLCipher [system] {
  umbrella header "SQLCipher.h"
  export *
}
MODULEMAP
}

compile_object() {
    local sdk="$1"
    local arch="$2"
    local output="$3"

    xcrun -sdk "$sdk" clang -arch "$arch" -c "$SOURCE_DIR/sqlite3.c" -o "$output" "${CFLAGS[@]}"
}

build_library() {
    local sdk="$1"
    local identifier="$2"
    local arches="$3"
    local output_dir="$WORK_DIR/$identifier"

    log_step "$identifier" "Building $sdk $arches..."

    rm -rf "$output_dir"
    mkdir -p "$output_dir"

    local arch_libs=()
    local arch
    for arch in $arches; do
        local object="$output_dir/sqlite3-$arch.o"
        local lib="$output_dir/libSQLCipher-$arch.a"
        compile_object "$sdk" "$arch" "$object"
        xcrun ar crs "$lib" "$object"
        xcrun ranlib "$lib"
        arch_libs+=("$lib")
    done

    if [ "${#arch_libs[@]}" -gt 1 ]; then
        xcrun lipo -create "${arch_libs[@]}" -output "$output_dir/libSQLCipher.a"
    else
        cp "${arch_libs[0]}" "$output_dir/libSQLCipher.a"
    fi
}

create_xcframework() {
    log_step xcframework "Creating $XCFRAMEWORK_NAME..."

    rm -rf "$XCFRAMEWORK_PATH" "$XCFRAMEWORK_ZIP" "$XCFRAMEWORK_CHECKSUM" "$MANIFEST_PATH" "$PRIVACY_MANIFEST"
    mkdir -p "$BUILD_DIR"

    build_library iphoneos ios-arm64_arm64e "arm64 arm64e"
    build_library macosx macos-arm64_arm64e "arm64 arm64e"
    build_library xros xros-arm64_arm64e "arm64 arm64e"
    build_library iphonesimulator ios-arm64-simulator "arm64"
    build_library xrsimulator xros-arm64-simulator "arm64"

    xcodebuild -create-xcframework \
        -library "$WORK_DIR/ios-arm64_arm64e/libSQLCipher.a" -headers "$INCLUDE_DIR" \
        -library "$WORK_DIR/macos-arm64_arm64e/libSQLCipher.a" -headers "$INCLUDE_DIR" \
        -library "$WORK_DIR/xros-arm64_arm64e/libSQLCipher.a" -headers "$INCLUDE_DIR" \
        -library "$WORK_DIR/ios-arm64-simulator/libSQLCipher.a" -headers "$INCLUDE_DIR" \
        -library "$WORK_DIR/xros-arm64-simulator/libSQLCipher.a" -headers "$INCLUDE_DIR" \
        -output "$XCFRAMEWORK_PATH"

    cp "$SOURCE_DIR/sqlcipher-resources/PrivacyInfo.xcprivacy" "$PRIVACY_MANIFEST"
}

package_outputs() {
    log_step package "Packaging release assets..."

    (
        cd "$BUILD_DIR"
        ditto -c -k --sequesterRsrc --keepParent "$XCFRAMEWORK_NAME" "$(basename "$XCFRAMEWORK_ZIP")"
        shasum -a 256 "$(basename "$XCFRAMEWORK_ZIP")" > "$(basename "$XCFRAMEWORK_CHECKSUM")"
    )
}

validate_outputs() {
    log_step validate "Validating XCFramework..."

    python3 "$REPO_ROOT/scripts/validate-sqlcipher-xcframework.py" \
        --xcframework "$XCFRAMEWORK_PATH" \
        --manifest-out "$MANIFEST_PATH" \
        --source-dir "$SOURCE_DIR" \
        --source-repository "$SQLCIPHER_REPOSITORY" \
        --source-tag "$SQLCIPHER_TAG" \
        --source-commit "$SQLCIPHER_EXPECTED_COMMIT" \
        --xcframework-zip "$XCFRAMEWORK_ZIP" \
        --checksum-file "$XCFRAMEWORK_CHECKSUM" \
        --privacy-manifest "$PRIVACY_MANIFEST"
}

main() {
    require_command git
    require_command make
    require_command python3
    require_command xcrun
    require_command xcodebuild
    require_command shasum
    require_command lipo

    validate_source_identity
    fetch_source
    generate_amalgamation
    prepare_headers
    create_xcframework
    package_outputs
    validate_outputs

    echo
    echo "Built SQLCipher XCFramework assets in $BUILD_DIR"
}

main "$@"

