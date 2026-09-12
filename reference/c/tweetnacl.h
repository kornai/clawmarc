/* TweetNaCl API subset. TweetNaCl source is public domain. */
#ifndef CXCC_TWEETNACL_H
#define CXCC_TWEETNACL_H
int crypto_hash(unsigned char *out, const unsigned char *in, unsigned long long inlen);
int crypto_sign(unsigned char *sm, unsigned long long *smlen, const unsigned char *m, unsigned long long n, const unsigned char *sk);
int crypto_sign_open(unsigned char *m, unsigned long long *mlen, const unsigned char *sm, unsigned long long n, const unsigned char *pk);
int crypto_sign_seed_keypair(unsigned char *pk, unsigned char *sk, const unsigned char *seed);
#endif
