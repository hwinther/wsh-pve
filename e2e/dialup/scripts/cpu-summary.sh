#!/bin/sh
# cpu-summary.sh <cpu.samples> : per process total CPU seconds, average and peak %CPU (1 s samples, 100 Hz ticks)
awk '{k=$2" "$3; if(!(k in f)){f[k]=$4; ft[k]=$1} if((k in l) && $1>lt[k]){r=($4-l[k])/($1-lt[k]); if(r>pk[k])pk[k]=r} l[k]=$4; lt[k]=$1}
 END{for(k in f){d=lt[k]-ft[k]; printf "CPU %-24s total %.2f s over %.0f s, avg %.1f%%, peak %.0f%%\n", k, (l[k]-f[k])/100, d, (d>0?(l[k]-f[k])/d:0), pk[k]}}' "$1"
