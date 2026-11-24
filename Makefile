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

DOCKER_TTY := $(if $(DEBUG_SHELL),-it,)

QEMU_SERVER_FILES := PVE/QemuServer.pm PVE/QemuServer/Helpers.pm PVE/QemuServer/Drive.pm PVE/QemuServer/DriveDevice.pm PVE/QemuServer/Machine.pm PVE/QemuServer/PCI.pm PVE/QemuServer/USB.pm PVE/QemuServer/Network.pm PVE/QemuServer/Blockdev.pm PVE/QemuConfig.pm PVE/API2/Qemu.pm
PVE_STORAGE_FILES := PVE/Storage.pm PVE/Storage/Plugin.pm PVE/Storage/DirPlugin.pm PVE/Storage/NFSPlugin.pm PVE/Storage/CIFSPlugin.pm PVE/Storage/BTRFSPlugin.pm PVE/Storage/CephFSPlugin.pm PVE/API2/Storage/Status.pm
PVE_MANAGER_FILES := manager6/pvemanagerlib.js css/ext6-pve.css
PATCH_SUBMODULES := pve-manager pve-qemu qemu-server pve-storage
CURRENT_DIR = $(shell pwd)
BRANCH_NAME := local_patches
GIT_AUTHOR = $(shell git log -1 --pretty=format:%an -- Makefile)
GIT_EMAIL = $(shell git log -1 --pretty=format:%ae -- Makefile)
DOCKER_BUILD_IMAGE = ghcr.io/hwinther/wsh-pve/pve-build:13
DJGPP_BUILD_IMAGE = ghcr.io/hwinther/wsh-pve/djgpp-build:13
DEBIAN_TAG = trixie

# The +wsh entry of submodules/pve-qemu/debian/changelog: one line per commit since the previous
# build (scripts/wsh-changelog-entries.sh, on the host, which has the history), written by
# scripts/wsh-changelog-dch.sh in the build image. The pve-qemu and pve-qemu-3dfx targets both use
# it, so the 3dfx binary's --version and entries match the package's. build-deb.yml does the same
# for the other packages.
WSH_PVEQEMU_DCH = entries=$$(scripts/wsh-changelog-entries.sh pve-qemu); \
	$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
		-v $(CURRENT_DIR)/scripts:/src/scripts:ro \
		-w /src/submodules/pve-qemu \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		-e WSH_CHANGELOG_ENTRIES="$$entries" \
		$(DOCKER_BUILD_IMAGE) \
		bash /src/scripts/wsh-changelog-dch.sh $(DEBIAN_TAG)

# The optional extras of pve-qemu-kvm (3dfx, openbios, sun-proms) never fail its build: debian/rules
# installs each only when it's there. A target whose extra drops out says so in one line of this form
# (scripts/report-qemu-extras.sh quotes it), plus an annotation in GitHub Actions:
#   WARNING: optional extra <name> missing: <reason>
WARN_EXTRA_MISSING = warn_extra_missing() { \
	echo "WARNING: optional extra $$1 missing: $$2"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then echo "::warning title=optional extra $$1 missing::$$2"; fi; \
}

all: init-submodules build

.PHONY: init-submodules
init-submodules:
	$(Q)if git submodule status | egrep -q '^[-+]' ; then \
		$(ECHO) "INFO: Need to reinitialize git submodules"; \
		git submodule update --init; \
	fi

