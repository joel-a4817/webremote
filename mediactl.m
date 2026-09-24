#import <Foundation/Foundation.h>
#import <MediaPlayer/MediaPlayer.h>
#import <dispatch/dispatch.h>
#import <dlfcn.h>
#import <math.h>
#import <objc/message.h>
#import <errno.h>
#import <stdint.h>
#import <stdio.h>
#import <stdlib.h>
#import <spawn.h>
#import <string.h>
#import <sys/wait.h>
#import <unistd.h>

#import "MusicLibraryCommands.h"
#import "MusicPlaylistRemoval.h"
#import "ipad_speaker_request.h"
#import "airplay_route_template.h"

/*
 * The Theos SDK does not ship xpc/xpc.h.
 * Declare only the libxpc interfaces used here.
 */
typedef void *xpc_object_t;
typedef xpc_object_t xpc_connection_t;

typedef void (^xpc_handler_t)(
    xpc_object_t object
);

extern xpc_connection_t
xpc_connection_create_mach_service(
    const char *name,
    dispatch_queue_t targetQueue,
    uint64_t flags
);

extern void
xpc_connection_set_event_handler(
    xpc_connection_t connection,
    xpc_handler_t handler
);

extern void
xpc_connection_resume(
    xpc_connection_t connection
);

extern xpc_object_t
xpc_dictionary_create(
    const char *const *keys,
    const xpc_object_t *values,
    size_t count
);

extern void
xpc_dictionary_set_data(
    xpc_object_t dictionary,
    const char *key,
    const void *bytes,
    size_t length
);

extern void
xpc_dictionary_set_string(
    xpc_object_t dictionary,
    const char *key,
    const char *value
);

extern void
xpc_dictionary_set_uint64(
    xpc_object_t dictionary,
    const char *key,
    uint64_t value
);

extern void
xpc_connection_send_message(
    xpc_connection_t connection,
    xpc_object_t message
);

@interface AVSystemController : NSObject
+ (instancetype)sharedAVSystemController;
- (BOOL)getVolume:(float *)volume
    forCategory:(NSString *)category;
- (BOOL)setVolumeTo:(float)volume
    forCategory:(NSString *)category;
@end


extern char **environ;

typedef uint8_t (*MRSendCommandWithReplyFunction)(
    uint32_t command,
    CFDictionaryRef options,
    dispatch_queue_t replyQueue,
    void (^reply)(CFArrayRef result)
);

static void printUsage(void) {
    fprintf(
        stderr,
        "Usage:\n"
        "  mediactl play\n"
        "  mediactl pause\n"
        "  mediactl toggle\n"
        "  mediactl next\n"
        "  mediactl previous\n"
        "  mediactl authorization\n"
        "  mediactl authorize\n"
        "  mediactl playlists\n"
        "  mediactl playlists-json\n"
        "  mediactl playlist \"Playlist Name\"\n"
        "  mediactl playlist-play \"Playlist Name\"\n"
        "  mediactl shuffle-json\n"
        "  mediactl shuffle-toggle\n"
        "  mediactl playlist-songs-json \"Playlist Name\"\n"
        "  mediactl song <persistent-id> \"Playlist Name\"\n"
        "  mediactl now-playing-json\n"
        "  mediactl repeat-json\n"
        "  mediactl repeat-cycle\n"
        "  mediactl volume-json\n"
        "  mediactl volume <0-1>\n"
        "  mediactl volume-lock <on|off>\n"
        "  mediactl seek <seconds>\n"
        "  mediactl lock-device\n"
        "  mediactl wake-screen\n"
        "  mediactl home-screen\n"
        "  mediactl airplay-connect-default\n"
        "  mediactl airplay-devices-json\n"
        "  mediactl airplay-show-picker\n"
        "  mediactl airplay-connect <uid> [name]\n"
        "  mediactl airplay-disconnect\n"
        "  mediactl airplay-set-default <uid> [name]\n"
        "  mediactl restart-music\n"
        "  mediactl resume\n"
        "  mediactl songs-json\n"
        "  mediactl song-play <persistent-id>\n"
        "  mediactl song-playlists-json <persistent-id>\n"
        "  mediactl song-add-to-playlist <persistent-id> \"Playlist Name\"\n"
        "  mediactl song-remove-from-playlist "
        "<persistent-id> \"Playlist Name\"\n"
        "  mediactl song-remove-from-library <persistent-id>\n"
        "  mediactl music-import-trigger\n"
    );
}

static const char *authorizationStatusName(
    MPMediaLibraryAuthorizationStatus status
) {
    switch (status) {
        case MPMediaLibraryAuthorizationStatusNotDetermined:
            return "not-determined";

        case MPMediaLibraryAuthorizationStatusDenied:
            return "denied";

        case MPMediaLibraryAuthorizationStatusRestricted:
            return "restricted";

        case MPMediaLibraryAuthorizationStatusAuthorized:
            return "authorized";
    }

    return "unknown";
}


static int requireMediaLibraryAuthorization(void) {
    MPMediaLibraryAuthorizationStatus status =
        [MPMediaLibrary authorizationStatus];

    if (
        status ==
        MPMediaLibraryAuthorizationStatusAuthorized
    ) {
        return 0;
    }

    fprintf(
        stderr,
        "Media-library access is %s.\n",
        authorizationStatusName(status)
    );

    if (
        status ==
        MPMediaLibraryAuthorizationStatusNotDetermined
    ) {
        fprintf(
            stderr,
            "Run 'mediactl authorize' first.\n"
        );
    } else {
        fprintf(
            stderr,
            "Allow MediaCtl under Settings > Privacy & Security "
            "> Media & Apple Music.\n"
        );
    }

    return 1;
}

static int requestMediaLibraryAccess(void) {
    MPMediaLibraryAuthorizationStatus currentStatus =
        [MPMediaLibrary authorizationStatus];

    printf(
        "Current media-library authorization: %s\n",
        authorizationStatusName(currentStatus)
    );

    if (
        currentStatus ==
        MPMediaLibraryAuthorizationStatusAuthorized
    ) {
        return 0;
    }

    if (
        currentStatus ==
        MPMediaLibraryAuthorizationStatusDenied ||
        currentStatus ==
        MPMediaLibraryAuthorizationStatusRestricted
    ) {
        fprintf(
            stderr,
            "Media-library access cannot be requested again "
            "from its current state.\n"
        );

        fprintf(
            stderr,
            "Allow MediaCtl under Settings > Privacy & Security "
            "> Media & Apple Music.\n"
        );

        return 1;
    }

    dispatch_semaphore_t semaphore =
        dispatch_semaphore_create(0);

    __block MPMediaLibraryAuthorizationStatus newStatus =
        MPMediaLibraryAuthorizationStatusNotDetermined;

    [MPMediaLibrary requestAuthorization:
        ^(MPMediaLibraryAuthorizationStatus status) {
            newStatus = status;
            dispatch_semaphore_signal(semaphore);
        }
    ];

    dispatch_time_t timeout =
        dispatch_time(
            DISPATCH_TIME_NOW,
            60 * NSEC_PER_SEC
        );

    long waitResult =
        dispatch_semaphore_wait(semaphore, timeout);

    if (waitResult != 0) {
        fprintf(
            stderr,
            "Timed out waiting for media-library authorization.\n"
        );

        fprintf(
            stderr,
            "Make sure the MediaCtl app bundle is installed, "
            "registered with uicache, and visible on the iPad.\n"
        );

        return 1;
    }

    printf(
        "New media-library authorization: %s\n",
        authorizationStatusName(newStatus)
    );

    return (
        newStatus ==
        MPMediaLibraryAuthorizationStatusAuthorized
    ) ? 0 : 1;
}

