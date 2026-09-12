---
title: "The clawmarc Catalog Card Format"
abbrev: "clawmarc"
category: info
docname: draft-kornai-clawmarc-01
submissiontype: independent
ipr: trust200902
stand_alone: true
area: "General"
keyword:
  - cataloging
  - content addressing
  - metadata
  - discovery
  - digital libraries
author:
  -
    fullname: "Andras Kornai"
    organization: "Independent"
    email: "andras@kornai.com"
informative:
  IPFS:
    title: "IPFS: Content Addressed, Versioned, P2P File System"
    author:
      -
        ins: "J. Benet"
        name: "Juan Benet"
    date: 2014
  SWARM:
    title: "Ethereum Swarm Documentation"
    target: "https://www.ethswarm.org/"
  BGE:
    title: "BAAI/bge-small-en-v1.5"
    target: "https://huggingface.co/BAAI/bge-small-en-v1.5"
normative:
  RFC2119:
  RFC8174:
  RFC8032:
  FIPS180-4:
    title: "Secure Hash Standard (SHS)"
    author:
      -
        org: "National Institute of Standards and Technology"
    date: 2015
    target: "https://doi.org/10.6028/NIST.FIPS.180-4"
  UAX15:
    title: "Unicode Normalization Forms"
    author:
      -
        org: "The Unicode Consortium"
    target: "https://www.unicode.org/reports/tr15/"
--- abstract

This document specifies clawmarc, a fixed-size, 4096-byte catalog card for
describing digital artefacts in content-addressed and replicated catalogs. A
clawmarc card binds to the bytes of an artefact, carries compact human-readable
descriptive text and an optional machine-readable search payload, records
retrieval hints, and is signed by its issuer. The format is intended to improve
interoperability among independent catalog producers and consumers without
requiring any particular storage backend, catalog governance model, or search
engine. This document is an Independent Stream Informational specification; it
does not represent IETF consensus and does not define an Internet standard.

--- middle

# Note to Readers

This draft is prepared for the RFC Editor Independent Submission stream. It is
not a standards-track document and requests no IANA action. The accompanying
public bundle includes a reference C header, a Python reference implementation,
and a reference card. The full design history and provenance are maintained in
the associated ClawXiv provenance bundle and are intentionally not reproduced
here.
GPT-5 Codex and Claude Opus provided AI assistance in drafting, reference
implementation work, and adversarial review; that assistance is acknowledged
below rather than represented as public byline authorship.

# Introduction

Publication makes an artefact retrievable; cataloging makes it findable. A
large catalog of research, cultural, or software artefacts needs a descriptor
that is small enough to replicate aggressively, uniform enough to be processed
mechanically, and rich enough to be useful to humans and search systems even
when detached from the artefact it describes.

clawmarc specifies such a descriptor. Each card is exactly 4096 bytes, a
size chosen to align with common memory pages and filesystem blocks while
remaining small enough for eager replication. The card is a descriptor, not a
proof of authenticity or availability. If a candidate artefact is later found,
the card's cryptographic binding can be checked against it.

The format is storage-neutral. Cards and artefacts may be carried over local
filesystems, HTTP mirrors, IPFS {{IPFS}}, Swarm {{SWARM}}, institutional
archives, or future content-addressed stores. The format specifies the card,
not the catalog
network.

## Layer Model

clawmarc is useful in a three-layer model:

* CARD: the 4096-byte descriptor specified here.
* ARTEFACT: the thing described by the card.
* CATALOG: a collection of cards, indices, shards, heads, and policy.

A card can outlive its artefact. Authenticity and availability are resolved at
the artefact and catalog layers; the card supplies a compact, signed,
content-bound description.

# Conventions and Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHOULD", "SHOULD
NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this
document are to be interpreted as described in BCP 14 {{RFC2119}} {{RFC8174}}
when, and only when, they appear in all capitals, as shown here.

Artefact:
: The digital object being cataloged.

Card:
: A 4096-byte clawmarc record as specified here.

Issuer:
: The party that mints and signs a card.

Producer:
: An implementation that creates cards.

Arena:
: The variable-content region of the card.

Catalog head:
: A signed mutable pointer to a set of cards or card shards. Catalog heads are
  outside the scope of this document.

