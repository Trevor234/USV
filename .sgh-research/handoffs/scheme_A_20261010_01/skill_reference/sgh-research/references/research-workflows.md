## Research Workflows

Detailed specification of each research workflow, its current status, inputs,
outputs, and inter-workflow dependencies.

## Workflow Registry

| ID | Workflow | Status | Sub-Skill | Storage |
|----|----------|--------|-----------|---------|
| WF-1 | Literature Discovery and Tracking | Active | usv-lit-search | `.usv-lit-search/` |
| WF-2 | Paper Reading and Notes | Active | sgh-reading-notes | `.sgh-research/reading-notes/` |
| WF-3 | Experiment Design and Simulation | Active | sgh-experiment-design | `.sgh-research/experiments/` |
| WF-4 | Manuscript Writing | Active | sgh-manuscript-writing | `.sgh-research/manuscripts/` |
| WF-5 | Code Reproduction | Active | sgh-code-reproduction | `.sgh-research/reproductions/` |
| WF-6 | Submission Tracking | Active | sgh-submission-tracking | `.sgh-research/submissions/` |

## WF-1: Literature Discovery and Tracking (Active)

**Sub-Skill**: usv-lit-search

**Inputs**:
- Search query (natural language or structured keywords)
- Optional filters: year range, arXiv categories, max results
- Researcher profile (topics, methods, venues, authors)

**Outputs**:
- Tiered paper list (Top Picks / Solid Matches / Boundary Expanders)
- Per-paper: title, authors, year, DOI/arXiv ID, abstract, citation count, OA status, match reasons
- Cached JSON results in `.usv-lit-search/search_cache/`

**Process**:
1. Build queries from user input + profile keywords (see `usv-lit-search/references/search-strategy.md`)
2. Run `multi_source_search.py` -- parallel search of arXiv, Semantic Scholar, OpenAlex, Crossref
3. Merge and dedup by DOI + arXiv ID + title hash
4. Run `rank_papers.py` -- 6-dimension scoring (topic 35%, method 20%, venue 15%, recency 15%, citation 10%, network 5%)
5. Present tiered results with match reasons
6. Save to cache, update preferences with feedback

**Downstream**: Flagged papers flow to WF-2 (Reading) for deep analysis.

## WF-2: Paper Reading and Notes (Active)

**Sub-skill**: sgh-reading-notes

**Inputs**:
- Paper identifier (DOI, arXiv ID, Zotero key, or index from WF-1 results)
- Full text or abstract (from cache, API fetch, or PDF file via pdf skill)

**Methodology**: Question-Driven Reading (4 phases)
1. Initial Comprehension -- read title + abstract, form brief understanding
2. Question Generation -- generate 3-6 domain-aware critical questions
3. Question-Driven Reading -- extract full text (pdf skill or Zotero), read to answer questions
4. Structured Summary -- produce QDR note for downstream consumption

**Outputs**:
- QDR note saved to `.sgh-research/reading-notes/<paper-id>_qdr.md`
- Quick scan notes: `<paper-id>_scan.md`
- Critical reviews: `<paper-id>_review.md`
- Synthesis: `_synthesis_<topic>.md`
- Candidate innovation ideas merged into the single cumulative register
  `.sgh-research/research-innovations.md`; do not create per-paper innovation files
- Zotero child notes synced via pyzotero (if configured)

**Downstream**: Reading insights first pass through innovation capture. Candidate ideas
flow to WF-3 only after novelty and theory checks; validated insights may flow to WF-4.

## WF-3: Experiment Design and Simulation (Active)

**Sub-skill**: sgh-experiment-design

**Inputs**:
- Hypothesis or research question (from WF-2 reading insights or direct user input)
- Methods identified from WF-1/WF-2 (baselines, algorithms to test)
- Available tools (MATLAB/Simulink, ROS2+Gazebo, Python)

**Methodology**: Three-Phase Experiment Loop
1. **Design** -- formulate falsifiable hypotheses, run theory check (veto gate),
   build parameter matrix, make go/no-go decision
2. **Execute** -- scaffold experiment directory via `new_experiment.py`, capture
   environment snapshot, run simulation with full logging, manage parameter sweeps
3. **Retrospective** -- consolidate results, diagnose mechanism (why, not just what),
   decide next step (iterate / collect more data / conclude / pivot)

**Outputs**:
- Self-contained experiment package in `.sgh-research/experiments/<exp-id>/`
  containing: design.md, hypothesis_matrix.tsv, params.json, env_snapshot.json,
  commands.log, results/ (metrics, figures, logs), report.md, retro.md

**Script**: `sgh-experiment-design/scripts/new_experiment.py` -- scaffolds the
experiment directory with templates and auto-detected environment info.

