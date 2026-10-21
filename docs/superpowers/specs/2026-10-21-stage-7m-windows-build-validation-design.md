# Stage 7M: Actual Windows standalone build validation

Continue the existing Stage 7B packaging acceptance, keeping Qt 6.11.2/pyside6-deploy/Nuitka 4.1.1/MSVC and all current application behavior. New authoritative inspection found Visual Studio Community 2022 17.10.3, MSVC 14.40.33807 and Windows SDK already installed. Previous PATH-only preflight correctly reported unavailable tools in that shell, but the broader assumption that MSVC was absent was too strong. Activate the existing x64 developer environment for owned build subprocesses only; do not install/modify system compilers or environment variables.

## Bounded build changes

Add optional `--artifact-root` / PowerShell `-ArtifactRoot` to the existing build wrapper. Default remains the project root. Explicit roots must be existing absolute local directories, not links, source tree or Git metadata. Preserve containment checks for generated child directories. Stage copied source, generated config, compiler/Nuitka cache, Python bytecode/temp and standalone output beneath that root. Never delete previous outputs or source. The application database, credentials, startup registry and model assets are not build inputs.

Inspect all existing ancestors top-down for symlinks/reparse points and reject mapped-network/resolved UNC destinations. Python3.10 deployment explicitly requires tomli (Qt's parser falls back from stdlib tomllib); declare that conditional build-only dependency and preflight it. Python3.11+ uses stdlib tomllib without the extra requirement.

Use `E:/AICompanionVoiceLab/build-lab` for this machine's separate build venv, dependency cache/temp and artifact root, consistent with the user's E-drive storage direction. Install only pinned base Qt and deployment dependencies into that owned environment from official PyPI; preserve the shared project/voice environments. A core standalone build intentionally omits optional voice model/native extras; packaged TTS remains explicitly unsupported, and this does not replace source voice acceptance.

## Execution and evidence

First RED tests: alternate artifact root keeps all generated output off the source tree and preserves prior artifacts; invalid/linked/source/Git roots fail before staging or process launch. Existing wrapper tests remain valid. Implement the option and environment paths, then run focused/full regression and independent review.

Discover/activate MSVC through its installed VsDevCmd, using owned process environment only. Create the E build environment, record package provenance/versions/pip check, run wrapper preflight and dry run, then compile only if those succeed. Keep diagnostic output/artifacts in E. Do not weaken preflight, change toolchain or silently accept a missing executable. Retry ordinary dependency/compiler issues boundedly and inspect actual tool source/official documentation before fixes.

After a successful build, inspect the artifact tree and launch only the owned executable with a fresh E-drive LOCALAPPDATA, voice opt-ins absent and offscreen platform if supported. Check actual process lifetime, isolated SQLite/schema/integrity and normal single-instance protection. Close/terminate only that owned smoke process; never interact with the real user profile, Credential Manager, startup settings, microphone or output devices. Do not claim manual tray/drag/real-device experience from a headless launch. No installer signing, GitHub binary publication or release distribution in this slice; source/docs commits only.

Self-review: this resolves a real remaining Stage 7 gate with existing installed tools and reversible local dependencies. An optional artifact directory is a small compatible wrapper extension, not an architecture or packaging-stack change. No product choice or paid credential is required. Compiler output size and incomplete manual/release gates will be recorded honestly.

Primary references: [Qt pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html), [Nuitka compiler manual](https://nuitka.net/user-documentation/user-manual.html). Installed pinned Qt helper source is authoritative for cleanup, output layout and dependency-install behavior.