static int sendMediaRemoteCommand(
    uint32_t command,
    const char *name
) {
    const char *frameworkPath =
        "/System/Library/PrivateFrameworks/"
        "MediaRemote.framework/MediaRemote";

    void *framework =
        dlopen(frameworkPath, RTLD_LAZY | RTLD_LOCAL);

    if (framework == NULL) {
        fprintf(
            stderr,
            "Could not load MediaRemote.framework: %s\n",
            dlerror()
        );

        return 1;
    }

    const char *symbolName =
        "MRMediaRemoteSendCommandWithReply";

    MRSendCommandWithReplyFunction sendCommand =
        (MRSendCommandWithReplyFunction)dlsym(
            framework,
            symbolName
        );

    if (sendCommand == NULL) {
        fprintf(
            stderr,
            "Could not resolve %s: %s\n",
            symbolName,
            dlerror()
        );

        dlclose(framework);
        return 1;
    }

    dispatch_semaphore_t semaphore =
        dispatch_semaphore_create(0);

    __block BOOL receivedReply = NO;

    dispatch_queue_t replyQueue =
        dispatch_get_global_queue(
            QOS_CLASS_USER_INITIATED,
            0
        );

    uint8_t queued = sendCommand(
        command,
        NULL,
        replyQueue,
        ^(__unused CFArrayRef result) {
            receivedReply = YES;
            dispatch_semaphore_signal(semaphore);
        }
    );

    if (!queued) {
        fprintf(
            stderr,
            "MediaRemote did not queue the command\n"
        );

        dlclose(framework);
        return 1;
    }

    dispatch_time_t timeout =
        dispatch_time(
            DISPATCH_TIME_NOW,
            2 * NSEC_PER_SEC
        );

    dispatch_semaphore_wait(semaphore, timeout);

    printf(
        "Sent command: %s%s\n",
        name,
        receivedReply ? "" : " (no reply received)"
    );

    dlclose(framework);
    return 0;
}

static BOOL volumeLockedAtMaximum(void);
static double currentSystemVolume(void);
static BOOL applySystemVolume(double volume);
static int resumeWithVolumePolicy(void);
static int requestShuffleEnabled(
    BOOL enabled,
    BOOL printResult
);


static int togglePlaybackAtFullVolume(void) {
    MPMusicPlayerController *player =
        [MPMusicPlayerController
            systemMusicPlayer];

    if (
        player.playbackState ==
        MPMusicPlaybackStatePlaying
    ) {
        return sendMediaRemoteCommand(
            1,
            "pause"
        );
    }

    return resumeWithVolumePolicy();
}


static NSArray<MPMediaPlaylist *> *getPlaylists(void) {
    MPMediaQuery *query =
        [MPMediaQuery playlistsQuery];

    NSArray<MPMediaItemCollection *> *collections =
        query.collections;

    NSMutableArray<MPMediaPlaylist *> *playlists =
        [NSMutableArray array];

    for (
        MPMediaItemCollection *collection
        in collections
    ) {
        if (
            [collection
                isKindOfClass:[MPMediaPlaylist class]]
        ) {
            [playlists
                addObject:(MPMediaPlaylist *)collection];
        }
    }

    return playlists;
}

static NSString *playlistName(
    MPMediaPlaylist *playlist
) {
    NSString *name =
        [playlist
            valueForProperty:MPMediaPlaylistPropertyName];

    return name ?: @"";
}

static int listPlaylists(void) {
    if (requireMediaLibraryAuthorization() != 0) {
        return 1;
    }

    NSArray<MPMediaPlaylist *> *playlists =
        getPlaylists();

    if (playlists.count == 0) {
        fprintf(
            stderr,
            "Media-library access is authorized, but no "
            "playlists were returned.\n"
        );

        fprintf(
            stderr,
            "Make sure the playlist is added to the iPad's "
            "Apple Music library.\n"
        );

        return 1;
    }

    NSArray<MPMediaPlaylist *> *sorted =
        [playlists
            sortedArrayUsingComparator:
                ^NSComparisonResult(
                    MPMediaPlaylist *first,
                    MPMediaPlaylist *second
                ) {
                    return [
                        playlistName(first)
                        localizedCaseInsensitiveCompare:
                            playlistName(second)
                    ];
                }
        ];

    for (MPMediaPlaylist *playlist in sorted) {
        printf(
            "%s\t%lu tracks\n",
            playlistName(playlist).UTF8String,
            (unsigned long)playlist.items.count
        );
    }

    return 0;
}

static MPMediaPlaylist *findPlaylist(
    NSString *requestedName
) {
    for (
        MPMediaPlaylist *playlist
        in getPlaylists()
    ) {
        NSString *name =
            playlistName(playlist);

        if (
            [name
                caseInsensitiveCompare:requestedName]
            == NSOrderedSame
        ) {
            return playlist;
        }
    }

    return nil;
}


static void printJSONObject(id object) {
    if (![NSJSONSerialization isValidJSONObject:object]) {
        fprintf(stderr, "Could not encode JSON\n");
        return;
    }

    NSError *error = nil;

    NSData *data =
        [NSJSONSerialization
            dataWithJSONObject:object
            options:0
            error:&error];

    if (data == nil) {
        fprintf(
            stderr,
            "Could not encode JSON: %s\n",
            error.localizedDescription.UTF8String
        );
        return;
    }

    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
}

static NSString *safeMediaProperty(
    MPMediaItem *item,
    NSString *property
) {
    id value = [item valueForProperty:property];

    if ([value isKindOfClass:[NSString class]]) {
        return (NSString *)value;
    }

    return @"";
}

static NSString *const
RepeatPreferencesDomain =
    @"com.joel.mediactl-repeat";


static NSUserDefaults *
repeatPreferences(void) {
    return [
        [NSUserDefaults alloc]
        initWithSuiteName:
            RepeatPreferencesDomain
    ];
}


static NSString *normalizedRepeatMode(
    NSString *mode
) {
    if ([mode isEqualToString:@"all"]) {
        return @"all";
    }

    if ([mode isEqualToString:@"one"]) {
        return @"one";
    }

    return @"off";
}


static NSString *savedRepeatMode(void) {
    NSString *mode = [
        repeatPreferences()
        stringForKey:@"mode"
    ];

    return normalizedRepeatMode(mode);
}


static MPMusicRepeatMode musicRepeatMode(
    NSString *mode
) {
    mode = normalizedRepeatMode(mode);

    if ([mode isEqualToString:@"all"]) {
        return MPMusicRepeatModeAll;
    }

    if ([mode isEqualToString:@"one"]) {
        return MPMusicRepeatModeOne;
    }

    return MPMusicRepeatModeNone;
}


static BOOL saveRepeatMode(
    NSString *mode
) {
    NSUserDefaults *preferences =
        repeatPreferences();

    [preferences
        setObject:normalizedRepeatMode(mode)
        forKey:@"mode"];

    return [preferences synchronize];
}


static int applyRepeatMode(
    NSString *mode
) {
    NSString *normalized =
        normalizedRepeatMode(mode);

    MPMusicPlayerController *player =
        [MPMusicPlayerController
            systemMusicPlayer];

    player.repeatMode =
        musicRepeatMode(normalized);

    if (!saveRepeatMode(normalized)) {
        fprintf(
            stderr,
            "Could not save repeat mode\n"
        );
        return 1;
    }

    /*
     * Return the mode that was requested and saved. Reading repeatMode
     * back immediately from a new command-line process can return
     * MPMusicRepeatModeDefault even after the system player accepted it.
     */
    printJSONObject(@{
        @"mode": normalized
    });

    return 0;
}


static int printRepeatModeJSON(void) {
    printJSONObject(@{
        @"mode": savedRepeatMode()
    });

    return 0;
}


static int cycleRepeatMode(void) {
    NSString *current =
        savedRepeatMode();
    NSString *next = @"all";

    if ([current isEqualToString:@"all"]) {
        next = @"one";
    } else if (
        [current isEqualToString:@"one"]
    ) {
        next = @"off";
    }

    return applyRepeatMode(next);
}


static int printNowPlayingJSON(void) {
    MPMusicPlayerController *player =
        [MPMusicPlayerController systemMusicPlayer];

    MPMediaItem *item =
        player.nowPlayingItem;

    if (item == nil) {
        printJSONObject(@{
            @"available": @NO,
            @"playing": @NO,
            @"title": @"",
            @"artist": @"",
            @"album": @"",
            @"id": @"",
            @"currentTime": @0,
            @"duration": @0
        });

        return 0;
    }

    NSNumber *persistentID =
        [item valueForProperty:
            MPMediaItemPropertyPersistentID];

    NSString *identifier =
        persistentID != nil
            ? persistentID.stringValue
            : @"";

    BOOL playing =
        player.playbackState ==
        MPMusicPlaybackStatePlaying;

    NSNumber *durationValue =
        [item valueForProperty:
            MPMediaItemPropertyPlaybackDuration];

    NSTimeInterval duration =
        durationValue != nil
            ? durationValue.doubleValue
            : 0.0;

    NSTimeInterval currentTime =
        player.currentPlaybackTime;

    if (
        !isfinite(currentTime) ||
        currentTime < 0
    ) {
        currentTime = 0;
    }

    if (
        !isfinite(duration) ||
        duration < 0
    ) {
        duration = 0;
    }

    printJSONObject(@{
        @"available": @YES,
        @"playing": @(playing),
        @"title":
            safeMediaProperty(
                item,
                MPMediaItemPropertyTitle
            ),
        @"artist":
            safeMediaProperty(
                item,
                MPMediaItemPropertyArtist
            ),
        @"album":
            safeMediaProperty(
                item,
                MPMediaItemPropertyAlbumTitle
            ),
        @"id": identifier,
        @"currentTime": @(currentTime),
        @"duration": @(duration)
    });

    return 0;
}

