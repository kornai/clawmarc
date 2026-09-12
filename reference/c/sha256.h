#ifndef CXCC_SHA256_H
#define CXCC_SHA256_H
#include <stddef.h>
#include <stdint.h>
typedef struct { uint32_t h[8]; uint64_t bits; unsigned char block[64]; size_t used; } cxcc_sha256;
void cxcc_sha256_init(cxcc_sha256 *s);
void cxcc_sha256_update(cxcc_sha256 *s, const void *data, size_t len);
void cxcc_sha256_final(cxcc_sha256 *s, unsigned char out[32]);
void cxcc_sha256_bytes(const void *data, size_t len, unsigned char out[32]);
#endif
