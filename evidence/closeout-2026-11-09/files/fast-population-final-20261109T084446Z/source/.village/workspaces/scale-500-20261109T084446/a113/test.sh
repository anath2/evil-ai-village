#!/bin/bash
cc -O0 -o vuln vuln.c
cc -O0 -o fixed fixed.c
python3 -c "open('large.bin','wb').write(b'A'*1000)"
./vuln large.bin; echo "vuln exit: $?"
./fixed large.bin; echo "fixed exit: $?"