.PHONY: reset-submodules
reset-submodules:
	$(ECHO) "INFO: Deleting and refetching submodules"; \
	rm -rf submodules/*; \
	git submodule update --init; \
	git reset --hard

.PHONY: build-containers
build-containers:
	sudo docker build . -f build.Dockerfile -t wsh-pve-deb-build
	sudo docker build . -f djgpp.Dockerfile -t wsh-pve-djgpp-build

.PHONY: build
build: pve-manager qemu-server pve-storage pve-qemu-bundle
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
	$(DOCKER) run $(DOCKER_ARG) $(DOCKER_TTY) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-manager:/src/submodules/pve-manager \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build/repo:/build/repo \
		-w /src/submodules/pve-manager \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		-e RUST_BACKTRACE=full \
		-v /run/systemd/journal/socket:/run/systemd/journal/socket \
		$(DOCKER_BUILD_IMAGE) \
		bash -c 'git config --global --add safe.directory /src/submodules/pve-manager && make distclean && make deb; rc=$$?; if [ $$rc -ne 0 ]; then echo "BUILD FAILED (rc=$$rc)"; if [ "$(DEBUG_SHELL)" = "1" ]; then echo "Dropping to shell inside container"; exec /bin/bash; fi; fi; cp -f pve-manager_*.deb /build/repo/'; \
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
	$(DOCKER) run $(DOCKER_ARG) $(DOCKER_TTY) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/qemu-server:/src/submodules/qemu-server \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build/repo:/build/repo \
		-w /src/submodules/qemu-server \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		-e DEB_BUILD_OPTIONS=nocheck \
		-v /run/systemd/journal/socket:/run/systemd/journal/socket \
		$(DOCKER_BUILD_IMAGE) \
		bash -c 'git config --global --add safe.directory /src/submodules/qemu-server && make distclean && make deb; rc=$$?; if [ $$rc -ne 0 ]; then echo "BUILD FAILED (rc=$$rc)"; if [ "$(DEBUG_SHELL)" = "1" ]; then echo "Dropping to shell inside container"; exec /bin/bash; fi; fi; cp -f qemu-server_*.deb /build/repo/'; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::endgroup::"; \
	fi

pve-storage-clean:
	$(Q)$(ECHO) "INFO: Cleaning pve-storage"; \
	rm -rf submodules/pve-storage; \
	git submodule update --init submodules/pve-storage; \
	$(MAKE) pve-storage

.PHONY: pve-storage
pve-storage:
	$(Q)$(ECHO) "INFO: Building pve-storage deb package"; \
		if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::group::Building pve-storage deb package"; \
	fi; \
	patch -d submodules/pve-storage -p1 --no-backup-if-mismatch --reject-file=/dev/null -i ../pve-storage.patch; \
	$(DOCKER) run $(DOCKER_ARG) $(DOCKER_TTY) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-storage:/src/submodules/pve-storage \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build/repo:/build/repo \
		-w /src/submodules/pve-storage \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		-e DEB_BUILD_OPTIONS=nocheck \
		-v /run/systemd/journal/socket:/run/systemd/journal/socket \
		$(DOCKER_BUILD_IMAGE) \
		bash -c 'git config --global --add safe.directory /src/submodules/pve-storage && make distclean && make deb; rc=$$?; if [ $$rc -ne 0 ]; then echo "BUILD FAILED (rc=$$rc)"; if [ "$(DEBUG_SHELL)" = "1" ]; then echo "Dropping to shell inside container"; exec /bin/bash; fi; fi; cp -f libpve-storage-perl_*.deb /build/repo/'; \
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
	$(WSH_PVEQEMU_DCH); \
	$(DOCKER) run $(DOCKER_ARG) $(DOCKER_TTY) --rm --pull always \
		-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
		-v $(CURRENT_DIR)/.git:/src/.git \
		-v $(CURRENT_DIR)/build:/src/build \
		-v $(CURRENT_DIR)/submodules/sparc:/src/submodules/sparc \
		-w /src/submodules/pve-qemu \
		-e DEBEMAIL="$(GIT_EMAIL)" \
		-e DEBFULLNAME="$(GIT_AUTHOR)" \
		-e DEB_BUILD_OPTIONS \
		$(DOCKER_BUILD_IMAGE) \
		bash -c 'git config --global --add safe.directory /src/submodules/pve-qemu && make distclean && meson subprojects download --sourcedir qemu && make deb; rc=$$?; if [ $$rc -ne 0 ]; then echo "BUILD FAILED (rc=$$rc)"; if [ "$(DEBUG_SHELL)" = "1" ]; then echo "Dropping to shell inside container"; exec /bin/bash; fi; fi; cp -f pve-qemu-kvm_*.deb /src/build/repo/'; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::endgroup::"; \
	fi

restore-pve-qemu:
	$(ECHO) "INFO: Restoring pve-qemu to current head"; \
	rm -rf submodules/pve-qemu; \
	git submodule update --init submodules/pve-qemu; \
	git -C submodules/pve-qemu submodule update --recursive

# The Sun PROMs (a private repository): without access, pve-qemu is built without them
restore-sparc:
	$(ECHO) "INFO: Restoring sparc submodule"; \
	$(WARN_EXTRA_MISSING); \
	git submodule update --init submodules/sparc || true; \
	missing=""; \
	for f in ss5.bin ss10_v2.25_rom ss20_v2.25_rom lx.bin; do [ -s "submodules/sparc/$$f" ] || missing="$$missing $$f"; done; \
	if [ -n "$$missing" ]; then \
		warn_extra_missing sun-proms "not in submodules/sparc (private repository: no access?):$$missing"; \
	fi

# openbios-sparc32, the cg3 FCode ROM (QEMU,cgthree.bin) and openbios-sparc64 with our patches
# (openbios/), each installed over QEMU's image by debian/rules. openbios-sparc64 is an extra of its
# own: the Dockerfile builds it in a step that may fail without taking the sparc32 files with it.
.PHONY: openbios-sparc32
openbios-sparc32:
	$(Q)$(ECHO) "INFO: Building openbios-sparc32, QEMU,cgthree.bin and openbios-sparc64"; \
	mkdir -p build/openbios; \
	rm -f build/openbios/*; \
	$(WARN_EXTRA_MISSING); \
	$(DOCKER) build --output type=local,dest=build/openbios -f openbios/Dockerfile openbios || true; \
	if [ ! -s build/openbios/openbios-sparc32 ] || [ ! -s "build/openbios/QEMU,cgthree.bin" ]; then \
		warn_extra_missing openbios "openbios-sparc32 failed to build, pve-qemu keeps QEMU's images"; \
	fi; \
	if [ ! -s build/openbios/openbios-sparc64 ]; then \
		warn_extra_missing openbios-sparc64 "openbios-sparc64 failed to build, pve-qemu keeps QEMU's image"; \
	fi

.PHONY: pve-qemu-bundle
pve-qemu-bundle: restore-sparc openbios-sparc32 pve-qemu-3dfx pve-qemu
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
			ln -s "$(CURRENT_DIR)/submodules/qemu-server/src/$$item" "$$symlink_path"; \
		fi; \
	done

	$(Q)for item in $(PVE_STORAGE_FILES); do \
		symlink_path="/usr/share/perl5/$$item"; \
		if [ -L "$$symlink_path" ]; then \
			$(ECHO) "INFO: $$symlink_path is already a symlink"; \
		elif [ -e "$$symlink_path" ]; then \
			$(ECHO) "INFO: $$symlink_path exists but is not a symlink"; \
			rm -f "$$symlink_path"; \
		fi; \
		if [ ! -e "$$symlink_path" ]; then \
			$(ECHO) "INFO: Creating symlink to $$symlink_path"; \
			ln -s "$(CURRENT_DIR)/submodules/pve-storage/src/$$item" "$$symlink_path"; \
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
	git submodule update --init submodules/qemu-3dfx || true

REV = $(shell cd submodules/qemu-3dfx; git rev-parse HEAD | sed "s/\(.......\).*/\1\-/")
# QEMU with qemu-3dfx, for debian/rules of the pve-qemu target to ship as qemu-system-x86_64-3dfx: the
# same tree as pve-qemu (pve-qemu.patch and its wsh/ series first), plus wsh/0099-WSH-qemu-3dfx.patch
# (submodules/pve-qemu-qemu-3dfx.patch, checked before the long build by
# scripts/refresh-qemu-3dfx-patch.sh) and qemu-3dfx's hw/3dfx and hw/mesa, stamped with its revision
# the way its scripts/sign_commit does (whose other edits are for older QEMUs). Never fails: without
# the binary, pve-qemu ships without it. pve-qemu starts over from a fresh submodules/pve-qemu.
# debian/changelog gets submodules/pve-qemu.changelog.patch and the +wsh entry (WSH_PVEQEMU_DCH) as in the pve-qemu target,
# so the binary's --version (QEMU's pkgversion, from the changelog) names the +wshN of the package it
# ships in; without the patch every build said +wsh1.
pve-qemu-3dfx: prepare-qemu-3dfx
	@set -e; \
	$(MAKE) restore-pve-qemu; \

	$(Q)$(ECHO) "INFO: Building pve-qemu with 3dfx support"; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::group::Building pve-qemu with 3dfx support"; \
	fi; \
	$(WARN_EXTRA_MISSING); \
	mkdir -p build/pve-qemu-3dfx; \
	rm -f build/pve-qemu-3dfx/*; \
	git -C submodules/pve-qemu submodule update --init qemu; \
	if [ ! -d submodules/qemu-3dfx/qemu-0/hw/3dfx ] || [ ! -d submodules/qemu-3dfx/qemu-1/hw/mesa ]; then \
		reason="submodules/qemu-3dfx is not checked out"; \
	elif ! patch -d submodules/pve-qemu -p1 -i ../pve-qemu.patch; then \
		reason="submodules/pve-qemu.patch does not apply"; \
	elif ! scripts/refresh-qemu-3dfx-patch.sh --check; then \
		reason="submodules/pve-qemu-qemu-3dfx.patch does not apply to this pve-qemu (rejected hunks above; scripts/refresh-qemu-3dfx-patch.sh refreshes it)"; \
	else \
		reason="the 3dfx build made no qemu-system-x86_64 (build errors above)"; \
		cp submodules/pve-qemu-qemu-3dfx.patch submodules/pve-qemu/debian/patches/wsh/0099-WSH-qemu-3dfx.patch; \
		echo "wsh/0099-WSH-qemu-3dfx.patch" >> submodules/pve-qemu/debian/patches/series; \
		cp -r submodules/qemu-3dfx/qemu-0/hw/3dfx submodules/qemu-3dfx/qemu-1/hw/mesa submodules/pve-qemu/qemu/hw/; \
		patch -d submodules/pve-qemu/qemu -p2 -i ../../qemu-3dfx.patch; \
		sed -i -e "s/\(rev_\[\).*\].*/\1\]\ =\ \"$(REV)\"/" submodules/pve-qemu/debian/patches/wsh/0099-WSH-qemu-3dfx.patch submodules/pve-qemu/qemu/hw/3dfx/g2xfuncs.h submodules/pve-qemu/qemu/hw/mesa/mglfuncs.h; \
		if [ -f submodules/pve-qemu.changelog.patch ] && ! patch -d submodules/pve-qemu -p1 -u --no-backup-if-mismatch --reject-file=/dev/null -i ../pve-qemu.changelog.patch; then \
			git -C submodules/pve-qemu checkout debian/changelog; \
		fi; \
		$(WSH_PVEQEMU_DCH); \
		$(DOCKER) run $(DOCKER_ARG) --rm --pull always \
			-v $(CURRENT_DIR)/submodules/pve-qemu:/src/submodules/pve-qemu \
			-v $(CURRENT_DIR)/.git:/src/.git \
			-v $(CURRENT_DIR)/build/pve-qemu-3dfx:/build/pve-qemu-3dfx \
			-w /src/submodules/pve-qemu \
			-e DEBEMAIL="$(GIT_EMAIL)" \
			-e DEBFULLNAME="$(GIT_AUTHOR)" \
			-e DEB_BUILD_OPTIONS \
			$(DOCKER_BUILD_IMAGE) \
			bash -c "git config --global --add safe.directory /src/submodules/pve-qemu && make distclean && meson subprojects download --sourcedir qemu && make deb || true && cp pve-qemu-kvm-*/debian/pve-qemu-kvm/usr/bin/qemu-system-x86_64 /build/pve-qemu-3dfx/"; \
	fi; \
	if [ "$(GITHUB_ACTIONS)" = "true" ]; then \
		echo "::endgroup::"; \
	fi; \
	if [ ! -s build/pve-qemu-3dfx/qemu-system-x86_64 ]; then \
		warn_extra_missing 3dfx "$$reason, pve-qemu ships without qemu-system-x86_64-3dfx"; \
	fi

