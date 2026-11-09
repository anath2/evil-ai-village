#!/bin/bash
cc -O0 -o /tmp/vuln vuln.c
cc -O0 -o /tmp/fixed fixed.c
for p in /dev/zero /dev/null /dev/random . /tmp /proc/self/mem /proc/self/fd/0 /dev/full; do
  echo "=== $p ==="
  /tmp/vuln "$p" >/dev/null 2>&1; echo "vuln exit $?"
  /tmp/fixed "$p" >/dev/null 2>&1; echo "fixed exit $?"
done
