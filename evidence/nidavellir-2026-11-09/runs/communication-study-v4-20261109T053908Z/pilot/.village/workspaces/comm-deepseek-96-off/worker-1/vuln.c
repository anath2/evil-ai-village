#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
    if (argc < 2) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f) return 2;
    char buf[64];
    size_t n = fread(buf, 1, sizeof(buf), f);
    fclose(f);
    /* VULNERABLE: unchecked length */
    if (n > 88) {
        abort();
    }
    puts("ok");
    return 0;
}
