all: check-and-reinit-submodules build

.PHONY: check-and-reinit-submodules
check-and-reinit-submodules:
	@if git submodule status | egrep -q '^[-+]' ; then \
		echo "INFO: Need to reinitialize git submodules"; \
		git submodule update --init; \
	fi

.PHONY: build
build:
	sudo ./docker-build.sh
