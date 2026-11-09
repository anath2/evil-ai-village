#include <stdio.h>
int main(){ FILE*f=fopen("testdir","rb"); if(!f){perror("fopen");return 2;} char b[64]; size_t n=fread(b,1,64,f); printf("n=%zu ferror=%d feof=%d\n",n,ferror(f),feof(f)); fclose(f); return 0;}
