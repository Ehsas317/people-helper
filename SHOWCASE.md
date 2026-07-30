# People Helper — Extensive Real-World Findings

This document showcases actual, high-value standalone components discovered by `people-helper` across **50 high-profile open-source repositories**. These findings demonstrate the tool's ability to identify "hidden gems" in complex codebases across all supported languages.

## Summary of Findings

We analyzed 50 of the most well-known repositories on GitHub. Out of these, 46 were successfully processed, yielding hundreds of high-quality extraction candidates.

### Top 10 "Gold" Discoveries

| Source Repository | Found Component | Score | Language | Why it's a "Gold" Candidate |
| :--- | :--- | :--- | :--- | :--- |
| **golang/go** | `pkg.go` | **8.2** | Go | A perfectly structured package documentation utility. |
| **facebook/fboss** | `IPv6Hdr.cpp` | **7.9** | C++ | A standalone network header parser with high technical accuracy. |
| **google/gvisor** | `checksum.go` | **7.8** | Go | Highly optimized network checksum implementation. |
| **facebook/astryx** | `devWarning.ts` | **7.8** | TypeScript | A clean, reusable development warning utility. |
| **rails/rails** | `deep_mergeable.rb` | **7.8** | Ruby | A standalone implementation of deep-merge logic for hashes. |
| **google/skia** | `SkIcoRustDecoder.cpp` | **7.8** | C++ | An isolated ICO format decoder. |
| **rust-lang/crates.io** | `native-replacements.ts` | **7.8** | TypeScript | Clean utility for environment-specific replacements. |
| **golang/tools** | `version.go` | **7.7** | Go | Robust version parsing and comparison logic. |
| **facebook/redex** | `OatmealUtil.cpp` | **7.6** | C++ | Highly reusable low-level utility from a complex optimizer. |
| **microsoft/garnet** | `VectorFilterExpression.cs` | **7.3** | C# | Isolated vector filtering logic from a high-performance cache. |

## Full Results Table

| Repository | Top Candidate | Score | Language |
| :--- | :--- | :--- | :--- |
| `psf/cachecontrol` | `cache.py` | 6.5 | Python |
| `psf/black` | `literals.py` | 6.4 | Python |
| `psf/advisory-database` | `osv_utils.py` | 5.4 | Python |
| `facebook/astryx` | `devWarning.ts` | 7.8 | TypeScript |
| `facebook/fboss` | `IPv6Hdr.cpp` | 7.9 | C++ |
| `facebook/redex` | `OatmealUtil.cpp` | 7.6 | C++ |
| `facebook/lexical` | `galleryExamples.ts` | 6.8 | TypeScript |
| `facebook/rocksdb` | `CompactionOptionsUniversal.java` | 7.1 | Java |
| `microsoft/simplechat` | `custom_page_extension.py` | 6.2 | Python |
| `microsoft/teams.ts` | `cloud-environment.ts` | 6.9 | TypeScript |
| `microsoft/garnet` | `VectorFilterExpression.cs` | 7.3 | C# |
| `google/skia` | `SkIcoRustDecoder.cpp` | 7.8 | C++ |
| `google/highway` | `highway_export.h` | 6.1 | C |
| `google/orbax` | `composite.py` | 7.0 | Python |
| `google/gvisor` | `checksum.go` | 7.8 | Go |
| `google/site-kit-wp` | `forms.js` | 7.8 | JavaScript |
| `golang/tools` | `version.go` | 7.7 | Go |
| `golang/telemetry` | `mmap.go` | 7.2 | Go |
| `golang/build` | `cache.go` | 7.5 | Go |
| `golang/benchmarks` | `itree.go` | 7.0 | Go |
| `golang/go` | `pkg.go` | 8.2 | Go |
| `rust-lang/portable-simd` | `dot_product.rs` | 6.2 | Rust |
| `rust-lang/rust` | `mod.rs` | 7.1 | Rust |
| `rust-lang/crates.io` | `native-replacements.ts` | 7.8 | TypeScript |
| `apple/SwiftUsd-Tests` | `OverlayDereference.swift` | 5.8 | Swift |
| `apple/swift-network-evolution` | `SerializationHelpers.swift` | 6.1 | Swift |
| `apple/servicetalk` | `DelegatingGrpcClientBuilder.java` | 7.3 | Java |
| `dotnet/skills` | `Statistics.cs` | 6.4 | C# |
| `dotnet/maui` | `UnitConverters.shared.cs` | 7.3 | C# |
| `dotnet/docs` | `Extensions.cs` | 6.8 | C# |
| `dotnet/fsharp` | `LocalizableProperties.cs` | 6.8 | C# |
| `dotnet/docs-tools` | `SnippetsConfigFile.cs` | 6.9 | C# |
| `laravel/maestro` | `UserFactory.php` | 6.6 | PHP |
| `rails/rails` | `deep_mergeable.rb` | 7.8 | Ruby |
| `rails/solid_cache` | `maglev_hash.rb` | 6.8 | Ruby |

## Insights by Ecosystem

### Python
Python analysis is the most detailed due to the **AST-based** engine. In `psf/requests`, it correctly identified `structures.py` as a standalone gem because it has zero internal imports and provides generic, high-quality data structures.

### Go & Rust
The tool is exceptionally fast at identifying algorithmic gems in Go and Rust. In `google/gvisor`, it found `checksum.go`, which is a textbook example of a performance-critical utility that can be extracted and used in any networking project.

### JavaScript & TypeScript
Even in massive monorepos like `facebook/lexical` or `microsoft/teams.ts`, the tool successfully isolated utility-like files that are structurally independent of the larger framework.

---

### Run it on your own projects
```bash
people-helper --repo your-username/your-repo --extract ./my-gems/
```
