---
name: sgh-research
description: >
  Personalized research lifecycle assistant for SGH's work in control systems, unmanned
  surface vehicles (USV), multi-agent formation, reinforcement learning, and model
  predictive control (MPC). Routes literature discovery, question-driven paper reading,
  cumulative innovation capture, experiment design, manuscript writing, code reproduction,
  and submission tracking to specialized sub-skills. Use when the user mentions 科研助手,
  研究助手, 文献检索, 论文检索, 读论文, 精读, 创新点, 写论文, 做实验, 投稿, or
  asks for help across the research workflow. Also use when the user asks to organize,
  file, archive, or create folders for local papers (整理文献, 文献整理, 创建文件夹,
  文件夹归档, 文献归档). After full-paper reading, candidate ideas are merged into one
  project-level research-innovations.md register rather than separate files.
---

# SGH Research

Personalized research lifecycle assistant for SGH, spanning control systems,
unmanned surface vehicles (USV), multi-agent formation, reinforcement learning,
and model predictive control (MPC).

## Research Identity

- **Researcher**: SGH, Shanghai Ocean University (SHOU)
- **Domain**: Control systems / USV / multi-agent formation / RL / MPC
- **Sub-skills**: See references/research-workflows.md for the full registry

## Sub-Skill Architecture

SGH_Research is an orchestrator. Specialized tasks are delegated to sub-skills:

| Sub-Skill | Status | Purpose |
|-----------|--------|---------|
| usv-lit-search | Active | Literature search, ranking, digest, download |
| sgh-reading-notes | Active | Question-driven reading, structured notes, Zotero sync |
| sgh-experiment-design | Active | Experiment design, simulation execution, retrospective analysis |
| sgh-manuscript-writing | Active | Outline, drafting, figure design, LaTeX |
| sgh-code-reproduction | Active | Algorithm reproduction, experiment code management |
| sgh-submission-tracking | Active | Journal selection, submission status, reviewer response |

When a task matches a sub-skill's domain, load and follow that sub-skill's SKILL.md.
When a task spans multiple domains or no sub-skill exists yet, handle directly using
the guidelines in references/research-workflows.md.

## Workflow Router

### 1. Literature Discovery and Tracking -> delegate to usv-lit-search

Triggers: 文献检索, 论文检索, 搜论文, 找文献, 查文献, 最新文献, 文献推荐,
每日推送, 下载论文, 摘要理解, arXiv, Semantic Scholar

Action: Load the **usv-lit-search** skill and follow its workflow router:
- Search and Discover (default) -- parallel multi-source search + scoring
- Daily or Period Digest -- latest arXiv submissions filtered by relevance
- Abstract Understanding -- structured summary of a specific paper
- Paper Download -- OA first, then SHOU library guided access

Scripts:
- usv-lit-search/scripts/multi_source_search.py -- parallel search (arXiv, S2, OpenAlex, Crossref)
- usv-lit-search/scripts/rank_papers.py -- 6-dimension domain scoring and tiering

Profile and cache remain at <workspace>/.usv-lit-search/.

### 2. Local Paper Organization and Archiving -> handle directly

Triggers: 整理文献, 文献整理, 整理过的文献, 创建文件夹, 建文件夹, 文件夹归档,
文献归档, 论文归档, 整理 PDF, 归档论文, organize papers, archive papers

Use this workflow when the user asks to organize local paper files into per-paper folders.
This is distinct from searching for or downloading new literature.

Workflow:
1. Scan the user-specified directory and its subdirectories. Inventory PDFs, Markdown
   files, and other files before making changes.
2. Match papers using titles, authors, DOI or other metadata, filenames, and the content
   of existing Markdown files. Do not assume unrelated PDFs in the same folder belong to
   the paper being discussed.
3. Search the relevant local library for an existing Markdown original. Never convert a
   PDF into Markdown to satisfy the original-text requirement. If no existing Markdown
   original is found, say so and archive no substitute as an original.
4. Create one short, clear, identifiable Chinese topic folder per paper. Use the minimum
   extra distinguishing words needed when names collide.
