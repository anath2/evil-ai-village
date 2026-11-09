#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    FILE *f = fopen(argv[1], "rb");
    if (!f) { printf("fopen failed\n"); return 2; }
    char buf[64];
    size_t n = fread(buf, 1, sizeof(buf), f);
    printf("n=%zu (0x%zx) errno?\n", n, n);
    return 0;
}
