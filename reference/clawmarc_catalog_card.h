#ifndef CLAWXIV_CATALOG_CARD_H
#define CLAWXIV_CATALOG_CARD_H

/*
 * ClawXiv Catalog Card — rc1 (layout 1.2)
 *
 * A fixed 4096-byte survivable descriptor for general artefact cataloging.
 * The card is signed by its issuer for attribution and anti-flooding,
 * but artifact authenticity lives in the artifact bundle and catalog head.
 *
 * Integers are little-endian on the wire. Character arrays are UTF-8/ASCII
 * and NUL padded. There are no pointers and no implicit padding.
 *
 * rc1 changes from layout 1.1: size_class byte (was class_reserved); ARCHIVE
 * artefact class; the arena generalized as a typed overlay carved by
 * arena_split — text classes store [doc-vector | text]; PICTURE stores
 * [favicon/visual | optional caption]; opaque binaries store a category
 * descriptor; work_created/work_revised clarified as cataloging-work
 * (mint-time) fields, not artefact dates.
 */

#include <stddef.h>
#include <stdint.h>

#define CXCC_CARD_BYTES 4096u
#define CXCC_HEADER_BYTES 1216u
#define CXCC_ARENA_BYTES 2816u
#define CXCC_FOOTER_BYTES 64u
#define CXCC_MAGIC "CXCC"

#define CXCC_LAYOUT_MAJOR 1u
#define CXCC_LAYOUT_MINOR 2u

enum cxcc_arena_class {
    CXCC_CLASS_CATALOG_OBJECT = 0,
    CXCC_CLASS_INDIRECT_CATALOG_CARD = 1,
    CXCC_CLASS_DOUBLY_INDIRECT_CATALOG_CARD = 2,

    CXCC_CLASS_ARTICLE = 16,
    CXCC_CLASS_BOOK = 17,
    CXCC_CLASS_PICTURE = 18,
    CXCC_CLASS_MOVIE = 19,
    CXCC_CLASS_MUSIC = 20,
    CXCC_CLASS_SOFTWARE = 21,
    CXCC_CLASS_DATASET = 22,
    CXCC_CLASS_MAP = 23,
    CXCC_CLASS_METADATA = 24,
    CXCC_CLASS_SEQUENCE = 25,
    CXCC_CLASS_MODEL = 26,
    CXCC_CLASS_WEBPAGE = 27,
    CXCC_CLASS_ARCHIVE = 28   /* zip/tar/etc.; no archival-format subtypes in rc1 */
};

/* Coarse artefact-size magnitude bucket (size_class byte). 256 values; rc1
 * uses a decimal-prefix ladder. 0 is a real value: an empty file may still
 * carry metadata worth cataloging. */
enum cxcc_size_class {
    CXCC_SIZE_EMPTY = 0,   /* 0 bytes */
    CXCC_SIZE_64BIT = 1,   /* 1..8 bytes (<= 64 bits) */
    CXCC_SIZE_KB = 2,      /* up to 10^3 bytes */
    CXCC_SIZE_MB = 3,      /* up to 10^6 */
    CXCC_SIZE_GB = 4,      /* up to 10^9 */
    CXCC_SIZE_TB = 5,      /* up to 10^12 */
    CXCC_SIZE_PB = 6,      /* up to 10^15 */
    CXCC_SIZE_EB = 7,      /* up to 10^18 */
    CXCC_SIZE_ZB = 8,      /* up to 10^21 */
    CXCC_SIZE_YB = 9       /* up to 10^24; larger reserved */
};

enum cxcc_access_mode {
    CXCC_ACCESS_OPEN = 0,
    CXCC_ACCESS_ENC_KEY_IN_CARD = 1,
    CXCC_ACCESS_ENC_KEY_VIA_REF = 2,
    CXCC_ACCESS_GATED_PLAINTEXT = 3
};

enum cxcc_encryption_profile {
    CXCC_ENC_NONE = 0,
    CXCC_ENC_AES_256_GCM = 1,
    CXCC_ENC_AGE_X25519_AES_256_GCM = 2
};

enum cxcc_flags {
    CXCC_FLAG_OBJECT_SHA256_PRESENT = 1u << 0,
    CXCC_FLAG_PREV_CARD_PRESENT = 1u << 1,
    CXCC_FLAG_SWARM_REF_PRESENT = 1u << 2,
    CXCC_FLAG_IPFS_CID_PRESENT = 1u << 3,
    CXCC_FLAG_IPNS_PRESENT = 1u << 4,
    CXCC_FLAG_HTTP_HINT_PRESENT = 1u << 5,
    CXCC_FLAG_ARTIFACT_ENCRYPTED = 1u << 6,
    CXCC_FLAG_ACCESS_GATED = 1u << 7,
    CXCC_FLAG_EMBEDDING_PRESENT = 1u << 8,
    CXCC_FLAG_TEXT_TRUNCATED = 1u << 9,
    CXCC_FLAG_ISSUER_CARD_REF_PRESENT = 1u << 10
};

#if defined(_MSC_VER)
#pragma pack(push, 1)
#define CXCC_PACKED
#elif defined(__GNUC__) || defined(__clang__)
#define CXCC_PACKED __attribute__((packed))
#else
#define CXCC_PACKED
#pragma pack(push, 1)
#endif