static int printPlaylistsJSON(void) {
    if (requireMediaLibraryAuthorization() != 0) {
        return 1;
    }

    NSArray<MPMediaPlaylist *> *playlists =
        getPlaylists();

    NSArray<MPMediaPlaylist *> *sorted =
        [playlists
            sortedArrayUsingComparator:
                ^NSComparisonResult(
                    MPMediaPlaylist *first,
                    MPMediaPlaylist *second
                ) {
                    return [
                        playlistName(first)
                        localizedCaseInsensitiveCompare:
                            playlistName(second)
                    ];
                }
        ];

    NSMutableArray *result =
        [NSMutableArray array];

    for (MPMediaPlaylist *playlist in sorted) {
        [result addObject:@{
            @"name": playlistName(playlist),
            @"count": @(playlist.items.count)
        }];
    }

    printJSONObject(@{
        @"playlists": result
    });

    return 0;
}

static int printPlaylistSongsJSON(
    NSString *requestedName
) {
    if (requireMediaLibraryAuthorization() != 0) {
        return 1;
    }

    MPMediaPlaylist *playlist =
        findPlaylist(requestedName);

    if (playlist == nil) {
        fprintf(
            stderr,
            "Playlist not found: %s\n",
            requestedName.UTF8String
        );

        return 1;
    }

    NSMutableArray *songs =
        [NSMutableArray array];

    for (MPMediaItem *item in playlist.items) {
        NSNumber *persistentID =
            [item valueForProperty:
                MPMediaItemPropertyPersistentID];

        NSString *identifier =
            persistentID != nil
                ? persistentID.stringValue
                : @"";

        if (identifier.length == 0) {
            continue;
        }

        [songs addObject:@{
            @"id": identifier,
            @"title":
                safeMediaProperty(
                    item,
                    MPMediaItemPropertyTitle
                ),
            @"artist":
                safeMediaProperty(
                    item,
                    MPMediaItemPropertyArtist
                ),
            @"album":
                safeMediaProperty(
                    item,
                    MPMediaItemPropertyAlbumTitle
                )
        }];
    }

    printJSONObject(@{
        @"name": playlistName(playlist),
        @"songs": songs
    });

    return 0;
}

static int playSingleSong(
    NSString *requestedName,
    unsigned long long requestedID
) {
    if (requireMediaLibraryAuthorization() != 0) {
        return 1;
    }

    MPMediaPlaylist *playlist =
        findPlaylist(requestedName);

    if (playlist == nil) {
        fprintf(
            stderr,
            "Playlist not found: %s\n",
            requestedName.UTF8String
        );

        return 1;
    }

    MPMediaItem *matchedItem = nil;

    for (MPMediaItem *item in playlist.items) {
        NSNumber *persistentID =
            [item valueForProperty:
                MPMediaItemPropertyPersistentID];

        if (
            persistentID != nil &&
            persistentID.unsignedLongLongValue ==
                requestedID
        ) {
            matchedItem = item;
            break;
        }
    }

    if (matchedItem == nil) {
        fprintf(
            stderr,
            "Song was not found in playlist: %s\n",
            requestedName.UTF8String
        );

        return 1;
    }

    MPMediaItemCollection *singleItemQueue =
        [[MPMediaItemCollection alloc]
            initWithItems:@[matchedItem]];

    MPMusicPlayerController *player =
        [MPMusicPlayerController systemMusicPlayer];

    [player stop];

    player.shuffleMode =
        MPMusicShuffleModeOff;

    if (
        requestShuffleEnabled(
            NO,
            NO
        ) != 0
    ) {
        return 1;
    }

    [player setQueueWithItemCollection:
        singleItemQueue];
    [player prepareToPlay];
    [player play];

    MPMusicRepeatMode repeatMode =
        musicRepeatMode(
            savedRepeatMode()
        );

    player.repeatMode = repeatMode;
    usleep(150000);
    player.repeatMode = repeatMode;

    printf(
        "Playing single song: %s\n",
        safeMediaProperty(
            matchedItem,
            MPMediaItemPropertyTitle
        ).UTF8String
    );

    return 0;
}

static NSString *const ShuffleRequestPath =
    @"/var/mobile/MediaCtlShuffle-request.plist";

static NSString *const ShuffleStatePath =
    @"/var/mobile/MediaCtlShuffle-state.plist";

static BOOL writeShuffleRequest(BOOL enabled) {
    return [@{
        @"enabled": @(enabled),
        @"updated": @(
            [[NSDate date] timeIntervalSince1970]
        )
    } writeToFile:ShuffleRequestPath atomically:YES];
}

static void notifySpringBoardShuffle(void) {
    CFNotificationCenterPostNotification(
        CFNotificationCenterGetDarwinNotifyCenter(),
        CFSTR(
            "com.joel.mediactl.shuffle-apply"
        ),
        NULL,
        NULL,
        true
    );
}

static NSDictionary *springBoardShuffleState(void) {
    NSDictionary *state = [NSDictionary
        dictionaryWithContentsOfFile:
            ShuffleStatePath];

    return [state isKindOfClass:[NSDictionary class]]
        ? state
        : nil;
}

static NSString *const
ShufflePreferencesDomain =
    @"com.joel.mediactl-shuffle";

static NSUserDefaults *shufflePreferences(void) {
    return [[NSUserDefaults alloc]
        initWithSuiteName:ShufflePreferencesDomain];
}

static BOOL savedShuffleEnabled(void) {
    return [shufflePreferences()
        boolForKey:@"enabled"];
}

static BOOL saveShuffleEnabled(BOOL enabled) {
    NSUserDefaults *preferences = shufflePreferences();
    [preferences setBool:enabled forKey:@"enabled"];
    return [preferences synchronize];
}

static BOOL currentPublishedShuffleEnabled(void) {
    NSDictionary *state =
        springBoardShuffleState();
    NSNumber *enabled =
        state[@"enabled"];

    if (enabled != nil) {
        return enabled.boolValue;
    }

    return savedShuffleEnabled();
}

static int printShuffleJSON(void) {
    BOOL enabled =
        currentPublishedShuffleEnabled();

    printJSONObject(@{
        @"enabled": @(enabled),
        @"mode": enabled ? @"songs" : @"off"
    });

    return 0;
}

static int requestShuffleEnabled(
    BOOL enabled,
    BOOL printResult
) {
    if (!writeShuffleRequest(enabled)) {
        fprintf(
            stderr,
            "Could not write shuffle request\n"
        );
        return 1;
    }

    if (!saveShuffleEnabled(enabled)) {
        fprintf(
            stderr,
            "Could not save shuffle preference\n"
        );
        return 1;
    }

    notifySpringBoardShuffle();

    if (printResult) {
        printJSONObject(@{
            @"enabled": @(enabled),
            @"mode": enabled ? @"songs" : @"off"
        });
    }

    return 0;
}

static int toggleShuffle(void) {
    return requestShuffleEnabled(
        !currentPublishedShuffleEnabled(),
        YES
    );
}


