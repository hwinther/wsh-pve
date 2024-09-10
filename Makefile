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
build:
	sudo ./docker-build.sh

.PHONY: unapply-patches clean
clean:
	$(ECHO) "INFO: Cleaning up"
	$(Q)qemu_path="submodules/pve-qemu/qemu"; \
	if [ -e "$$qemu_path" ]; then \
		$(ECHO) "INFO: Removing $$qemu_path"; \
		git submodule deinit --force "$$qemu_path"; \
	fi; \
	git submodule deinit --all

.PHONY: test
test:
	@echo "TODO: Add tests"

QEMU_SERVER_FILES := PVE/QemuServer.pm PVE/QemuServer/Drive.pm PVE/QemuServer/Machine.pm PVE/QemuServer/PCI.pm PVE/QemuServer/USB.pm
PVE_MANAGER_FILES := manager6/pvemanagerlib.js css/ext6-pve.css
PATCH_SUBMODULES := pve-manager pve-qemu qemu-server
CURRENT_DIR = $(shell pwd)

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
	done; \

.PHONY: qemu-server
qemu-server:
	$(Q)if [ $$(id -u) -eq 0 ]; then \
		$(ECHO) "INFO: Running as root"; \
	else \
		echo "ERROR: This target must be run as root"; \
		exit 1; \
	fi; \
	systemctl restart pveproxy pvedaemon

.PHONY: pve-manager
pve-manager:
	$(Q)make -C submodules/pve-manager/www/manager6 pvemanagerlib.js

.PHONY: apply-patches
apply-patches:
	$(Q)for submodule in $(PATCH_SUBMODULES); do \
		$(ECHO) "INFO: Applying patch for submodule: $$submodule"; \
		patch -d submodules/$$submodule -p1 -i ../$$submodule.patch; \
	done

.PHONY: unapply-patches
unapply-patches:
	$(Q)for submodule in $(PATCH_SUBMODULES); do \
		$(ECHO) "INFO: Applying patch for submodule: $$submodule"; \
		patch -d submodules/$$submodule -p1 -R -i ../$$submodule.patch; \
	done

.PHONY: update-patches
update-patches:
	$(Q)for submodule in $(PATCH_SUBMODULES); do \
		$(ECHO) "INFO: Creating patch for submodule: $$submodule"; \
		git -C submodules/$$submodule diff -p > submodules/$$submodule.patch; \
	done

.PHONY: 3dfx prepare-qemu-3dfx build-qemu-3dfx
3dfx: clean-qemu-3dfx prepare-qemu-3dfx build-qemu-3dfx
prepare-qemu-3dfx:
	git submodule update --init submodules/qemu-3dfx

REV = $(shell cd submodules/qemu-3dfx; git rev-parse HEAD | sed "s/\(.......\).*/\1\-/")
build-qemu-3dfx: prepare-qemu-3dfx
	cd submodules/pve-qemu && make submodule && cd ../../; \
	mkdir -p submodules/pve-qemu/debian/patches/wsh; \
	cp submodules/pve-qemu-qemu-3dfx.patch submodules/pve-qemu/debian/patches/wsh/0099-WSH-qemu-3dfx.patch; \
	echo "wsh/0099-WSH-qemu-3dfx.patch" >> submodules/pve-qemu/debian/patches/series; \
	cp -r submodules/qemu-3dfx/qemu-0/hw/3dfx submodules/qemu-3dfx/qemu-1/hw/mesa submodules/pve-qemu/qemu/hw/; \
	sed -i -e "s/\(rev_\[\).*\].*/\1\]\ =\ \"$(REV)\"/" submodules/pve-qemu/debian/patches/wsh/0099-WSH-qemu-3dfx.patch submodules/pve-qemu/qemu/hw/3dfx/g2xfuncs.h submodules/pve-qemu/qemu/hw/mesa/mglfuncs.h; \
	cd submodules/pve-qemu && make deb

.PHONY: clean-qemu-3dfx
clean-qemu-3dfx:
	rm -rf submodules/pve-qemu/debian/patches/wsh submodules/pve-qemu/qemu/hw/3dfx submodules/pve-qemu/qemu/hw/mesa; \
	cd submodules/pve-qemu && git checkout debian/patches/series && make clean

.PHONY: build-3dfx-drivers
build-3dfx-drivers:
	git submodule update --init submodules/qemu-3dfx

	podman run --rm -v .git:/src/.git -v "./submodules/qemu-3dfx":"/src/submodules/qemu-3dfx" -w /src/submodules/qemu-3dfx/wrappers/3dfx -it ghcr.io/hwinther/wsh-pve/djgpp-build:12 bash -c "mkdir -p build && cd build && bash ../../../scripts/conf_wrapper && make && make clean"
	podman run --rm -v .git:/src/.git -v "./submodules/qemu-3dfx":"/src/submodules/qemu-3dfx" -w /src/submodules/qemu-3dfx/wrappers/mesa -it ghcr.io/hwinther/wsh-pve/djgpp-build:12 bash -c "mkdir -p build && cd build && bash ../../../scripts/conf_wrapper && make && make clean"

	ls -la submodules/qemu-3dfx/wrappers/3dfx/build
	ls -la submodules/qemu-3dfx/wrappers/mesa/build

	mkdir -p build && rm -rf build/3dfx build/mesa
	mv submodules/qemu-3dfx/wrappers/3dfx/build build/3dfx && rm -f build/3dfx/Makefile build/3dfx/*.a
	mv submodules/qemu-3dfx/wrappers/mesa/build build/mesa && rm -f build/mesa/Makefile build/mesa/*.a

.PHONY: help
help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  all:                  Build the project"
	@echo "  check-and-reinit-submodules: Check and reinitialize git submodules"
	@echo "  build:                Build the project"
	@echo "  clean:                Clean the project"
	@echo "  test:                 Run tests"
	@echo "  dev-links:            Create symlinks for QemuServer files"
	@echo "  clean-qemu-3dfx:      Clean QEMU 3dfx"
	@echo "  build-3dfx-drivers:   Build 3dfx drivers"
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
	@echo "  make build-3dfx-drivers"
	@echo "  make help"
	@echo ""
	@echo "For more information, see the README.md file."
	@echo ""

# vim:ft=make
