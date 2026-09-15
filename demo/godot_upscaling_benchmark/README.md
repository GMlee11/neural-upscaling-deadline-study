# Compact interactive benchmark source

This directory contains the portable Godot project and shaders named by the
manuscript. It supports ordinary interactive/classical rendering and the
instrumented request path. It is included as publication source, not as the
deterministic paper replay.

The RK3576 native bridge, compiled libraries, board deployment scripts, editor
state, model binaries, and capture configuration are intentionally excluded
from this minimal V1 release. Their exact historical identities are pinned in
`artifact/paper1_hotmobile2027/historical_provenance.json`. The paper-facing
tables and figure reproduce without Godot or board access.
