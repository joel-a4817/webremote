#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <AVKit/AVKit.h>
#import <CoreFoundation/CoreFoundation.h>


static NSString *const AirPlayPreferencesDomain =
    @"com.joel.mediactl-airplay";

static CFStringRef const
AirPlayShowPickerNotification =
    CFSTR(
        "com.joel.mediactl.airplay-show-picker"
    );


@interface AVRoutePickerView (
    MediaCtlPrivate
)

- (void)presentRoutePicker:
    (id)sender;

- (void)_routePickerButtonTapped:
    (id)sender;

@end


@interface MRAVOutputDevice :
    NSObject

- (NSString *)name;
- (NSString *)localizedName;
- (NSString *)uid;

- (BOOL)isPickable;
- (BOOL)isLocalDevice;

@end


/*
 * Weak because Music owns the real picker.
 *
 * We only retain a reference while its configured
 * picker remains alive in Music's interface.
 */
static __weak AVRoutePickerView *
    MusicRoutePicker = nil;


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
        setObject:devices
        forKey:@"devices"];

    [preferences
        setObject:
            [NSDate date]
        forKey:@"devicesUpdatedAt"];

    [preferences synchronize];
}


static void showMusicRoutePicker(void) {
    dispatch_async(
        dispatch_get_main_queue(),
        ^{
            AVRoutePickerView *picker =
                MusicRoutePicker;

            if (picker == nil) {
                NSLog(
                    @"[MediaCtlRoutes] "
                    @"No configured Music "
                    @"AVRoutePickerView available"
                );

                return;
            }

            if (
                picker.window == nil
            ) {
                NSLog(
                    @"[MediaCtlRoutes] "
                    @"Music route picker is "
                    @"not attached to a window"
                );

                return;
            }

            if (
                [picker respondsToSelector:
                    @selector(
                        presentRoutePicker:
                    )]
            ) {
                NSLog(
                    @"[MediaCtlRoutes] "
                    @"Presenting native "
                    @"Music AirPlay picker"
                );

                [picker
                    presentRoutePicker:nil];

                return;
            }

            /*
             * Verified fallback from the runtime
             * class inspection.
             */
            if (
                [picker respondsToSelector:
                    @selector(
                        _routePickerButtonTapped:
                    )]
            ) {
                NSLog(
                    @"[MediaCtlRoutes] "
                    @"Using native picker "
                    @"button fallback"
                );

                [picker
                    _routePickerButtonTapped:nil];

                return;
            }

            NSLog(
                @"[MediaCtlRoutes] "
                @"Music route picker exposes "
                @"no supported presentation method"
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
    showMusicRoutePicker();
}


%hook AVRoutePickerView

- (void)didMoveToWindow {
    %orig;

    if (self.window != nil) {
        MusicRoutePicker =
            self;

        NSLog(
            @"[MediaCtlRoutes] "
            @"Captured configured Music "
            @"route picker: %@",
            self
        );
    } else if (
        MusicRoutePicker == self
    ) {
        MusicRoutePicker =
            nil;
    }
}

%end


%hook MRAVRoutingDiscoverySession

- (void)setOutputDevicesSnapshot:
    (NSArray *)snapshot
{
    %orig;

    saveOutputDevices(
        snapshot ?: @[]
    );
}

%end


%ctor {
    @autoreleasepool {
        CFNotificationCenterAddObserver(
            CFNotificationCenterGetDarwinNotifyCenter(),
            NULL,
            airPlayNotificationReceived,
            AirPlayShowPickerNotification,
            NULL,
            CFNotificationSuspensionBehaviorDeliverImmediately
        );

        NSLog(
            @"[MediaCtlRoutes] "
            @"Native AirPlay picker trigger ready"
        );
    }
}
