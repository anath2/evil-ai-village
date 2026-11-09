#include <stdio.h>
int main(){ FILE *f=fopen("/tmp","rb"); if(!f){perror("fopen"); return 2;} char b[64]; size_t n=fread(b,1,sizeof(b),f); printf("n=%zu\n",n); perror("fread"); fclose(f); return 0;}
