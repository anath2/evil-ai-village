#include <stdio.h>
int main(int argc,char**argv){FILE*f=fopen(argv[1],"rb"); if(!f){perror("fopen");return 2;} char b[64]; size_t n=fread(b,1,sizeof(b),f); printf("n=%zu err=%d\n",n,ferror(f)); if(fclose(f)) perror("fclose");}