static int playPlaylist(
    NSString *requestedName,
    BOOL shuffled
) {
    if (requireMediaLibraryAuthorization() != 0) {
        return 1;
    }

    MPMediaPlaylist *playlist =
        findPlaylist(requestedName);

    if (playlist == nil) {
        fprintf(
            stderr,
            "Playlist not found: %s\n",
            requestedName.UTF8String
        );

        fprintf(
            stderr,
            "Run 'mediactl playlists' to list exact names.\n"
        );

        return 1;
    }

    if (playlist.items.count == 0) {
        fprintf(
            stderr,
            "Playlist contains no available tracks: %s\n",
            requestedName.UTF8String
        );

        return 1;
    }

    MPMusicPlayerController *player =
        [MPMusicPlayerController systemMusicPlayer];

    [player stop];

    player.shuffleMode =
        shuffled
            ? MPMusicShuffleModeSongs
            : MPMusicShuffleModeOff;

    if (
        requestShuffleEnabled(
            shuffled,
            NO
        ) != 0
    ) {
        return 1;
    }

    [player setQueueWithItemCollection:playlist];
    [player prepareToPlay];
    [player play];

    MPMusicRepeatMode repeatMode =
        musicRepeatMode(
            savedRepeatMode()
        );

    player.repeatMode = repeatMode;
    usleep(150000);
    player.repeatMode = repeatMode;

    printf(
        "Playing playlist: %s\n",
        playlistName(playlist).UTF8String
    );

    return 0;
}

static BOOL parsePersistentID(
    const char *value,
    unsigned long long *result
) {
    if (value == NULL || result == NULL) {
        return NO;
    }

    char *endPointer = NULL;
    errno = 0;

    unsigned long long identifier =
        strtoull(
            value,
            &endPointer,
            10
        );

    if (
        errno == ERANGE ||
        endPointer == value ||
        *endPointer != '\0' ||
        identifier == 0
    ) {
        return NO;
    }

    *result = identifier;
    return YES;
}


static BOOL parseFiniteDouble(
    const char *value,
    double *result
) {
    if (value == NULL || result == NULL) {
        return NO;
    }

    char *endPointer = NULL;
    errno = 0;

    double parsed =
        strtod(
            value,
            &endPointer
        );

    if (
        errno == ERANGE ||
        endPointer == value ||
        *endPointer != '\0' ||
        !isfinite(parsed)
    ) {
        return NO;
    }

    *result = parsed;
    return YES;
}


static NSString *stringArgument(
    const char *value
) {
    if (value == NULL) {
        return nil;
    }

    return [
        NSString
        stringWithUTF8String:
            value
    ];
}


static NSString *joinArguments(
    int argc,
    char *argv[],
    int startingAt
) {
    NSMutableArray<NSString *> *parts =
        [NSMutableArray array];

    for (
        int index = startingAt;
        index < argc;
        index++
    ) {
        NSString *part =
            [NSString
                stringWithUTF8String:argv[index]];

        if (part != nil) {
            [parts addObject:part];
        }
    }

    return [parts componentsJoinedByString:@" "];
}


static NSString *const
AirPlayPreferencesDomain =
    @"com.joel.mediactl-airplay";


static NSString *const
InitialDefaultAirPlayUID =
    @"07b32858-19ad-447c-"
    @"898c-13d7f0ea07fe";


static NSString *const
InitialDefaultAirPlayName =
    @"rt4817";


static NSUserDefaults *
airPlayPreferences(void) {
    return [
        [NSUserDefaults alloc]
        initWithSuiteName:
            AirPlayPreferencesDomain
    ];
}


static BOOL validAirPlayIdentifier(
    NSString *uid
) {
    if (
        uid == nil ||
        uid.length == 0
    ) {
        return NO;
    }

    NSData *utf8 =
        [uid dataUsingEncoding:
            NSUTF8StringEncoding];

    if (
        utf8 == nil ||
        utf8.length == 0 ||
        utf8.length > 4096
    ) {
        return NO;
    }

    return YES;
}


static NSString *
defaultAirPlayUID(void) {
    NSString *uid =
        [
            airPlayPreferences()
            stringForKey:
                @"defaultUID"
        ];

    if (!validAirPlayIdentifier(uid)) {
        return InitialDefaultAirPlayUID;
    }

    return uid;
}


static NSString *
defaultAirPlayName(void) {
    NSString *name =
        [
            airPlayPreferences()
            stringForKey:
                @"defaultName"
        ];

    if (name.length == 0) {
        return InitialDefaultAirPlayName;
    }

    return name;
}


static int printAirPlayDevicesJSON(void) {
    NSUserDefaults *preferences =
        airPlayPreferences();

    NSArray *storedDevices =
        [preferences
            arrayForKey:
                @"devices"];

    if (storedDevices == nil) {
        storedDevices = @[];
    }

    NSString *defaultUID =
        defaultAirPlayUID();

    NSMutableArray *devices =
        [NSMutableArray array];

    for (
        NSDictionary *stored
        in storedDevices
    ) {
        if (
            ![stored
                isKindOfClass:
                    [NSDictionary class]]
        ) {
            continue;
        }

        NSString *uid =
            stored[@"uid"];

        NSString *name =
            stored[@"name"];

        if (
            !validAirPlayIdentifier(uid) ||
            name.length == 0
        ) {
            continue;
        }

        [devices addObject:@{
            @"name":
                name,

            @"uid":
                uid,

            @"connectable":
                @YES,

            @"default":
                @(
                    [uid
                        isEqualToString:
                            defaultUID]
                )
        }];
    }

    printJSONObject(@{
        @"devices":
            devices,
        @"default": @{
            @"name":
                defaultAirPlayName(),
            @"uid":
                defaultUID
        }
    });

    return 0;
}


static int setDefaultAirPlayDevice(
    NSString *uid,
    NSString *name
) {
    if (!validAirPlayIdentifier(uid)) {
        fprintf(
            stderr,
            "Invalid AirPlay device UID\n"
        );

        return 2;
    }

    if (name.length == 0) {
        name = uid;
    }

    NSUserDefaults *preferences =
        airPlayPreferences();

    [preferences
        setObject:uid
        forKey:@"defaultUID"];

    [preferences
        setObject:name
        forKey:@"defaultName"];

    if (![preferences synchronize]) {
        fprintf(
            stderr,
            "Could not save AirPlay default\n"
        );

        return 1;
    }

    printJSONObject(@{
        @"name":
            name,
        @"uid":
            uid,
        @"default":
            @YES
    });

    return 0;
}


static NSData *encodeProtobufVarint(
    NSUInteger value
) {
    uint8_t bytes[10];
    NSUInteger count = 0;

    do {
        uint8_t byte =
            value & 0x7f;

        value >>= 7;

        if (value != 0) {
            byte |= 0x80;
        }

        bytes[count++] =
            byte;

    } while (
        value != 0 &&
        count < sizeof(bytes)
    );

    return [
        NSData
        dataWithBytes:
            bytes
        length:
            count
    ];
}


static BOOL decodeProtobufVarint(
    NSData *data,
    NSUInteger offset,
    NSUInteger *value,
    NSUInteger *encodedLength
) {
    if (
        data == nil ||
        offset >= data.length
    ) {
        return NO;
    }

    const uint8_t *bytes =
        data.bytes;

    NSUInteger result = 0;
    NSUInteger shift = 0;

    for (
        NSUInteger index = offset;
        index < data.length &&
        index < offset + 10;
        index++
    ) {
        uint8_t byte =
            bytes[index];

        result |=
            ((NSUInteger)(
                byte & 0x7f
            )) << shift;

        if (
            (byte & 0x80) == 0
        ) {
            if (value != NULL) {
                *value = result;
            }

            if (
                encodedLength != NULL
            ) {
                *encodedLength =
                    index - offset + 1;
            }

            return YES;
        }

        shift += 7;

        if (
            shift >=
            sizeof(NSUInteger) * 8
        ) {
            return NO;
        }
    }

    return NO;
}


static NSMutableData *
dataByReplacingUIDField(
    NSData *source,
    NSData *oldUID,
    NSData *newUID
) {
    if (
        source == nil ||
        oldUID == nil ||
        newUID == nil
    ) {
        return nil;
    }

    const uint8_t *bytes =
        source.bytes;

    for (
        NSUInteger offset = 0;
        offset < source.length;
        offset++
    ) {
        /*
         * Protobuf field number 3,
         * wire type 2:
         *
         * 0x1a <varint length> <UID bytes>
         */
        if (bytes[offset] != 0x1a) {
            continue;
        }

        NSUInteger oldLength = 0;
        NSUInteger oldLengthBytes = 0;

        if (
            !decodeProtobufVarint(
                source,
                offset + 1,
                &oldLength,
                &oldLengthBytes
            )
        ) {
            continue;
        }

        if (
            oldLength !=
            oldUID.length
        ) {
            continue;
        }

        NSUInteger valueOffset =
            offset +
            1 +
            oldLengthBytes;

        if (
            valueOffset >
            source.length ||
            oldLength >
            source.length -
                valueOffset
        ) {
            continue;
        }

        NSRange valueRange =
            NSMakeRange(
                valueOffset,
                oldLength
            );

        NSData *candidate =
            [source subdataWithRange:
                valueRange];

        if (
            ![candidate
                isEqualToData:
                    oldUID]
        ) {
            continue;
        }

        NSData *newLength =
            encodeProtobufVarint(
                newUID.length
            );

        NSMutableData *result =
            [NSMutableData data];

        [result appendData:
            [source subdataWithRange:
                NSMakeRange(
                    0,
                    offset + 1
                )
            ]
        ];

        [result appendData:
            newLength];

        [result appendData:
            newUID];

        NSUInteger suffixOffset =
            NSMaxRange(valueRange);

        if (
            suffixOffset <
            source.length
        ) {
            [result appendData:
                [source subdataWithRange:
                    NSMakeRange(
                        suffixOffset,
                        source.length -
                            suffixOffset
                    )
                ]
            ];
        }

        return result;
    }

    return nil;
}