All integers are unsigned and little-endian unless stated otherwise. Character
fields are UTF-8 or ASCII, NUL-padded to their fixed width.

# Design Rationale

## Fixed Size

A fixed-size card can be packed into shards, addressed by ordinal,
memory-mapped, scanned in constant stride, and validated by a single length
check before parsing. A variable-size record would save some bytes but would
make every one of those operations more complex.

## 4096 Bytes

The 4096-byte size is selected to match common system granules. It is one
frequent filesystem block, one common virtual-memory page, and small enough
that a catalog of one million cards is about four gigabytes. It is large enough
to hold SHA-256 digests, Ed25519 public keys and signatures, locators,
human-readable metadata, and a compact machine-readable search payload.

## Header, Arena, and Footer

The card is divided into:

* a 1216-byte header;
* a 2816-byte arena;
* a 64-byte footer.

The header contains fixed-position fields. The arena is interpreted according
to the artefact class and split point. The footer contains non-cryptographic
CRC checks.

## Alignment

Every multi-byte field is on its natural boundary. The reference structure
compiles to exactly 4096 bytes without padding and is nevertheless declared
packed to guarantee the wire layout across compilers.

# Card Format

The normative byte layout is the companion C structure in
`clawmarc_catalog_card.h`, included in the public bundle. The layout is
summarized in {{offset-table}}.

## Version Prefix

The first eight bytes contain:

* `magic`, the ASCII string `CXCC`;
* `layout_major`;
* `layout_minor`.

The magic string is retained for wire compatibility with the implementation
history. The public format name is clawmarc.

## Split, Class, Size, and Flags

`arena_split` divides the arena into machine payload and human text.
`arena_class` names the artefact class or card-collection kind. `size_class`
is a coarse magnitude bucket for the artefact size. `flags` records the
presence of optional fields.

## Timestamps and Sequence

`card_issued_unix`, `work_created_unix`, and `work_revised_unix` describe the
cataloging work, not the artefact's creation or filesystem timestamps. A
producer MUST NOT infer these timestamps from artefact content. `sequence` is
issuer-local monotone freshness metadata.

Independent producers are expected to differ in these fields.

## Bindings

`schema_sha256` identifies the frozen specification bundle used by a producer:
the RFC prose together with its normative reference header. `object_sha256` is
the primary SHA-256 {{FIPS180-4}} binding to the artefact bytes.
`source_or_manifest_sha256` is an optional secondary binding to a build
manifest. `prev_card_sha256` forms a supersession chain.

The object binding says that the card describes those bytes. It does not say
that the artefact is authentic, available, or endorsed by anyone other than the
card issuer.

## Issuer Identity and Signature

The issuer signs the card with Ed25519 {{RFC8032}}. The signature attributes the
card to the issuer; it is also the basis for catalog-level flood control and
issuer reputation. It is not an authenticity proof for the artefact.

## Locators

The inline locator fields are:

* `swarm_reference`;
* `ipfs_cid`;
* `ipns_name`;
* `http_hint`;
* `locator_set_sha256`.

Inline locators are fast paths. A fuller mirror set can be stored elsewhere and
bound by `locator_set_sha256`.

## Text and Machine Payload Descriptors

`embedding_profile_id`, the four text lengths, `text_flags`, `text_sha256`,
and `embedding_sha256` describe how the arena is read.

`text_sha256` is the SHA-256 digest of the full used human-text byte string:
`arena[arena_split:2816]` with trailing NUL padding removed. It therefore
covers the title, abstract, keywords, classification, and any stored body
prefix. The four text lengths delimit only the fixed metadata segments at the
front of that string; remaining non-NUL bytes, if any, are the body prefix.

## Indirection Target

`target_card_id` is available for future bounded indirection. It is unused by
the rc1 collection model, where the collection artefact itself is bound by
`object_sha256` and read at 4096-byte stride.

# The Arena

The 2816-byte arena is split by `arena_split`:

* `arena[0:arena_split]`: machine payload;
* `arena[arena_split:2816]`: human text.

The machine payload is interpreted by `arena_class`.

For text artefacts, the payload is a document vector when one is present. The
human text contains title, abstract, keywords, classification, and as much of
the body prefix as fits.

