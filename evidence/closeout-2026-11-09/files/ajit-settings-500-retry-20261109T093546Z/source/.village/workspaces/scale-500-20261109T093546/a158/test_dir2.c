#include <stdio.h>
#include <stdint.h>
int main(){FILE*f=fopen("dir_test","rb"); char b[64]; size_t n=fread(b,1,sizeof(b),f); printf("n=%zu (0x%zx) err=%d\n", n, n, ferror(f)); return 0;}