5. Copy matched source PDFs and existing Markdown originals into the paper folder.
   Preserve source files in place; never delete or overwrite originals or same-named files.
   If a destination folder or file already exists, inspect it and avoid overwriting it.
6. Create 简单概要.md with a plain-language account of the problem, method, and main
   conclusion, readable in under a minute. Create 详细讲解.md covering background,
   problem definition, principles, core equations and method, algorithm flow, experiment
   design, main results, limitations, and relationships to relevant concepts. Include
   useful questions raised in the conversation when the user asks for this.
7. Ground paper claims and reported numbers in the source PDF or existing Markdown.
   Clearly label general explanations not stated by the paper as “补充理解”.
8. Report the created folder list, each paper's PDF/Markdown match, unmatched files, and
   any naming conflicts. Do not claim that an original Markdown exists unless it was
   found locally.

### 3. Paper Reading and Notes -> delegate to sgh-reading-notes

Triggers: 读论文, 看论文, 文献阅读, 阅读笔记, 论文笔记, 精读, 泛读, 做笔记,
整理笔记, Zotero, 批判性阅读, reading list

Action: Load the **sgh-reading-notes** skill and follow its workflow router:
- Question-Driven Read (default, 20-30 min) -- 4-phase methodology: comprehend,
  generate 3-6 questions, read full text to answer, structured summary
- Quick Scan (5 min) -- lighter question-driven scan with 2-3 questions, read/skip verdict
- Critical Review (1 hr+) -- methodology critique, comparison, reproducibility assessment
- Reading List Management -- manage to-read/reading/read status via Zotero tags
- Batch Reading -- scan multiple papers from usv-lit-search results
- Knowledge Synthesis -- synthesize themes across read papers

Uses the **pdf skill** for PDF text extraction when the user provides PDF files.

After every completed full-paper reading, require an innovation-capture pass:
- Identify potentially novel, testable extensions grounded in the paper and SGH's project.
- Separate the paper's claims from SGH's derived ideas; never present an unverified idea as a contribution.
- Append or merge all ideas into the single project register at
  <workspace>/.sgh-research/research-innovations.md.
- Never create one innovation file per paper. If no new idea emerges, append the paper
  to the register's "no new innovation" log.

Script: sgh-reading-notes/scripts/zotero_sync.py -- Zotero integration (list, search,
fetch, note, status, add, stats)

Notes saved to <workspace>/.sgh-research/reading-notes/<paper-id>_<mode>.md.
Zotero child notes synced via pyzotero Web API v3.

### 4. Experiment Design and Simulation -> delegate to sgh-experiment-design

Triggers: 实验设计, 做实验, 仿真实验, 跑仿真, 参数扫描, 参数设置, 对比实验,
消融实验, 实验结果分析, 实验复盘, MATLAB, ROS2, Gazebo

Action: Load the **sgh-experiment-design** skill and follow its three-phase loop:
- Design (Phase 1) -- hypothesis formulation, theory check (veto gate), parameter
  matrix, go/no-go decision
- Execute (Phase 2) -- scaffold experiment directory, capture environment, run with
  logging, parameter sweep (MATLAB / ROS2 / Python)
- Retrospective (Phase 3) -- result consolidation, mechanism diagnosis, next-step
  decision (iterate / collect more data / conclude / pivot)

Script: sgh-experiment-design/scripts/new_experiment.py -- scaffolds experiment
directory with templates, env snapshot, and logging structure.

Experiments saved to <workspace>/.sgh-research/experiments/<exp-id>/.

### 5. Manuscript Writing -> delegate to sgh-manuscript-writing

Triggers: 写论文, 论文写作, 初稿, 润色, LaTeX, 画图, 投稿材料, 写摘要, 写引言,
写方法, 写结果, 写结论, 图表设计, 中翻英

Action: Load the **sgh-manuscript-writing** skill and follow its five-stage pipeline:
- PLAN -- outline construction, paper type, target venue, citation plan
- DRAFT -- section-by-section drafting in academic English (System Model,
  Problem Formulation, Controller Design, Simulation Results, etc.)
- FIGURE -- figure and table design from sgh-experiment-design data
- POLISH -- English polishing, notation/terminology consistency, self-review
- PACKAGE -- cover letter, title page, highlights, declarations

