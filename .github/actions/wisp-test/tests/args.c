/*
 * The action's own check of what reaches the program: argc and argv from the args input (after
 * "--" on the kernel command line) and the environment PID 1 passes on. Fails if nolibc's sparc
 * _start is not replaced (it read argc 96 bytes too low, see start-sparc.c).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
	const char *mode = getenv("wisp");

	printf("argc %d argv[0] %s argv[1] %s argv[2] %s wisp=%s\n", argc, argv[0],
	       argc > 1 ? argv[1] : "-", argc > 2 ? argv[2] : "-", mode ? mode : "-");
	if (argc != 3 || strcmp(argv[0], "/test") != 0 || strcmp(argv[1], "hello") != 0 ||
	    strcmp(argv[2], "big-endian") != 0 || !mode || strcmp(mode, "test") != 0) {
		printf("FAIL: want argc 3, /test hello big-endian, wisp=test\n");
		return 1;
	}
	printf("PASS\n");
	return 0;
}
