ARCHS = arm64
TARGET = iphone:clang:16.5:15.0
THEOS_PACKAGE_SCHEME = rootless

include $(THEOS)/makefiles/common.mk

TOOL_NAME = mediactl

mediactl_FILES = mediactl.m
mediactl_FRAMEWORKS = Foundation MediaPlayer
mediactl_CFLAGS = -fobjc-arc
mediactl_CODESIGN_FLAGS = -Sentitlements.plist
mediactl_INSTALL_PATH = /Applications/MediaCtl.app

include $(THEOS_MAKE_PATH)/tool.mk

TWEAK_NAME = MediaCtlLock

MediaCtlLock_FILES = Tweak.x
MediaCtlLock_CFLAGS = -fobjc-arc
MediaCtlLock_FRAMEWORKS = Foundation CoreFoundation

include $(THEOS_MAKE_PATH)/tweak.mk

after-install::
	install.exec "killall -9 SpringBoard"
