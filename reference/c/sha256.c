/* Small, integer-only SHA-256 implementation (public domain). */
#include "sha256.h"
static const uint32_t K[64]={
0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U};
static uint32_t rr(uint32_t x,unsigned n){return (x>>n)|(x<<(32-n));}
static void transform(cxcc_sha256*s,const unsigned char*b){uint32_t w[64],a,c,d,e,f,g,h,t1,t2,bb;int i;
 for(i=0;i<16;i++)w[i]=((uint32_t)b[4*i]<<24)|((uint32_t)b[4*i+1]<<16)|((uint32_t)b[4*i+2]<<8)|b[4*i+3];
 for(i=16;i<64;i++){uint32_t x=w[i-15],y=w[i-2];w[i]=(rr(x,7)^rr(x,18)^(x>>3))+w[i-16]+(rr(y,17)^rr(y,19)^(y>>10))+w[i-7];}
 a=s->h[0];bb=s->h[1];c=s->h[2];d=s->h[3];e=s->h[4];f=s->h[5];g=s->h[6];h=s->h[7];
 for(i=0;i<64;i++){t1=h+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^(~e&g))+K[i]+w[i];t2=(rr(a,2)^rr(a,13)^rr(a,22))+((a&bb)^(a&c)^(bb&c));h=g;g=f;f=e;e=d+t1;d=c;c=bb;bb=a;a=t1+t2;}
 s->h[0]+=a;s->h[1]+=bb;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;}
void cxcc_sha256_init(cxcc_sha256*s){static const uint32_t iv[8]={0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};int i;for(i=0;i<8;i++)s->h[i]=iv[i];s->bits=0;s->used=0;}
void cxcc_sha256_update(cxcc_sha256*s,const void*p,size_t n){const unsigned char*b=p;while(n){size_t k=64-s->used;if(k>n)k=n;{size_t i;for(i=0;i<k;i++)s->block[s->used+i]=b[i];}s->used+=k;b+=k;n-=k;s->bits+=(uint64_t)k*8;if(s->used==64){transform(s,s->block);s->used=0;}}}
void cxcc_sha256_final(cxcc_sha256*s,unsigned char out[32]){uint64_t bits=s->bits;unsigned i;s->block[s->used++]=0x80;if(s->used>56){while(s->used<64)s->block[s->used++]=0;transform(s,s->block);s->used=0;}while(s->used<56)s->block[s->used++]=0;for(i=0;i<8;i++)s->block[63-i]=(unsigned char)(bits>>(8*i));transform(s,s->block);for(i=0;i<8;i++){out[4*i]=(unsigned char)(s->h[i]>>24);out[4*i+1]=(unsigned char)(s->h[i]>>16);out[4*i+2]=(unsigned char)(s->h[i]>>8);out[4*i+3]=(unsigned char)s->h[i];}}
void cxcc_sha256_bytes(const void*d,size_t n,unsigned char out[32]){cxcc_sha256 s;cxcc_sha256_init(&s);cxcc_sha256_update(&s,d,n);cxcc_sha256_final(&s,out);}