**Downstream**: Results and reports flow to WF-4 (Writing) for figure/table
generation and manuscript claims.

## WF-4: Manuscript Writing (Active)

**Sub-Skill**: sgh-manuscript-writing

**Inputs**:
- Research results from WF-3 (experiment reports, metrics, figures)
- Literature context from WF-1/WF-2 (citations, related work, gaps)
- Target venue (journal/conference)

**Methodology**: Five-Stage Manuscript Pipeline
1. **PLAN** -- outline construction, paper type classification, target venue
   selection, citation plan, section-by-section outline
2. **DRAFT** -- section-by-section drafting in academic English, following
   control-specific structure (System Model, Problem Formulation, Controller
   Design, Stability Analysis, Simulation Results)
3. **FIGURE** -- figure and table design from sgh-experiment-design data,
   publication standards (vector format, colorblind-safe, consistent fonts)
4. **POLISH** -- English polishing, notation/terminology consistency check,
   self-review checklist, Chinese-to-English translation
5. **PACKAGE** -- cover letter, title page, highlights, declarations

**Outputs**:
- Manuscript package in `.sgh-research/manuscripts/<manuscript-id>/`
  containing: main.tex, references.bib, outline.md, notes.md, sections/,
  figures/
- LaTeX scaffolding for IEEE conference, IEEE Transactions, or generic

**Script**: `sgh-manuscript-writing/scripts/new_manuscript.py` -- scaffolds
manuscript directory with LaTeX template and outline.

**Downstream**: Completed manuscript flows to WF-6 (Submission).

## WF-5: Code Reproduction (Active)

**Sub-Skill**: sgh-code-reproduction

**Inputs**:
- Paper from WF-1/WF-2 with algorithm to reproduce
- QDR note from sgh-reading-notes (algorithm analysis foundation)
- Open-source code link (if available)

**Methodology**: Four-Phase Reproduction Workflow
1. **IDENTIFY** -- extract core algorithm, mathematical formulation, key
   equations, input requirements, expected results from the paper
2. **LOCATE** -- search author GitHub, PapersWithCode, GitHub search,
   conference repos; assess quality (completeness, documentation, license,
   activity, test coverage)
3. **REPRODUCE** -- set up environment (Python/MATLAB/ROS2), run code, log
   all commands and outputs, capture environment snapshot, troubleshoot
4. **VERIFY** -- compare metrics against paper's reported values, classify
   match level (exact/approximate/qualitative/mismatch), diagnose
   mismatches, write reproduction report

**Outputs**:
- Reproduction package in `.sgh-research/reproductions/<reproduction-id>/`
  containing: algorithm_analysis.md, code_search.md, reproduction_log.md,
  report.md, env_snapshot.json, commands.log, code/, results/

**Script**: `sgh-code-reproduction/scripts/new_reproduction.py` -- scaffolds
reproduction directory with templates.

**Downstream**: Reproduced algorithms become baselines for WF-3 (Experiment)
and provide comparison data for WF-4 (Writing).

## WF-6: Submission Tracking (Active)

**Sub-Skill**: sgh-submission-tracking

**Inputs**:
- Completed manuscript package from WF-4
- Target journal/conference

**Methodology**: Four-Mode Workflow
1. **JOURNAL SELECT** -- match manuscript to venue based on scope fit (40%),
   impact factor (20%), review speed (15%), OA (10%), indexing (10%),
   special issues (5%); present 2-3 ranked recommendations
2. **PRE-SUBMISSION** -- run submission checklist (technical soundness,
   novelty, completeness, reproducibility, formatting, language, references,
   figures, ethical compliance); conduct simulated peer review; draft cover
   letter
3. **TRACK** -- maintain submission record with status tracking, timeline
   management, deadline reminders for revisions
4. **RESPOND** -- categorize reviewer comments (agree/change, agree/cannot
   fully change, respectfully disagree), draft point-by-point responses,
   revise manuscript, cross-reference responses to changes

**Outputs**:
- Submission package in `.sgh-research/submissions/<submission-id>/`
  containing: submission_record.md, cover_letter.md, response_letter.md,
  timeline.md, commands.log, reviewer_comments/, revisions/

**Script**: `sgh-submission-tracking/scripts/new_submission.py` -- scaffolds
submission directory with templates.

**Downstream**: If rejected, feedback flows back to WF-1 (Search) for
alternative venue identification and WF-4 (Writing) for revisions.

## Inter-Workflow Data Flow

```
WF-1 (Search) --> WF-2 (Read) --> WF-3 (Experiment)
                      |                  |
                      v                  v
                 WF-4 (Write) <---- WF-5 (Code)
                      |
                      v
                 WF-6 (Submit)
```

Each arrow represents a data handoff. SGH_Research coordinates these handoffs
by reading from one workflow's output and feeding context to the next.
