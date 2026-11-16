# lmbench 3.0-a9 subset, sourced by run.sh ($BIN, $T set). Fixed parameters, lmbench's own option
# defaults otherwise; ENOUGH (microseconds per timed interval) fixed so every machine times the same.
# Not here: the network tests (no network set up), and lat_ctx, bw_pipe and lat_fifo, which fail on
# Solaris 2.6 (their reads end in EINTR: lmbench expects BSD signal semantics; see README).
ENOUGH=100000; export ENOUGH
cp $BIN/hello /tmp/hello; cp $BIN/hello /tmp/hello-s     # lat_proc exec/shell run these
mkfile 8m $T/file
mkdir $T/fs
# lm <name> <unit> <command...>: the number in the last line of the output (lmbench writes to stderr)
lm() {
  n=$1; u=$2; shift 2
  "$@" > $T/lm.out 2>&1
  v=`nawk 'NF { l = $0 } END { n = split(l, f, /[ :]+/); for (i = n; i > 0; i--) if (f[i] ~ /^[0-9.]+$/) { print f[i]; exit } }' $T/lm.out`
  out $n "$v" $u
}
# out <name> <value> <unit>: a BENCH line, or BENCH-ERROR for no value or lmbench's -1 (nothing timed)
out() {
  case "$2" in
    "" | -*) err $1 "$2 `tail -2 $T/lm.out | tr '\n' ' '`" ;;
    *) echo "BENCH $1 $2 $3" ;;
  esac
}
# lmv <name> <unit> <field> <command...>: field <field> of the last line (tables: size value)
lmv() {
  n=$1; u=$2; f=$3; shift 3
  "$@" > $T/lm.out 2>&1
  v=`nawk -v f=$f 'NF { l = $0 } END { split(l, a, /[ \t]+/); print a[f] }' $T/lm.out`
  out $n "$v" $u
}
lm lm_null us $BIN/lat_syscall null
lm lm_read us $BIN/lat_syscall read
lm lm_write us $BIN/lat_syscall write
lm lm_stat us $BIN/lat_syscall stat $T/file
lm lm_open us $BIN/lat_syscall open $T/file
lm lm_sig_install us $BIN/lat_sig install
lm lm_sig_catch us $BIN/lat_sig catch
lm lm_prot_fault us $BIN/lat_sig prot $T/file
lm lm_pipe us $BIN/lat_pipe
lm lm_fork us $BIN/lat_proc fork
lm lm_exec us $BIN/lat_proc exec
lm lm_sh us $BIN/lat_proc shell
lm lm_pagefault us $BIN/lat_pagefault $T/file
lmv lm_mmap_8m us 2 $BIN/lat_mmap 8m $T/file
lmv lm_file_rd_8m MB/s 2 $BIN/bw_file_rd 8m io_only $T/file
lmv lm_mem_rd_4m MB/s 2 $BIN/bw_mem 4m rd
lmv lm_mem_wr_4m MB/s 2 $BIN/bw_mem 4m wr
lmv lm_bcopy_4m MB/s 2 $BIN/bw_mem 4m bcopy
lmv lm_mem_lat_8m ns 2 $BIN/lat_mem_rd 8 128
# lat_fs: no options, its directory argument is read from argv[1] (and -s 0 means all sizes anyway);
# the 0k line of its 0k/1k/4k/10k table: size, files, creates/s, deletes/s
# On Solaris 2.5.1 it times nothing (-1 for every size): skipped there.
if [ "`uname -r`" = 5.5.1 ]; then
  echo "BENCH-SKIP lm_fs_create_0k lm_fs_delete_0k: lat_fs times nothing on 5.5.1"
else
  $BIN/lat_fs $T/fs > $T/lm.out 2>&1
  out lm_fs_create_0k "`nawk '$1 == "0k" { print $3 }' $T/lm.out`" files/s
  out lm_fs_delete_0k "`nawk '$1 == "0k" { print $4 }' $T/lm.out`" files/s
fi
rm -f /tmp/hello /tmp/hello-s
