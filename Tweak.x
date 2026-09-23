#import <Foundation/Foundation.h>
#import <math.h>
#import <CoreFoundation/CoreFoundation.h>
#import <objc/message.h>
#import <objc/runtime.h>


static CFStringRef const LockNotification =
    CFSTR(
        "com.joel.mediactl.lock-device"
    );

static CFStringRef const WakeNotification =
    CFSTR(
        "com.joel.mediactl.wake-screen"
    );

static CFStringRef const HomeNotification =
    CFSTR(
        "com.joel.mediactl.home-screen"
    );


static NSString *const SystemVolumePath =
    @"/var/mobile/MediaCtlSystemVolume.plist";

@interface AVSystemController : NSObject
+ (instancetype)sharedAVSystemController;
- (BOOL)getVolume:(float *)volume
    forCategory:(NSString *)category;
@end

static void saveSystemVolume(float volume) {
    if (!isfinite(volume) || volume < 0.0f || volume > 1.0f) {
        return;
    }

    [@{
        @"volume": @(volume),
        @"updated": @([[NSDate date] timeIntervalSince1970])
    } writeToFile:SystemVolumePath atomically:YES];
}

static void captureCurrentSystemVolume(void) {
    Class controllerClass =
        NSClassFromString(@"AVSystemController");
    if (
        controllerClass == Nil ||
        ![controllerClass respondsToSelector:
            @selector(sharedAVSystemController)]
    ) {
        return;
    }

    AVSystemController *controller =
        [controllerClass sharedAVSystemController];
    float volume = 0.0f;
    if (
        controller != nil &&
        [controller respondsToSelector:
            @selector(getVolume:forCategory:)] &&
        [controller
            getVolume:&volume
            forCategory:@"Audio/Video"]
    ) {
        saveSystemVolume(volume);
    }
}

static void receivedSystemVolumeNotification(
    NSNotification *notification
) {
    NSDictionary *info = notification.userInfo;
    NSNumber *value = info[@"Volume"];

    if (value == nil) {
        value = info[
            @"AVSystemController_AudioVolumeNotificationParameter"
        ];
    }

    if (value != nil) {
        saveSystemVolume(value.floatValue);
    } else {
        captureCurrentSystemVolume();
    }
}

static NSString *const StatusPath =
    @"/var/mobile/MediaCtlLock-status.txt";


static void writeStatus(
    NSString *message
) {
    NSString *line =
        [NSString stringWithFormat:
            @"%@\n",
            message
        ];

    NSFileHandle *handle =
        [NSFileHandle
            fileHandleForWritingAtPath:
                StatusPath];

    if (handle == nil) {
        [
            [NSData data]
            writeToFile:
                StatusPath
            atomically:
                YES
        ];

        handle =
            [NSFileHandle
                fileHandleForWritingAtPath:
                    StatusPath];
    }

    if (handle == nil) {
        return;
    }

    [handle seekToEndOfFile];

    [handle writeData:
        [line dataUsingEncoding:
            NSUTF8StringEncoding]
    ];

    [handle closeFile];
}


static void lockDevice(void) {
    writeStatus(
        @"lockDevice entered"
    );

    Class managerClass =
        objc_getClass(
            "SBLockScreenManager"
        );

    if (managerClass == Nil) {
        writeStatus(
            @"SBLockScreenManager missing"
        );

        return;
    }

    writeStatus(
        @"SBLockScreenManager found"
    );

    SEL sharedSelector =
        sel_registerName(
            "sharedInstance"
        );

    if (
        !class_respondsToSelector(
            object_getClass(
                managerClass
            ),
            sharedSelector
        )
    ) {
        writeStatus(
            @"sharedInstance missing"
        );

        return;
    }

    id manager =
        ((id (*)(id, SEL))objc_msgSend)(
            managerClass,
            sharedSelector
        );

    if (manager == nil) {
        writeStatus(
            @"sharedInstance returned nil"
        );

        return;
    }

    writeStatus(
        @"sharedInstance returned object"
    );

    SEL lockSelector =
        sel_registerName(
            "lockUIFromSource:"
            "withOptions:"
        );

    if (
        ![manager
            respondsToSelector:
                lockSelector]
    ) {
        writeStatus(
            @"lockUIFromSource selector missing"
        );

        return;
    }

    writeStatus(
        @"calling lockUIFromSource"
    );

    ((void (*)(
        id,
        SEL,
        NSUInteger,
        NSDictionary *
    ))objc_msgSend)(
        manager,
        lockSelector,
        1,
        @{}
    );

    writeStatus(
        @"lockUIFromSource returned"
    );
}


