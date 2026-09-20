#import <Foundation/Foundation.h>
#import <MediaPlayer/MediaPlayer.h>
#import <dispatch/dispatch.h>
#import <dlfcn.h>
/*
 * The Theos SDK does not ship xpc/xpc.h.
 * Declare only the libxpc interfaces used here.
 */
typedef void *xpc_object_t;
typedef xpc_object_t xpc_connection_t;

struct _xpc_type_s;
typedef const struct _xpc_type_s *xpc_type_t;

typedef void (^xpc_handler_t)(
    xpc_object_t object
);

extern const struct _xpc_type_s
    _xpc_type_error;

#define XPC_TYPE_ERROR \
    ((xpc_type_t)&_xpc_type_error)

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

extern xpc_object_t
xpc_connection_send_message_with_reply_sync(
    xpc_connection_t connection,
    xpc_object_t message
);

extern xpc_type_t
xpc_get_type(
    xpc_object_t object
);

extern char *
xpc_copy_description(
    xpc_object_t object
);
#import <spawn.h>
#import <string.h>
#import <sys/wait.h>
#import <unistd.h>

#import "rt4817_request.h"

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
        "  mediactl playlist-songs-json \"Playlist Name\"\n"
        "  mediactl song <persistent-id> \"Playlist Name\"\n"
        "  mediactl now-playing-json\n"
        "  mediactl airplay-rt4817\n"
        "  mediactl restart-music\n"
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
        ^(CFArrayRef result) {
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
            @"id": @""
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
        @"id": identifier
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

    player.repeatMode =
        MPMusicRepeatModeNone;

    [player setQueueWithItemCollection:singleItemQueue];
    [player prepareToPlay];
    [player play];

    printf(
        "Playing single song: %s\n",
        safeMediaProperty(
            matchedItem,
            MPMediaItemPropertyTitle
        ).UTF8String
    );

    return 0;
}

static int playPlaylist(
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
        MPMusicShuffleModeSongs;

    player.repeatMode =
        MPMusicRepeatModeNone;

    [player setQueueWithItemCollection:playlist];
    [player prepareToPlay];
    [player play];

    printf(
        "Playing shuffled playlist with repeat disabled: %s\n",
        playlistName(playlist).UTF8String
    );

    return 0;
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


static int sendRt4817RouteRequest(void) {
    const char serviceName[] =
        "com.apple.mediaremoted.xpc";

    const char contextUID[] =
        "577E1BCA-2D9B-41C2-"
        "A8F8-C515CE8072D4";

    const uint64_t messageID =
        216172782113783848ULL;

    NSString *customID =
        NSUUID.UUID.UUIDString
            .uppercaseString;

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
        fprintf(
            stderr,
            "Could not connect to "
            "mediaremoted.\n"
        );

        return 1;
    }

    xpc_connection_set_event_handler(
        connection,
        ^(xpc_object_t event) {
        }
    );

    xpc_connection_resume(
        connection
    );

    xpc_object_t message =
        xpc_dictionary_create(
            NULL,
            NULL,
            0
        );

    if (message == NULL) {
        fprintf(
            stderr,
            "Could not create the "
            "AirPlay request.\n"
        );

        return 1;
    }

    xpc_dictionary_set_data(
        message,
        "MRXPC_CONTEXT_MODIFICATION_DATA_KEY",
        kRt4817ModificationPayload,
        kRt4817ModificationPayloadLength
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

    xpc_object_t reply =
        xpc_connection_send_message_with_reply_sync(
            connection,
            message
        );

    if (reply == NULL) {
        fprintf(
            stderr,
            "mediaremoted returned no reply.\n"
        );

        return 1;
    }

    if (
        xpc_get_type(reply)
        == XPC_TYPE_ERROR
    ) {
        char *description =
            xpc_copy_description(
                reply
            );

        fprintf(
            stderr,
            "mediaremoted rejected "
            "the request: %s\n",
            description != NULL
                ? description
                : "unknown XPC error"
        );

        if (
            description != NULL
        ) {
            free(description);
        }

        return 1;
    }

    char *description =
        xpc_copy_description(
            reply
        );

    printf(
        "AirPlay request sent "
        "to rt4817\n"
    );

    printf(
        "Context: %s\n",
        contextUID
    );

    printf(
        "Device UID: "
        "07b32858-19ad-447c-898c-"
        "13d7f0ea07fe\n"
    );

    printf(
        "Custom ID: %s\n",
        customID.UTF8String
    );

    if (
        description != NULL
    ) {
        printf(
            "Reply: %s\n",
            description
        );

        free(description);
    }

    return 0;
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
        runExecutable(
            "/var/jb/usr/bin/killall",
            killArguments
        );
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


int main(int argc, char *argv[]) {
    @autoreleasepool {
        if (argc < 2) {
            printUsage();
            return 2;
        }

        NSString *argument =
            [NSString
                stringWithUTF8String:argv[1]];

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

        if (
            [argument
                isEqualToString:@"playlist-songs-json"]
        ) {
            if (argc < 3) {
                fprintf(stderr, "Missing playlist name\\n");
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

            unsigned long long requestedID =
                strtoull(argv[2], NULL, 10);

            if (requestedID == 0) {
                fprintf(
                    stderr,
                    "Invalid persistent ID\\n"
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

            return playPlaylist(requestedName);
        }

        if (
            [argument
                isEqualToString:
                    @"airplay-rt4817"]
        ) {
            return sendRt4817RouteRequest();
        }

        if (
            [argument
                isEqualToString:
                    @"restart-music"]
        ) {
            return restartMusicInstance();
        }

        NSDictionary<NSString *, NSNumber *> *commands = @{
            @"play": @0,
            @"pause": @1,
            @"toggle": @2,
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
