ifeq ($(VERBOSE),1)
  Q := @
  ECHO := echo
else ifeq ($(VERBOSE),2)
  Q := 
  ECHO := echo
else
  Q := @
  ECHO := echo > /dev/null
endif

ifeq ($(FORCE),1)
  F := -f
else
  F := 
endif

ifeq ($(origin DOCKER), undefined)
	ifeq ($(shell command -v podman 2> /dev/null),)
		ifeq ($(shell command -v docker 2> /dev/null),)
			$(error Neither podman nor docker is installed.)
		else
			DOCKER=docker
		endif
	else
		DOCKER=podman
	endif
endif

ifeq ($(origin DOCKER_ARG), undefined)
	DOCKER_ARG :=
else
	DOCKER_ARG := $(DOCKER_ARG)
endif

QEMU_SERVER_FILES := PVE/QemuServer.pm PVE/QemuServer/Helpers.pm PVE/QemuServer/Drive.pm PVE/QemuServer/Machine.pm PVE/QemuServer/PCI.pm PVE/QemuServer/USB.pm
PVE_MANAGER_FILES := manager6/pvemanagerlib.js css/ext6-pve.css
PATCH_SUBMODULES := pve-manager pve-qemu qemu-server
CURRENT_DIR = $(shell pwd)
BRANCH_NAME := local_patches
GIT_AUTHOR = $(shell git log -1 --pretty=format:%an -- Makefile)
GIT_EMAIL = $(shell git log -1 --pretty=format:%ae -- Makefile)
GIT_QEMU72_SUBJECT = $(shell git log -1 --pretty=format:%s -- submodules/pve-qemu-7.2-sparc.patch)
GIT_QEMU3DFX_SUBJECT = $(shell git log -1 --pretty=format:%s -- submodules/pve-qemu-qemu-3dfx.patch)
GIT_PVEQEMU_SUBJECT = $(shell git log -1 --pretty=format:%s -- submodules/pve-qemu.patch)

all: check-and-reinit-submodules build

.PHONY: check-and-reinit-submodules
check-and-reinit-submodules:
	$(Q)if git submodule status | egrep -q '^[-+]' ; then \
		$(ECHO) "INFO: Need to reinitialize git submodules"; \
		git submodule update --init; \
	fi

.PHONY: build-containers
build-containers:
	sudo docker build . -f build.Dockerfile -t wsh-pve-deb-build
	sudo docker build . -f djgpp.Dockerfile -t wsh-pve-djgpp-build

.PHONY: build
build: pve-manager qemu-server pve-qemu-bundle
	echo Building all

pve-manager-clean:
	$(Q)$(ECHO) "INFO: Cleaning pve-manager"; \
	rm -rf submodules/pve-manager; \
	git submodule update --init submodules/pve-manager; \
	$(MAKE) pve-manager

.PHONY: pve-manager
pve-manager:
	$(Q)$(ECHO) "INFO: Building pve-manager deb package"; \
		if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::group::Building pve-manager deb package"; \
	fi; \
	patch -d submodules/pve-manager -p1 --no-backup-if-mismatch --reject-file=/dev/null -i ../pve-manager.patch; \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-manager:/src/submodules/pve-manager \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build/repo:/build/repo \
		-w /src/submodules/pve-manager \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		-e RUST_BACKTRACE=full \
		-v /run/systemd/journal/socket:/run/systemd/journal/socket \
		ghcr.io/hwinther/wsh-pve/pve-build:12 \
		bash -c "git config --global --add safe.directory /src/submodules/pve-manager && make distclean && make deb || true && cp -f pve-manager_*.deb /build/repo/"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::endgroup::"; \
	fi

qemu-server-clean:
	$(Q)$(ECHO) "INFO: Cleaning qemu-server"; \
	rm -rf submodules/qemu-server; \
	git submodule update --init submodules/qemu-server; \
	$(MAKE) qemu-server

