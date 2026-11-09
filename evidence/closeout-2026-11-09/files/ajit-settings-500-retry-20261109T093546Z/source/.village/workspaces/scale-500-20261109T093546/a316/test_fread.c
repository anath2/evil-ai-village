#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    FILE *f = fopen(argv[1], "rb");
    if (!f) { printf("open fail\n"); return 2; }
    char buf[64];
    size_t n = fread(buf, 1, sizeof(buf), f);
    fclose(f);
    printf("n=%zu\n", n);
    return 0;
}
