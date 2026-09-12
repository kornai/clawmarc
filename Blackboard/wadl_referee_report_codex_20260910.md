# Referee report: “The 4096-byte catalog card”

## Recommendation

**Major revision before acceptance; weak reject in the present form.** The topic is a good fit for WADL: the submission describes an archival metadata format, a reference implementation, content binding, machine-assisted description, and offline discovery. The core idea is sufficiently concrete to merit workshop discussion. The present manuscript, however, does not yet provide a reliable evaluation of the claimed retrieval benefits, and the paper/specification/bundle are not in a single reproducible version state. The style is also more essayistic than scholarly in several places. These are fixable before the deadline, but the numerical and version inconsistencies are blocking issues.

## Summary

The paper proposes a 4096-byte descriptor separate from an artefact and a catalog. It contains fixed-position metadata, SHA-256 bindings, an Ed25519 signature, locators, a human-readable arena, and an optional half-precision document vector. The most plausible contribution is not that fixed-size records are universally superior, but that a fixed-size, content-bound descriptor may be useful as a portable shard-level primitive for archival catalogs: it can be scanned by stride, ranked without fetching the artefact, and carried independently of a particular storage backend.

That narrower contribution could be publishable as a system/position paper if the manuscript distinguished demonstrated properties from design hypotheses and supplied one clean, reproducible experimental record.

## Major content concerns

### 1. Pilot results and bundle provenance are not synchronized

This is the most serious problem. The paper’s pilot paragraph reports profile 2, 0.08 s extraction, 5.9 s minting, 74,000 characters, and pairwise cosine mean 0.95 with range 0.84–0.99. These numbers do appear in `Blackboard/pilot_run_20260907_mbert_fulltext.json`, so they may correspond to a real second run. However:

- `Blackboard/pilot_run_20260907.md` describes the canonical/superseding pilot as profile 1 (`bge-small-en-v1.5`), 11.45 s mean minting, 53,701 mean preimage characters, and cosine mean 0.796 with range 0.592–0.959.
- `provenance/provenance.json` records those profile-1 figures as the project pilot.
- `project.yaml` likewise records the profile-1 pilot.
- The paper does not identify the JSON artifact, exact command, model revision, machine, or relationship between the two runs.

Resolve this explicitly: choose one run as the paper’s experiment, give it a stable identifier, state the model/profile and command, and either remove the other run from the evidentiary path or report both as separate experiments. The profile-2 run is especially important because the staged Internet-Draft still registers profile 1 only, while the paper treats profiles 1–3 as assigned and calls profile 2 the default. Paper, code, specification, cards, and project metadata must be synchronized before submission.

### 2. The IR evaluation is descriptive, not an evaluation of retrieval quality

The twenty-document sample is a useful smoke test, but nearest-neighbor anecdotes and a keyword-hit list do not establish retrieval effectiveness. There are no queries, relevance judgments, baselines, confidence intervals, or held-out data. The sample is drawn from the author’s own paper archive and contains several visibly related papers. Statements such as “retrieval behaved as intended,” “correct,” and “every usable model finds the same clusters” therefore overstate what is measured.

At minimum, recast the section as an implementation demonstration. Preferably add 50–200 documents and 10–20 documented queries, with precision@5/10 or nDCG for (i) keyword search, (ii) vector search, and (iii) a simple hybrid. Define relevance independently of the exact text used to construct the vector. This is feasible on an M1 laptop.

The model-comparison figures have the same limitation. Cosine ranges, pairwise Spearman agreement, and preservation of nearest-neighbor order after float16 conversion are engineering diagnostics, not evidence that one model has better semantic retrieval. “The tuned models approximate a common similarity” is an interpretation; label it as such or test it against judgments.

### 3. The fixed-size advantage is argued but not measured

The manuscript gives plausible arguments for constant stride, memory mapping, bounded corruption, and predictable replication cost. It does not show that these advantages matter relative to a variable-length baseline. The claim that JSON records require “a parser, an index, or a pointer chain whose failure is a failure of the whole” is rhetorically strong and technically imprecise; SQLite/JSON/Parquet and vector-index baselines can provide local access and corruption handling.

Add a small benchmark, or narrow the claims. Generate 1k, 10k, and, if practical, 100k synthetic records/cards with identical metadata and vectors. Measure build time, storage, sequential top-k scan, random-card access, and peak memory for raw cards versus a transparent baseline such as SQLite/JSON plus a NumPy matrix. The point need not be that clawmarc wins every metric; it should identify the workload for which fixed-size records help.

Qualify the storage-language claims as well. “One common filesystem block,” “one common virtual-memory page,” and the assertion that ext4, NTFS, APFS, and XFS all default to 4k fragments are platform-dependent. A 4096-byte card is a portable wire choice, not a guaranteed I/O or VM unit.

### 4. Embedding profiles are not yet a stable interoperability mechanism

The proposal to archive model weights and tokenizers as content-bound artefacts is sensible. But the paper presents it as if it solved model identity while material issues remain open:

- profiles 2 and 3 appear in the paper/code but not in the staged Internet-Draft’s registration table;
- the profile registry/authority is unresolved;
- pooling, chunk size, tokenization, runtime, and floating-point behavior are not all pinned;
- `bert-base-multilingual-cased` is an untuned base encoder, so “768 dimensions” should not be conflated with a validated document-embedding model;
- the proposed model-card mechanism is future architecture, not demonstrated interoperability.