For image artefacts, the payload can be a small visual reduction when permitted
by the producer's extraction policy, and the text can contain a caption or
descriptor.

For opaque artefacts, `arena_split` is zero and the text contains a category
descriptor. A producer MUST NOT fabricate a document vector for bytes that do
not contain running text.

# Artefact Classes and Enum Governance {#enum-governance}

The initial `arena_class` values are sparse:

~~~
0   Catalog object / direct card
1   Indirect catalog-card collection
2   Doubly-indirect catalog-card collection
3-15 Unassigned
16  Article
17  Book
18  Picture
19  Movie
20  Music
21  Software
22  Dataset
23  Map
24  Metadata
25  Sequence
26  Model
27  Web page
28  Archive
29-255 Unassigned
~~~

Similarly, `embedding_profile_id` and `enc_profile` define small initial
allocations and leave most values unassigned:

~~~
embedding_profile_id:
0  No embedding
1  BAAI/bge-small-en-v1.5, 384 dimensions, binary16 little-endian
2-65535 Unassigned

enc_profile:
0  None
1  AES-256-GCM
2  age/X25519-style recipient wrapping with AES-256-GCM content
3-255 Unassigned
~~~

Embedding profile 1 names BAAI/bge-small-en-v1.5 {{BGE}}.

Stable registration authority for these enum spaces would improve
interoperability. This document deliberately does not name that authority.
Possible future authorities include a public digital-library committee, a
clawmarc/LibrarianAngel governance body, or another competent public cataloging
institution. Until an authority exists, producers SHOULD avoid consuming
unassigned values in public cards except by agreement among the catalogs that
will consume them.

# Signing and Verification

The 64-byte `card_signature` field is treated as zero for signing, CRC
calculation, and `card_content_id`. The CRC fields are also treated as zero for
the cryptographic signature and `card_content_id`.

Two identifiers are useful:

* `card_content_id`: SHA-256 of the card with signature and CRCs zeroed.
* `card_id`: SHA-256 of the full signed card.

To verify a card, a consumer checks size and magic, validates both CRCs with
the signature field zeroed, and verifies the Ed25519 signature against
`issuer_pubkey`.

# Card Collections {#collections}

clawmarc supports card collections with bounded depth.

A direct card describes a leaf artefact. An indirect card describes a
collection of direct cards, typically a binary artefact that concatenates
4096-byte cards and can be read at 4096-byte stride. A doubly-indirect card
describes a collection of indirect cards. Consumers therefore descend at most
two collection levels.

This mechanism is for aggregation, not arbitrary alias recursion.

# Producer Requirements

A producer SHOULD identify artefact type by content rather than filename
alone. It SHOULD use version-pinned extractors for text formats and normalize
text to Unicode NFC {{UAX15}}. It SHOULD degrade to a category descriptor rather
than fail when an artefact is opaque.

For text artefacts, the document vector is computed over the full extracted
body when the producer creates one. Long-body reduction is not settled by this
document. Producers MUST record enough information about extraction and
reduction for comparison and reproduction, but consumers SHOULD compare such
vectors by cosine similarity rather than byte identity.

## Producer Authority and Derived Representations

A clawmarc card is intended to be informative. Its human text, machine payload,
locators, and hashes are designed to help catalogs and readers identify,
compare, retrieve, and understand artefacts.

Some card fields are derived representations of the artefact rather than merely
external metadata. Examples include text prefixes, document vectors, image
reductions, OCR text, transcripts, captions, and archive-member listings.
Producers MAY omit any such representation even when the artefact type would
permit it. Omission can reflect local policy, operator authorization,
publication context, cost, resource limits, or unavailable tooling.

A producer that stores a derived representation SHOULD record, in implementation
metadata or an associated manifest, the extraction policy and tooling that
produced it. The clawmarc format defines where such representations can be
stored and how they are bound to the card; it does not define who is authorized
to create, store, replicate, or publish them.

# Catalog Use

Cards are immutable objects suitable for replication. Catalog heads, admission
policy, reputation, search indexing, anchoring, and governance are outside the
scope of this document. A catalog can shard cards into larger artefacts and use
indirect and doubly-indirect cards to describe those shards.

