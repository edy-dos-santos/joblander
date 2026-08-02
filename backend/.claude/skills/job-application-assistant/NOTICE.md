# Notice

The files in this folder (`SKILL.md`, `01-candidate-profile.md`, `02-behavioral-profile.md`,
`03-writing-style.md`, `04-job-evaluation.md`, `05-cv-templates.md`,
`06-cover-letter-templates.md`) are copied, with only a placeholder-redacted candidate profile,
from the `job-application-assistant` skill in
**[ai-job-search](https://github.com/MadsLorentzen/ai-job-search)** by **Mads Lorentzen**,
used under that project's MIT license.

Only this small subset is included — the specific files JobLander's own server
(`server/main.py`) reads by path to drive job-fit evaluation, CV tailoring, and cover-letter
writing. The rest of the `ai-job-search` project (its job-search/scraping CLIs, LaTeX/PDF
document generation, and interview-prep feature) is not included here, because JobLander
doesn't use any of it — see the root `README.md`'s "Where the AI logic comes from" section for
the full explanation.
