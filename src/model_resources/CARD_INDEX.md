# Model-resource card index

The four cards below are the **root cards** for these model archives: signed,
text-only Software cards whose `object_sha256` is the digest of the corresponding
`.tar.zst`. Their schema digest binds the normative C header
(`reference/clawmarc_catalog_card.h`, SHA-256 `1dfaee46…`), as the two reference
cards do. Each carries locators for the identical bytes — an HTTPS hint
(lebadus.ai) with a second HTTPS mirror (the GitHub release `v1.rc3` assets),
an IPFS CIDv1, and a Swarm reference — in the signed card and its `.cxcc.json`
sidecar (the mirror list is covered by the signed locator-set digest). The
signatures use the deterministic **test** issuer seed recorded in the sidecar and
are therefore reproducible and forgeable by design; they attest reproducibility,
not issuer identity (see `PUBLISH_MANIFEST.md`).

| model | archive SHA-256 | card ID |
|---|---|---|
| `BAAI/bge-small-en-v1.5` | `417c6f409e54bb5e2c69f70572dae50c5a21fab33aeb1e775cb9296549a7b8ca` | `1e6f3f41f4afbc678a1118d837ffd3664f9d80d033b7ee81cb11aaf1e1a55c1c` |
| `bert-base-multilingual-cased` | `e6b69b84dcddbccc09da5f433cd816ebab5d9ed55d4ccf06f3103eeebcf2defa` | `52e67acd73ba1b3e527a6f30e15052b75de608548b7c9aa44b7a520490449dbc` |
| `xlm-roberta-base` | `17fe5d884ba71ad3e3777fbcf14fed3b1c0a8a884f1d232e11ceeb9531abfe39` | `a452acf6cafd8950ceb6548c494a532895de550e56b7deae036b141a58d18732` |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | `2c69401687941ea50096af37554dd6f65baa0cadb0074bc92d326f52f173a1b2` | `2071b96f8812bf9e52801423706118ddb1eab36d71a537a66f32a6968602b976` |

Locators (identical bytes on every route):

| model | IPFS CID | Swarm reference | HTTPS (hint; mirror) |
|---|---|---|---|
| `BAAI/bge-small-en-v1.5` | `bafybeigayb3vbhwjzl7oegaq3o6rveczpqwepl3ujp6cwyfknpgdb3ajdq` | `2f8f27a1e8d410ca89f326c9ee192dc9dc3c3cfbd45aa7c4fb5496294dbf6072` | `https://lebadus.ai/Resources/Models/bge-small-en-v1.5.tar.zst`; `https://github.com/kornai/clawmarc/releases/download/v1.rc3/bge-small-en-v1.5.tar.zst` |
| `bert-base-multilingual-cased` | `bafybeifcdyij2s76mjyq4dz6ewhylshabirarix3hlpssm2az2ll6qdozy` | `8d37f0629330e85531c4538713a5d09d32438b7c7ded3b142348af555a1703fc` | `https://lebadus.ai/Resources/Models/bert-base-multilingual-cased.tar.zst`; `https://github.com/kornai/clawmarc/releases/download/v1.rc3/bert-base-multilingual-cased.tar.zst` |
| `xlm-roberta-base` | `bafybeie2yxjx476trpufwly63cxoav7yyem6knbcqj7iu4l3zynz652rlu` | `163af1893aa1dab12f02ed4b74046ea7f13ef696bab0c4fe73a5559698965f66` | `https://lebadus.ai/Resources/Models/xlm-roberta-base.tar.zst`; `https://github.com/kornai/clawmarc/releases/download/v1.rc3/xlm-roberta-base.tar.zst` |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | `bafybeiaj5xm2znmqajxzh76rpdvq76pdartldy3g64zmarcdyafgsen5ea` | `159c66f03fcb736ca6ea3ca45c5e5ac4fd064e194cf1eb09adf814b558e5e7b6` | `https://lebadus.ai/Resources/Models/paraphrase-multilingual-mpnet-base-v2.tar.zst`; `https://github.com/kornai/clawmarc/releases/download/v1.rc3/paraphrase-multilingual-mpnet-base-v2.tar.zst` |

## Embedding-profile status

Which of the four a libangel instance can use as an approved embedding profile
(for content-card vectors). The three tuned models resolve their profile from the
Hugging Face id or the bare archive/directory name
(`libangel_mint.lookup_embedding_profile`).

| model | embedding profile | usable for card vectors |
|---|---|---|
| `BAAI/bge-small-en-v1.5` | profile 1 (384-dim f16, `bge-small-en-v1.5-f16le`) | yes |
| `bert-base-multilingual-cased` | profile 2 (768-dim f16, `mbert-cased-f16le`) | yes |
| `xlm-roberta-base` | none | no (degenerate; reference/comparison only) |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | profile 3 (768-dim f16, `paraphrase-multilingual-mpnet-base-v2-f16le`) | yes |
