# SQLCipher XCFramework for CypherAir

This repository builds the CypherAir-owned `SQLCipher.xcframework` for Apple
targets that need `arm64e` device slices.

It is not a fork of SQLCipher core. The build script consumes the upstream
`sqlcipher/sqlcipher` `v4.16.0` tag, verifies the peeled commit, generates the
SQLCipher amalgamation, and packages a static framework-shaped XCFramework for
CypherAir app integration.

## Current Status

- Status: stable external binary dependency infrastructure for CypherAir, with
  separate experiment and drill channels for validation.
- Upstream source: `https://github.com/sqlcipher/sqlcipher`
- Upstream tag: `v4.16.0`
- Expected peeled commit: `e2a6040f2ae5cfff2b3e08eb3320007d93cdf3fc`
- Package shape: static `SQLCipher.framework` slices inside
  `SQLCipher.xcframework`.
- Crypto provider: Apple CommonCrypto / Security framework
  (`SQLCIPHER_CRYPTO_CC`).

This repository provides the SQLCipher binary artifact consumed by the main
CypherAir repository. It does not by itself implement Contacts SQLCipher
storage; that application behavior remains owned by `cypherair/cypherair`.

## Supported Slices

The artifact intentionally builds only the slices needed by CypherAir:

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

Stable releases use SSH-signed annotated tags such as
`sqlcipher-xcframework-v4.16.0-cypherair.1`. The stable release workflow only
publishes from those tags, produces non-prerelease immutable releases, and
verifies both GitHub release integrity and artifact attestations after
publication.

Stable releases publish:

- `SQLCipher.xcframework.zip`
- `SQLCipher.xcframework.sha256`
- `SQLCipher.arm64e-build-manifest.json`
- `SQLCipher-PrivacyInfo.xcprivacy`
- `SQLCipher.xcframework.release.json`

Experiment and drill releases remain available for validation work and publish
channel-specific metadata such as `sqlcipher-xcframework-experiment.json`.

Release assets must be immutable. If a stable artifact is wrong, publish a new
semantic release tag such as `sqlcipher-xcframework-v4.16.0-cypherair.2`
instead of replacing existing assets.

## Licensing

The build scripts and repository-specific glue are distributed under the
BSD 3-Clause license in `LICENSE`.

SQLCipher remains under its upstream BSD-style license, and SQLite remains
public domain. Generated artifacts must preserve upstream SQLCipher, SQLite,
and privacy-manifest notices when consumed by CypherAir.
