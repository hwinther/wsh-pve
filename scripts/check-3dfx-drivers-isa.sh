#!/usr/bin/env bash
# Checks that the qemu-3dfx guest drivers run on a Pentium-class guest CPU: disassembles each file
# and fails on any instruction beyond the Pentium Pro (MMX, SSE and later: any mm/xmm/ymm/zmm
# register, POPCNT, LZCNT, BMI, CRC32, MOVBE, fences, prefetch, MXCSR, FXSAVE/XSAVE, RDRAND, 3DNow!). Upstream's makefiles build the MinGW parts with -march=x86-64-v2,
# which a `cpu: pentium3` guest under TCG faults on; submodules/qemu-3dfx-drivers.patch builds them
# for the Pentium, and `make 3dfx-drivers` runs this check on the result.
#
#   scripts/check-3dfx-drivers-isa.sh FILE...
#
#   *.dll *.exe *.sys  PE images (MinGW objdump, else objdump)
#   *.o                DJGPP COFF objects, the DXEs' code before dxe3gen links them (DJGPP objdump)
#   *.obj              Open Watcom OMF objects, the OVL's code (wdis)
#   *.so *.so.N        i386 ELF shared libraries, the Linux guest wrapper (objdump)
#
# P6 instructions (CMOV, FCMOV, FCOMI) are counted but allowed: the MinGW runtime (printf, gdtoa,
# the pseudo-relocation code) that the DLLs link statically is built for i686 by the toolchain.
# TZCNT is allowed too: GCC emits `rep bsf` for __builtin_ctz where a zero input is undefined, which
# objdump shows as tzcnt and a CPU without BMI1 runs as BSF (the same result for a non-zero input).
# Runs in the djgpp-build image (ghcr.io/hwinther/wsh-pve/djgpp-build), which has all three tools;
# the ELF libraries need only binutils' objdump (scripts/build-3dfx-linux-glide.sh runs it on those).
# Exit status: 0 all clean, 1 a file has such an instruction, 2 a file couldn't be disassembled.
set -euo pipefail

[ $# -gt 0 ] || { sed -n '2,/^set -euo/{/^set -euo/d;s/^# \{0,1\}//;p}' "$0" >&2; exit 2; }

tool() {
    local t
    for t in "$@"; do
        if command -v "$t" > /dev/null 2>&1; then echo "$t"; return; fi
    done
}
pe_objdump=$(tool i686-w64-mingw32-objdump objdump)
coff_objdump=$(tool i686-pc-msdosdjgpp-objdump)
wdis=$(tool wdis)
elf_objdump=$(tool objdump)

# One instruction per line ("mnemonic operands"), lower case; objdump's and wdis's layouts
disasm() {
    case "$1" in
        *.dll | *.DLL | *.exe | *.EXE | *.sys | *.SYS)
            [ -n "$pe_objdump" ] || return 2
            "$pe_objdump" -d --no-show-raw-insn "$1" | sed -n 's/^ *[0-9a-f]\{1,\}:\t//p' ;;
        *.o)
            [ -n "$coff_objdump" ] || return 2
            "$coff_objdump" -d --no-show-raw-insn "$1" | sed -n 's/^ *[0-9a-f]\{1,\}:\t//p' ;;
        *.so | *.so.[0-9]*)
            [ -n "$elf_objdump" ] || return 2
            "$elf_objdump" -d --no-show-raw-insn "$1" | sed -n 's/^ *[0-9a-f]\{1,\}:\t//p' ;;
        *.obj)
            [ -n "$wdis" ] || return 2
            # "0016  66 BA F8 03<tabs>mov<tabs>dx,0x03f8"; data lines have no tab after the bytes
            "$wdis" "$1" | sed -n 's/^[0-9A-F]\{4,\}  [0-9A-F ]*[0-9A-F]\t\{1,\}//p' ;;
        *) return 2 ;;
    esac | tr '[:upper:]' '[:lower:]' | sed 's/<[^>]*>//g'
}

status=0
for f in "$@"; do
    if [ ! -f "$f" ]; then
        echo "check-3dfx-drivers-isa: FAIL $f: no such file"
        status=2
        continue
    fi
    if ! dis=$(disasm "$f") || [ -z "$dis" ]; then
        echo "check-3dfx-drivers-isa: FAIL $f: could not disassemble it (no tool for it in this image?)"
        status=2
        continue
    fi
    # $1 the mnemonic (after any prefix), the rest the operands
    result=$(printf '%s\n' "$dis" | awk '
        {
            gsub(/\t+/, " ")
            n = split($0, w, " ")
            i = 1
            while (i < n && w[i] ~ /^(rep|repz|repnz|repe|repne|lock|data16|addr16|addr32|cs|ds|es|fs|gs|ss|notrack|bnd)$/) i++
            m = w[i]
            ops = ""
            for (j = i + 1; j <= n; j++) ops = ops " " w[j]
            total++
            bad = 0
            if (m ~ /^(emms|femms|popcnt|lzcnt|crc32|movbe|ldmxcsr|stmxcsr|sfence|lfence|mfence|clflush|clflushopt|clwb|movnti|andn|bextr|blsi|blsmsk|blsr|bzhi|pdep|pext|rorx|sarx|shlx|shrx|mulx|adcx|adox|rdrand|rdseed|xgetbv|cmpxchg16b|monitor|mwait)$/) bad = 1
            if (m ~ /^(prefetch|fxsave|fxrstor|xsave|xrstor|pf|pi2f|pmulhrw|pavgusb|pswapd)/) bad = 1
            if (ops ~ /(^|[^a-z0-9_])[xyz]mm[0-9]/ || ops ~ /(^|[^a-z0-9_])mm[0-7]([^0-9]|$)/) bad = 1
            if (bad) { nbad++; if (nbad <= 10) print "  " $0 }
            if (m ~ /^(cmov|fcmov|fcomi|fucomi)/) p6++
        }
        END { printf "SUMMARY %d %d %d\n", total, nbad, p6 }')
    read -r _ total nbad p6 <<< "$(printf '%s\n' "$result" | tail -n 1)"
    if [ "$nbad" -gt 0 ]; then
        echo "check-3dfx-drivers-isa: FAIL $f: $nbad of $total instructions use MMX, SSE or later (beyond a Pentium Pro), e.g.:"
        printf '%s\n' "$result" | sed '$d'
        status=1
    else
        echo "check-3dfx-drivers-isa: ok $f ($total instructions, $p6 P6 CMOV/FCOMI)"
    fi
done
exit "$status"
