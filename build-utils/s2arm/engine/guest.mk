# RewindBox: S2Arm's iOS engine linked as one dynamic framework, for RewindBox to dlopen.
# Used as `make -f Makefile -f <this file> ios-guest` in the S2Arm tree, after `make ios`: the same
# objects and libraries as the S2Arm.app executable (runtime, UIKit host, graphics, NativeAOT
# services, codecs), linked with -dynamiclib instead of as an app. S2Arm's own makefiles are not
# changed. Exports are restricted (export_list.py next to this file): a first, unrestricted link gives the export set,
# the framework keeps only the guest entry points and the exported names the engine looks up by name (strings of
# that link), then the final link uses -exported_symbols_list; third-party exports such as glslang's, whose weak
# definitions dyld would coalesce with DolphinCore's, are hidden. The guest interface (runtime/src/rb_guest.h, patches 0003-0009)
# goes into Headers/; the host string tables (<lang>.lproj/S2ArmHost.strings) sit at the framework root, where the engine looks for them.
# In a guest the engine reads its own Info.plist, not the host app's (patch 0009): S2ACommit, as `make ios` writes it for S2Arm.app,
# is the build identity of its diagnostics and of the direct-mode safety net (runtime/src/dguard.c).
S2ARM_GUEST_FW := $(BUILD)/ios/S2ArmEngine.framework
S2ARM_GUEST_TOOLS := $(dir $(lastword $(MAKEFILE_LIST)))
S2ARM_GUEST_OPEN := $(BUILD)/ios/S2ArmEngine.unrestricted
S2ARM_GUEST_EXPORTS := $(BUILD)/ios/S2ArmEngine.exports
S2ARM_GUEST_LINK = $(IOS_LD_REPRO) $(IOS_CC) -fobjc-arc -dynamiclib $(IOS_LD_DET) -Wl,-oso_prefix,$(IOS_BUILD_ABS)/ \
  -install_name @rpath/S2ArmEngine.framework/S2ArmEngine \
  $(call ios_objlist,$(BUILD)/ios/obj_app,$(IOS_SRCS)) $(IOS_LIBS) \
  -framework UIKit -framework Foundation -framework CoreGraphics $(IOS_SHELLUI_LINK) $(call S2A_WEAK_U,ios) -Wl,-S
.PHONY: ios-guest
ios-guest: ios
	@test -n "$(BUILD)" && rm -rf "$(BUILD)/ios/S2ArmEngine.framework" && mkdir -p "$(S2ARM_GUEST_FW)"
	$(S2ARM_GUEST_LINK) -o $(S2ARM_GUEST_OPEN)
	nm -gU $(S2ARM_GUEST_OPEN) > $(S2ARM_GUEST_OPEN).nm
	python3 $(S2ARM_GUEST_TOOLS)export_list.py $(S2ARM_GUEST_OPEN) $(S2ARM_GUEST_OPEN).nm $(S2ARM_GUEST_EXPORTS) $(S2ARM_GUEST_EXPORTS).json
	$(S2ARM_GUEST_LINK) -Wl,-exported_symbols_list,$(S2ARM_GUEST_EXPORTS) -Wl,-map,$(BUILD)/ios/S2ArmEngine.map -o $(S2ARM_GUEST_FW)/S2ArmEngine
	@rm -f $(S2ARM_GUEST_OPEN)
	@cp -R ios/l10n/*.lproj "$(S2ARM_GUEST_FW)/"
	@mkdir -p "$(S2ARM_GUEST_FW)/Headers" && cp runtime/src/rb_guest.h "$(S2ARM_GUEST_FW)/Headers/"   # guest interface for the host (patch 0003)
	@/usr/bin/plutil -create xml1 "$(S2ARM_GUEST_FW)/Info.plist" && for kv in CFBundleIdentifier=com.neogamelab.neostation.S2ArmEngine CFBundleExecutable=S2ArmEngine CFBundleName=S2ArmEngine CFBundlePackageType=FMWK CFBundleDevelopmentRegion=en CFBundleShortVersionString=1.0 CFBundleVersion=1 MinimumOSVersion=$(IPHONEOS_DEPLOYMENT_TARGET); do /usr/bin/plutil -insert $${kv%%=*} -string "$${kv#*=}" "$(S2ARM_GUEST_FW)/Info.plist"; done
	@/usr/bin/plutil -insert CFBundleSupportedPlatforms -xml '<array><string>iPhoneOS</string></array>' "$(S2ARM_GUEST_FW)/Info.plist"
	@/usr/bin/plutil -insert S2ACommit -string "$$(git rev-parse HEAD 2> /dev/null || echo unknown)" "$(S2ARM_GUEST_FW)/Info.plist"   # same value as S2Arm.app's (runtime/build.mk)
	@# The direct shader library chain this engine expects (DMSH_CHAIN of the generated, checked-in dmsh_chain.h, read as
	@# graphics/widen/scan/closed_loop.sh reads it): RewindBox's preparation stamps the game's shaders/direct skeleton with it.
	@chain=$$(sed -n 's/^#define DMSH_CHAIN "\([0-9a-f]*\)".*/\1/p' graphics/nvn/gfx/nvn/dmsh_chain.h); \
	  test -n "$$chain" && test $${#chain} -le 12 || { echo "DMSH_CHAIN not found in graphics/nvn/gfx/nvn/dmsh_chain.h" >&2; exit 1; }; \
	  printf '%s\n' "$$chain" > "$(S2ARM_GUEST_FW)/S2ArmDirectChain.txt"
	@echo "Guest framework: $(S2ARM_GUEST_FW) ($$(du -sh "$(S2ARM_GUEST_FW)" | cut -f1))"
