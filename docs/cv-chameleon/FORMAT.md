# CV master format (MASTER_CV.docx)

Canonical template: `templates/cv-master/MASTER_CV.docx`

## Fixed header (paragraph indices in template)

| Index | Style   | Field            | Chameleon edits |
|------:|---------|------------------|-----------------|
| 0     | Title   | Full name        | no              |
| 1     | Heading 1 | Headline skills (`Title1 \| Title2 \| Skill \| …`) | **yes** (primary tailor target) |
| 2     | normal  | Contact line (phone, email, LinkedIn, portfolio, location) | on profile update |

## Sections (Heading 1 markers)

Sections are located by exact Heading 1 text, in order:

1. **Summary** — one or more body paragraphs until the next Heading 1
2. **Key Achievements** — optional highlight blocks (Heading 2 + body)
3. **Experience** — repeating job blocks (see below)
4. **Languages** — programming languages line (`• Python 5 years …`)
5. **Github projects** — project title + description pairs
6. **Education** — school + degree lines
7. **Languages** — spoken languages (second section with same H1 label)

## Experience block pattern

```
   {Company}\t{Location}          ← normal, company line (leading spaces + tab)
{Role}\t{Date range}              ← Heading 2
{Optional context}                ← Heading 3 (optional)
{bullet line}                     ← normal
Stack: {skills pipe-separated}    ← normal, optional
```

## JSON schema

Stored per track at `state/chameleon/profile/{track_id}.json` (runtime, not committed).

See `scripts/cv_master_schema.py` for validation and required fields before `build_master_docx()`.

## Build algorithm

1. Validate profile JSON (`validate_cv_profile`)
2. Copy template → output path
3. Replace header paragraphs (name, headline, contact, summary)
4. Rebuild dynamic sections from JSON (achievements, experience, projects, education)
5. Register output in `resume-chameleon-config.json` masters list
6. Optional: export PDF + `chameleon sync` for keywords

## Tests

- `tests/test_cv_master_docx.py` — parse/build round-trip on fixture matching this layout
- Future: LinkedIn profile HTML fixture → `import_linkedin_profile()` → same schema
