#include <stdio.h>
#include <stdint.h>
int main(){ FILE* f=fopen(".","rb"); if(!f){puts("fopen fail");return 3;} size_t n=fread((char[64]){0},1,64,f); printf("n=%zu\n",n); return n>999?1:0; }