static void replaceUIDDataRecursively(
    id object,
    NSData *oldUID,
    NSData *newUID,
    NSUInteger *replacementCount
) {
    if (
        object == nil ||
        replacementCount == NULL
    ) {
        return;
    }

    if (
        [object
            isKindOfClass:
                [NSMutableDictionary class]]
    ) {
        NSMutableDictionary *dictionary =
            object;

        NSArray *keys =
            dictionary.allKeys;

        for (id key in keys) {
            id value =
                dictionary[key];

            if (
                [value
                    isKindOfClass:
                        [NSData class]]
            ) {
                NSMutableData *replacement =
                    dataByReplacingUIDField(
                        value,
                        oldUID,
                        newUID
                    );

                if (replacement != nil) {
                    dictionary[key] =
                        replacement;

                    *replacementCount += 1;
                }

                continue;
            }

            replaceUIDDataRecursively(
                value,
                oldUID,
                newUID,
                replacementCount
            );
        }

        return;
    }

    if (
        [object
            isKindOfClass:
                [NSMutableArray class]]
    ) {
        NSMutableArray *array =
            object;

        for (
            NSUInteger index = 0;
            index < array.count;
            index++
        ) {
            id value =
                array[index];

            if (
                [value
                    isKindOfClass:
                        [NSData class]]
            ) {
                NSMutableData *replacement =
                    dataByReplacingUIDField(
                        value,
                        oldUID,
                        newUID
                    );

                if (replacement != nil) {
                    array[index] =
                        replacement;

                    *replacementCount += 1;
                }

                continue;
            }

            replaceUIDDataRecursively(
                value,
                oldUID,
                newUID,
                replacementCount
            );
        }

        return;
    }
}

static NSData *routePayloadForUID(
    NSString *uid,
    NSError **error
) {
    if (
        !validAirPlayIdentifier(uid)
    ) {
        if (error != NULL) {
            *error = [
                NSError
                errorWithDomain:
                    @"MediaCtlAirPlay"
                code:
                    1
                userInfo:@{
                    NSLocalizedDescriptionKey:
                        @"Invalid AirPlay "
                        @"device identifier"
                }
            ];
        }

        return nil;
    }

    NSData *template =
        [NSData
            dataWithBytes:
                kAirPlayRouteTemplatePayload
            length:
                kAirPlayRouteTemplatePayloadLength];

    NSError *parseError = nil;

    NSPropertyListFormat format =
        NSPropertyListBinaryFormat_v1_0;

    id archive =
        [NSPropertyListSerialization
            propertyListWithData:
                template
            options:
                NSPropertyListMutableContainersAndLeaves
            format:
                &format
            error:
                &parseError];

    if (archive == nil) {
        if (error != NULL) {
            *error =
                parseError
                ?: [
                    NSError
                    errorWithDomain:
                        @"MediaCtlAirPlay"
                    code:
                        2
                    userInfo:@{
                        NSLocalizedDescriptionKey:
                            @"Could not parse "
                            @"AirPlay request template"
                    }
                ];
        }

        return nil;
    }

    NSData *oldUID =
        [InitialDefaultAirPlayUID
            dataUsingEncoding:
                NSUTF8StringEncoding];

    NSData *newUID =
        [uid
            dataUsingEncoding:
                NSUTF8StringEncoding];

    NSUInteger replacementCount = 0;

    replaceUIDDataRecursively(
        archive,
        oldUID,
        newUID,
        &replacementCount
    );

    if (replacementCount != 1) {
        if (error != NULL) {
            NSString *message =
                [
                    NSString
                    stringWithFormat:
                        @"Expected one AirPlay UID "
                        @"field, found %lu",
                        (unsigned long)
                            replacementCount
                ];

            *error = [
                NSError
                errorWithDomain:
                    @"MediaCtlAirPlay"
                code:
                    3
                userInfo:@{
                    NSLocalizedDescriptionKey:
                        message
                }
            ];
        }

        return nil;
    }

    NSError *serializationError = nil;

    NSData *payload =
        [NSPropertyListSerialization
            dataWithPropertyList:
                archive
            format:
                NSPropertyListBinaryFormat_v1_0
            options:
                0
            error:
                &serializationError];

    if (payload == nil) {
        if (error != NULL) {
            *error =
                serializationError
                ?: [
                    NSError
                    errorWithDomain:
                        @"MediaCtlAirPlay"
                    code:
                        4
                    userInfo:@{
                        NSLocalizedDescriptionKey:
                            @"Could not serialize "
                            @"AirPlay request"
                    }
                ];
        }

        return nil;
    }

    return payload;
}


static int sendAirPlayPayload(
    NSData *payload,
    NSString *name,
    NSString *uid,
    BOOL connected
) {
    if (payload == nil || payload.length == 0) {
        fprintf(stderr, "AirPlay payload is empty\n");
        return 1;
    }

    const char serviceName[] =
        "com.apple.mediaremoted.xpc";
    const char contextUID[] =
        "577E1BCA-2D9B-41C2-"
        "A8F8-C515CE8072D4";
    const uint64_t messageID =
        216172782113783848ULL;

    NSString *customID =
        NSUUID.UUID.UUIDString.uppercaseString;
    dispatch_queue_t queue =
        dispatch_get_global_queue(
            QOS_CLASS_USER_INITIATED,
            0
        );
    xpc_connection_t connection =
        xpc_connection_create_mach_service(
            serviceName,
            queue,
            0
        );
    if (connection == NULL) {
        fprintf(stderr, "Could not connect to mediaremoted.\n");
        return 1;
    }

    xpc_connection_set_event_handler(
        connection,
        ^(__unused xpc_object_t event) {
        }
    );
    xpc_connection_resume(connection);

    xpc_object_t message =
        xpc_dictionary_create(NULL, NULL, 0);
    if (message == NULL) {
        fprintf(stderr, "Could not create the AirPlay request.\n");
        return 1;
    }

    xpc_dictionary_set_data(
        message,
        "MRXPC_CONTEXT_MODIFICATION_DATA_KEY",
        payload.bytes,
        payload.length
    );
    xpc_dictionary_set_string(
        message,
        "MRXPC_ROUTING_CONTEXT_UID_KEY",
        contextUID
    );
    xpc_dictionary_set_uint64(
        message,
        "MRXPC_MESSAGE_ID_KEY",
        messageID
    );
    xpc_dictionary_set_string(
        message,
        "MRXPC_MESSAGE_CUSTOM_ID_KEY",
        customID.UTF8String
    );

    /*
     * Routing requests can apply successfully while the synchronous
     * reply path never returns. Queue the validated native request and
     * return immediately so mediactl cannot wedge the web server.
     */
    xpc_connection_send_message(
        connection,
        message
    );

    printJSONObject(@{
        @"name": name ?: @"",
        @"uid": uid ?: @"",
        @"connected": @(connected)
    });
    return 0;
}

static int sendAirPlayRouteRequest(
    NSString *uid,
    NSString *name
) {
    NSError *payloadError = nil;
    NSData *payload =
        routePayloadForUID(uid, &payloadError);
    if (payload == nil) {
        fprintf(
            stderr,
            "%s\n",
            payloadError.localizedDescription.UTF8String
        );
        return 1;
    }

    return sendAirPlayPayload(
        payload,
        name.length > 0 ? name : uid,
        uid,
        YES
    );
}

