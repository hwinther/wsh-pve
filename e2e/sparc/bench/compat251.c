/*
 * Linked into the statically linked benchmarks so that they also run on Solaris 2.5.1: the stdio of
 * Solaris 2.6's libc.a sizes a stream's buffer with fstat64 (system call 217, new in 2.6), which
 * kills the program on 2.5.1 with SIGSYS on its first buffered output. This fstat64 answers from
 * fstat, which every release has; the benchmarks themselves don't call it.
 */
#define _LARGEFILE64_SOURCE 1
#include <sys/types.h>
#include <sys/stat.h>
#include <string.h>

int
_fstat64(int fd, struct stat64 *b)
{
	struct stat s;

	if (fstat(fd, &s) < 0)
		return -1;
	memset(b, 0, sizeof (*b));
	b->st_dev = s.st_dev;
	b->st_ino = s.st_ino;
	b->st_mode = s.st_mode;
	b->st_nlink = s.st_nlink;
	b->st_uid = s.st_uid;
	b->st_gid = s.st_gid;
	b->st_rdev = s.st_rdev;
	b->st_size = s.st_size;
	b->st_atim = s.st_atim;
	b->st_mtim = s.st_mtim;
	b->st_ctim = s.st_ctim;
	b->st_blksize = s.st_blksize;
	b->st_blocks = s.st_blocks;
	strncpy(b->st_fstype, s.st_fstype, sizeof (b->st_fstype));
	return 0;
}

int
fstat64(int fd, struct stat64 *b)
{
	return _fstat64(fd, b);
}