# Security Considerations

## Card Signatures Do Not Authenticate Artefacts

A valid card signature proves that an issuer made a signed statement about an
object hash. It does not prove that the artefact is authentic, available, safe,
or endorsed by another party.

## Flooding and Impersonation

Anyone can mint signed cards. The format makes cards attributable; catalogs
must still decide which issuers to admit, rank, or quarantine.

## Encrypted Artefacts

If a card carries a decryption key, possessing the card can be equivalent to
possessing access to the artefact. Such cards require the same distribution
care as the material they unlock.

## Embeddings as Descriptions

A stored embedding is a compact content-derived description. It can support
search and comparison, and it can also reveal gist-level information about the
content it represents. Producers SHOULD treat embeddings as publication-bearing
metadata rather than as anonymization or concealment.

## Publication Posture

Publishing a card is itself a publication act. Even when an artefact is not
included, a card may intentionally disclose enough information to identify,
summarize, retrieve, classify, or compare it. Producers and catalogs should
therefore apply the same institutional, legal, and ethical review to card
payloads that they apply to other catalog records and finding aids.

## Parser Robustness

Consumers MUST validate length, magic, split boundaries, reserved-zero fields,
and CRCs before interpreting fields. Consumers MUST reject cards whose
`arena_split` exceeds the arena size.

# IANA Considerations

This document makes no request of IANA.

The enum spaces in {{enum-governance}} would benefit from
future public registration authority, but this document does not ask IANA to
serve as that authority.

# Independent Stream Status

This document is intended for the RFC Editor Independent Submission stream. It
does not represent IETF consensus, does not define an Internet Standard, and
does not modify any Internet protocol. It defines a data format that may be
useful to Internet-connected catalogs and archives.

# Reference Implementation

The public clawmarc bundle includes:

* `reference/clawmarc_catalog_card.h`;
* `reference/libangel_card.py`;
* `reference/libangel_catalog.py`;
* `reference/libangel_mint.py`;
* `reference/libangel_inspect.py`;
* `cards/reference_dropofwater.cxcc`.

The C header is the reference layout. The Python implementation is a reference
producer and inspector, not a required implementation language.

--- back

# Offset Table {#offset-table}

~~~
offset  size  field
0x000      4  magic[4] = "CXCC"
0x004      2  layout_major
0x006      2  layout_minor
0x008      2  arena_split
0x00a      1  arena_class
0x00b      1  size_class
0x00c      4  flags
0x010      8  card_issued_unix
0x018      8  work_created_unix
0x020      8  work_revised_unix
0x028      8  sequence
0x030     32  schema_sha256
0x050     32  object_sha256
0x070     32  source_or_manifest_sha256
0x090     32  prev_card_sha256
0x0b0     32  issuer_pubkey
0x0d0     64  card_signature
0x110     32  issuer_card_ref
0x130      1  access_mode
0x131      1  enc_profile
0x132      1  key_flags
0x133      1  access_reserved
0x134     32  artefact_key
0x154     64  access_ref
0x194     20  responsible_orcid
0x1a8      1  author_count
0x1a9      1  classification_count
0x1aa      1  url_count
0x1ab      1  summary_flags
0x1ac     32  primary_author_fpr
0x1cc     32  author_list_sha256
0x1ec      8  license_id
0x1f4     32  swarm_reference
0x214     64  ipfs_cid
0x254     48  ipns_name
0x284     96  http_hint
0x2e4     32  locator_set_sha256
0x304      2  embedding_profile_id
0x306      2  title_len
0x308      2  abstract_len
0x30a      2  keywords_len
0x30c      2  classification_len
0x30e      2  text_flags
0x310     32  text_sha256
0x330     32  embedding_sha256
0x350     32  target_card_id
0x370    336  header_reserved
0x4c0   2816  arena
0xfc0      4  header_crc32
0xfc4      4  body_crc32
0xfc8     56  footer_reserved
~~~

# Acknowledgments

GPT-5 Codex and Claude Opus provided AI assistance in drafting, reference
implementation work, and adversarial review. Detailed provenance is kept with
the ClawXiv `rfc-clawhiv` provenance bundle. The public clawmarc bundle
contains the clean specification and reference artifacts.
