/* CXCC layout 1.3 portable tools. C99, libc only; no floating point. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <ctype.h>
#include <errno.h>
#include "sha256.h"
#include "tweetnacl.h"
#define CARD 4096u
#define HEADER 1216u
#define ARENA 2816u
#define FOOT 0xfc0u
#define SIG 0xd0u
static uint16_t le16(const unsigned char*p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static uint32_t le32(const unsigned char*p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint64_t le64(const unsigned char*p){uint64_t v=0;int i;for(i=7;i>=0;i--)v=(v<<8)|p[i];return v;}
static void put16(unsigned char*p,uint16_t v){p[0]=(unsigned char)v;p[1]=(unsigned char)(v>>8);}
static void put32(unsigned char*p,uint32_t v){int i;for(i=0;i<4;i++)p[i]=(unsigned char)(v>>(8*i));}
static void put64(unsigned char*p,uint64_t v){int i;for(i=0;i<8;i++)p[i]=(unsigned char)(v>>(8*i));}
static uint32_t crc32(const unsigned char*p,size_t n){uint32_t c=0xffffffffU;size_t i;int j;for(i=0;i<n;i++){c^=p[i];for(j=0;j<8;j++)c=(c>>1)^(0xedb88320U&((uint32_t)-(int32_t)(c&1)));}return c^0xffffffffU;}
static int readfile(const char*path,unsigned char**out,size_t*n){FILE*f=fopen(path,"rb");long z;if(!f)return -1;if(fseek(f,0,SEEK_END)||((z=ftell(f))<0)||fseek(f,0,SEEK_SET)){fclose(f);return -1;}*out=(unsigned char*)malloc((size_t)z+1);if(!*out){fclose(f);return -1;}*n=(size_t)z;if(fread(*out,1,*n,f)!=*n){free(*out);fclose(f);return -1;}fclose(f);(*out)[*n]=0;return 0;}
static void hex(const unsigned char*p,size_t n,char*out){static const char h[]="0123456789abcdef";size_t i;for(i=0;i<n;i++){out[2*i]=h[p[i]>>4];out[2*i+1]=h[p[i]&15];}out[2*n]=0;}
static int zeroes(const unsigned char*p,size_t n){size_t i;for(i=0;i<n;i++)if(p[i])return 0;return 1;}
static int sha_file(const char*path,unsigned char out[32],uint64_t*size){FILE*f=fopen(path,"rb");unsigned char b[8192];size_t n;cxcc_sha256 s;if(!f)return -1;cxcc_sha256_init(&s);*size=0;while((n=fread(b,1,sizeof b,f))!=0){cxcc_sha256_update(&s,b,n);*size+=(uint64_t)n;}if(ferror(f)){fclose(f);return -1;}fclose(f);cxcc_sha256_final(&s,out);return 0;}
static const char*class_name(unsigned c){static const char*names[]={"Collection","Dataset","Event","Image","InteractiveResource","MovingImage","PhysicalObject","Service","Software","Sound","StillImage","Text"};if(c>=16&&c<=27)return names[c-16];return c==0?"Unspecified":c==1?"IndirectCatalogCard":c==2?"DoublyIndirectCatalogCard":"Unassigned";}
static int verify_card(unsigned char card[CARD],const char*object){unsigned char work[CARD],msg[CARD+64],opened[CARD+64],hash[32];unsigned long long mlen;uint64_t sz;
 if(memcmp(card,"CXCC",4))return puts("FAIL bad magic"),1;
 if(le16(card+4)!=1||le16(card+6)!=3)return puts("FAIL unsupported layout"),1;
 if(le16(card+8)>ARENA)return puts("FAIL arena_split out of range"),1;
 if(card[0x133]||!zeroes(card+0x370,336)||!zeroes(card+FOOT+8,56))return puts("FAIL reserved bytes nonzero"),1;
 memcpy(work,card,CARD);memset(work+SIG,0,64);
 if(le32(card+FOOT)!=crc32(work,HEADER))return puts("FAIL header CRC"),1;
 if(le32(card+FOOT+4)!=crc32(work+HEADER,FOOT-HEADER))return puts("FAIL body CRC"),1;
 memcpy(msg,card+SIG,64);memcpy(msg+64,work,CARD);
 if(crypto_sign_open(opened,&mlen,msg,CARD+64,card+0xb0)||mlen!=CARD)return puts("FAIL Ed25519 signature"),1;
 if(object){if(sha_file(object,hash,&sz))return puts("FAIL cannot read object"),1;if(memcmp(hash,card+0x50,32))return puts("FAIL object SHA-256"),1;}
 printf("OK layout=1.3 crc32=ok ed25519=ok object=%s\n",object?"ok":"unchecked");return 0;
}
static int inspect(unsigned char card[CARD]){unsigned char h[32],work[CARD];char x[65],stored[65];size_t split=le16(card+8),cap=ARENA-split,n;const unsigned char*t=card+0x4c0+split;uint16_t lens[4];int i;
 if(memcmp(card,"CXCC",4)||le16(card+4)!=1||le16(card+6)!=3){puts("ERROR unsupported card/layout");return 1;}
 cxcc_sha256_bytes(card,CARD,h);hex(h,32,x);printf("card_id: %s\n",x);memcpy(work,card,CARD);memset(work+SIG,0,64);memset(work+FOOT,0,8);cxcc_sha256_bytes(work,CARD,h);hex(h,32,x);printf("card_content_id: %s\n",x);
 printf("layout: %u.%u\narena_split: %u\narena_class: %u\narena_class_name: %s\nsize_class: %u\nflags: 0x%08x\n",le16(card+4),le16(card+6),(unsigned)split,(unsigned)card[10],class_name(card[10]),(unsigned)card[11],le32(card+12));
 printf("card_issued_unix: %llu\nwork_created_unix: %llu\nwork_revised_unix: %llu\nsequence: %llu\n",(unsigned long long)le64(card+16),(unsigned long long)le64(card+24),(unsigned long long)le64(card+32),(unsigned long long)le64(card+40));
 for(i=0;i<4;i++){hex(card+0x30+32*i,32,x);printf("%s: %s\n",i==0?"schema_sha256":i==1?"object_sha256":i==2?"source_or_manifest_sha256":"prev_card_sha256",x);}
 hex(card+0xb0,32,x);printf("issuer_pubkey: %s\n",x);cxcc_sha256_bytes(card+0xb0,32,h);hex(h,8,x);printf("issuer_fingerprint_prefix: %s\n",x);hex(card+0x110,32,x);printf("issuer_card_ref: %s\naccess_mode: %u\nenc_profile: %u\nkey_flags: %u\n",x,card[0x130],card[0x131],card[0x132]);
 printf("responsible_orcid: %.*s\nauthor_count: %u\nclassification_count: %u\nurl_count: %u\n",20,(const char*)(card+0x194),card[0x1a8],card[0x1a9],card[0x1aa]);hex(card+0x1ac,32,x);printf("primary_author_fpr: %s\n",x);hex(card+0x1cc,32,x);printf("author_list_sha256: %s\nlicense_id: %.*s\n",x,8,card+0x1ec);
 hex(card+0x1f4,32,x);printf("swarm_reference: %s\nipfs_cid: %.*s\nipns_name: %.*s\nhttp_hint: %.*s\n",x,64,card+0x214,48,card+0x254,96,card+0x284);hex(card+0x2e4,32,x);printf("locator_set_sha256: %s\n",x);
 printf("embedding_profile_id: %u\n",le16(card+0x304));lens[0]=le16(card+0x306);lens[1]=le16(card+0x308);lens[2]=le16(card+0x30a);lens[3]=le16(card+0x30c);
 n=cap;while(n&&t[n-1]==0)n--;cxcc_sha256_bytes(t,n,h);hex(h,32,x);hex(card+0x310,32,stored);printf("text_sha256: %s\ncomputed_text_sha256: %s\ntext_flags: %u\n",stored,x,le16(card+0x30e));hex(card+0x330,32,x);printf("embedding_sha256: %s\n",x);hex(card+0x350,32,x);printf("target_card_id: %s\n",x);printf("header_crc32: %08x\nbody_crc32: %08x\ntext_lengths: %u,%u,%u,%u\n",le32(card+FOOT),le32(card+FOOT+4),lens[0],lens[1],lens[2],lens[3]);
 {size_t off=0;const char*names[]={"title","abstract","keywords","classification","body"};for(i=0;i<5;i++){size_t len=i<4?lens[i]:(off<=n?n-off:0);if(off+len>n){puts("ERROR text lengths exceed stored text");return 1;}printf("%s: %.*s\n",names[i],(int)len,(const char*)t+off);off+=len;}}
 return 0;}
static int rdcard(const char*path,unsigned char c[CARD]){unsigned char*b;size_t n;if(readfile(path,&b,&n)){fprintf(stderr,"cannot read %s\n",path);return -1;}if(n!=CARD){fprintf(stderr,"card must be exactly 4096 bytes (got %lu)\n",(unsigned long)n);free(b);return -1;}memcpy(c,b,CARD);free(b);return 0;}
static int b64v(int c){if(c>='A'&&c<='Z')return c-'A';if(c>='a'&&c<='z')return c-'a'+26;if(c>='0'&&c<='9')return c-'0'+52;if(c=='+')return 62;if(c=='/')return 63;return -1;}
static int pem_seed(const char*path,unsigned char seed[32]){
 unsigned char*b,*der;size_t n,i,j=0,k=0;char*raw;int inbody=0;
 if(readfile(path,&b,&n))return -1;
 if(n==32){memcpy(seed,b,32);free(b);return 0;}
 raw=(char*)malloc(n+1);if(!raw){free(b);return -1;}
 for(i=0;i<n;i++){
  if(b[i]=='\n'||b[i]=='\r'){inbody=1;continue;}
  if(inbody&&b[i]=='-')break;
  if(inbody&&!isspace(b[i]))raw[j++]=(char)b[i];
 }
 raw[j]=0;der=(unsigned char*)malloc(j*3/4+4);if(!der){free(raw);free(b);return -1;}
 for(i=0;i+1<j;i+=4){
  int a=b64v(raw[i]),bb=b64v(raw[i+1]);
  int c=i+2<j&&raw[i+2]!='='?b64v(raw[i+2]):0;
  int d=i+3<j&&raw[i+3]!='='?b64v(raw[i+3]):0;
  if(a<0||bb<0)break;
  der[k++]=(unsigned char)((a<<2)|(bb>>4));
  if(i+2<j&&raw[i+2]!='=')der[k++]=(unsigned char)((bb<<4)|((c>>2)&15));
  if(i+3<j&&raw[i+3]!='=')der[k++]=(unsigned char)((c<<6)|d);
 }
 for(i=0;i+36<=k;i++)if(der[i]==4&&der[i+1]==34&&der[i+2]==4&&der[i+3]==32){memcpy(seed,der+i+4,32);free(der);free(raw);free(b);return 0;}
 free(der);free(raw);free(b);return -1;
}
static int parse_u64(const char*s,uint64_t*v){char*e;unsigned long long x;errno=0;x=strtoull(s,&e,10);if(errno||!*s||*e)return -1;*v=(uint64_t)x;return 0;}
static int fromhex(const char*s,unsigned char*out,size_t n){size_t i;if(strlen(s)!=2*n)return -1;for(i=0;i<n;i++){int a;char x=s[2*i],y=s[2*i+1];a=(x>='0'&&x<='9')?x-'0':(x>='a'&&x<='f')?x-'a'+10:(x>='A'&&x<='F')?x-'A'+10:-1;{int b=(y>='0'&&y<='9')?y-'0':(y>='a'&&y<='f')?y-'a'+10:(y>='A'&&y<='F')?y-'A'+10:-1;if(a<0||b<0)return -1;out[i]=(unsigned char)((a<<4)|b);}}return 0;}
static size_t clean(const unsigned char*src,size_t n,unsigned char*out){size_t i=0,o=0;int pending=0;while(i<n){unsigned char c=src[i++];if(c==' '||c=='\t'||c=='\r'||c=='\n'||c=='\v'||c=='\f'){if(o)pending=1;continue;}if(pending){out[o++]=' ';pending=0;}out[o++]=c;}return o;}
static size_t clip_utf8(unsigned char*p,size_t n){size_t start=n;if(!n)return 0;start=n-1;while(start>0&&(p[start]&0xc0)==0x80)start--;{unsigned char c=p[start];size_t need=c<0x80?1:(c&0xe0)==0xc0?2:(c&0xf0)==0xe0?3:(c&0xf8)==0xf0?4:1;if(n-start<need)n=start;}while(n&&(p[n-1]==' '||p[n-1]=='\t'||p[n-1]=='\r'||p[n-1]=='\n'))n--;return n;}
static int fieldarg(int argc,char**argv,int*i,const char*name,unsigned char**dst,size_t*n){size_t z;unsigned char*b;if(strcmp(argv[*i],name))return 0;if(*i+1>=argc)return -1;if(readfile(argv[*i+1],&b,&z))return -1;*dst=(unsigned char*)realloc(*dst,z+1);if(!*dst){free(b);return -1;}memcpy(*dst,b,z+1);*n=z;free(b);(*i)++;return 1;}
static int mint(int argc,char**argv){const char*object=NULL,*outpath=NULL,*seedlabel=NULL,*keyfile=NULL;uint64_t issued=0,created=0,revised=0,seq=0,obj_size=0;unsigned cls=27,sizeclass=0;unsigned char seed[32],pk[32],sk[64],objhash[32],card[CARD],*fields[5]={0},*norm[5]={0};size_t flen[5]={0},nlen[5]={0};const char*opts[]={"--title-file","--abstract-file","--keywords-file","--classification-file","--body-file"};const char*texts[]={"--title","--abstract","--keywords","--classification","--body"};int i,j;unsigned char author[32],loc[32],usedhash[32];size_t fixed,cap,used,absn,bodyn;uint16_t lens[4];FILE*f;
 for(i=1;i<argc;i++){if(!strcmp(argv[i],"--object")&&i+1<argc)object=argv[++i];else if(!strcmp(argv[i],"--out")&&i+1<argc)outpath=argv[++i];else if(!strcmp(argv[i],"--seed-label")&&i+1<argc)seedlabel=argv[++i];else if(!strcmp(argv[i],"--key-file")&&i+1<argc)keyfile=argv[++i];else if(!strcmp(argv[i],"--issued")&&i+1<argc){if(parse_u64(argv[++i],&issued))goto bad;}else if(!strcmp(argv[i],"--work-created")&&i+1<argc){if(parse_u64(argv[++i],&created))goto bad;}else if(!strcmp(argv[i],"--work-revised")&&i+1<argc){if(parse_u64(argv[++i],&revised))goto bad;}else if(!strcmp(argv[i],"--sequence")&&i+1<argc){if(parse_u64(argv[++i],&seq))goto bad;}else if(!strcmp(argv[i],"--class")&&i+1<argc){uint64_t v;if(parse_u64(argv[++i],&v)||v>255)goto bad;cls=(unsigned)v;}else if(!strcmp(argv[i],"--locator-sha256")&&i+1<argc){if(fromhex(argv[++i],loc,32))goto bad;}else if(!strcmp(argv[i],"--author-list-sha256")&&i+1<argc){if(fromhex(argv[++i],author,32))goto bad;}else {int found=0;for(j=0;j<5;j++){int r=fieldarg(argc,argv,&i,opts[j],&fields[j],&flen[j]);if(r<0)goto bad;if(r){found=1;break;}if(!strcmp(argv[i],texts[j])&&i+1<argc){const char*s=argv[++i];flen[j]=strlen(s);fields[j]=(unsigned char*)malloc(flen[j]+1);if(!fields[j])goto bad;memcpy(fields[j],s,flen[j]+1);found=1;break;}}if(!found){fprintf(stderr,"unknown/incomplete option: %s\n",argv[i]);goto bad;}}}
 if(!object||!outpath||(!seedlabel&&!keyfile)||(seedlabel&&keyfile)){fprintf(stderr,"required: --object FILE --out FILE and exactly one of --seed-label LABEL / --key-file PEM\n");goto bad;}
 if(sha_file(object,objhash,&obj_size)){fprintf(stderr,"cannot read object file\n");goto bad;}if(!obj_size)sizeclass=0;else if(obj_size<=8)sizeclass=1;else if(obj_size<=1000)sizeclass=2;else if(obj_size<=1000000)sizeclass=3;else if(obj_size<=1000000000ULL)sizeclass=4;else if(obj_size<=1000000000000ULL)sizeclass=5;else if(obj_size<=1000000000000000ULL)sizeclass=6;else if(obj_size<=1000000000000000000ULL)sizeclass=7;else sizeclass=8;
 if(seedlabel)cxcc_sha256_bytes(seedlabel,strlen(seedlabel),seed);else if(pem_seed(keyfile,seed)){fprintf(stderr,"key must be a raw 32-byte seed or Ed25519 PKCS#8 PEM\n");goto bad;}crypto_sign_seed_keypair(pk,sk,seed);
 {static const char empty_auth[]="{\"authors\":[],\"signers\":[]}";static const char empty_loc[]="{\"http_hint\":\"\",\"http_mirrors\":[],\"ipfs_cid\":\"\",\"ipns_name\":\"\",\"swarm_reference\":\"\"}";cxcc_sha256_bytes(empty_auth,sizeof(empty_auth)-1,author);cxcc_sha256_bytes(empty_loc,sizeof(empty_loc)-1,loc);}
 /* Explicit digest options override the canonical empty-set defaults. */
 for(i=1;i<argc;i++){if(!strcmp(argv[i],"--locator-sha256")&&i+1<argc)fromhex(argv[++i],loc,32);else if(!strcmp(argv[i],"--author-list-sha256")&&i+1<argc)fromhex(argv[++i],author,32);}
 for(j=0;j<5;j++){if(!fields[j]){fields[j]=(unsigned char*)calloc(1,1);if(!fields[j])goto bad;}norm[j]=(unsigned char*)malloc(flen[j]+2);if(!norm[j])goto bad;nlen[j]=clean(fields[j],flen[j],norm[j]);}
 fixed=nlen[0]+nlen[2]+nlen[3];if(fixed>ARENA){fprintf(stderr,"title+keywords+classification exceed arena\n");goto bad;}cap=ARENA-fixed;absn=nlen[1];if(absn>cap){absn=clip_utf8(norm[1],cap);}cap-=absn;bodyn=nlen[4];if(bodyn>cap)bodyn=clip_utf8(norm[4],cap);
 memset(card,0,CARD);memcpy(card,"CXCC",4);put16(card+4,1);put16(card+6,3);put16(card+8,0);card[10]=(unsigned char)cls;card[11]=(unsigned char)sizeclass;put32(card+12,1U|(absn<nlen[1]||bodyn<nlen[4]?1U<<9:0));put64(card+16,issued);put64(card+24,created);put64(card+32,revised);put64(card+40,seq);
 {static const unsigned char schema[32]={0x1d,0xfa,0xee,0x46,0x85,0x3b,0x9b,0x3e,0x4c,0x27,0x86,0xac,0x7b,0x73,0x0c,0xc3,0x93,0x96,0x7a,0xc8,0x44,0x4e,0xcb,0xf5,0x56,0x96,0x7e,0x73,0xef,0x4d,0x86,0xf1};memcpy(card+0x30,schema,32);}memcpy(card+0x50,objhash,32);memcpy(card+0xb0,pk,32);card[0x130]=0;card[0x131]=0;
 memcpy(card+0x1cc,author,32);memcpy(card+0x1ec,"CC0-1.0",7);memcpy(card+0x2e4,loc,32);put16(card+0x304,0);lens[0]=(uint16_t)nlen[0];lens[1]=(uint16_t)absn;lens[2]=(uint16_t)nlen[2];lens[3]=(uint16_t)nlen[3];for(j=0;j<4;j++)put16(card+0x306+2*j,lens[j]);put16(card+0x30e,1);
 {unsigned char*t=card+0x4c0;size_t pos=0;memcpy(t+pos,norm[0],nlen[0]);pos+=nlen[0];memcpy(t+pos,norm[1],absn);pos+=absn;memcpy(t+pos,norm[2],nlen[2]);pos+=nlen[2];memcpy(t+pos,norm[3],nlen[3]);pos+=nlen[3];memcpy(t+pos,norm[4],bodyn);pos+=bodyn;used=pos;cxcc_sha256_bytes(t,used,usedhash);memcpy(card+0x310,usedhash,32);}
 put32(card+FOOT,crc32(card,HEADER));put32(card+FOOT+4,crc32(card+HEADER,FOOT-HEADER));{unsigned char sm[CARD+64];unsigned long long smlen;if(crypto_sign(sm,&smlen,card,CARD,sk)||smlen!=CARD+64){fprintf(stderr,"signing failed\n");goto bad;}memcpy(card+SIG,sm,64);}
 f=fopen(outpath,"wb");if(!f||fwrite(card,1,CARD,f)!=CARD||fclose(f)){fprintf(stderr,"cannot write output\n");goto bad;}printf("OK minted %s bytes=4096 object_size=%llu text_bytes=%lu truncated=%s\n",outpath,(unsigned long long)obj_size,(unsigned long)used,(absn<nlen[1]||bodyn<nlen[4])?"yes":"no");
 for(j=0;j<5;j++){free(fields[j]);free(norm[j]);}return 0;
bad:for(j=0;j<5;j++){free(fields[j]);free(norm[j]);}return 2;}
int main(int argc,char**argv){const char*prog=strrchr(argv[0],'/');unsigned char card[CARD];const char*mode=prog?prog+1:argv[0];if(argc<2){fprintf(stderr,"usage: %s CARD [--object FILE]\n       cxcc-mint-text --object FILE --out FILE --seed-label LABEL [options]\n",mode);return 2;}if(!strcmp(mode,"cxcc-mint-text")||!strcmp(argv[1],"mint"))return mint(argc,argv);if(rdcard(argv[1],card))return 2;if(!strcmp(mode,"cxcc-inspect")||!strcmp(argv[1],"inspect"))return inspect(card);if(!strcmp(mode,"cxcc-verify")||!strcmp(argv[1],"verify")){const char*object=NULL;int i;for(i=2;i+1<argc;i++)if(!strcmp(argv[i],"--object"))object=argv[++i];return verify_card(card,object);}fprintf(stderr,"unknown command\n");return 2;}
