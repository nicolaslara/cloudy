#!/bin/sh
# Synthesis soft cap: warn >300 lines, fail >600 (source dirs only).
fail=0
for f in $(find backend/cloudy frontend/src -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) 2>/dev/null); do
  n=$(wc -l < "$f")
  if [ "$n" -gt 600 ]; then echo "FAIL $f: $n lines (>600)"; fail=1
  elif [ "$n" -gt 300 ]; then echo "WARN $f: $n lines (>300 soft cap)"; fi
done
exit $fail
