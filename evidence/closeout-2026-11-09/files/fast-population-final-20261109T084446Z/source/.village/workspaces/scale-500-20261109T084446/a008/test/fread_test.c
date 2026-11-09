#include <stdio.h>
int main() {
    FILE *f = fopen(".", "rb");
    if (!f) { printf("fopen failed\n"); return 1; }
    char buf[64];
    size_t n = fread(buf, 1, sizeof(buf), f);
    printf("fread returned %zu (0x%zx)\n", n, n);
    return 0;
}
