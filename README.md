# SQLCipher XCFramework for CypherAir

Builds the `SQLCipher.xcframework` that CypherAir links: static
`SQLCipher.framework` slices with `arm64e` device architectures, which upstream
SQLCipher does not publish. This is not a fork of SQLCipher. The build consumes
one explicit upstream tag, verifies its peeled commit, and packages the
amalgamation over Apple CommonCrypto. The pinned tag, commit, and SQLite
baseline live in `scripts/`.

## Scope

Only the slices CypherAir links are built: iOS, macOS, and visionOS devices
with `arm64` and `arm64e`, plus `arm64` iOS and visionOS simulators. tvOS,
watchOS, Mac Catalyst, and `x86_64` simulators stay out until the app needs
them.

## Releases

A stable release is triggered only by pushing an SSH-signed annotated tag
`sqlcipher-xcframework-v<upstream version>-cypherair.<n>`. The workflow
publishes a non-prerelease immutable release and verifies release integrity
and artifact attestations after publication. Published assets are never
replaced: a wrong artifact is fixed by a new `-cypherair.<n+1>` tag and
release. Experiment and drill releases exist for validation only.

## Licensing

Build scripts and repository glue: BSD 3-Clause (`LICENSE`). SQLCipher keeps
its upstream BSD-style license and SQLite is public domain; artifacts must
preserve the upstream SQLCipher, SQLite, and privacy-manifest notices when
consumed by CypherAir.
