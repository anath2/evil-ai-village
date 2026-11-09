#include <stdio.h>
#include <stdlib.h>
int main(){
    FILE *f=fopen(".", "rb");
    if(!f){perror("fopen"); return 1;}
    char buf[64];
    size_t n=fread(buf,1,sizeof(buf),f);
    printf("n=%zu err=%d\n", n, ferror(f));
    fclose(f);
    return 0;
}
