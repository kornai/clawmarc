# Adversarial review for Claude: `clawmarc_wadl`

**Reviewer:** GPT-5 Codex (OpenAI), 2026-09-11  
**Artifact reviewed:** `src/clawmarc_wadl.tex`, compiled PDF, local reference implementation, result artifacts, cards, model-resource bundle, and public endpoints checked on 2026-09-11.  
**Recommendation:** revise before submission; weak reject in the present externally released state.

## Summary judgment

The paper has a real and defensible systems contribution if stated narrowly: a fixed-size, content-bound descriptor can be a useful portable catalog substrate, particularly where dense card-only scans, independent storage locators, and offline validation matter. The paper is substantially improved over the earlier draft: it now acknowledges Linked Data, migration, profile obsolescence, proxy relevance, and the limits of its retrieval claims.

The present submission is not yet release-ready because the public reproducibility story is false as written, the ACM template reports a mandatory-format violation, and the signing demonstration does not provide issuer authenticity against an adversary. These are not cosmetic issues. A skeptical WADL reviewer who follows the GitHub and model links will not find the version described in the manuscript, and a reader who follows the code can derive the reference issuer's private key from a public seed label.

## Findings

### 1. [technical] Blocking — The manuscript disables mandatory ACM reference metadata

The build succeeds, but `acmart` emits:

> ACM reference format is mandatory for papers over one page. Please add `printacmref=true` to the `\\settopmatter` command.

The source explicitly contains `\\settopmatter{printacmref=false}`. The result is a six-page ACM paper that suppresses the reference strip despite the class warning. Unless WADL explicitly instructs authors to suppress it, this is a submission-format defect. Change it to `printacmref=true` or obtain an organizer-approved exception and document that exception. Do not submit with a known class-level compliance warning.

### 2. [technical] Blocking — The public GitHub repository is not the bundle described by the paper

The paper says the public bundle contains the specification in Markdown, XML, text, and HTML, the C header, the Python tools, reference cards, and the implementation footnote links readers to `https://github.com/kornai/clawmarc`.

The live GitHub repository was reachable on 2026-09-11, and it does contain `libangel_catalog.py`, `libangel_mint.py`, `libangel_inspect.py`, the C header, and `cards/reference_dropofwater.cxcc`. But its root exposes only `draft-kornai-clawmarc-00.xml`; the current `src/` tree, `clawmarc_wadl.tex`, layout-1.3 draft, model resources, and `reference_geminiexit.cxcc` are absent. Direct checks returned 404 for:

- `https://raw.githubusercontent.com/kornai/clawmarc/main/src/model_resources/CARD_INDEX.md`
- `https://raw.githubusercontent.com/kornai/clawmarc/main/cards/reference_geminiexit.cxcc`
- `https://raw.githubusercontent.com/kornai/clawmarc/main/draft-kornai-clawmarc-02.md`

This is particularly damaging because `project.yaml` itself says GitHub is “still at layout 1.2 — push after AK review.” The paper must either delay submission until the public repository is a reproducible snapshot of the submitted version, or state clearly that the linked repository is historical and provide a versioned archive/commit containing the actual artifact. A moving, known-stale GitHub link is not sufficient for a paper whose central claims concern byte-level interoperability.

### 3. [technical] Blocking — The external model-resource release is incomplete and ambiguous

The local model-resource cards and archives are internally coherent: all four local archives match `SHA256SUMS` and the cards' signed object hashes, and all six local cards are 4096 bytes and verify under the local verifier. The public situation is different.

The live `https://lebadus.ai/Resources/Models/` directory was reachable and listed the four canonical archives, but it did **not** list `SHA256SUMS`, although the local README says it is a file to publish. It also lists an extra older-looking file, `paraphrase-multilingual-mpnet-base-v.tar.zst`, alongside the canonical `...-v2.tar.zst`. The exact archive URLs respond, but a ranged request confirmed only transfer availability, not end-to-end byte identity. The BGE transfer also timed out in the check after 1.5 MB while returning HTTP 200, so availability is not the same as a usable, verifiable download.

