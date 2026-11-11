# RewindBox: S2Arm's iOS engine linked as one dynamic framework, for RewindBox to dlopen.
# Used as `make -f Makefile -f <this file> ios-guest` in the S2Arm tree, after `make ios`: the same
# objects and libraries as the S2Arm.app executable (runtime, UIKit host, graphics, NativeAOT
# services, codecs), linked with -dynamiclib instead of as an app. S2Arm's own makefiles are not
# changed. Exported symbols are not restricted yet (inventory first). The guest interface (runtime/src/rb_guest.h, patches 0003-0008)
# goes into Headers/; the host string tables (<lang>.lproj/S2ArmHost.strings) sit at the framework root, where the engine looks for them.
S2ARM_GUEST_FW := $(BUILD)/ios/S2ArmEngine.framework
.PHONY: ios-guest
ios-guest: ios
	@test -n "$(BUILD)" && rm -rf "$(BUILD)/ios/S2ArmEngine.framework" && mkdir -p "$(S2ARM_GUEST_FW)"
	$(IOS_LD_REPRO) $(IOS_CC) -fobjc-arc -dynamiclib $(IOS_LD_DET) -Wl,-oso_prefix,$(IOS_BUILD_ABS)/ \
	  -install_name @rpath/S2ArmEngine.framework/S2ArmEngine \
	  -o $(S2ARM_GUEST_FW)/S2ArmEngine $(call ios_objlist,$(BUILD)/ios/obj_app,$(IOS_SRCS)) $(IOS_LIBS) \
	  -framework UIKit -framework Foundation -framework CoreGraphics $(IOS_SHELLUI_LINK) $(call S2A_WEAK_U,ios) -Wl,-S
	@cp -R ios/l10n/*.lproj "$(S2ARM_GUEST_FW)/"
	@mkdir -p "$(S2ARM_GUEST_FW)/Headers" && cp runtime/src/rb_guest.h "$(S2ARM_GUEST_FW)/Headers/"   # guest interface for the host (patch 0003)
	@/usr/bin/plutil -create xml1 "$(S2ARM_GUEST_FW)/Info.plist" && for kv in CFBundleIdentifier=com.neogamelab.neostation.S2ArmEngine CFBundleExecutable=S2ArmEngine CFBundleName=S2ArmEngine CFBundlePackageType=FMWK CFBundleDevelopmentRegion=en CFBundleShortVersionString=1.0 CFBundleVersion=1 MinimumOSVersion=$(IPHONEOS_DEPLOYMENT_TARGET); do /usr/bin/plutil -insert $${kv%%=*} -string "$${kv#*=}" "$(S2ARM_GUEST_FW)/Info.plist"; done
	@/usr/bin/plutil -insert CFBundleSupportedPlatforms -xml '<array><string>iPhoneOS</string></array>' "$(S2ARM_GUEST_FW)/Info.plist"
	@echo "Guest framework: $(S2ARM_GUEST_FW) ($$(du -sh "$(S2ARM_GUEST_FW)" | cut -f1))"
