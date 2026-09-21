#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <CoreFoundation/CoreFoundation.h>


static NSString *const
AirPlayPreferencesDomain =
    @"com.joel.mediactl-airplay";


static CFStringRef const
AirPlayShowPickerNotification =
    CFSTR(
        "com.joel.mediactl.airplay-show-picker"
    );


static NSString *const
AirPlayPickerStatusPath =
    @"/var/mobile/Library/Preferences/"
    @"com.joel.mediactl-airplay-picker-status.plist";


@interface MRAVOutputDevice :
    NSObject

- (NSString *)name;
- (NSString *)localizedName;
- (NSString *)uid;

- (BOOL)isPickable;
- (BOOL)isLocalDevice;

@end


/*
 * Music owns the route buttons.
 *
 * Weak storage avoids changing their lifetime.
 */
static NSHashTable *
MusicRouteButtons = nil;


static BOOL runningInProcess(
    NSString *name
) {
    return [
        NSProcessInfo
            .processInfo
            .processName
        isEqualToString:
            name
    ];
}


static void writePickerStatus(
    NSString *status,
    NSString *detail
) {
    NSDictionary *record = @{
        @"status":
            status ?: @"unknown",

        @"detail":
            detail ?: @"",

        @"timestamp":
            @(
                [[NSDate date]
                    timeIntervalSince1970]
            )
    };

    [record
        writeToFile:
            AirPlayPickerStatusPath
        atomically:
            YES];
}


static NSString *deviceName(
    MRAVOutputDevice *device
) {
    NSString *name = nil;

    if (
        [device respondsToSelector:
            @selector(localizedName)]
    ) {
        name =
            [device localizedName];
    }

    if (
        name.length == 0 &&
        [device respondsToSelector:
            @selector(name)]
    ) {
        name =
            [device name];
    }

    if (name.length == 0) {
        name =
            @"Unknown AirPlay Device";
    }

    return name;
}


static void saveOutputDevices(
    NSArray *snapshot
) {
    NSMutableArray *devices =
        [NSMutableArray array];

    for (
        id candidate
        in snapshot
    ) {
        if (
            ![candidate
                respondsToSelector:
                    @selector(uid)]
        ) {
            continue;
        }

        MRAVOutputDevice *device =
            candidate;

        BOOL pickable = YES;
        BOOL local = NO;

        if (
            [device respondsToSelector:
                @selector(isPickable)]
        ) {
            pickable =
                [device isPickable];
        }

        if (
            [device respondsToSelector:
                @selector(isLocalDevice)]
        ) {
            local =
                [device isLocalDevice];
        }

        if (
            !pickable ||
            local
        ) {
            continue;
        }

        NSString *uid =
            [device uid];

        if (uid.length == 0) {
            continue;
        }

        [devices addObject:@{
            @"name":
                deviceName(device),

            @"uid":
                uid,

            @"pickable":
                @YES,

            @"local":
                @NO
        }];
    }

    [devices sortUsingComparator:
        ^NSComparisonResult(
            NSDictionary *first,
            NSDictionary *second
        ) {
            NSComparisonResult nameResult =
                [
                    first[@"name"]
                    localizedCaseInsensitiveCompare:
                        second[@"name"]
                ];

            if (
                nameResult !=
                NSOrderedSame
            ) {
                return nameResult;
            }

            return [
                first[@"uid"]
                compare:
                    second[@"uid"]
            ];
        }
    ];

    NSUserDefaults *preferences =
        [[NSUserDefaults alloc]
            initWithSuiteName:
                AirPlayPreferencesDomain];

    [preferences
        setObject:
            devices
        forKey:
            @"devices"];

    [preferences
        setObject:
            [NSDate date]
        forKey:
            @"devicesUpdatedAt"];

    [preferences synchronize];

    writePickerStatus(
        @"snapshot-received",
        [
            NSString
            stringWithFormat:
                @"Received %lu external devices",
                (unsigned long)devices.count
        ]
    );
}


