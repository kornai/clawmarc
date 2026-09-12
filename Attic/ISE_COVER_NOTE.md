# Draft ISE Cover Note for clawmarc

To: rfc-ise@rfc-editor.org

Subject: Independent Submission request for draft-kornai-clawmarc-00

Dear Independent Submissions Editor,

We request consideration of `draft-kornai-clawmarc-00`, "The clawmarc Catalog
Card Format", for publication in the RFC Editor Independent Submission stream
as an Informational RFC.

clawmarc specifies a fixed-size, 4096-byte catalog-card data format for
content-addressed discovery metadata. The format is intended to improve
interoperability among independent catalog producers and consumers across
storage backends such as local filesystems, HTTP mirrors, IPFS, Swarm, and
institutional archives. It defines a compact signed descriptor, not a network
protocol, not a catalog governance system, and not an Internet Standard.

The draft requests no IANA action. It does describe enum spaces whose future
governance would benefit from stable registration authority, but the identity
of that authority is deliberately left open.

The public bundle includes:

- the Internet-Draft source;
- a reference C layout header;
- a Python reference producer/inspector;
- a reference card.

The public draft author is Andras Kornai. GPT-5 Codex and Claude Opus are
acknowledged in the public draft as AI assistance for drafting, reference
implementation work, and adversarial review.

Detailed provenance for the design and implementation process is maintained in
the associated ClawXiv provenance bundle and can be supplied if useful, but it
is not part of the public-facing draft.

We believe the document is appropriate for the Independent Stream because it
describes an independently developed data format relevant to interoperable
Internet-connected catalogs and replicated archives, while making no claim of
IETF consensus or standards-track status.

Sincerely,

Andras Kornai
