/*
 * The program entry point for sparc32 and sparc64, linked in by wisp-test.sh with the user's
 * sources (which are built with -D_start=wisp_nolibc_start).
 *
 * nolibc's _start for sparc is a C function holding the asm that passes the address of argc to
 * _start_c. gcc has no "naked" functions on sparc and puts a "save %sp, -96, %sp" in front of it,
 * so _start_c reads argc, argv and the environment 96 bytes too low. This is the same asm without
 * a prologue; e2e/wisp/init.c carries the same fix for wisp's PID 1.
 */
__asm__(".pushsection .text\n"
	".global _start\n"
	".type _start, #function\n"
	"_start:\n"
#ifdef __arch64__
	"	add %sp, 128 + 2047, %o0\n"
#else
	"	add %sp, 64, %o0\n"
#endif
	"	b,a _start_c\n"
	".size _start, . - _start\n"
	".popsection\n");
