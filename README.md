# SQLCipher XCFramework for CypherAir

This repository builds a CypherAir-owned experimental `SQLCipher.xcframework`
for Apple targets that need `arm64e` device slices.

It is not a fork of SQLCipher core. The build script consumes the upstream
`sqlcipher/sqlcipher` `v4.16.0` tag, verifies the peeled commit, generates the
SQLCipher amalgamation, and packages a static framework-shaped XCFramework for
CypherAir integration experiments.

## Current Status

- Status: experimental prerelease infrastructure.
- Upstream source: `https://github.com/sqlcipher/sqlcipher`
- Upstream tag: `v4.16.0`
- Expected peeled commit: `e2a6040f2ae5cfff2b3e08eb3320007d93cdf3fc`
- Package shape: static `SQLCipher.framework` slices inside
  `SQLCipher.xcframework`.
- Crypto provider: Apple CommonCrypto / Security framework
  (`SQLCIPHER_CRYPTO_CC`).

This repository does not make SQLCipher a formal CypherAir Contacts storage
dependency by itself. The main CypherAir repository must explicitly opt in and
add consumer-side validation before relying on this artifact.

## Supported Slices

The first experimental artifact intentionally builds only the slices needed by
CypherAir:

| Library identifier | Platform | Architectures |
| --- | --- | --- |
| `ios-arm64_arm64e` | iOS device | `arm64`, `arm64e` |
| `macos-arm64_arm64e` | macOS | `arm64`, `arm64e` |
| `xros-arm64_arm64e` | visionOS device | `arm64`, `arm64e` |
| `ios-arm64-simulator` | iOS Simulator | `arm64` |
| `xros-arm64-simulator` | visionOS Simulator | `arm64` |

tvOS, watchOS, Mac Catalyst, and `x86_64` simulator slices are intentionally
out of scope until CypherAir needs them.

## Build

Requirements:

- macOS with Xcode 26.5 platform SDKs
- `git`
- `make`
- `python3`
- `xcrun` / `xcodebuild`

Build and validate:

```bash
./scripts/build-sqlcipher-xcframework.sh
```

The script writes these ignored outputs under `build/`:

- `SQLCipher.xcframework`
- `SQLCipher.xcframework.zip`
- `SQLCipher.xcframework.sha256`
- `SQLCipher.arm64e-build-manifest.json`
- `SQLCipher-PrivacyInfo.xcprivacy`

Each XCFramework slice contains:

```text
SQLCipher.framework/
├── Headers/
├── Modules/module.modulemap
├── PrivacyInfo.xcprivacy
└── SQLCipher
```

`SQLCipher.framework/SQLCipher` is a static-library binary. This shape lets
Xcode consume the artifact through the normal Frameworks phase while keeping
CypherAir's static-linking intent.

Run validation again against an existing build:

```bash
python3 scripts/validate-sqlcipher-xcframework.py \
  --xcframework build/SQLCipher.xcframework \
  --manifest build/SQLCipher.arm64e-build-manifest.json \
  --xcframework-zip build/SQLCipher.xcframework.zip \
  --checksum-file build/SQLCipher.xcframework.sha256 \
  --privacy-manifest build/SQLCipher-PrivacyInfo.xcprivacy
```

## Release Discipline

Experimental releases publish:

- `SQLCipher.xcframework.zip`
- `SQLCipher.xcframework.sha256`
- `SQLCipher.arm64e-build-manifest.json`
- `SQLCipher-PrivacyInfo.xcprivacy`
- `sqlcipher-xcframework-experiment.json`

Release assets must be immutable. If an artifact is wrong, publish a new
experiment release instead of replacing existing assets.

## Licensing

The build scripts and repository-specific glue are distributed under the
BSD 3-Clause license in `LICENSE`.

SQLCipher remains under its upstream BSD-style license, and SQLite remains
public domain. Generated artifacts must preserve upstream SQLCipher, SQLite,
and privacy-manifest notices when consumed by CypherAir.