Script: sgh-manuscript-writing/scripts/new_manuscript.py -- scaffolds manuscript
directory with LaTeX template (ieee-conf, ieee-trans, or generic) and outline.

Manuscripts saved to <workspace>/.sgh-research/manuscripts/<manuscript-id>/.

### 6. Code Reproduction -> delegate to sgh-code-reproduction

Triggers: 复现, 代码复现, 算法复现, 跑实验代码, 开源代码, 找代码, 验证结果,
reproduce, implementation

Action: Load the **sgh-code-reproduction** skill and follow its four-phase workflow:
- IDENTIFY -- extract core algorithm, mathematical formulation, expected results
- LOCATE -- search GitHub, PapersWithCode, author repos; assess quality
- REPRODUCE -- set up environment (Python/MATLAB/ROS2), run, log outputs
- VERIFY -- compare metrics against paper, diagnose mismatches, write report

Script: sgh-code-reproduction/scripts/new_reproduction.py -- scaffolds reproduction
directory with templates for algorithm analysis, code search, and verification.

Reproductions saved to <workspace>/.sgh-research/reproductions/<reproduction-id>/.

### 7. Submission Tracking -> delegate to sgh-submission-tracking

Triggers: 投稿, 选期刊, 审稿状态, 回复审稿人, submit, response letter, cover letter,
期刊选择, 投稿状态

Action: Load the **sgh-submission-tracking** skill and follow its four-mode workflow:
- JOURNAL SELECT -- match manuscript to venue (scope, IF, speed, OA, indexing)
- PRE-SUBMISSION -- run checklist, simulated peer review, cover letter
- TRACK -- submission record, status tracking, timeline management
- RESPOND -- point-by-point reviewer responses, revision management

Script: sgh-submission-tracking/scripts/new_submission.py -- scaffolds submission
directory with templates for record, cover letter, response letter, and timeline.

Submissions saved to <workspace>/.sgh-research/submissions/<submission-id>/.

## Cross-Workflow Coordination

SGH_Research's unique value is connecting workflows into a research pipeline:

1. **Search -> Read**: Papers found by usv-lit-search get flagged for question-driven reading
2. **Read -> Innovate**: Completed readings update the shared innovation register
3. **Innovate -> Experiment**: Candidate ideas become hypotheses only after novelty and theory checks
4. **Experiment -> Write**: Validated results feed into manuscript figures and claims
5. **Write -> Submit**: Completed manuscripts enter submission tracking

The shared profile at <workspace>/.sgh-research/profile.json maintains context
across workflows. See references/domain-profile.md for the full profile schema.

## Storage

```
<workspace>/.sgh-research/
  profile.json              # Global research profile (identity, domain, toolchain)
  research-innovations.md   # Single cumulative innovation register across all papers
  reading-notes/            # Paper reading notes (QDR, scan, review, synthesis)
  experiments/              # Experiment logs and results
  manuscripts/              # Draft manuscripts
  submissions/              # Submission tracking
```

Sub-skills maintain their own storage:
- usv-lit-search: <workspace>/.usv-lit-search/

## Research Principles

- Never fabricate citations, results, or experimental data.
- Distinguish published findings from assistant interpretation or speculation.
- Respect academic integrity in all writing and analysis assistance.
- Ground summaries and notes in actual paper content, not generic praise.
- When unsure about a claim, verify against the source before stating it.
- Default language follows the user's language. For Chinese output, use Simplified Chinese.

## Extending SGH_Research

To add a new sub-skill:

1. Create the sub-skill directory under ~/.codex/skills/<sub-skill-name>/
2. Write its SKILL.md with domain-specific workflows, scripts, and references
3. Register it in this SKILL.md's Sub-Skill Architecture table (set status to Active)
4. Add routing rules in the Workflow Router section
5. Update <workspace>/.sgh-research/profile.json under sub_skills

See references/research-workflows.md for the workflow design spec and
references/domain-profile.md for the research domain profile.

## References

| File | When to Load |
|------|-------------|
| references/research-workflows.md | Detailed workflow descriptions, status, I/O contracts |
| references/domain-profile.md | SGH's research domain profile, toolchain, profile schema |
