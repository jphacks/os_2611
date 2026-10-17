---
name: company-research
description: Investigate companies in a Japan work or event context, including hackathon sponsor discovery, business lines, products, directions and evidence-based relevance. Distinguish event sponsorship, local attendance and award eligibility. Use when user asks for company intelligence, sponsor fit or an event-derived company map.
---

# Company investigation

Use the host's live search and the sibling work-context evidence standards. Keep
the person's private profile out of queries. Use their usual language, with actual
Japanese company/product names where useful. Ordinary workers need practical
business context, not automatic financial statements.

1. Anchor event year, location and dates in original organizer material. Open any
   user-provided guide; if inaccessible, explicitly record that gap and use the
   official public pages. Never imply Slack/Notion was read when it was not.
2. Derive a roster from the organizer. Separately record event_sponsor,
   technical_partner, osaka_attendance and osaka_prize (adapt the implementation
   before using other locations). Global sponsorship is not evidence of local
   presence or a cash prize. Unknown is not no. Local schedule updates may override
   public pages; preserve conflicts and attribution.
3. Resolve exact entity and sponsoring department. A parent group, Japanese
   subsidiary, sister company and product brand are not interchangeable. Follow
   organizer links to first-party company sources. For a long roster, deliver a
   sourced compact whole-roster map, then deeply investigate 3–6 relevant companies.
   Expand the usual six-source budget explicitly when a whole roster requires it.
4. Collect actual business/customer group, representative products and publicly
   stated direction. Open product/service pages for priority companies. Do not
   invent strategy, integrations or private pain points from a slogan. Label your
   proposed collaboration angle as a hypothesis. Seek an existing similar product
   as counterevidence, including from the sponsor itself.
5. Return company facts + source/date + why they matter to this user's task + one
   concrete question for validation. Avoid an investment/finance report unless
   requested. Don't collect personal contacts or send messages as part of research.
6. Create one or more evidence packets using the sibling find-capabilities
   `scripts/catalog.py`, action `validate_companies`: as_of, scope, sources and
   companies. A company has name, entity_scope, relationships, claims and gaps.
   A relationship has type, status (documented/unknown) and source_ids. A claim has
   kind (fact/inference), topic (business/product/direction/fit), text, source_ids.
   Max12 sources per packet; split large rosters into small packets, not evidence-free
   summaries. See the script for exact keys. The validator enforces references and
   dates, not their truth. Manually review sources for each important claim.
7. Present 3–5 useful implications and the full compact table as an artifact if
   needed. Keep unknown local award terms and inaccessible sources visible. Do
   not claim exhaustive research or market demand validated by company advertising.

Attach clickable original sources beside important business facts, product
claims and event conditions. Label proposed collaboration fit as our hypothesis,
not the company's stated need or endorsement. Preserve known source dates.

Use find-capabilities for existing implementation discovery. Keep company evidence
separate from confirmed personal facts; neither workflow installs anything or
creates a background job.