.PHONY: qemu-server
qemu-server:
	$(Q)$(ECHO) "INFO: Building qemu-server deb package"; \
		if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::group::Building qemu-server deb package"; \
	fi; \
	patch -d submodules/qemu-server -p1 --no-backup-if-mismatch --reject-file=/dev/null -i ../qemu-server.patch; \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/qemu-server:/src/submodules/qemu-server \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build/repo:/build/repo \
		-w /src/submodules/qemu-server \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		-e DEB_BUILD_OPTIONS=nocheck \
		-v /run/systemd/journal/socket:/run/systemd/journal/socket \
		ghcr.io/hwinther/wsh-pve/pve-build:12 \
		bash -c "git config --global --add safe.directory /src/submodules/qemu-server && make distclean && make deb || true && cp -f qemu-server_*.deb /build/repo/"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::endgroup::"; \
	fi

.PHONY: pve-qemu
pve-qemu:
	@set -e; \
	$(MAKE) restore-pve-qemu; \

	$(Q)$(ECHO) "INFO: Building pve-qemu deb package"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::group::Building pve-qemu deb package"; \
	fi; \
	patch -d submodules/pve-qemu -p1 -i ../pve-qemu.patch; \
	mkdir -p build/repo; \
	git -C submodules/pve-qemu submodule update --init qemu; \
	if [ -f "submodules/pve-qemu.changelog.patch" ]; then \
		cd submodules/pve-qemu && patch -p1 -u --no-backup-if-mismatch --reject-file=/dev/null -i ../pve-qemu.changelog.patch || rm ../pve-qemu.changelog.patch && cd ../../; \
	fi; \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
		-w /src/submodules/pve-qemu \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		ghcr.io/hwinther/wsh-pve/pve-build:12 \
		dch -l +wsh -D bookworm "$(GIT_PVEQEMU_SUBJECT)"; \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build:/src/build \
		-v $(CURRENT_DIR)/submodules/sparc:/src/submodules/sparc \
		-w /src/submodules/pve-qemu \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		ghcr.io/hwinther/wsh-pve/pve-build:12 \
		bash -c "git config --global --add safe.directory /src/submodules/pve-qemu && make distclean && meson subprojects download --sourcedir qemu && make deb || true && cp -f pve-qemu-kvm_*.deb /src/build/repo/"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::endgroup::"; \
	fi

.PHONY: pve-qemu-7.2-sparc
pve-qemu-7.2-sparc:
	@set -e; \
	$(MAKE) restore-pve-qemu; \

	$(Q)$(ECHO) "INFO: Building pve-qemu 7.2 sparc"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::group::Building pve-qemu 7.2 sparc"; \
	fi; \
	rm -rf submodules/pve-qemu/qemu; \
	git -C submodules/pve-qemu checkout 93d558c1eef8f3ec76983cbe6848b0dc606ea5f1; \
	git -C submodules/pve-qemu submodule update --recursive; \
	patch -d submodules/pve-qemu -p1 -i ../pve-qemu-7.2-sparc.patch; \
	mkdir -p build/pve-qemu-7.2-sparc; \
	rm -f build/pve-qemu-7.2-sparc/*; \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
		-w /src/submodules/pve-qemu \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		ghcr.io/hwinther/wsh-pve/pve-build:12 \
		dch -l +wsh -D bookworm "$(GIT_QEMU72_SUBJECT)"; \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build/pve-qemu-7.2-sparc:/build/pve-qemu-7.2-sparc \
		-w /src/submodules/pve-qemu \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		ghcr.io/hwinther/wsh-pve/pve-build:12 \
		bash -c "git config --global --add safe.directory /src/submodules/pve-qemu && make distclean && make deb || true && cp pve-qemu-kvm-7.2.0/debian/pve-qemu-kvm/usr/bin/qemu-system-sparc* /build/pve-qemu-7.2-sparc/"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::endgroup::"; \
	fi

restore-pve-qemu:
	$(ECHO) "INFO: Restoring pve-qemu to current head"; \
	rm -rf submodules/pve-qemu; \
	git submodule update --init submodules/pve-qemu; \
	git -C submodules/pve-qemu submodule update --recursive

restore-sparc:
	$(ECHO) "INFO: Restoring sparc submodule"; \
	git submodule update --init submodules/sparc

.PHONY: pve-qemu-bundle
pve-qemu-bundle: restore-sparc pve-qemu-7.2-sparc pve-qemu-3dfx pve-qemu
	$(Q)$(ECHO) "INFO: Building qemu-bundle deb package"; \
	echo "TODO: figure out the order"

