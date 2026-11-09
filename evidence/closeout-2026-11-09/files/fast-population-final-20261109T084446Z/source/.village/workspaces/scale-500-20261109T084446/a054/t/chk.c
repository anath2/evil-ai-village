#include <stdio.h>
int main(int argc,char**argv){FILE*f=fopen(argv[1],"rb");char b[64];size_t n=fread(b,1,sizeof(b),f);printf("n=%zu\n",n);return 0;}