The paper does not cite these model archives or their cards at all, yet Section 3 presents model identity and archived weights as a central part of the design. Publish the checksum manifest and four cards/sidecars at the same stable endpoint, remove or label superseded files, and give readers a manifest with exact URLs, sizes, hashes, and card IDs. Until then, call the model archive publication staged rather than public.

### 4. [technical] Blocking — The reference signer is forgeable by anyone who reads the source

`reference/libangel_mint.py` sets:

```text
DEFAULT_ISSUER_SEED = "LibAngel reference issuer v1: GPT-5 Codex independent DropOfWater card"
```

and `deterministic_private_key()` hashes the seed label into an Ed25519 private key. The same seed label is exposed in the model-card JSON sidecars. Thus anyone can reproduce the private key and mint a different card carrying a valid signature under the same issuer public key. This is acceptable for a deterministic differential-test fixture, but it is not an issuer signature in an adversarial or archival sense.

The paper carefully says a valid signature is not proof of authenticity, but it still repeatedly describes cards as “signed by their issuer” and treats signatures as attribution and anti-flooding. Those claims need a trust model. Separate test fixtures from release signing: use an unrecoverable/random private key for published reference artifacts, publish the public key through an authenticated trust channel, and say what key rotation, revocation, and compromise mean. If deterministic signatures are retained for reproducibility, label them test signatures and explicitly say that the published key is intentionally forgeable.

### 5. [technical] Should-fix — The manuscript overstates binding of content policy and manifests

Section 3 says the extraction/reduction policy is “recorded in a manifest the card binds,” and Section 4 says the producer records the policy in the card's manifest. In the general producer, ordinary-file cards set `source_or_manifest_sha256` to zero; the content policy and embedding metadata are placed in the JSON sidecar and are not hashed into the card. The manifest hash is populated only in selected archive/project paths and in the collection script.

This distinction matters: a reader can verify that the card describes the object bytes, but cannot infer from the card that the sidecar policy is the policy used. Either hash a canonical policy/reduction manifest into every relevant card or rewrite the paper to say that policy evidence is external sidecar metadata unless an explicit manifest is supplied.

### 6. [technical] Should-fix — The paper/specification/profile version state is still split

The paper presents layout 1.3 and profiles 1–3 as current. The local code and cards do use layout 1.3, and the staged local specification is draft -02. The uploaded IETF Datatracker document remains draft -00, while the live GitHub tree is an older layout. The paper gives no stable version identifier or schema hash for the exact format used in the experiments.

Add a one-line reproducibility declaration containing the layout version, schema SHA-256, code commit/archive hash, model-resource card IDs, and experiment artifact names. Clarify that draft -02 is staged and not the uploaded I-D. A paper about self-describing fixed records cannot leave the reader to guess which of three public format states is normative.

### 7. [argument] Should-fix — The fixed-size case remains a plausible rationale, not an evaluated result

The paper makes sensible claims about fixed-stride addressing, predictable catalog size, memory mapping, and card-only ranking. It does not compare those operations with a realistic variable-length baseline. The paper therefore demonstrates that fixed-size cards *permit* these operations, not that they improve a digital-library workload.

The strongest unsupported sentence is the suggestion that variable-length formats generally require a separate indexing/parsing layer whose failure can take down the catalog. SQLite, Parquet, JSON-lines plus offsets, and ordinary vector matrices are obvious counterexamples. Either add a small raw-card versus SQLite/NumPy benchmark, or consistently label these as design hypotheses and remove comparative language.

### 8. [technical] Should-fix — The retrieval evaluation is reproducible numerically but under-described scientifically

The reported Cranfield and NewReuters numbers match the checked-in result JSONs to the displayed precision. The 20-PDF profile-2 pilot also matches `Blackboard/pilot_run_20260907_mbert_fulltext.json` (0.08 seconds extraction, 5.88 seconds minting, 74,076-character mean preimage, cosine range 0.839–0.991). This is good evidence that the figures were not simply invented.

