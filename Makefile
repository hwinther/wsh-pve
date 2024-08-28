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

.PHONY: build
build:
	sudo ./docker-build.sh

.PHONY: clean
clean:
	$(ECHO) "INFO: Cleaning up"
	git submodule deinit --all

.PHONY: test
test:
	@echo "TODO: Add tests"

QEMU_SERVER_FILES := PVE/QemuServer.pm PVE/QemuServer/Drive.pm PVE/QemuServer/Machine.pm PVE/QemuServer/PCI.pm PVE/QemuServer/USB.pm
PVE_MANAGER_FILES := js/pvemanagerlib.js css/ext6-pve.css
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
		if [ -L "/usr/share/perl5/$$item" ]; then \
			$(ECHO) "INFO: /usr/share/perl5/$$item is already a symlink"; \
		elif [ -e "/usr/share/perl5/$$item" ]; then \
			$(ECHO) "INFO: /usr/share/perl5/$$item exists but is not a symlink"; \
			rm -f "/usr/share/perl5/$$item"; \
		fi; \
		if [ ! -e "/usr/share/perl5/$$item" ]; then \
			$(ECHO) "INFO: Creating symlink to /usr/share/perl5/$$item"; \
            ln -s "$(CURRENT_DIR)/submodules/qemu-server/$$item" "/usr/share/perl5/$$item"; \
        fi; \
	done

	$(Q)if [ ! -e "$(CURRENT_DIR)/submodules/pve-manager/www/js" ]; then \
		$(ECHO) "INFO: Creating symlink to $(CURRENT_DIR)/submodules/pve-manager/www/js"; \
		ln -s "$(CURRENT_DIR)/submodules/pve-manager/www/manager6" "$(CURRENT_DIR)/submodules/pve-manager/www/js"; \
	fi; \
	for item in $(PVE_MANAGER_FILES); do \
		if [ -L "/usr/share/pve-manager/$$item" ]; then \
			$(ECHO) "INFO: /usr/share/pve-manager/$$item is already a symlink"; \
		elif [ -e "/usr/share/pve-manager/$$item" ]; then \
			$(ECHO) "INFO: /usr/share/pve-manager/$$item exists but is not a symlink"; \
			rm -f "/usr/share/pve-manager/$$item"; \
		fi; \
		if [ ! -e "/usr/share/pve-manager/$$item" ]; then \
			$(ECHO) "INFO: Creating symlink to /usr/share/pve-manager/$$item"; \
            ln -s "$(CURRENT_DIR)/submodules/pve-manager/www/$$item" "/usr/share/pve-manager/$$item"; \
        fi; \
	done

.PHONY: apply-patches
apply-patches:
	$(Q)for submodule in $(PATCH_SUBMODULES); do \
		$(ECHO) "INFO: Applying patch for submodule: $$submodule"; \
		patch -d submodules/$$submodule -p1 -i ../$$submodule.patch; \
	done

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
	@echo "  make help"
	@echo ""
	@echo "For more information, see the README.md file."
	@echo ""

# vim:ft=make