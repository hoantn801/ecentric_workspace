#!/usr/bin/env bash
# Chay TOAN BO test JS va bao cao theo MA THOAT, khong theo dong chu cuoi.
#
# Vi sao can file nay. Cach chay cu la mot vong lap ad-hoc doc `tail -1` roi tim chuoi
# "0 hong" / "0 failed". Ngay 01/09 mot suite in "81 dat, 0 hong" nhung exit 1 (nguong
# hard-code 78 cua thoi 26 feature) - vong lap dem no la XANH suot nhieu ngay. Dong chu la
# thu de doc; ma thoat moi la thu de tin.
#
# Dung: bash ecentric_workspace/approval_center/tests/run_js.sh
set -u
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pass=0; fail=0; failed=()
shopt -s nullglob
files=("$here"/js/*.mjs)
if [ ${#files[@]} -eq 0 ]; then
  echo "HONG: khong tim thay file test JS nao - bo test da mo cau truc"
  exit 1
fi
for f in "${files[@]}"; do
  out="$(node "$f" 2>&1)"; rc=$?
  last="$(printf '%s' "$out" | tail -1)"
  if [ $rc -eq 0 ]; then
    pass=$((pass+1)); printf '  [OK]   %-42s %s\n' "$(basename "$f")" "$last"
  else
    fail=$((fail+1)); failed+=("$(basename "$f")")
    printf '  [HONG] %-42s (exit %d) %s\n' "$(basename "$f")" "$rc" "$last"
  fi
done
echo "----"
echo "JS: $pass xanh / $fail hong / ${#files[@]} file"
if [ $fail -gt 0 ]; then printf 'Hong: %s\n' "${failed[*]}"; exit 1; fi
exit 0