.PHONY: clean
clean: unapply-patches
	$(ECHO) "INFO: Cleaning up"
	$(Q)qemu_path="submodules/pve-qemu/qemu"; \
	if [ -e "$$qemu_path" ]; then \
		if [ -z "$(ls -A qemu_path)" ]; then \
			$(ECHO) "INFO: Ignoring $$qemu_path"; \
		else \
			$(ECHO) "INFO: Removing $$qemu_path"; \
			git submodule deinit $(F) "$$qemu_path"; \
		fi; \
	fi; \
	git submodule deinit --all $(F)

.PHONY: dev-links
dev-links:
	$(Q)if [ $$(id -u) -eq 0 ]; then \
		$(ECHO) "INFO: Running as root"; \
	else \
		echo "ERROR: This target must be run as root"; \
		exit 1; \
	fi

	$(Q)for item in $(QEMU_SERVER_FILES); do \
		symlink_path="/usr/share/perl5/$$item"; \
		if [ -L "$$symlink_path" ]; then \
			$(ECHO) "INFO: $$symlink_path is already a symlink"; \
		elif [ -e "$$symlink_path" ]; then \
			$(ECHO) "INFO: $$symlink_path exists but is not a symlink"; \
			rm -f "$$symlink_path"; \
		fi; \
		if [ ! -e "$$symlink_path" ]; then \
			$(ECHO) "INFO: Creating symlink to $$symlink_path"; \
			ln -s "$(CURRENT_DIR)/submodules/qemu-server/$$item" "$$symlink_path"; \
		fi; \
	done

	$(Q)for item in $(PVE_MANAGER_FILES); do \
		symlink_path="/usr/share/pve-manager/$$(echo $$item | sed 's/manager6/js/')"; \
		echo $$symlink_path; \
		if [ -L "$$symlink_path" ]; then \
			$(ECHO) "INFO: $$symlink_path is already a symlink"; \
		elif [ -e "$$symlink_path" ]; then \
			$(ECHO) "INFO: $$symlink_path exists but is not a symlink"; \
			rm -f "$$symlink_path"; \
		fi; \
		if [ ! -e "$$symlink_path" ]; then \
			$(ECHO) "INFO: Creating symlink to $$symlink_path"; \
            ln -s "$(CURRENT_DIR)/submodules/pve-manager/www/$$item" "$$symlink_path"; \
        fi; \
	done

.PHONY: dev
dev: dev-links qemu-server-dev pve-manager-dev

.PHONY: qemu-server-dev
qemu-server-dev:
	$(Q)if [ $$(id -u) -eq 0 ]; then \
		$(ECHO) "INFO: Running as root"; \
	else \
		echo "ERROR: This target must be run as root"; \
		exit 1; \
	fi; \
	systemctl restart pveproxy pvedaemon

.PHONY: pve-manager-dev
pve-manager-dev:
	$(Q)make -C submodules/pve-manager/www/manager6 pvemanagerlib.js && rm -f submodules/pve-manager/www/manager6/.lint-incremental

.PHONY: apply-patches
apply-patches:
	git submodule update --init
	$(Q)for submodule in $(PATCH_SUBMODULES); do \
		$(ECHO) "INFO: Applying patch for submodule: $$submodule"; \
		patch -d submodules/$$submodule -p1 -i ../$$submodule.patch; \
	done

.PHONY: unapply-patches
unapply-patches:
	$(Q)for submodule in $(PATCH_SUBMODULES); do \
		$(ECHO) "INFO: Applying reverse patch for submodule: $$submodule"; \
		current_branch=$$(git -C submodules/$$submodule rev-parse --abbrev-ref HEAD); \
        if [ "$$current_branch" = "$(BRANCH_NAME)" ]; then \
            $(ECHO) "INFO: Restoring staged files in branch $(BRANCH_NAME) for submodule: $$submodule"; \
            git -C submodules/$$submodule restore --staged .; \
        fi; \
		patch -d submodules/$$submodule -p1 -R --no-backup-if-mismatch -r - $(F) -i ../$$submodule.patch; \
	done

