# rmRenderer downstream patches

This branch is maintained as the RenderDoc replay backend for rmRenderer's
AI-assisted rendering debugging workflow. It remains an independent Git
repository and is referenced by the parent rmRenderer repository as a submodule.

## Compatibility target

- RenderDoc tag: `v1.45`
- RenderDoc commit: `2fc0bc04cb95499635f63986a55bc6f67849dd9f`
- Primary host: Windows x64
- Primary Python ABI: CPython 3.13 x64
- Session mode: local replay

## Downstream behavior

- `rdc setup-renderdoc` builds the pinned RenderDoc commit only.
- Windows builds the Breakpad `common`, `crash_generation_client`, and
  `exception_handler` projects before `pyrenderdoc_module`; these dependencies
  are solution-order metadata rather than `ProjectReference` entries.
- Python headers and import libraries are copied into a build-local SDK prefix;
  the base Python installation is not modified.
- Vulkan implicit-layer registration is opt-in through
  `--register-vulkan-layer`. rmRenderer's normal replay build must not pass it.
- Installed artifacts include `renderdoc-runtime.json`; cache reuse requires an
  exact RenderDoc commit, Python ABI, architecture, and platform match.
- `rdc doctor --profile replay` validates the offline replay environment without
  requiring capture tooling or a second Vulkan layer.
- RenderDoc discovery rejects namespace packages and other false-positive
  `renderdoc` imports. This matters in rmRenderer because the ignored
  `renderdoc/` capture directory would otherwise shadow `renderdoc.pyd`.
- RenderDoc 1.45 mock/API sync rejects both missing and stale struct fields. The
  downstream mock follows the 1.45 `ResourceDescription`, `ResourceFormat`,
  `ConstantBlock`, `ShaderReflection`, and `EventUsage` surfaces.
- Resource sizes come from `TextureDescription.byteSize` or
  `BufferDescription.length`; RenderDoc 1.45 no longer exposes
  `ResourceDescription.byteSize`.
- Resource diff records accept the dimensional metadata returned by the richer
  resource query while retaining name/type comparison semantics.

## Upstream update procedure

1. Fetch and merge/rebase the desired upstream rdc-cli revision in this
   repository, resolving downstream patches here rather than in rmRenderer.
2. Update the pinned RenderDoc tag and commit together.
3. Review RenderDoc release notes for Python breaking API changes.
4. Run unit tests, real-module API sync tests, fixture replay tests, and the
   rmRenderer `renderdoc/tools` tests.
5. Verify the Windows Vulkan implicit-layer registry is unchanged by the replay
   setup.
6. Commit and push this repository first, then update the parent repository's
   submodule gitlink.

Generated build trees, virtual environments, caches, RenderDoc binaries, and
session data must remain untracked.
