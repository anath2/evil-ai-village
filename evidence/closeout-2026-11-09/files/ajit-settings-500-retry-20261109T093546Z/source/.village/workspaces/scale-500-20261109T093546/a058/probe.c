#include <stdio.h>
#include <errno.h>
int main(int argc,char**argv){FILE*f=fopen(argv[1],"rb"); if(!f){perror("fopen");return 2;} char b[64]; errno=0; size_t n=fread(b,1,sizeof b,f); printf("n=%zu errno=%d\n",n,errno); perror("fread"); return 0;}