.PHONY: update-patches
update-patches:
	$(Q)for submodule in $(PATCH_SUBMODULES); do \
		$(ECHO) "INFO: Creating patch for submodule: $$submodule"; \
		current_branch=$$(git -C submodules/$$submodule rev-parse --abbrev-ref HEAD); \
        if [ "$$current_branch" != "$(BRANCH_NAME)" ]; then \
            $(ECHO) "INFO: Checking out branch $(BRANCH_NAME) for submodule: $$submodule"; \
            git -C submodules/$$submodule checkout -b $(BRANCH_NAME); \
        fi; \
		git -C submodules/$$submodule add .; \
		git -C submodules/$$submodule diff --staged -p > submodules/$$submodule.patch; \
	done

.PHONY: 3dfx prepare-qemu-3dfx pve-qemu-3dfx
3dfx: clean-qemu-3dfx prepare-qemu-3dfx pve-qemu-3dfx
prepare-qemu-3dfx:
	git submodule update --init submodules/qemu-3dfx

REV = $(shell cd submodules/qemu-3dfx; git rev-parse HEAD | sed "s/\(.......\).*/\1\-/")
pve-qemu-3dfx: prepare-qemu-3dfx
	@set -e; \
	$(MAKE) restore-pve-qemu; \

	$(Q)$(ECHO) "INFO: Building pve-qemu with 3dfx support"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::group::Building pve-qemu with 3dfx support"; \
	fi; \
	mkdir -p submodules/pve-qemu/debian/patches/wsh; \
	git -C submodules/pve-qemu submodule update --init qemu; \
	cp submodules/pve-qemu-qemu-3dfx.patch submodules/pve-qemu/debian/patches/wsh/0099-WSH-qemu-3dfx.patch; \
	echo "wsh/0099-WSH-qemu-3dfx.patch" >> submodules/pve-qemu/debian/patches/series; \
	cp -r submodules/qemu-3dfx/qemu-0/hw/3dfx submodules/qemu-3dfx/qemu-1/hw/mesa submodules/pve-qemu/qemu/hw/; \
	sed -i -e "s/\(rev_\[\).*\].*/\1\]\ =\ \"$(REV)\"/" submodules/pve-qemu/debian/patches/wsh/0099-WSH-qemu-3dfx.patch submodules/pve-qemu/qemu/hw/3dfx/g2xfuncs.h submodules/pve-qemu/qemu/hw/mesa/mglfuncs.h; \
	patch -d submodules/pve-qemu -p1 -i ../pve-qemu.patch; \
	mkdir -p build/pve-qemu-3dfx; \
	rm -f build/pve-qemu-3dfx/*; \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
		-w /src/submodules/pve-qemu \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		ghcr.io/hwinther/wsh-pve/pve-build:12 \
		dch -l +wsh -D bookworm "$(GIT_QEMU3DFX_SUBJECT)"; \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build/pve-qemu-3dfx:/build/pve-qemu-3dfx \
		-w /src/submodules/pve-qemu \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		ghcr.io/hwinther/wsh-pve/pve-build:12 \
		bash -c "git config --global --add safe.directory /src/submodules/pve-qemu && make distclean && meson subprojects download --sourcedir qemu && make deb || true && cp pve-qemu-kvm-*/debian/pve-qemu-kvm/usr/bin/qemu-system-x86_64 /build/pve-qemu-3dfx/"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::endgroup::"; \
	fi

.PHONY: clean-qemu-3dfx
clean-qemu-3dfx:
	rm -rf submodules/pve-qemu/debian/patches/wsh submodules/pve-qemu/qemu/hw/3dfx submodules/pve-qemu/qemu/hw/mesa; \
	cd submodules/pve-qemu && git checkout debian/patches/series && make clean

