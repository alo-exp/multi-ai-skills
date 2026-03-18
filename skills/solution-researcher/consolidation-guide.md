# Consolidation Guide — Solution Research

This guide defines the structure and rules for synthesising raw AI responses into a Consolidated Intelligence Report (CIR). The consolidator skill uses this guide when invoked by the solution-researcher skill.

---

## Input

- A raw AI responses archive containing 3–7 individual AI analyses of a software product
- Each response follows the prompt template structure: Executive Summary, Capability Groups, Assumptions & Gaps, Marketing Claims vs. Demonstrated, Capabilities Checklist

---

## Output Structure

The CIR must include exactly these sections in this order:

### 1. Executive Summary

- **Primary purpose:** 2–3 sentence factual summary of the product's core problem-solution fit. Synthesise across all sources — use consensus language, not any single source's wording.
- **Target personas:** Primary and secondary user types, based on cross-source agreement.
- **Core value propositions:** The 3–5 most emphasised capability areas across all sources.
- **Source coverage:** Note how many sources were used and any that failed or were excluded.

### 2. Capability Groups

Organise into 5–15 logical, high-level capability groups. Use the product's own terminology where possible.

For each capability group:

#### [Capability Group Name]

For each capability within the group:

**[Capability Name]**
- **What it is:** 1–2 sentence functional description. Prefer descriptions confirmed by multiple sources.
- **Problem it solves:** User/business pain point. Use consensus language.
- **Key sub-features:** Bullet list. Include sub-features mentioned by ANY source (union, not intersection).
- **Source agreement:** Note if all sources agree, or flag where sources disagree.
- **Plan/tier availability:** If specified by any source.

**Rules for capability synthesis:**
- Include a capability if mentioned by 2+ sources (strong signal) or if mentioned by 1 highly reliable source with specific detail (not vague marketing language).
- If sources disagree on a capability's existence or scope, note the disagreement explicitly.
- Never invent capabilities not mentioned by any source.
- Preserve specificity: "Kubernetes-native GitOps with ArgoCD integration" is better than "deployment automation."

### 3. Assumptions, Gaps & Ambiguities

| Area | Observation | Impact | Sources |
|------|-------------|--------|---------|
| (area) | (what is unknown or ambiguous) | (why it matters) | (which sources noted this) |

**Rules:**
- Include gaps noted by ANY source, not just consensus gaps.
- Add synthesis-level gaps: areas where sources contradict each other.
- Flag areas where all sources said "not specified" — these are confirmed information gaps.

### 4. Marketing Claims vs. Demonstrated Capabilities

| Claim | Evidence | Assessment | Sources |
|-------|----------|------------|---------|
| (marketing claim from the product site) | (what the AI sources found to substantiate or contradict) | Substantiated / Partially substantiated / Unsubstantiated / Contradicted | (which sources assessed this) |

**Rules:**
- Only document discrepancies objectively — do not critique or editorialise.
- A claim is "substantiated" only if 2+ sources found supporting evidence.
- A claim is "contradicted" only if a source found explicit counter-evidence.

### 5. Comparison-Ready Capabilities Checklist

Standalone, product-agnostic hierarchy for competitive benchmarking. Format:

```
- [ ] Category 1
  - [ ] Sub-capability 1.1
  - [ ] Sub-capability 1.2
    - [ ] Detail 1.2.1
- [ ] Category 2
  ...
```

**Rules:**
- No product name references. Generic, self-explanatory naming only.
- No descriptions — names must be self-explanatory.
- Union of all capabilities found across all sources.
- Hierarchical: Category → Capability → Sub-feature (max 3 levels).
- This checklist must function as a standalone requirements template usable for evaluating ANY product in this category.

### 6. Source Reliability Assessment

| Source | Quality | Depth | Unique Contributions | Notes |
|--------|---------|-------|---------------------|-------|
| (AI platform name) | High/Medium/Low | Deep/Moderate/Shallow | (capabilities only this source found) | (extraction issues, mode used, etc.) |

**Source reliability heuristics:**
- **Perplexity:** Strong on factual claims due to web search grounding. Often provides source URLs.
- **ChatGPT (Deep Research):** Highly reliable in DEEP mode — extensive web crawling. REGULAR mode: check for content duplication artefacts.
- **Copilot (Deep Research):** Often crawls GitHub README — high quality for open-source products. May fail due to voice mode hazard.
- **Grok:** Receives condensed prompt (~900 chars) — shallower analysis expected. Weight accordingly.
- **DeepSeek:** May fail URL access entirely. Even when successful, may only analyze homepage. Exclude if response quality is very low.
- **Claude.ai:** In REGULAR mode, often produces the deepest single-source analysis (~2-5x content vs others). Weight heavily when available.
- **Gemini (Deep Research):** High quality when successful. May fail with capacity errors.

---

## Synthesis Rules

1. **Consensus-first:** Lead with what multiple sources agree on. Flag disagreements separately.
2. **Union of capabilities:** The checklist includes everything found by ANY reliable source. The detailed sections note source agreement levels.
3. **No fabrication:** If no source mentions a capability, it does not exist in the report.
4. **Preserve specificity:** Keep technical detail from the most knowledgeable source rather than generalising.
5. **Source attribution:** When a unique insight comes from a single source, note which source.
6. **Domain knowledge:** If a domain knowledge file was provided (e.g., `domains/devops-platforms.md`), use its evaluation categories as a lens for organising capability groups and its terminology for consistent naming. Weight capabilities according to the domain's evaluation criteria.

---

## Quality Checks

Before finalising the CIR:
- [ ] Every capability group has at least 2 capabilities
- [ ] No capability group has more than 10 capabilities (split if needed)
- [ ] The checklist is product-agnostic (no product name references)
- [ ] Source reliability assessment covers all sources used
- [ ] Gaps section includes at least 3 entries (every product has gaps)
- [ ] Marketing claims section has at least 1 entry
- [ ] No hallucinated capabilities (everything traces to at least one source)
