#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <objc/message.h>
#import <objc/runtime.h>


static CFStringRef const LockNotification =
    CFSTR(
        "com.joel.mediactl.lock-device"
    );

static CFStringRef const HomeNotification =
    CFSTR(
        "com.joel.mediactl.home-screen"
    );


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