.PHONY: 3dfx-drivers
3dfx-drivers:
	git submodule update --init submodules/qemu-3dfx; \
    $(DOCKER) run $(DOCKER_ARG) --rm \
        -v $(CURRENT_DIR)/.git:/src/.git \
        -v $(CURRENT_DIR)/submodules/qemu-3dfx:/src/submodules/qemu-3dfx \
        -w /src/submodules/qemu-3dfx/wrappers/3dfx \
        ghcr.io/hwinther/wsh-pve/djgpp-build:12 \
        bash -c "mkdir -p build && cd build && bash ../../../scripts/conf_wrapper && make && make clean"; \
    $(DOCKER) run $(DOCKER_ARG) --rm \
        -v $(CURRENT_DIR)/.git:/src/.git \
        -v $(CURRENT_DIR)/submodules/qemu-3dfx:/src/submodules/qemu-3dfx \
        -w /src/submodules/qemu-3dfx/wrappers/mesa \
        ghcr.io/hwinther/wsh-pve/djgpp-build:12 \
        bash -c "mkdir -p build && cd build && bash ../../../scripts/conf_wrapper && make TOOLS=wglinfo.exe && make clean"; \
	ls -la submodules/qemu-3dfx/wrappers/3dfx/build; \
	ls -la submodules/qemu-3dfx/wrappers/mesa/build; \
	mkdir -p build && rm -rf build/3dfx build/mesa; \
	mv submodules/qemu-3dfx/wrappers/3dfx/build build/3dfx && rm -f build/3dfx/Makefile build/3dfx/*.a; \
	mv submodules/qemu-3dfx/wrappers/mesa/build build/mesa && rm -f build/mesa/Makefile build/mesa/*.a

.PHONY: repo-update
repo-update:
	$(Q)if [ $$(id -u) -eq 0 ]; then \
		$(ECHO) "INFO: Running as root"; \
	else \
		echo "ERROR: This target must be run as root"; \
		exit 1; \
	fi; \
	mkdir -p repo/db repo/dists repo/incoming repo/pool

	# Note: do not push this image to a remote registry as it contains the gpg key
	$(DOCKER) build . -t repo -f repo.Dockerfile --pull
	$(DOCKER) run --rm -v ./repo:/opt/repo -w /opt/repo --env-file .gpg-password-env -i repo bash -c "cp /opt/repo-incoming/*.deb /opt/repo/incoming/ && expect /usr/local/bin/reprepro.exp -Vb . includedeb bookworm /opt/repo/incoming/*.deb"

	# Interactive password prompt
	# $(DOCKER) run --rm -v ./repo:/opt/repo -w /opt/repo -it repo bash -c "cp /opt/repo-incoming/*.deb /opt/repo/incoming/ && reprepro -Vb . includedeb bookworm /opt/repo/incoming/*.deb"

	# Optionally, run a container with the repo mounted at /opt/repo
	# $(DOCKER) run --rm -v repo:/opt/repo -v nginx/nginx-site.conf:/etc/nginx/conf.d/default.conf -p 8080:80 -it nginx

.PHONY: help
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  all:                  Initialize submodules and build the project"
	@echo "  dev: 				   Create symlinks for QemuServer files and restart services"
	@echo "  check-and-reinit-submodules: Check and reinitialize git submodules"
	@echo "  build:                Build the project"
	@echo "  clean:                Clean the project"
	@echo "  test:                 Run tests"
	@echo "  dev-links:            Create symlinks for QemuServer files"
	@echo "  clean-qemu-3dfx:      Clean QEMU 3dfx"
	@echo "  3dfx-drivers:   Build 3dfx drivers"
	@echo "  repo:                 Build and run the Docker container for the repo"
	@echo "  repo-update:          Run the repo container and fetch newest packages to combine into a debian repo folder structure on local disk"
	@echo "  help:                 Show this help message"
	@echo ""
	@echo "Variables:"
	@echo "  VERBOSE:              Set to 1 or 2 to enable verbose output"
	@echo ""
	@echo "Examples:"
	@echo "  make"
	@echo "  make all"
	@echo "  make check-and-reinit-submodules"
	@echo "  make build"
	@echo "  make clean"
	@echo "  make test"
	@echo "  make dev-links"
	@echo "  make clean-qemu-3dfx"
	@echo "  make 3dfx-drivers"
	@echo "  make pve-qemu-7.2-sparc"
	@echo "  make pve-qemu-3dfx"
	@echo "  make pve-qemu-bundle"
	@echo "  make repo"
	@echo "  make repo-update"
	@echo "  make help"
	@echo ""
	@echo "For more information, see the README.md file."
	@echo ""

# vim:ft=make
