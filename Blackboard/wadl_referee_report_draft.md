### WADL 2026 Referee Report: "The 4096-byte catalog card"

**Overall Recommendation:** Weak Reject / Major Revision (Requires Significant Rewriting)

**1. Topic Suitability:**
The topic is theoretically an excellent fit for WADL. The Call for Papers explicitly invites work on "archival standards, protocols, systems, and tools" and "AI and automation for archiving." A proposal for a machine-native metadata descriptor that integrates cryptographic bindings, decentralized locators (IPFS/Swarm), and AI-generated document vectors is highly relevant to the web archiving community. 

However, the submission claims to be a "system description + lessons from practice" (a Short Paper under the CFP). By the author’s own admission in Section 7, the system "has not yet been run at that scale, and no claim is made here about throughput or about the behaviour of a catalog of millions of cards." A differential test between two LLMs producing two cards is a toy experiment, not a "lesson from practice." The paper reads more like a position piece or a provocation.

**2. Presentation Style and Framing (The IETF Grievance):**
The presentation style is the paper's most fatal flaw. Roughly 60% of the paper (the abstract and Sections 3 through 6) is structured as a point-by-point rebuttal to an unnamed "Independent Submissions Editor" (ISE) who rejected the format at the IETF. 

This framing is entirely inappropriate for a free-standing academic paper. WADL attendees are here to evaluate the technical merits of a system, not to serve as an appellate court for an IETF rejection. Framing the architecture purely as a defense against someone else's objections gives the paper a defensive, chip-on-the-shoulder tone. It forces the author to spend precious page space arguing *against* the ISE rather than demonstrating *for* the digital library community. The paper must be completely rewritten to present `clawmarc` on its own terms, relegating the IETF history to a brief footnote or acknowledging the ISE's feedback neutrally without structuring the entire argument around it.

**3. Technical Execution and Merit:**
The core technical premise—fixing the card size at exactly 4096 bytes—is an extreme, anachronistic engineering choice that creates more problems than it solves. 
* **Premature Optimization:** The author argues that variable-length records require parsers and pointer chains, which are slow or brittle. In 2026, we parse gigabytes of JSON or Protocol Buffers in milliseconds. Truncating an author's abstract or human-readable description simply to avoid a `malloc()` call or to guarantee constant-stride memory mapping is an unacceptable trade-off for a library catalog.
* **Embedding Brittleness:** Embedding a 384-dimensional document vector directly into the binary layout is clever for local search. However, the vector space is tied to a specific embedding model (`bge-small-en-v1.5`). AI models age incredibly fast. What happens in two years when the community moves to a 768-dimensional model, or a multi-modal embedding? The fixed 4096-byte layout has no graceful upgrade path without wasting space or breaking the format entirely.
* **Hash Fragility:** Binding the card to the artifact via SHA-256 is cryptographically sound, but operationally fragile for digital libraries. If an artifact undergoes a trivial format migration (e.g., PDF/A conversion) or a metadata header change, the SHA-256 hash breaks, rendering the card entirely orphaned. The paper needs to address how archiving workflows handle format normalization.

**4. Consideration of Relevant Literature:**
The literature review is myopic. The author cites MARC, Dublin Core, and OAI-PMH, which is standard. But there is a glaring, almost willful omission of the last two decades of metadata research—specifically, Linked Open Data, the Semantic Web, `schema.org`, and JSON-LD. 

The digital library community has spent 20 years moving away from rigid, siloed binary records toward graph-based, extensible, machine-readable semantic triples. Proposing a fixed-position binary structure in C without so much as comparing it to RDF or JSON-LD is a massive oversight. If the author believes flat binary records are superior to graph metadata for AI agents, they must argue that explicitly against the established literature.

**5. Additional Objections (The "Axe to Grind"):**
* **The "Librarians vs. Systems Engineers" friction:** The author asserts that "the problem of discovery is false positives, not missing selectors" and dismisses human cataloging nuance in favor of AI-generated "thought vectors." This borders on technical chauvinism. A vector cosine similarity score cannot replace controlled vocabularies and authority control (e.g., VIAF, ORCID—though ORCID is minimally supported in the header). The paper treats traditional subject codes as an afterthought, which will alienate the exact community the author is trying to woo.
* **The Registry Problem:** The author admits in Section 6 that they have created enumerations (like "arena class") without a registrar, and suggests this workshop community might want to take on the burden of governing it. This is naive. You cannot drop an orphaned specification on a workshop and ask them to maintain its magic numbers. 

**Conclusion for the Author:**
There is a highly interesting provocation here about using fixed-size binary structures for edge-based, AI-native catalog search. But to be published, you must remove the IETF grievance narrative, situate your binary format against modern Linked Data architectures, and provide actual benchmark data showing that a 4096-byte constant-stride scan actually outperforms modern variable-length vector databases at scale.