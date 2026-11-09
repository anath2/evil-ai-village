#include <stdio.h>
int main(int c,char**v){FILE*f=fopen(v[1],"rb");char b[64];size_t n=fread(b,1,sizeof(b),f);printf("n=%zu\n",n);return 0;}