static void showHomeScreen(void) {
    writeStatus(
        @"showHomeScreen entered"
    );

    Class controllerClass =
        objc_getClass(
            "SBUIController"
        );

    if (controllerClass != Nil) {
        SEL sharedSelector =
            sel_registerName(
                "sharedInstance"
            );

        if (
            class_respondsToSelector(
                object_getClass(
                    controllerClass
                ),
                sharedSelector
            )
        ) {
            id controller =
                ((id (*)(id, SEL))objc_msgSend)(
                    controllerClass,
                    sharedSelector
                );

            SEL selectors[] = {
                sel_registerName(
                    "clickedMenuButton"
                ),
                sel_registerName(
                    "handleHomeButtonSinglePressUp"
                ),
                sel_registerName(
                    "handleHomeButtonSinglePress"
                )
            };

            NSUInteger count =
                sizeof(selectors) /
                sizeof(selectors[0]);

            for (
                NSUInteger index = 0;
                index < count;
                index++
            ) {
                if (
                    controller != nil &&
                    [controller
                        respondsToSelector:
                            selectors[index]]
                ) {
                    ((void (*)(
                        id,
                        SEL
                    ))objc_msgSend)(
                        controller,
                        selectors[index]
                    );

                    writeStatus(
                        @"Home Screen selector sent"
                    );
                    return;
                }
            }
        }
    }

    Class applicationClass =
        objc_getClass(
            "UIApplication"
        );
    SEL sharedApplicationSelector =
        sel_registerName(
            "sharedApplication"
        );

    if (
        applicationClass != Nil &&
        class_respondsToSelector(
            object_getClass(
                applicationClass
            ),
            sharedApplicationSelector
        )
    ) {
        id application =
            ((id (*)(id, SEL))objc_msgSend)(
                applicationClass,
                sharedApplicationSelector
            );
        SEL simulateSelector =
            sel_registerName(
                "_simulateHomeButtonPress"
            );

        if (
            application != nil &&
            [application
                respondsToSelector:
                    simulateSelector]
        ) {
            ((void (*)(
                id,
                SEL
            ))objc_msgSend)(
                application,
                simulateSelector
            );

            writeStatus(
                @"Simulated Home button press"
            );
            return;
        }
    }

    writeStatus(
        @"No Home Screen selector available"
    );
}


static void receivedHomeNotification(
    CFNotificationCenterRef center,
    void *observer,
    CFStringRef name,
    const void *object,
    CFDictionaryRef userInfo
) {
    writeStatus(
        @"Home notification received"
    );

    dispatch_async(
        dispatch_get_main_queue(),
        ^{
            showHomeScreen();
        }
    );
}