However, the paper still omits the exact code revision, model directory hashes, hardware/software versions, random seeds for all runs, and a compact results table with the number of evaluated queries. It also reports no uncertainty or statistical comparison. The NewReuters “MAP” is a same-topic proxy over queries sampled from the same 5,000-document pool; the paper acknowledges this, but the metric should be named `proxy-MAP` in every table and sentence. It must not visually resemble judged Cranfield MAP.

The sentence that the tuned models “approximate a common similarity” is an interpretation of a small pairwise Spearman comparison, not an empirical conclusion about semantic similarity. Mark it as a hypothesis.

### 9. [technical] Should-fix — The embedding profile description is not enough for interoperability

The paper correctly recognizes that model weights alone do not determine a vector. But the actual profile still leaves pooling, chunk boundaries, chunk weighting, tokenizer/runtime behavior, and floating-point environment partly producer-chosen. The differential test's 0.989 same-text cross-pipeline cosine is evidence of this residual, not a bound on it.

The paper should distinguish “model identity is content-bound” from “vectors are reproducible.” The current model cards are opaque archives and the current runtime is not pinned. Also replace or supplement `Xiao:2023`, which cites the C-Pack paper, with the authoritative checkpoint/model-card citation for `BAAI/bge-small-en-v1.5`; the paper currently makes a named-checkpoint claim with a paper citation that does not identify that checkpoint precisely.

### 10. [technical] Note — The local validation story contains a stale script

`reference/scripts/validate_clawmarc_repo.sh` fails from this repository because it computes its root as `reference/` and then expects draft files, `content_policy.py`, and scripts at paths that belong to the earlier checkout layout. The README already admits that the script is not runnable from this split tree. That is honest, but the public “reference implementation” should not ship a validation command known to fail in the bundle it accompanies. Either repair it for this layout or move it to an explicitly historical directory.

Independent local checks did pass for the C header size/offset assertions, Python compilation in the available cryptography environment, card byte lengths, archive SHA-256 values, and Ed25519 verification of the six local cards.

### 11. [argument] Note — The paper's central contribution should be framed as a substrate, not a search method

The abstract mostly does this correctly, and the limitations around Cranfield/NewReuters are responsible. Keep that discipline throughout. The 20-document nearest-neighbor examples are a demonstration of card-only access, not evidence that the catalog finds semantically relevant material. The paper is strongest when it says the format preserves a place for different retrieval methods; it weakens itself whenever it sounds as if vectors solve catalog quality, authority control, or semantic interoperability.

### 12. [other] Note — Add an explicit comparison table and a trust/authority paragraph

The related-work prose is now broad enough to include Dublin Core, Linked Data/JSON-LD, schema.org, Signposting, WARC, Memento, and BagIt, but readers still have to reconstruct the comparison. A small table should contrast extensibility, content binding, signatures, transport assumptions, offline verification, and vector/ranking support.

The governance section should also state who is allowed to mint profile IDs, how a consumer learns which issuer keys to trust, and whether a card with a valid signature but unknown issuer is merely syntactically valid or admissible to a catalog. These are not implementation details; they determine whether “signed” means anything outside a local experiment.

## What I would require before submission

1. Restore ACM reference metadata or document an organizer-approved exception.
2. Publish one immutable, complete version of the exact bundle linked by the paper, including layout-1.3 spec, WADL source/PDF, code, both reference cards, model cards, and checksum manifest.
3. Replace the forgeable deterministic release signer with a clearly labeled test key or a real release key and trust statement.
4. Correct the policy/manifest binding language.
5. Add a reproducibility block with schema hash, code hash, model card IDs, hardware, software, seeds, and exact result artifacts.
6. Keep Cranfield MAP and NewReuters proxy-MAP visibly separate, and call the 20-document pilot an implementation demonstration.

**Final recommendation to Claude and the releaser:** **revise before submission**. The design is worth presenting, but the current version asks the reader to trust a public reproducibility path that is demonstrably one revision behind and a signature mechanism whose private key is public. Those two defects should be repaired before the paper is sent out.
