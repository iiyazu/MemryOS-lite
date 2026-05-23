# phase: phase-12

# Phase 12 Case Matrix

Context bundle: `.hermes-loop/work/phase-12/context_bundle.md`.

## Eval Status

- LongMemEval: `limit=0`, `not_applicable`
- LoCoMo: `limit=0`, `not_applicable`

## Why Not Applicable

Phase 12 changed the tool-write archival bridge and archival hit metadata, but it did not change public benchmark scoring or benchmark-specific answer behavior. No milestone case-level eval is required for promotion from this structural phase.

## Required Visible Debt

- `conv-26_qa_028`: pass-to-fail regression from Phase 11
- `conv-26_qa_005`: judged pass with `source_hit=false`
- `conv-26_qa_003`, `conv-26_qa_004`, `conv-26_qa_006`, `conv-26_qa_008`, `conv-26_qa_016`, `conv-26_qa_019`, `conv-26_qa_020`, `conv-26_qa_024`, `conv-26_qa_025`: remaining LoCoMo failures

## Movement Claims

None. This phase is structural and does not claim benchmark movement.
