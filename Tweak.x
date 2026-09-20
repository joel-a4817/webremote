#import <Foundation/Foundation.h>
#import <CoreFoundation/CoreFoundation.h>
#import <objc/message.h>
#import <objc/runtime.h>


static CFStringRef const LockNotification =
    CFSTR(
        "com.joel.mediactl.lock-device"
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

        writeStatus(
            @"Darwin observer installed"
        );
    }
}