typedef struct CXCC_PACKED ClawXivCatalogCardV1 {
    /* 0x000 version prefix (8) */
    uint8_t magic[4];
    uint16_t layout_major;
    uint16_t layout_minor;

    /* 0x008 split governor + class + size + flags (8) */
    uint16_t arena_split;       /* embedding length in arena; text = 2816 - arena_split */
    uint8_t arena_class;        /* artefact type / indirection kind */
    uint8_t size_class;         /* artefact size magnitude bucket (enum cxcc_size_class) */
    uint32_t flags;

    /* 0x010 descriptor-grade timestamps (24); all mint-time-grade and EXPECTED
     *       TO DIFFER across producers. work_* describe the CATALOGING work,
     *       not the artefact: work_created = first card in this supersession
     *       chain, work_revised = this revision. Never artefact creation,
     *       never filesystem mtime, never inferred from body content. */
    uint64_t card_issued_unix;
    uint64_t work_created_unix;
    uint64_t work_revised_unix;

    /* 0x028 issuer-local freshness (8) */
    uint64_t sequence;

    /* 0x030 spec self-reference (32) */
    uint8_t schema_sha256[32];

    /* 0x050 object binding + version chain (96) */
    uint8_t object_sha256[32];
    uint8_t source_or_manifest_sha256[32];
    uint8_t prev_card_sha256[32];

    /* 0x0b0 issuer identity + signature (128) */
    uint8_t issuer_pubkey[32];
    uint8_t card_signature[64];
    uint8_t issuer_card_ref[32];

    /* 0x130 access mechanism (100) */
    uint8_t access_mode;
    uint8_t enc_profile;
    uint8_t key_flags;
    uint8_t access_reserved;
    uint8_t artefact_key[32];
    uint8_t access_ref[64];

    /* 0x194 authorship summary (96) */
    uint8_t responsible_orcid[20];
    uint8_t author_count;
    uint8_t classification_count;
    uint8_t url_count;
    uint8_t summary_flags;
    uint8_t primary_author_fpr[32];
    uint8_t author_list_sha256[32];
    uint8_t license_id[8];

    /* 0x1f4 locators (272) */
    uint8_t swarm_reference[32];
    uint8_t ipfs_cid[64];
    uint8_t ipns_name[48];
    uint8_t http_hint[96];
    uint8_t locator_set_sha256[32];

    /* 0x304 text + embedding descriptors (12) */
    uint16_t embedding_profile_id;
    uint16_t title_len;
    uint16_t abstract_len;
    uint16_t keywords_len;
    uint16_t classification_len;
    uint16_t text_flags;

    /* 0x310 content hashes (64) */
    uint8_t text_sha256[32];
    uint8_t embedding_sha256[32];

    /* 0x350 bounded-indirection target (32) */
    uint8_t target_card_id[32];

    /* 0x370 reserved header growth (336) */
    uint8_t header_reserved[336];

    /* 0x4c0 arena (2816): typed overlay carved by arena_split.
     *   arena[0 .. arena_split)    = machine payload, interpreted per arena_class:
     *                                doc embedding vector for text classes
     *                                (profile = embedding_profile_id); a favicon /
     *                                visual bitmap for PICTURE; empty for opaque
     *                                binaries (arena_split = 0).
     *   arena[arena_split .. 2816) = human text: article text, image caption, or
     *                                a category descriptor.
     * An (uncaptioned) image's favicon lives HERE, in the arena, not in a
     * reserved header field. */
    uint8_t arena[2816];

    /* 0xfc0 footer (64) */
    uint32_t header_crc32;
    uint32_t body_crc32;
    uint8_t footer_reserved[56];
} ClawXivCatalogCardV1;

#if defined(_MSC_VER) || !(defined(__GNUC__) || defined(__clang__))
#pragma pack(pop)
#endif

#if defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
#define CXCC_STATIC_ASSERT _Static_assert
#elif defined(__cplusplus) && __cplusplus >= 201103L
#define CXCC_STATIC_ASSERT static_assert
#else
#define CXCC_STATIC_ASSERT(cond, msg) typedef char cxcc_static_assertion_##__LINE__[(cond) ? 1 : -1]
#endif

CXCC_STATIC_ASSERT(sizeof(ClawXivCatalogCardV1) == CXCC_CARD_BYTES,
                   "ClawXivCatalogCardV1 must be exactly 4096 bytes");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, target_card_id) == 0x350,
                   "target_card_id offset must be 0x350");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, arena) == 0x4c0,
                   "arena offset must be 0x4c0");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, header_crc32) == 0xfc0,
                   "footer offset must be 0xfc0");

/* Word-alignment invariants. Every multi-byte field sits on its natural
 * boundary, so the layout needs no padding (the struct is 4096 bytes even
 * WITHOUT __attribute__((packed))) and no field straddles a 64-bit word.
 * These asserts make that guarantee self-enforcing across future edits. */
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, flags) % 4 == 0,
                   "flags must be 4-aligned");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, card_issued_unix) % 8 == 0,
                   "card_issued_unix must be 8-aligned");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, work_created_unix) % 8 == 0,
                   "work_created_unix must be 8-aligned");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, work_revised_unix) % 8 == 0,
                   "work_revised_unix must be 8-aligned");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, sequence) % 8 == 0,
                   "sequence must be 8-aligned");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, embedding_profile_id) % 2 == 0,
                   "embedding_profile_id must be 2-aligned");
CXCC_STATIC_ASSERT(offsetof(ClawXivCatalogCardV1, header_crc32) % 4 == 0,
                   "header_crc32 must be 4-aligned");

#define CXCC_EMBED_PTR(card) ((card)->arena)
#define CXCC_EMBED_LEN(card) ((card)->arena_split)
#define CXCC_TEXT_PTR(card) ((card)->arena + (card)->arena_split)
#define CXCC_TEXT_LEN(card) (CXCC_ARENA_BYTES - (card)->arena_split)

#endif
