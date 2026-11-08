# Post-hackathon development boundary

Recorded November 8, 2026. This document and the develop branch were created after the hackathon deadline. No timestamps or competition history are backdated.

## Preserved references

| Reference | Preserved commit | Meaning |
| --- | --- | --- |
| main | ef8b1e5e5c41a8458111e6768598b78782c26a62 | Existing default-branch baseline, unchanged by the new Telegram work |
| feature/h15-opening-bid-foundation | 1883bc548704534dd30be6e37274ff8187ba631d | Pre-deadline H15 implementation baseline |

The submission form evidence identifies the repository root URL, not a commit. These are preserved baselines, not a certification of the exact submitted or demonstrated artifact. The demo and deployed service can refer to different revisions; do not infer a deployment pin from a branch name.

## Continued development

- develop begins at the H15 baseline above. It is for continued product development after the deadline.
- PR #17 targets develop. PR #18 remains stacked on PR #17's feature branch until that dependency is reviewed and integrated.
- New product work branches from develop and proposes changes back to develop.
- Do not merge continued development into main or the preserved H15 branch, change the repository's default branch, or repoint submitted demo/deployment links as part of this workflow.
- Do not move or overwrite archive tags once published. Planned names are meta-hackathon-2026-main-baseline and meta-hackathon-2026-h15-baseline, pointing to the exact commits above. A tag created now records an older commit; it is not proof that the tag existed before the deadline.
- A merge, deployment or runtime change still requires separate owner authorization under AGENTS.md.

## Competition status

The official event page lists submissions due November 4, 2026 at 9 PM Eastern, with judging November 4–8:
https://dev.meta.ai/events/global-hackathon

The full accepted rules about post-deadline repository activity have not been independently established. Branch separation and preserved commits document provenance; they do not guarantee eligibility or substitute for an organizer ruling. Do not describe new features as part of the competition submission. Do not alter the submission form or contact organizers without owner authorization.
