/* A serial HTTP/1.0 service for the wisp network-tier smoke test. */
#include <arpa/inet.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/utsname.h>
#include <unistd.h>

static int serve(int fd, const struct utsname *u, unsigned long *counter)
{
	char request[4096], body[512], reply[768];
	const char *status = "200 OK";
	size_t used = 0;
	ssize_t n;
	int len, quit = 0;

	/* Consume the headers even when the request spans several TCP segments. */
	for (;;) {
		n = read(fd, request + used, sizeof(request) - 1 - used);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			return 0;
		used += n;
		request[used] = '\0';
		if (strstr(request, "\r\n\r\n"))
			break;
	}

	if (!strncmp(request, "GET / HTTP/1.", 13)) {
		snprintf(body, sizeof(body), "%s %s %s request=%lu\n",
			 u->sysname, u->release, u->machine, ++*counter);
	} else if (!strncmp(request, "GET /quit HTTP/1.", 17)) {
		strcpy(body, "bye\n");
		quit = 1;
	} else {
		status = "404 Not Found";
		strcpy(body, "not found\n");
	}
	len = snprintf(reply, sizeof(reply), "HTTP/1.0 %s\r\nContent-Type: text/plain\r\n"
		       "Content-Length: %zu\r\n\r\n%s", status, strlen(body), body);
	used = 0;
	while (used < (size_t)len) {
		n = write(fd, reply + used, len - used);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			return 0;
		used += n;
	}
	return quit;
}

int main(void)
{
	struct sockaddr_in addr = { .sin_family = AF_INET, .sin_port = htons(8080) };
	struct utsname u;
	unsigned long counter = 0;
	int listener, client, quit = 0;

	signal(SIGPIPE, SIG_IGN);
	listener = socket(AF_INET, SOCK_STREAM, 0);
	if (listener < 0 || bind(listener, (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
	    listen(listener, 4) < 0 || uname(&u) < 0) {
		perror("httpd startup");
		return 1;
	}
	puts("WISP-HTTPD listening port=8080");
	fflush(stdout);
	do {
		client = accept(listener, NULL, NULL);
		if (client < 0) {
			if (errno == EINTR)
				continue;
			perror("accept");
			return 1;
		}
		quit = serve(client, &u, &counter);
		close(client);
	} while (!quit);
	close(listener);
	return 0;
}