.PHONY: clean-qemu-3dfx
clean-qemu-3dfx:
	rm -rf submodules/pve-qemu/debian/patches/wsh submodules/pve-qemu/qemu/hw/3dfx submodules/pve-qemu/qemu/hw/mesa; \
	cd submodules/pve-qemu && git checkout debian/patches/series && make clean

# The qemu-3dfx guest drivers (wrappers/) into build/3dfx and build/mesa, for a Pentium-class guest:
# submodules/qemu-3dfx-drivers.patch replaces upstream's -march=x86-64-v2 (SSE2 to SSE4.2, POPCNT) for
# the build and is reverted afterwards, and scripts/check-3dfx-drivers-isa.sh fails the build on any
# MMX/SSE or later instruction in what was compiled (the DLLs and EXEs, the DXEs' and OVL's objects).
.PHONY: 3dfx-drivers
3dfx-drivers:
	set -e; \
	git submodule update --init submodules/qemu-3dfx; \
	if ! git -C submodules/qemu-3dfx apply --reverse --check ../qemu-3dfx-drivers.patch 2>/dev/null; then \
		git -C submodules/qemu-3dfx apply ../qemu-3dfx-drivers.patch; \
	fi; \
	trap 'git -C submodules/qemu-3dfx apply --reverse ../qemu-3dfx-drivers.patch' EXIT; \
    $(DOCKER) run $(DOCKER_ARG) --rm \
        -v $(CURRENT_DIR)/.git:/src/.git \
        -v $(CURRENT_DIR)/submodules/qemu-3dfx:/src/submodules/qemu-3dfx \
        -v $(CURRENT_DIR)/scripts:/src/scripts:ro \
        -w /src/submodules/qemu-3dfx/wrappers/3dfx \
        $(DJGPP_BUILD_IMAGE) \
        bash -c "git config --global --add safe.directory '*' && mkdir -p build && cd build && bash ../../../scripts/conf_wrapper && make && /src/scripts/check-3dfx-drivers-isa.sh *.dll *.exe *.sys ../dxe/*.o ../ovl/*.obj && make clean"; \
    $(DOCKER) run $(DOCKER_ARG) --rm \
        -v $(CURRENT_DIR)/.git:/src/.git \
        -v $(CURRENT_DIR)/submodules/qemu-3dfx:/src/submodules/qemu-3dfx \
        -v $(CURRENT_DIR)/scripts:/src/scripts:ro \
        -w /src/submodules/qemu-3dfx/wrappers/mesa \
        $(DJGPP_BUILD_IMAGE) \
        bash -c "git config --global --add safe.directory '*' && mkdir -p build && cd build && bash ../../../scripts/conf_wrapper && make TOOLS=wglinfo.exe && /src/scripts/check-3dfx-drivers-isa.sh *.dll *.exe && make clean"; \
	ls -la submodules/qemu-3dfx/wrappers/3dfx/build; \
	ls -la submodules/qemu-3dfx/wrappers/mesa/build; \
	mkdir -p build && rm -rf build/3dfx build/mesa; \
	mv submodules/qemu-3dfx/wrappers/3dfx/build build/3dfx && rm -f build/3dfx/Makefile build/3dfx/*.a; \
	mv submodules/qemu-3dfx/wrappers/mesa/build build/mesa && rm -f build/mesa/Makefile build/mesa/*.a

# The optional wsh-lab package (packages/wsh-lab): the sparc lab, Architecture: all, built from this
# checkout in a plain Debian 13 image, into build/wsh-lab/; lintian runs at the end of the build. Its
# version comes from git (packages/wsh-lab/version.sh), so it needs the full history and no changelog.
.PHONY: wsh-lab
wsh-lab:
	$(Q)eval "$$(packages/wsh-lab/version.sh | sed 's/^/export /')"; \
	$(ECHO) "INFO: building wsh-lab $$WSH_LAB_VERSION"; \
	$(DOCKER) build -f packages/wsh-lab/build.Dockerfile -t wsh-lab-build packages/wsh-lab && \
	mkdir -p build/wsh-lab && \
	$(DOCKER) run --rm $(DOCKER_ARG) -v "$(CURRENT_DIR):/src:ro" -v "$(CURRENT_DIR)/build/wsh-lab:/out" \
		-e WSH_LAB_VERSION -e WSH_LAB_COMMIT -e WSH_LAB_EPOCH \
		wsh-lab-build /src/packages/wsh-lab/build.sh /out

# The optional wsh-openglide package (packages/wsh-openglide): OpenGLide from kjliew/qemu-xtra at the
# pinned commit (packages/wsh-openglide/upstream.env), the libglide2x.so/libglide3x.so that
# qemu-3dfx's Glide pass-through dlopen()s, built in a plain Debian 13 image into build/wsh-openglide/
# with lintian at the end. Its version comes from git (packages/wsh-openglide/version.sh), so it
# needs the full history and no changelog. packages/wsh-openglide/test.sh tests the result.
.PHONY: wsh-openglide
wsh-openglide:
	$(Q)eval "$$(packages/wsh-openglide/version.sh | sed 's/^/export /')"; \
	$(ECHO) "INFO: building wsh-openglide $$WSH_OPENGLIDE_VERSION"; \
	$(DOCKER) build -f packages/wsh-openglide/build.Dockerfile -t wsh-openglide-build packages/wsh-openglide && \
	mkdir -p build/wsh-openglide && \
	$(DOCKER) run --rm $(DOCKER_ARG) -v "$(CURRENT_DIR):/src:ro" -v "$(CURRENT_DIR)/build/wsh-openglide:/out" \
		-e WSH_OPENGLIDE_VERSION -e WSH_OPENGLIDE_COMMIT -e WSH_OPENGLIDE_EPOCH \
		wsh-openglide-build /src/packages/wsh-openglide/build.sh /out

# The optional wsh-qemu-rdp package (packages/wsh-qemu-rdp): qemu-rdp, the RDP server of Marc-André
# Lureau's qemu-display, at the pinned commit (packages/wsh-qemu-rdp/upstream.env) with its crates
# from crates.io (cargo vendor), and the unit wsh-qemu-rdp@<vmid> that serves a VM's D-Bus display;
# built in a plain Debian 13 image into build/wsh-qemu-rdp/ with lintian at the end. Its version
# comes from git (packages/wsh-qemu-rdp/version.sh), so it needs the full history and no changelog.
# JOBS limits cargo's parallel jobs. packages/wsh-qemu-rdp/test.sh tests the result.
.PHONY: wsh-qemu-rdp
wsh-qemu-rdp:
	$(Q)eval "$$(packages/wsh-qemu-rdp/version.sh | sed 's/^/export /')"; \
	$(ECHO) "INFO: building wsh-qemu-rdp $$WSH_QEMU_RDP_VERSION"; \
	$(DOCKER) build -f packages/wsh-qemu-rdp/build.Dockerfile -t wsh-qemu-rdp-build packages/wsh-qemu-rdp && \
	mkdir -p build/wsh-qemu-rdp && \
	$(DOCKER) run --rm $(DOCKER_ARG) -v "$(CURRENT_DIR):/src:ro" -v "$(CURRENT_DIR)/build/wsh-qemu-rdp:/out" \
		-e WSH_QEMU_RDP_VERSION -e WSH_QEMU_RDP_COMMIT -e WSH_QEMU_RDP_EPOCH -e JOBS \
		wsh-qemu-rdp-build /src/packages/wsh-qemu-rdp/build.sh /out

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
	$(DOCKER) run --rm -v ./repo:/opt/repo -w /opt/repo --env-file .gpg-password-env -i repo bash -c "cp /opt/repo-incoming/*.deb /opt/repo/incoming/ && expect /usr/local/bin/reprepro.exp -Vb . includedeb $(DEBIAN_TAG) /opt/repo/incoming/*.deb"

	# Interactive password prompt
	# $(DOCKER) run --rm -v ./repo:/opt/repo -w /opt/repo -it repo bash -c "cp /opt/repo-incoming/*.deb /opt/repo/incoming/ && reprepro -Vb . includedeb $(DEBIAN_TAG) /opt/repo/incoming/*.deb"

	# Optionally, run a container with the repo mounted at /opt/repo
	# $(DOCKER) run --rm -v repo:/opt/repo -v nginx/nginx-site.conf:/etc/nginx/conf.d/default.conf -p 8080:80 -it nginx

.PHONY: help
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  all:                     Initialize submodules and build all components"
	@echo "  build:                   Build all components (pve-manager, qemu-server, pve-storage, pve-qemu-bundle)"
	@echo "  build-containers:        Build Docker containers for development"
	@echo "  init-submodules:         Check and reinitialize git submodules"
	@echo "  reset-submodules:        Deletes and initializes git submodules (WARNING: potential loss of data if there are local patches)"
	@echo "  clean:                   Clean all submodules and built components"
	@echo "  dev:                     Set up development environment with symlinks and restart services"
	@echo "  dev-links:               Create symlinks for development files"
	@echo "  pve-manager:             Build pve-manager deb package"
	@echo "  pve-manager-clean:       Clean and rebuild pve-manager"
	@echo "  pve-manager-dev:         Build pve-manager web interface files"
	@echo "  qemu-server:             Build qemu-server deb package"
	@echo "  qemu-server-clean:       Clean and rebuild qemu-server"
	@echo "  qemu-server-dev:         Restart PVE services for development"
	@echo "  pve-storage:             Build pve-storage (libpve-storage-perl) deb package"
	@echo "  pve-storage-clean:       Clean and rebuild pve-storage"
	@echo "  pve-qemu:                Build pve-qemu deb package"
	@echo "  pve-qemu-3dfx:           Build QEMU with 3dfx support"
	@echo "  pve-qemu-bundle:         Build complete QEMU bundle with SPARC and 3dfx support"
	@echo "  3dfx:                    Clean, prepare and build QEMU with 3dfx support"
	@echo "  3dfx-drivers:            Build 3dfx DOS drivers"
	@echo "  clean-qemu-3dfx:         Clean 3dfx-specific QEMU files"
	@echo "  prepare-qemu-3dfx:       Initialize 3dfx submodule"
	@echo "  restore-pve-qemu:        Restore pve-qemu to current head"
	@echo "  restore-sparc:           Restore SPARC submodule"
	@echo "  openbios-sparc32:        Build openbios-sparc32 and openbios-sparc64 with the patches in openbios/"
	@echo "  apply-patches:           Apply patches to submodules"
	@echo "  unapply-patches:         Remove patches from submodules"
	@echo "  update-patches:          Update patch files from submodule changes"
	@echo "  repo-update:             Update local Debian repository with new packages"
	@echo "  wsh-lab:                 Build the optional wsh-lab package (the sparc lab) into build/wsh-lab"
	@echo "  wsh-openglide:           Build the optional wsh-openglide package (Glide host libraries for 3dfx) into build/wsh-openglide"
	@echo "  wsh-qemu-rdp:            Build the optional wsh-qemu-rdp package (RDP server for the D-Bus display) into build/wsh-qemu-rdp"
	@echo ""
	@echo "Variables:"
	@echo "  VERBOSE:                 Set to 1 or 2 to enable verbose output"
	@echo "  FORCE:                   Set to 1 to force operations"
	@echo "  DOCKER:                  Override Docker/Podman command (default: auto-detect)"
	@echo "  DOCKER_ARG:              Additional Docker/Podman arguments"
	@echo ""
	@echo "Examples:"
	@echo "  make                     # Build everything"
	@echo "  make VERBOSE=1           # Build with verbose output"
	@echo "  make dev                 # Set up development environment"
	@echo "  make 3dfx-drivers        # Build DOS drivers for 3dfx support"
	@echo ""
	@echo "For more information, see the README.md file."
	@echo ""

# vim:ft=make
