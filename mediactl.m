#import <Foundation/Foundation.h>
#import <MediaPlayer/MediaPlayer.h>
#import <dispatch/dispatch.h>
#import <dlfcn.h>

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