static int disconnectAirPlay(void) {
    NSData *payload = [NSData
        dataWithBytes:kIPadSpeakerModificationPayload
        length:kIPadSpeakerModificationPayloadLength];

    return sendAirPlayPayload(
        payload,
        @"Speaker",
        @"local-speaker",
        NO
    );
}

static int connectDefaultAirPlayDevice(void) {
    return sendAirPlayRouteRequest(
        defaultAirPlayUID(),
        defaultAirPlayName()
    );
}


static int runExecutable(
    const char *executable,
    char *const arguments[]
) {
    pid_t processID = 0;

    int result =
        posix_spawn(
            &processID,
            executable,
            NULL,
            NULL,
            arguments,
            environ
        );

    if (result != 0) {
        fprintf(
            stderr,
            "Could not run %s: %s\n",
            executable,
            strerror(result)
        );

        return result;
    }

    int status = 0;

    if (
        waitpid(
            processID,
            &status,
            0
        ) < 0
    ) {
        perror("waitpid");
        return 1;
    }

    if (
        !WIFEXITED(status)
    ) {
        return 1;
    }

    return WEXITSTATUS(status);
}


static int restartMusicInstance(void) {
    char *killArguments[] = {
        "killall",
        "-9",
        "Music",
        "MusicUIService",
        NULL
    };

    int killResult =
        runExecutable(
            "/usr/bin/killall",
            killArguments
        );

    if (killResult != 0) {
        killResult =
            runExecutable(
                "/var/jb/usr/bin/killall",
                killArguments
            );
    }

    if (killResult != 0) {
        fprintf(
            stderr,
            "Could not stop Music or "
            "MusicUIService.\n"
        );

        return 1;
    }

    usleep(700000);

    char *openArguments[] = {
        "uiopen",
        "music://",
        NULL
    };

    int openResult =
        runExecutable(
            "/usr/bin/uiopen",
            openArguments
        );

    if (openResult != 0) {
        openResult =
            runExecutable(
                "/var/jb/usr/bin/uiopen",
                openArguments
            );
    }

    if (openResult != 0) {
        fprintf(
            stderr,
            "Music was killed but could "
            "not be reopened.\n"
        );

        return 1;
    }

    printf(
        "Music and MusicUIService "
        "restarted\n"
    );

    return 0;
}


static int seekToPlaybackTime(
    NSTimeInterval requestedTime
) {
    if (
        !isfinite(requestedTime) ||
        requestedTime < 0
    ) {
        fprintf(
            stderr,
            "Invalid playback time\n"
        );

        return 2;
    }

    MPMusicPlayerController *player =
        [MPMusicPlayerController
            systemMusicPlayer];

    MPMediaItem *item =
        player.nowPlayingItem;

    if (item == nil) {
        fprintf(
            stderr,
            "Nothing is currently playing\n"
        );

        return 1;
    }

    NSNumber *durationValue =
        [item valueForProperty:
            MPMediaItemPropertyPlaybackDuration];

    NSTimeInterval duration =
        durationValue != nil
            ? durationValue.doubleValue
            : 0.0;

    NSTimeInterval target =
        requestedTime;

    if (
        isfinite(duration) &&
        duration > 0 &&
        target > duration
    ) {
        target = duration;
    }

    player.currentPlaybackTime =
        target;

    printJSONObject(@{
        @"currentTime": @(target),
        @"duration": @(
            duration > 0
                ? duration
                : 0
        )
    });

    return 0;
}


static NSString *const
VolumePreferencesDomain =
    @"com.joel.mediactl-volume";

static NSString *const
SystemVolumeCategory =
    @"Audio/Video";


static NSUserDefaults *
volumePreferences(void) {
    return [
        [NSUserDefaults alloc]
        initWithSuiteName:
            VolumePreferencesDomain
    ];
}


static BOOL volumeLockedAtMaximum(void) {
    NSUserDefaults *preferences =
        volumePreferences();

    /*
     * New installs and missing preferences start unlocked.
     */
    if (
        [preferences
            objectForKey:
                @"lockAtMaximum"]
        == nil
    ) {
        return NO;
    }

    return [
        preferences
        boolForKey:
            @"lockAtMaximum"
    ];
}


static void saveKnownSystemVolume(
    double volume
) {
    if (!isfinite(volume)) {
        return;
    }

    NSUserDefaults *preferences =
        volumePreferences();
    [preferences
        setDouble:fmax(0.0, fmin(1.0, volume))
        forKey:@"lastKnownSystemVolume"];
    [preferences synchronize];
}

static double lastKnownSystemVolume(void) {
    NSUserDefaults *preferences =
        volumePreferences();
    if ([preferences objectForKey:@"lastKnownSystemVolume"] == nil) {
        return NAN;
    }
    double volume =
        [preferences doubleForKey:@"lastKnownSystemVolume"];
    return isfinite(volume)
        ? fmax(0.0, fmin(1.0, volume))
        : NAN;
}

static double audioSessionOutputVolume(void) {
    const char *frameworkPath =
        "/System/Library/Frameworks/"
        "AVFAudio.framework/AVFAudio";

    void *framework =
        dlopen(frameworkPath, RTLD_LAZY | RTLD_LOCAL);

    if (framework == NULL) {
        frameworkPath =
            "/System/Library/Frameworks/"
            "AVFoundation.framework/AVFoundation";

        framework =
            dlopen(frameworkPath, RTLD_LAZY | RTLD_LOCAL);
    }

    Class sessionClass =
        NSClassFromString(@"AVAudioSession");

    if (sessionClass == Nil) {
        if (framework != NULL) {
            dlclose(framework);
        }
        return NAN;
    }

    SEL sharedSelector =
        NSSelectorFromString(@"sharedInstance");
    SEL volumeSelector =
        NSSelectorFromString(@"outputVolume");

    if (
        ![sessionClass respondsToSelector:sharedSelector]
    ) {
        if (framework != NULL) {
            dlclose(framework);
        }
        return NAN;
    }

    id session =
        ((id (*)(id, SEL))objc_msgSend)(
            sessionClass,
            sharedSelector
        );

    if (
        session == nil ||
        ![session respondsToSelector:volumeSelector]
    ) {
        if (framework != NULL) {
            dlclose(framework);
        }
        return NAN;
    }

    float outputVolume =
        ((float (*)(id, SEL))objc_msgSend)(
            session,
            volumeSelector
        );

    if (framework != NULL) {
        dlclose(framework);
    }

    if (
        !isfinite(outputVolume) ||
        outputVolume < 0.0f ||
        outputVolume > 1.0f
    ) {
        return NAN;
    }

    return outputVolume;
}


static double springBoardSystemVolume(void) {
    NSDictionary *state = [NSDictionary
        dictionaryWithContentsOfFile:
            @"/var/mobile/MediaCtlSystemVolume.plist"];

    NSNumber *value = state[@"volume"];
    if (value == nil) {
        return NAN;
    }

    double volume = value.doubleValue;
    if (!isfinite(volume) || volume < 0.0 || volume > 1.0) {
        return NAN;
    }

    return volume;
}


static double currentSystemVolume(void) {
    double springBoardVolume =
        springBoardSystemVolume();

    if (isfinite(springBoardVolume)) {
        saveKnownSystemVolume(springBoardVolume);
        return springBoardVolume;
    }

    /*
     * AVAudioSession.outputVolume is the authoritative system-output
     * volume exposed by iPadOS. It changes with the hardware buttons,
     * Control Center, and successful writes from this tool.
     */
    double volume =
        audioSessionOutputVolume();

    if (isfinite(volume)) {
        volume = fmax(0.0, fmin(1.0, volume));
        saveKnownSystemVolume(volume);
        return volume;
    }

    /*
     * Keep AVSystemController only as a fallback. Some iPadOS versions
     * return a stale 1.0 from getVolume:forCategory:, which is why it is
     * no longer the primary reader.
     */
    Class controllerClass =
        NSClassFromString(@"AVSystemController");

    if (
        controllerClass != Nil &&
        [controllerClass respondsToSelector:
            @selector(sharedAVSystemController)]
    ) {
        AVSystemController *controller =
            [controllerClass sharedAVSystemController];

        if (controller != nil) {
            float queriedVolume = 0.0f;

            if (
                [controller respondsToSelector:
                    @selector(getVolume:forCategory:)] &&
                [controller
                    getVolume:&queriedVolume
                    forCategory:SystemVolumeCategory] &&
                isfinite(queriedVolume) &&
                queriedVolume >= 0.0f &&
                queriedVolume <= 1.0f
            ) {
                volume = queriedVolume;
                saveKnownSystemVolume(volume);
                return volume;
            }
        }
    }

    volume = lastKnownSystemVolume();

    if (isfinite(volume)) {
        return volume;
    }

    return 0.0;
}

