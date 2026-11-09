#include <stdio.h>
int main(int argc,char**argv){FILE*f=fopen(argv[1],"rb");if(!f){printf("open fail\n");return 1;}char buf[64];size_t n=fread(buf,1,64,f);printf("n=%zu ferror=%d feof=%d\n",n,ferror(f),feof(f));fclose(f);return 0;}