static void wakeDevice(void) {
    writeStatus(@"wakeDevice entered");

    Class backlightClass =
        objc_getClass("SBBacklightController");
    SEL sharedSelector =
        sel_registerName("sharedInstance");

    if (
        backlightClass != Nil &&
        class_respondsToSelector(
            object_getClass(backlightClass),
            sharedSelector
        )
    ) {
        id backlight =
            ((id (*)(id, SEL))objc_msgSend)(
                backlightClass,
                sharedSelector
            );
        SEL wakeSelector =
            sel_registerName(
                "turnOnScreenFullyWithBacklightSource:"
            );

        if (
            backlight != nil &&
            [backlight respondsToSelector:wakeSelector]
        ) {
            ((void (*)(id, SEL, long long))objc_msgSend)(
                backlight,
                wakeSelector,
                1
            );
            writeStatus(@"backlight wake sent");
        } else {
            writeStatus(@"backlight wake selector missing");
        }
    } else {
        writeStatus(@"SBBacklightController missing");
    }

    dispatch_after(
        dispatch_time(
            DISPATCH_TIME_NOW,
            350 * NSEC_PER_MSEC
        ),
        dispatch_get_main_queue(),
        ^{
            Class managerClass =
                objc_getClass("SBLockScreenManager");

            if (
                managerClass == Nil ||
                !class_respondsToSelector(
                    object_getClass(managerClass),
                    sharedSelector
                )
            ) {
                writeStatus(@"unlock manager missing");
                return;
            }

            id manager =
                ((id (*)(id, SEL))objc_msgSend)(
                    managerClass,
                    sharedSelector
                );
            SEL unlockSelector =
                sel_registerName(
                    "unlockUIFromSource:withOptions:"
                );

            if (
                manager != nil &&
                [manager respondsToSelector:unlockSelector]
            ) {
                ((void (*)(
                    id,
                    SEL,
                    NSUInteger,
                    NSDictionary *
                ))objc_msgSend)(
                    manager,
                    unlockSelector,
                    1,
                    @{}
                );
                writeStatus(@"unsecured unlock sent");
            } else {
                writeStatus(@"unlock selector missing");
            }
        }
    );
}


static void receivedWakeNotification(
    CFNotificationCenterRef center,
    void *observer,
    CFStringRef name,
    const void *object,
    CFDictionaryRef userInfo
) {
    writeStatus(@"wake notification received");

    dispatch_async(
        dispatch_get_main_queue(),
        ^{
            wakeDevice();
        }
    );
}


static void receivedLockNotification(
    CFNotificationCenterRef center,
    void *observer,
    CFStringRef name,
    const void *object,
    CFDictionaryRef userInfo
) {
    writeStatus(
        @"Darwin notification received"
    );

    dispatch_async(
        dispatch_get_main_queue(),
        ^{
            lockDevice();
        }
    );
}


%ctor {
    @autoreleasepool {
        NSString *processName =
            NSProcessInfo
                .processInfo
                .processName;

        if (
            ![processName
                isEqualToString:
                    @"SpringBoard"]
        ) {
            return;
        }

        writeStatus(
            @"MediaCtlLock loaded into SpringBoard"
        );
        [[NSNotificationCenter defaultCenter]
            addObserverForName:@"SystemVolumeDidChange"
            object:nil
            queue:nil
            usingBlock:^(NSNotification *notification) {
                receivedSystemVolumeNotification(notification);
            }];

        [[NSNotificationCenter defaultCenter]
            addObserverForName:
                @"AVSystemController_SystemVolumeDidChangeNotification"
            object:nil
            queue:nil
            usingBlock:^(NSNotification *notification) {
                receivedSystemVolumeNotification(notification);
            }];

        captureCurrentSystemVolume();

        CFNotificationCenterAddObserver(
            CFNotificationCenterGetDarwinNotifyCenter(),
            NULL,
            receivedLockNotification,
            LockNotification,
            NULL,
            CFNotificationSuspensionBehaviorDeliverImmediately
        );

        CFNotificationCenterAddObserver(
            CFNotificationCenterGetDarwinNotifyCenter(),
            NULL,
            receivedWakeNotification,
            WakeNotification,
            NULL,
            CFNotificationSuspensionBehaviorDeliverImmediately
        );

        CFNotificationCenterAddObserver(
            CFNotificationCenterGetDarwinNotifyCenter(),
            NULL,
            receivedHomeNotification,
            HomeNotification,
            NULL,
            CFNotificationSuspensionBehaviorDeliverImmediately
        );

        writeStatus(
            @"Darwin observer installed"
        );
    }
}
