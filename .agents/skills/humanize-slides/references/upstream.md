# Optional AstraDraw integration

This skill adapts the reference-guided design principles of [AstraDraw](https://github.com/IamJerryXu/AstraDraw), reviewed at commit `cc13467d3b5fe9404267e723327bf383664d96ab`. At that revision, the upstream repository did not declare an overall open-source license. This repository therefore links to AstraDraw without copying its code, PPTX files, images, fonts, or other assets.

Use AstraDraw only when the user provides a local copy, identifies an existing AstraDraw project, or authorizes obtaining it.

1. Read the upstream `SKILL.md` completely, then read only the references it routes to for the current task.
2. Resolve relative paths and run helpers from the AstraDraw root. On Windows, use `python -X utf8` when a helper reads or compares UTF-8 text.
3. Treat reference material as visual guidance, not scientific evidence. Preserve source and license boundaries.
4. Return editable source and a rendered preview. Do not describe a rasterized slide as an editable deck.

If AstraDraw is unavailable, continue with the self-contained slide-humanization rules and the presentation tools available in the current environment.
