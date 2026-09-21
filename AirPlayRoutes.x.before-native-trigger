#import <Foundation/Foundation.h>


static NSString *const AirPlayPreferencesDomain =
    @"com.joel.mediactl-airplay";


@interface MRAVOutputDevice : NSObject

- (NSString *)name;
- (NSString *)localizedName;
- (NSString *)uid;

- (BOOL)isPickable;
- (BOOL)isLocalDevice;

@end


static NSString *deviceName(
    MRAVOutputDevice *device
) {
    NSString *name = nil;

    if (
        [device respondsToSelector:
            @selector(localizedName)]
    ) {
        name = [device localizedName];
    }

    if (
        name.length == 0 &&
        [device respondsToSelector:
            @selector(name)]
    ) {
        name = [device name];
    }

    if (name.length == 0) {
        name = @"Unknown AirPlay Device";
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
                isKindOfClass:
                    NSClassFromString(
                        @"MRAVOutputDevice"
                    )]
        ) {
            continue;
        }

        MRAVOutputDevice *device =
            candidate;

        if (
            ![device isPickable] ||
            [device isLocalDevice]
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
