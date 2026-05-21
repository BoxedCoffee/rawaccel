# Repository Guidelines

## Project Structure & Module Organization
- `driver/`: Windows kernel-mode driver (C/C++). Built via `rawaccel.sln`.
- `common/`: shared acceleration logic and headers used across components.
- `grapher/`: Windows UI (C#/.NET) for configuring and visualizing curves.
- `wrapper-* / writer/`: .NET helper libraries, tests, and small tooling.
- `doc/`: user documentation (`doc/Guide.md`, `doc/FAQ.md`) and images.

## Build, Test, and Development Commands
- Open `rawaccel.sln` in Visual Studio (recommended) and build the desired project(s).
- From a Developer Command Prompt:
  - Build solution: `msbuild rawaccel.sln /m /p:Configuration=Release`
  - Run .NET tests: `vstest.console rawaccel\\wrapper-tests\\bin\\Release\\wrapper-tests.dll`

## Coding Style & Naming Conventions
- Indentation: 4 spaces; keep braces on their own line in C#/C++ to match existing files.
- Naming: C# `PascalCase` types/methods, `camelCase` fields/locals; C/C++ follow existing header conventions.
- Keep public APIs stable: changes in `common/` often affect the driver and wrappers.

## Testing Guidelines
- Test framework: MSTest (`[TestClass]`, `[TestMethod]`) under `wrapper-tests/`.
- Add regression tests for behavioral changes (e.g., new accel curve parameters).
- Prefer descriptive test names like `ModifyInput_WithOutputDPI_HasCorrectFactor`.

## Commit & Pull Request Guidelines
- Commits: use short, imperative subjects (e.g., `Fix LUT interpolation edge case`).
- PRs should include: what changed, why, how to verify (commands/steps), and screenshots for UI (`grapher/`) changes.
- Link relevant issues and note any driver-signing or install-impacting changes.

## Security & Configuration Notes
- Driver development affects system input. Avoid logging sensitive input and keep changes deterministic.
- Do not commit built binaries or signed driver artifacts; keep repo source-focused.