static BOOL applySystemVolume(
    double requestedVolume
) {
    double target =
        fmax(0.0, fmin(1.0, requestedVolume));
    Class controllerClass =
        NSClassFromString(@"AVSystemController");
    if (
        controllerClass != Nil &&
        [controllerClass respondsToSelector:
            @selector(sharedAVSystemController)]
    ) {
        AVSystemController *controller =
            [controllerClass sharedAVSystemController];
        if (
            controller != nil &&
            [controller respondsToSelector:
                @selector(setVolumeTo:forCategory:)]
        ) {
            for (NSUInteger attempt = 0; attempt < 5; attempt++) {
                [controller
                    setVolumeTo:(float)target
                    forCategory:SystemVolumeCategory];
                saveKnownSystemVolume(target);
                usleep(60000);
                double observed = currentSystemVolume();
                if (fabs(observed - target) <= 0.03) {
                    saveKnownSystemVolume(observed);
                    return YES;
                }
            }
        }
    }

    MPMusicPlayerController *player =
        [MPMusicPlayerController systemMusicPlayer];
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
    player.volume = (float)target;
#pragma clang diagnostic pop
    saveKnownSystemVolume(target);
    usleep(100000);
    return YES;
}

static int printVolumeJSON(void) {
    double volume =
        currentSystemVolume();

    printJSONObject(@{
        @"volume":
            @(volume),

        @"percent":
            @(
                (NSInteger)llround(
                    volume * 100.0
                )
            ),

        @"locked":
            @(volumeLockedAtMaximum())
    });

    return 0;
}


static int setPlaybackVolume(
    double requestedVolume
) {
    if (
        !isfinite(requestedVolume) ||
        requestedVolume < 0.0 ||
        requestedVolume > 1.0
    ) {
        fprintf(
            stderr,
            "Volume must be between 0 and 1\n"
        );

        return 2;
    }

    BOOL locked =
        volumeLockedAtMaximum();

    if (!applySystemVolume(requestedVolume)) {
        fprintf(
            stderr,
            "Could not apply iPad system volume\n"
        );

        return 1;
    }

    double appliedVolume =
        currentSystemVolume();

    printJSONObject(@{
        @"volume":
            @(appliedVolume),

        @"percent":
            @(
                (NSInteger)llround(
                    appliedVolume * 100.0
                )
            ),

        @"locked":
            @(locked)
    });

    return 0;
}


static int setVolumeLock(
    BOOL locked
) {
    NSUserDefaults *preferences =
        volumePreferences();

    [preferences
        setBool:
            locked
        forKey:
            @"lockAtMaximum"];

    if (![preferences synchronize]) {
        fprintf(
            stderr,
            "Could not save 100%%-on-Play setting\n"
        );

        return 1;
    }

    double volume =
        currentSystemVolume();

    printJSONObject(@{
        @"volume":
            @(volume),

        @"percent":
            @(
                (NSInteger)llround(
                    volume * 100.0
                )
            ),

        @"locked":
            @(locked)
    });

    return 0;
}


static int resumeWithVolumePolicy(void) {
    MPMusicPlayerController *player =
        [MPMusicPlayerController
            systemMusicPlayer];

    BOOL locked =
        volumeLockedAtMaximum();

    if (
        locked &&
        !applySystemVolume(1.0)
    ) {
        fprintf(
            stderr,
            "Could not enforce 100%% system volume\n"
        );

        return 1;
    }

    [player play];

    printf(
        "%s\n",
        locked
            ? "Set system volume to 100% and resumed playback"
            : "Resumed playback without changing volume"
    );

    return 0;
}


static int showNativeAirPlayPicker(void) {
    CFNotificationCenterPostNotification(
        CFNotificationCenterGetDarwinNotifyCenter(),
        CFSTR(
            "com.joel.mediactl.airplay-show-picker"
        ),
        NULL,
        NULL,
        true
    );

    printJSONObject(@{
        @"ok":
            @YES,

        @"triggered":
            @YES
    });

    return 0;
}


static int showHomeScreen(void) {
    CFNotificationCenterPostNotification(
        CFNotificationCenterGetDarwinNotifyCenter(),
        CFSTR(
            "com.joel.mediactl.home-screen"
        ),
        NULL,
        NULL,
        true
    );

    printf(
        "SpringBoard Home Screen request sent\n"
    );

    return 0;
}


static int wakeScreen(void) {
    CFNotificationCenterPostNotification(
        CFNotificationCenterGetDarwinNotifyCenter(),
        CFSTR(
            "com.joel.mediactl.wake-screen"
        ),
        NULL,
        NULL,
        true
    );

    printf("SpringBoard wake request sent\n");
    return 0;
}


static int lockDeviceOnly(void) {
    CFNotificationCenterPostNotification(
        CFNotificationCenterGetDarwinNotifyCenter(),
        CFSTR(
            "com.joel.mediactl.lock-device"
        ),
        NULL,
        NULL,
        true
    );

    printf(
        "SpringBoard lock request sent\n"
    );

    return 0;
}

static int triggerMusicImportBridge(void) {
    CFNotificationCenterPostNotification(
        CFNotificationCenterGetDarwinNotifyCenter(),
        CFSTR(
            "com.joel.mediactl.music-import-request"
        ),
        NULL,
        NULL,
        true
    );

    printJSONObject(@{
        @"triggered": @YES
    });

    return 0;
}

