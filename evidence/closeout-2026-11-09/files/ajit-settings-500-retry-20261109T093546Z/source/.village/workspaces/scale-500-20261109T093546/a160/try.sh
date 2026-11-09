#!/bin/bash
cc -O0 -o /tmp/v vuln.c
cc -O0 -o /tmp/f fixed.c
for p in big /dev/zero /dev/null /dev/full /dev/urandom /dev/stdin /proc/self/mem /proc/self/fd/0; do
  /tmp/v "$p" >/dev/null 2>&1; echo "v $p => $?"
done
