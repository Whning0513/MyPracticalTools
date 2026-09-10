---
name: humanize-text
description: Humanize or de-AI prose only when the user explicitly asks for wording such as 写得像人类、像人写的、去AI化、去AI味、降低AI感、humanize, de-AI, or an equivalent request, and the target is text, prose, a paper, PR, memoir, email, or other written language. Do not trigger for ordinary drafting or editing without humanization intent, code-only work, or slides/PPT/visual design; use humanize-slides for those visual artifacts.
---

# Humanize Text

Revise the writing so a specific person appears to have made deliberate choices. Preserve the author's meaning, facts, uncertainty, technical terms, and requested format.

## Confirm the boundary

Apply this workflow only when both conditions hold:

1. The user explicitly asks to humanize, de-AI, remove AI flavor, make the language sound human, or uses an equivalent phrase.
2. The artifact is written language rather than a slide deck or visual design.

If either condition is absent, do not apply this skill's humanization workflow. A request to improve clarity, draft a PR, or write a paper does not by itself count as humanization intent.

## Rewrite

- Put the actual claim, event, decision, or request near the beginning.
- Replace generic framing with details present in the source. Mark missing information instead of inventing it.
- Vary paragraph and sentence shape according to the argument. Do not manufacture fragments or quirks to simulate a person.
- Remove throat-clearing, inflated importance claims, canned reversals, decorative three-part lists, business jargon, and repeated summaries.
- Keep necessary qualifications. Academic caution, test scope, and remembered uncertainty are evidence, not AI tells.
- Name the actor when responsibility matters. Passive voice remains useful when a method or result is the focus.
- Preserve useful unevenness: a short transition, a dense technical sentence, or a personal aside may belong if it serves the text.
- In Chinese, avoid bureaucratic and translated phrasing such as stacked `进行`, `相关`, `层面`, and `赋能`. In English, prefer familiar verbs to inflated synonyms.

Return the revised text first. Add an explanation only when the user requests one or when a factual ambiguity needs attention. Never promise that detector software will classify the result as human-written.

## Optional scholar styles

When the user names a scholar, asks to imitate a supplied scholarly style guide, or wants to build a new style from papers, read [references/upstream.md](references/upstream.md). Do not select a scholar as a hidden persona for ordinary humanization.

## Check

Remove any sentence that only announces importance, repeats the previous sentence, or sounds designed for quotation. Confirm that no fact, citation, test, memory, or emotion was added without support.
