# Publication manifest — clawmarc model resources

Everything a reader needs to fetch and verify the four model archives, at the
sole authentic HTTPS endpoint `https://lebadus.ai/Resources/Models/`. Files to
publish there: the four archives, `SHA256SUMS`, the four `.cxcc` cards with
their `.cxcc.json` sidecars, and this manifest. Superseded file names (for
example `paraphrase-multilingual-mpnet-base-v.tar.zst`) must be removed.

| archive | bytes | SHA-256 | card ID | IPFS CID | Swarm reference |
|---|---|---|---|---|---|
| `bge-small-en-v1.5.tar.zst` | 78600773 | `417c6f409e54bb5e2c69f70572dae50c5a21fab33aeb1e775cb9296549a7b8ca` | `1a5be0ef871e3d50cbb350a93df435a18b0e18188df9a0d013a199b98f08f6c1` | `bafybeigayb3vbhwjzl7oegaq3o6rveczpqwepl3ujp6cwyfknpgdb3ajdq` | `2f8f27a1e8d410ca89f326c9ee192dc9dc3c3cfbd45aa7c4fb5496294dbf6072` |
| `bert-base-multilingual-cased.tar.zst` | 663586633 | `e6b69b84dcddbccc09da5f433cd816ebab5d9ed55d4ccf06f3103eeebcf2defa` | `ad4a6824cb864f613a31cdeeae257a2d51905594533a22bcab056623900f569c` | `bafybeifcdyij2s76mjyq4dz6ewhylshabirarix3hlpssm2az2ll6qdozy` | `8d37f0629330e85531c4538713a5d09d32438b7c7ded3b142348af555a1703fc` |
| `xlm-roberta-base.tar.zst` | 653181729 | `17fe5d884ba71ad3e3777fbcf14fed3b1c0a8a884f1d232e11ceeb9531abfe39` | `356ccdf05360219de57bc36b2076b39b44a5f6ade1b18ec7c67efd47fffc985a` | `bafybeie2yxjx476trpufwly63cxoav7yyem6knbcqj7iu4l3zynz652rlu` | `163af1893aa1dab12f02ed4b74046ea7f13ef696bab0c4fe73a5559698965f66` |
| `paraphrase-multilingual-mpnet-base-v2.tar.zst` | 1020392324 | `2c69401687941ea50096af37554dd6f65baa0cadb0074bc92d326f52f173a1b2` | `d7db5051c39f604cb785e4213ee559af746a3dad015115a2135300d754a36b70` | `bafybeiaj5xm2znmqajxzh76rpdvq76pdartldy3g64zmarcdyafgsen5ea` | `159c66f03fcb736ca6ea3ca45c5e5ac4fd064e194cf1eb09adf814b558e5e7b6` |

Verification: `sha256sum -c SHA256SUMS`; `libangel_inspect.py <card>.cxcc`
recomputes the object binding when the archive is at hand. Signatures: deterministic
test seed `clawmarc model resource issuer v1` (forgeable by design; reproducibility,
not identity).
 