int main(int argc, char *argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            printUsage();
            return 2;
        }

        NSString *argument =
            [NSString
                stringWithUTF8String:argv[1]];

        if (argument == nil) {
            fprintf(
                stderr,
                "Command is not valid UTF-8\n"
            );

            return 2;
        }

        if (
            [argument
                isEqualToString:@"authorization"]
        ) {
            MPMediaLibraryAuthorizationStatus status =
                [MPMediaLibrary authorizationStatus];

            printf(
                "%s\n",
                authorizationStatusName(status)
            );

            return 0;
        }

        if (
            [argument
                isEqualToString:@"authorize"]
        ) {
            return requestMediaLibraryAccess();
        }

        if (
            [argument
                isEqualToString:
                    @"music-import-trigger"]
        ) {
            return triggerMusicImportBridge();
        }

        if (
            [argument
                isEqualToString:@"repeat-json"]
        ) {
            return printRepeatModeJSON();
        }

        if (
            [argument
                isEqualToString:@"repeat-cycle"]
        ) {
            return cycleRepeatMode();
        }

        if (
            [argument
                isEqualToString:@"now-playing-json"]
        ) {
            return printNowPlayingJSON();
        }

        if (
            [argument
                isEqualToString:@"playlists-json"]
        ) {
            return printPlaylistsJSON();
        }

        if ([argument isEqualToString:@"songs-json"]) {
            if (requireMediaLibraryAuthorization() != 0) return 1;
            return MLCPrintAllSongsJSON();
        }

        if ([argument isEqualToString:@"song-play"] ||
            [argument isEqualToString:@"song-playlists-json"] ||
            [argument isEqualToString:@"song-add-to-playlist"]) {
            if (argc < 3) {
                fprintf(stderr, "Missing persistent ID\n");
                return 2;
            }
            unsigned long long requestedID = 0;

            if (
                !parsePersistentID(
                    argv[2],
                    &requestedID
                )
            ) {
                fprintf(
                    stderr,
                    "Invalid persistent ID\n"
                );
                return 2;
            }
            if (requireMediaLibraryAuthorization() != 0) return 1;
            if ([argument isEqualToString:@"song-play"]) {
                return MLCPlaySong(requestedID);
            }
            if ([argument isEqualToString:@"song-playlists-json"]) {
                return MLCPrintSongPlaylistsJSON(requestedID);
            }
            if (argc < 4) {
                fprintf(stderr, "Missing playlist name\n");
                return 2;
            }
            return MLCAddSongToPlaylist(requestedID, joinArguments(argc, argv, 3));
        }

        if (
            [argument
                isEqualToString:
                    @"song-remove-from-library"]
        ) {
            if (argc < 3) {
                fprintf(
                    stderr,
                    "Usage: mediactl "
                    "song-remove-from-library "
                    "<persistent-id>\n"
                );
                return 2;
            }

            unsigned long long requestedID = 0;

            if (
                !parsePersistentID(
                    argv[2],
                    &requestedID
                )
            ) {
                fprintf(
                    stderr,
                    "Invalid persistent ID\n"
                );
                return 2;
            }

            if (requireMediaLibraryAuthorization() != 0) {
                return 1;
            }

            return MLCRemoveSongFromLibrary(requestedID);
        }

        if (
            [argument
                isEqualToString:
                    @"song-remove-from-playlist"]
        ) {
            if (argc < 4) {
                fprintf(
                    stderr,
                    "Usage: mediactl "
                    "song-remove-from-playlist "
                    "<persistent-id> "
                    "\"Playlist Name\"\n"
                );
                return 2;
            }

            unsigned long long requestedID = 0;

            if (
                !parsePersistentID(
                    argv[2],
                    &requestedID
                )
            ) {
                fprintf(
                    stderr,
                    "Invalid persistent ID\n"
                );
                return 2;
            }

            if (
                requireMediaLibraryAuthorization()
                != 0
            ) {
                return 1;
            }

            return MLCRemoveSongFromPlaylist(
                requestedID,
                joinArguments(argc, argv, 3)
            );
        }

        if (
            [argument
                isEqualToString:@"playlist-songs-json"]
        ) {
            if (argc < 3) {
                fprintf(stderr, "Missing playlist name\n");
                return 2;
            }

            NSString *requestedName =
                joinArguments(argc, argv, 2);

            return printPlaylistSongsJSON(
                requestedName
            );
        }

        if (
            [argument
                isEqualToString:@"song"]
        ) {
            if (argc < 4) {
                fprintf(
                    stderr,
                    "Usage: mediactl song "
                    "<persistent-id> "
                    "\"Playlist Name\"\n"
                );

                return 2;
            }

            unsigned long long requestedID = 0;

            if (
                !parsePersistentID(
                    argv[2],
                    &requestedID
                )
            ) {
                fprintf(
                    stderr,
                    "Invalid persistent ID\n"
                );
                return 2;
            }

            NSString *requestedName =
                joinArguments(argc, argv, 3);

            return playSingleSong(
                requestedName,
                requestedID
            );
        }

        if (
            [argument
                isEqualToString:@"playlists"]
        ) {
            return listPlaylists();
        }

        if (
            [argument isEqualToString:@"shuffle-json"]
        ) {
            return printShuffleJSON();
        }

        if (
            [argument isEqualToString:@"shuffle-toggle"]
        ) {
            return toggleShuffle();
        }

        if (
            [argument isEqualToString:@"playlist-play"]
        ) {
            if (argc < 3) {
                fprintf(stderr, "Missing playlist name\n");
                return 2;
            }
            return playPlaylist(
                joinArguments(argc, argv, 2),
                NO
            );
        }

        if (
            [argument
                isEqualToString:@"playlist"]
        ) {
            if (argc < 3) {
                fprintf(
                    stderr,
                    "Missing playlist name\n"
                );

                printUsage();
                return 2;
            }

            NSString *requestedName =
                joinArguments(argc, argv, 2);

            return playPlaylist(requestedName, YES);
        }

        if (
            [argument
                isEqualToString:
                    @"volume-json"]
        ) {
            return printVolumeJSON();
        }

        if (
            [argument
                isEqualToString:
                    @"volume"]
        ) {
            if (argc < 3) {
                fprintf(
                    stderr,
                    "Usage: mediactl volume <0-1>\n"
                );

                return 2;
            }

            double requestedVolume = 0.0;

            if (
                !parseFiniteDouble(
                    argv[2],
                    &requestedVolume
                )
            ) {
                fprintf(
                    stderr,
                    "Invalid volume\n"
                );
                return 2;
            }

            return setPlaybackVolume(
                requestedVolume
            );
        }

        if (
            [argument
                isEqualToString:
                    @"volume-lock"]
        ) {
            if (argc < 3) {
                fprintf(
                    stderr,
                    "Usage: mediactl volume-lock "
                    "<on|off>\n"
                );

                return 2;
            }

            NSString *value =
                stringArgument(argv[2]);

            if (value == nil) {
                fprintf(
                    stderr,
                    "Value is not valid UTF-8\n"
                );
                return 2;
            }

            if (
                [value
                    isEqualToString:
                        @"on"]
            ) {
                return setVolumeLock(
                    YES
                );
            }

            if (
                [value
                    isEqualToString:
                        @"off"]
            ) {
                return setVolumeLock(
                    NO
                );
            }

            fprintf(
                stderr,
                "100%%-on-Play setting must be on or off\n"
            );

            return 2;
        }

        if (
            [argument
                isEqualToString:@"seek"]
        ) {
            if (argc < 3) {
                fprintf(
                    stderr,
                    "Usage: mediactl seek <seconds>\n"
                );

                return 2;
            }

            double requestedTime = 0.0;

            if (
                !parseFiniteDouble(
                    argv[2],
                    &requestedTime
                )
            ) {
                fprintf(
                    stderr,
                    "Invalid playback time\n"
                );
                return 2;
            }

            return seekToPlaybackTime(
                requestedTime
            );
        }

        if (
            [argument
                isEqualToString:@"resume"]
        ) {
            return resumeWithVolumePolicy();
        }

        if (
            [argument
                isEqualToString:
                    @"airplay-show-picker"]
        ) {
            return showNativeAirPlayPicker();
        }

        if (
            [argument
                isEqualToString:
                    @"airplay-devices-json"]
        ) {
            return printAirPlayDevicesJSON();
        }

        if (
            [argument
                isEqualToString:
                    @"airplay-connect"]
        ) {
            if (argc < 3) {
                fprintf(
                    stderr,
                    "Missing AirPlay device UID\n"
                );

                return 2;
            }

            NSString *uid =
                stringArgument(argv[2]);

            if (uid == nil) {
                fprintf(
                    stderr,
                    "AirPlay device UID is not valid UTF-8\n"
                );
                return 2;
            }

            NSString *name =
                argc >= 4
                    ? joinArguments(
                        argc,
                        argv,
                        3
                    )
                    : uid;

            return sendAirPlayRouteRequest(
                uid,
                name
            );
        }

        if (
            [argument
                isEqualToString:
                    @"airplay-set-default"]
        ) {
            if (argc < 3) {
                fprintf(
                    stderr,
                    "Missing AirPlay device UID\n"
                );

                return 2;
            }

            NSString *uid =
                stringArgument(argv[2]);

            if (uid == nil) {
                fprintf(
                    stderr,
                    "AirPlay device UID is not valid UTF-8\n"
                );
                return 2;
            }

            NSString *name =
                argc >= 4
                    ? joinArguments(
                        argc,
                        argv,
                        3
                    )
                    : uid;

            return setDefaultAirPlayDevice(
                uid,
                name
            );
        }

        if (
            [argument
                isEqualToString:
                    @"airplay-disconnect"]
        ) {
            return disconnectAirPlay();
        }
        if (
            [argument
                isEqualToString:
                    @"airplay-connect-default"]
        ) {
            return connectDefaultAirPlayDevice();
        }

        if (
            [argument
                isEqualToString:
                    @"restart-music"]
        ) {
            return restartMusicInstance();
        }

        if (
            [argument
                isEqualToString:@"toggle"]
        ) {
            return togglePlaybackAtFullVolume();
        }

        if (
            [argument
                isEqualToString:
                    @"home-screen"]
        ) {
            return showHomeScreen();
        }

        if (
            [argument
                isEqualToString:
                    @"wake-screen"]
        ) {
            return wakeScreen();
        }

        if (
            [argument
                isEqualToString:@"lock-device"]
        ) {
            return lockDeviceOnly();
        }

        if (
            [argument
                isEqualToString:
                    @"play"]
        ) {
            return resumeWithVolumePolicy();
        }

        NSDictionary<NSString *, NSNumber *> *commands = @{
            @"pause": @1,
            @"next": @4,
            @"previous": @5
        };

        NSNumber *command =
            commands[argument];

        if (command == nil) {
            fprintf(
                stderr,
                "Unknown command: %s\n",
                argv[1]
            );

            printUsage();
            return 2;
        }

        return sendMediaRemoteCommand(
            command.unsignedIntValue,
            argv[1]
        );
    }
}
