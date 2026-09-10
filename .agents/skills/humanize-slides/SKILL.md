---
name: humanize-slides
description: Humanize or de-AI slides only when the user explicitly asks for wording such as PPT像人做的、slides去AI化、去AI味、降低AI感、humanize the deck, de-AI the presentation, or an equivalent request, and the target is slides, PPT/PPTX, a deck, research figure, or presentation visual. Do not trigger for ordinary slide creation without humanization intent, text-only rewriting, papers, PR prose, or code; use humanize-text for written language.
---

# Humanize Slides

Make the deck look shaped by a person who understands its audience and content. Preserve scientific meaning, approved regions, and editable structure.

## Confirm the boundary

Apply this workflow only when both conditions hold:

1. The user explicitly asks to humanize, de-AI, remove AI flavor, make the slides look human-made, or uses an equivalent phrase.
2. The artifact is a slide deck, PPT/PPTX, research figure, or presentation visual.

If either condition is absent, do not apply this skill's humanization workflow. Route text-only humanization to `humanize-text`. A normal request to create slides does not by itself count as humanization intent.

## Diagnose the AI look

Inspect the actual deck, rendered slides, and editable objects before proposing changes. Name the visible problem rather than applying a preset. Common signals include:

- repeated card grids with identical weight;
- decorative gradients, glows, icons, or arrows that encode nothing;
- centered text everywhere and uniform sentence lengths;
- headings that announce themes while slides lack evidence or a visual argument;
- stock illustration styles mixed without a reason;
- excessive symmetry, empty polish, or one layout repeated across unrelated content.

Do not treat asymmetry, hand-drawn decoration, or random variation as proof of human design.

## Revise deliberately

- Give each slide one communicative job and make its hierarchy reflect that job.
- Let the content determine layout. Use repeated components only where repetition expresses a real relationship.
- Retrieve a small set of user-approved visual references and state what each contributes: layout, typography, palette, or a matched mechanism.
- Preserve accurate labels, equations, data encodings, causal arrows, and distinctions between training and inference.
- Prefer native, named, editable objects. Do not pass off a full-slide raster as an editable PPT.
- Use font, color, spacing, and alignment as a coherent system. Allow controlled variation where the narrative changes.
- Edit selected objects and attached connectors while protecting accepted regions.

For a research figure or an existing AstraDraw project, read [references/upstream.md](references/upstream.md). For a full presentation, apply the rules above and follow an available presentation-authoring workflow for deck construction and rendering.

## Deliver and verify

Provide the editable source and a rendered preview. Inspect the result at actual presentation or paper size. State which slides, objects, links, fonts, and protected regions were checked, along with limits that remain. Publishing or uploading still requires the user's authorization.
