ARCHS = arm64
TARGET = iphone:clang:16.5:15.0
THEOS_PACKAGE_SCHEME = rootless

include $(THEOS)/makefiles/common.mk

TOOL_NAME = mediactl

mediactl_FILES = mediactl.m MusicLibraryCommands.m MusicPlaylistRemoval.m
mediactl_FRAMEWORKS = Foundation MediaPlayer AVFoundation
mediactl_CFLAGS = -fobjc-arc
mediactl_CODESIGN_FLAGS = -Sentitlements.plist
mediactl_INSTALL_PATH = /Applications/MediaCtl.app

include $(THEOS_MAKE_PATH)/tool.mk

TWEAK_NAME = MediaCtlLock MediaCtlRoutes MediaCtlMusicImport

MediaCtlLock_FILES = Tweak.x
MediaCtlLock_CFLAGS = -fobjc-arc
MediaCtlLock_FRAMEWORKS = Foundation CoreFoundation MediaPlayer

MediaCtlRoutes_FILES = AirPlayRoutes.x
MediaCtlRoutes_CFLAGS = -fobjc-arc
MediaCtlRoutes_FRAMEWORKS = Foundation UIKit AVKit CoreFoundation

MediaCtlMusicImport_FILES = MusicImportBridge.x
MediaCtlMusicImport_CFLAGS = -fobjc-arc
MediaCtlMusicImport_FRAMEWORKS = Foundation CoreFoundation AVFoundation MediaPlayer

include $(THEOS_MAKE_PATH)/tweak.mk

after-install::
	install.exec "killall -9 SpringBoard"