Mark each feature as assigned/tested, implemented but provisional, or proposed. A cheap M1 experiment would run one pinned model through two local loading/runtime paths and report a cosine agreement matrix. Also run a reduction ablation (for example, prefix-only versus full text with two chunk sizes) so readers can separate model effects from reduction-policy effects.

### 5. Cryptographic and migration claims need a threat model

The paper correctly says that a signature authenticates an issuer’s statement, not the artefact’s quality or availability. State explicitly what the card protects against and what it does not: altered bytes, accidental corruption, stale locators, malicious issuer claims, key compromise, replay, and supersession. Embedding a public key does not establish that the key is trusted; provide a trust/distribution and revocation statement, even if the answer is “outside the format.”

The migration discussion is reasonable, but a `previous-card` digest alone does not establish that two cards represent the same intellectual work, nor does it resolve branching migrations. Give one concrete PDF→PDF/A example with two cards and a bound manifest, and state the invariants a consumer can verify.

### 6. Related work should be more operational

The revised section now mentions Linked Data, JSON-LD, schema.org, WARC, Memento, and BagIt, which is an improvement. It still mostly asserts complementarity. A compact comparison table should state what is represented, what is signed, what is content-bound, whether extension is supported, whether retrieval is independent, and whether ranking is possible without fetching. The statement that a classification field can carry a “JSON-LD fragment” needs a serialization, escaping rule, size limit, and consumer interpretation; it should not sound like a substitute for graph interoperability.

There is also a citation issue: `Xiao:2023` is the C-Pack paper, whereas the text presents `bge-small-en-v1.5` as a named model. Cite the authoritative model card or the paper defining that checkpoint, and distinguish checkpoint and embedding-method citations.

## Style and presentation

The paper is readable, but it repeatedly adopts a polished essay voice where a WADL paper would benefit from neutral, testable prose. Examples include:

- “Embedding models age quickly, and a format that froze one would age with it. The card does not.”
- “a drawer of cards and a query vector is a search engine”;
- “the card is the thing that must be everywhere, quickly, in a form that can be trusted without being trusted much”;
- “the choice will be made by the number of producers rather than by argument”;
- “the experiment will have said so before a reviewer did.”

These lines are memorable but sound like advocacy or a manifesto. Replace them with explicit claims and conditions. The card/drawer metaphor is useful once in the introduction; it should not carry the technical argument throughout.

Other recommended edits:

- Replace “nothing more,” “trivial,” “obviously,” “exactly,” and “as intended” when they conceal scope conditions.
- Avoid anthropomorphic or adversarial phrasing about what “the card” does; identify the format, producer, consumer, or catalog operation.
- State the paper type early. Given the evidence, “system description with a preliminary pilot” is more defensible than a completed evaluation.
- Recover space from repeated defenses of 4096 bytes and spend it on one baseline and a limitations paragraph.
- Use consistent terminology for artefact/artifact, profile/model, text prefix/embedding preimage, and card identifier/object digest.
- Give exact laptop hardware and software versions; the bundle currently has M1/M2-era execution references.
- Keep AI-process and cross-model provenance in acknowledgments or a short reproducibility note rather than the technical narrative.

The section organization is serviceable. The main presentation problem is the confidence level of the prose relative to the evidence.

## Experiments feasible on an M1 laptop

1. **Fixed-stride benchmark:** compare raw cards with SQLite/JSON plus a NumPy vector matrix at 1k/10k/100k records; report build time, storage, scan latency, random access, and memory.
2. **Small judged retrieval test:** use 50–200 archive documents and 10–20 queries; compare keyword, vector, and hybrid search using precision@5/10 and nDCG.
3. **Profile/reduction sensitivity:** recompute the same documents with current profiles and at least two reductions; report cosine matrices and ranking overlap.
4. **Reproducibility test:** use one pinned model directory, tokenizer, code revision, and schema across two local loading/runtime paths; report vector cosine, byte-level equality, and legitimately variable fields.
5. **Migration/corruption test:** create a PDF/PDF-A or metadata-modified pair, verify the old card fails against new bytes, verify the new card and previous-card link, and flip bytes at several offsets.
6. **Policy/privacy sanity check:** show that a no-prefix/no-vector policy yields a valid card and document what remains discoverable from digest, title, locators, and signature.

The first two experiments have the highest value for the submission because they directly answer whether the fixed card improves a relevant catalog workload and whether the payload improves retrieval.

## Minor corrections

- Reconcile the abstract’s “current 768-dimensional profile” with the specification’s profile-1 status and the paper’s profile-2 default.
- Give the differential-test artefact a stable name and cite the exact output.
- Explain which fields are normative and which remain producer choice when independent cards differ.
- Clarify whether the 1280-byte text limit is measured in bytes or characters in every layer.
- State whether CRCs are integrity checks only and what regions they cover.
- Do not imply that vectors are comparable across profiles; use separate indices, as the later section says.
- Replace the conclusion’s “either the experiment or the community that will decide them” with a distinction between empirical questions and governance questions.

## Final assessment

There is a worthwhile engineering idea here, and the bundle demonstrates a real implementation rather than only a format sketch. The paper will be substantially stronger if it presents clawmarc as a narrow descriptor primitive, documents one authoritative experimental version, and measures the two central claims: whether fixed-size cards improve a relevant catalog workload, and whether the embedded payload improves retrieval against a baseline. With the pilot/version inconsistency repaired, profile/specification status made coherent, claims softened to match evidence, and essayistic sentences rewritten in neutral scholarly prose, I would be willing to reconsider the submission.