static UIControl *
bestMusicRouteButton(void) {
    UIControl *fallback = nil;

    for (
        UIControl *button
        in MusicRouteButtons.allObjects
    ) {
        if (button == nil) {
            continue;
        }

        fallback =
            fallback ?: button;

        if (
            button.window != nil &&
            !button.hidden &&
            button.alpha > 0.01 &&
            button.enabled &&
            button.userInteractionEnabled
        ) {
            return button;
        }
    }

    return fallback;
}


static void showNativeMusicRoutePicker(void) {
    if (
        !runningInProcess(
            @"Music"
        )
    ) {
        return;
    }

    dispatch_async(
        dispatch_get_main_queue(),
        ^{
            UIControl *button =
                bestMusicRouteButton();

            if (button == nil) {
                writePickerStatus(
                    @"no-route-button",
                    @"Music has not created "
                    @"an MPRouteButton"
                );

                return;
            }

            if (button.window == nil) {
                writePickerStatus(
                    @"detached-route-button",
                    @"MPRouteButton exists but "
                    @"is not attached to a window"
                );

                return;
            }

            if (
                button.hidden ||
                button.alpha <= 0.01 ||
                !button.enabled ||
                !button.userInteractionEnabled
            ) {
                writePickerStatus(
                    @"inactive-route-button",
                    @"MPRouteButton is not "
                    @"currently interactive"
                );

                return;
            }

            writePickerStatus(
                @"triggering",
                @"Sending TouchUpInside to "
                @"Music's MPRouteButton"
            );

            /*
             * This is the exact mechanism validated
             * against Music's live Now Playing button.
             *
             * UIControlEventTouchUpInside = 1 << 6.
             */
            [button
                sendActionsForControlEvents:
                    UIControlEventTouchUpInside];

            writePickerStatus(
                @"triggered",
                @"Music's MPRouteButton "
                @"accepted TouchUpInside"
            );
        }
    );
}


static void airPlayNotificationReceived(
    CFNotificationCenterRef center,
    void *observer,
    CFStringRef name,
    const void *object,
    CFDictionaryRef userInfo
) {
    showNativeMusicRoutePicker();
}


%hook MPRouteButton

- (id)initWithFrame:
    (CGRect)frame
{
    id result =
        %orig;

    if (
        result != nil &&
        runningInProcess(
            @"Music"
        )
    ) {
        [MusicRouteButtons
            addObject:
                result];
    }

    return result;
}


- (id)initWithCoder:
    (NSCoder *)coder
{
    id result =
        %orig;

    if (
        result != nil &&
        runningInProcess(
            @"Music"
        )
    ) {
        [MusicRouteButtons
            addObject:
                result];
    }

    return result;
}


- (void)didMoveToWindow {
    %orig;

    if (
        runningInProcess(
            @"Music"
        )
    ) {
        [MusicRouteButtons
            addObject:
                self];
    }
}

%end


%hook MRAVRoutingDiscoverySession

- (void)setOutputDevicesSnapshot:
    (NSArray *)snapshot
{
    %orig;

    if (
        runningInProcess(
            @"MusicUIService"
        )
    ) {
        saveOutputDevices(
            snapshot ?: @[]
        );
    }
}

%end


%ctor {
    @autoreleasepool {
        NSString *processName =
            NSProcessInfo
                .processInfo
                .processName;

        if (
            ![processName
                isEqualToString:
                    @"Music"] &&
            ![processName
                isEqualToString:
                    @"MusicUIService"]
        ) {
            return;
        }

        if (
            [processName
                isEqualToString:
                    @"Music"]
        ) {
            MusicRouteButtons =
                [NSHashTable
                    weakObjectsHashTable];

            CFNotificationCenterAddObserver(
                CFNotificationCenterGetDarwinNotifyCenter(),
                NULL,
                airPlayNotificationReceived,
                AirPlayShowPickerNotification,
                NULL,
                CFNotificationSuspensionBehaviorDeliverImmediately
            );

            writePickerStatus(
                @"ready",
                @"MediaCtlRoutes loaded "
                @"into Music"
            );
        }
    }
}
