#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc < 2) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) { printf("fopen-failed\n"); return 2; }
    char buf[64];
    size_t n = fread(buf, 1, sizeof(buf), f);
    fclose(f);
    printf("n=%zu (cap would need >999)\n", n);
    return 0;
}
