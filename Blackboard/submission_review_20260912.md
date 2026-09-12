# Final Review of WADL Submission (2026-09-12)

Overall, the paper successfully incorporates the required changes from the earlier adversarial review: the ACM reference strip is restored, test-key signatures are transparently addressed, and the results accurately differentiate between the evaluated proxies. 

Here are the specific consistency checks and outstanding items to resolve before final submission:

### 1. The "Every Route" Checksum Claim
**The promise:** On line ~704 of `clawmarc_wadl.tex`, the reproducibility declaration states: 
> *"All four archives were verified byte-exact against \nolinkurl{SHA256SUMS} on every route on 2026-09-12."*
**To deliver:** The `CODEX` handover notes indicate that while HTTP (Lebadus), IPFS, and Swarm routes were hash-verified, the GitHub release log only records asset presence and server-side sizes, not a full byte-exact download verification. 
**Action required:** Perform a full download and SHA-256 verification of the 2.2 GB GitHub assets, or edit this sentence in the paper to explicitly scope it only to the routes that were fully hash-verified. *(Currently in progress)*

### 2. PDF Formatting (Overfull \hbox)
**The promise:** A clean, margin-compliant submission.
**To deliver:** I ran `pdflatex` on the manuscript, and it builds fully into a 7-page PDF, but it throws the following warning in the reproducibility block (around lines 672–703):
`Overfull \hbox (9.07672pt too wide) in paragraph at lines 672--703`
The warning is tied to the long filenames and hashes (e.g., `pilot_run_20260907_mbert_fulltext.json`). 
**Action required:** Visually inspect the final PDF to ensure this line doesn't obtrusively violate the margin. There is also a `Package balance Warning: You have called \balance in second column`, which is typical but worth a quick visual check on the final page.

### 3. Portability Claims (No changes strictly needed)
**The promise:** The C implementation supports the rationale for 32-bit execution, but the paper shouldn't claim it as a measured result since it hasn't been tested yet.
**Status:** The current wording in the paper appropriately maintains this distinction. It accurately states that the operations *"belong on 32-bit machines"*, are *"sized for a Raspberry Pi"*, and explicitly notes that *"the drift experiment of Section~\ref{sec:governance} is where those environments get measured"*. No wording changes are necessary here.

### 4. Lebadus Mirror Status
**The promise:** The paper says the checksum manifest and cards *"are being mirrored"* to the Lebadus endpoint.
**Status:** This language is accurate and appropriately constrained to an ongoing action. 
**Action required:** If you update that mirror, recall Codex's note to remove or label the older `paraphrase-multilingual-mpnet-base-v.tar.zst` file so it doesn't sit alongside the canonical `-v2` file.

### 5. C Tools Repository (If making public)
**The promise:** The paper references public tools.
**Action required:** If the new `reference/c/` dependency-free toolset is meant to be a public submission artifact, ensure you commit the snapshot and update the submitted GitHub reference to point to it, as these are not in the current `v1.rc3` release.
