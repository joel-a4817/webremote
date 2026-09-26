#import "MusicLibraryCommands.h"
#import <MediaPlayer/MediaPlayer.h>
#import <dispatch/dispatch.h>
#import <unistd.h>

@interface MPMediaLibrary (MediaCtlPrivateLibraryRemoval)
- (BOOL)deleteItems:(NSArray *)items;
- (void)getPlaylistWithUUID:(NSUUID *)uuid
    creationMetadata:(MPMediaPlaylistCreationMetadata *)metadata
    completionHandler:(void (^)(MPMediaPlaylist *, NSError *))completion;
- (BOOL)removePlaylist:(MPMediaPlaylist *)playlist;
- (MPMediaPlaylist *)addPlaylistWithName:(NSString *)name;
@end
static void MLCPrintJSON(id object) {
    if (![NSJSONSerialization isValidJSONObject:object]) {
        fprintf(stderr, "Could not encode JSON\n");
        return;
    }
    NSError *error = nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:object options:0 error:&error];
    if (data == nil) {
        fprintf(stderr, "Could not encode JSON: %s\n", error.localizedDescription.UTF8String);
        return;
    }
    fwrite(data.bytes, 1, data.length, stdout);
    fputc('\n', stdout);
}

static NSString *MLCString(MPMediaItem *item, NSString *property) {
    id value = [item valueForProperty:property];
    return [value isKindOfClass:[NSString class]] ? value : @"";
}

static NSString *MLCPlaylistName(MPMediaPlaylist *playlist) {
    id value = [playlist valueForProperty:MPMediaPlaylistPropertyName];
    return [value isKindOfClass:[NSString class]] ? value : @"";
}

static NSArray<MPMediaPlaylist *> *MLCPlaylists(void) {
    NSMutableArray *result = [NSMutableArray array];
    for (MPMediaItemCollection *collection in [MPMediaQuery playlistsQuery].collections ?: @[]) {
        if ([collection isKindOfClass:[MPMediaPlaylist class]]) {
            [result addObject:(MPMediaPlaylist *)collection];
        }
    }
    return result;
}

static MPMediaPlaylist *MLCFindPlaylist(NSString *requestedName) {
    for (MPMediaPlaylist *playlist in MLCPlaylists()) {
        if ([MLCPlaylistName(playlist) caseInsensitiveCompare:requestedName] == NSOrderedSame) {
            return playlist;
        }
    }
    return nil;
}

static MPMediaItem *MLCFindSong(unsigned long long requestedID) {
    MPMediaPropertyPredicate *predicate = [MPMediaPropertyPredicate
        predicateWithValue:@(requestedID)
        forProperty:MPMediaItemPropertyPersistentID];
    MPMediaQuery *query = [[MPMediaQuery alloc] initWithFilterPredicates:[NSSet setWithObject:predicate]];
    for (MPMediaItem *item in query.items ?: @[]) {
        NSNumber *identifier = [item valueForProperty:MPMediaItemPropertyPersistentID];
        if (identifier != nil && identifier.unsignedLongLongValue == requestedID) {
            return item;
        }
    }
    return nil;
}

static NSDictionary *MLCSongObject(MPMediaItem *item) {
    NSNumber *identifier = [item valueForProperty:MPMediaItemPropertyPersistentID];
    return @{
        @"id": identifier != nil ? identifier.stringValue : @"",
        @"title": MLCString(item, MPMediaItemPropertyTitle),
        @"artist": MLCString(item, MPMediaItemPropertyArtist),
        @"album": MLCString(item, MPMediaItemPropertyAlbumTitle)
    };
}

int MLCPrintAllSongsJSON(void) {
    NSArray<MPMediaItem *> *items = [MPMediaQuery songsQuery].items ?: @[];
    NSArray *sorted = [items sortedArrayUsingComparator:^NSComparisonResult(MPMediaItem *a, MPMediaItem *b) {
        NSComparisonResult title = [MLCString(a, MPMediaItemPropertyTitle)
            localizedCaseInsensitiveCompare:MLCString(b, MPMediaItemPropertyTitle)];
        if (title != NSOrderedSame) return title;
        return [MLCString(a, MPMediaItemPropertyArtist)
            localizedCaseInsensitiveCompare:MLCString(b, MPMediaItemPropertyArtist)];
    }];
    NSMutableArray *songs = [NSMutableArray arrayWithCapacity:sorted.count];
    for (MPMediaItem *item in sorted) {
        NSNumber *identifier = [item valueForProperty:MPMediaItemPropertyPersistentID];
        if (identifier != nil && identifier.unsignedLongLongValue != 0) {
            [songs addObject:MLCSongObject(item)];
        }
    }
    MLCPrintJSON(@{@"songs": songs});
    return 0;
}

int MLCPlaySong(unsigned long long persistentID) {
    MPMediaItem *item = MLCFindSong(persistentID);
    if (item == nil) {
        fprintf(stderr, "Song not found\n");
        return 1;
    }
    MPMediaItemCollection *queue = [[MPMediaItemCollection alloc] initWithItems:@[item]];
    MPMusicPlayerController *player = [MPMusicPlayerController systemMusicPlayer];
    [player stop];
    player.shuffleMode = MPMusicShuffleModeOff;
    [player setQueueWithItemCollection:queue];
    [player prepareToPlay];
    [player play];
    MLCPrintJSON(@{@"id": @(persistentID).stringValue, @"playing": @YES});
    return 0;
}

int MLCPrintSongPlaylistsJSON(unsigned long long persistentID) {
    if (MLCFindSong(persistentID) == nil) {
        fprintf(stderr, "Song not found\n");
        return 1;
    }
    NSMutableArray *memberships = [NSMutableArray array];
    for (MPMediaPlaylist *playlist in MLCPlaylists()) {
        BOOL included = NO;
        for (MPMediaItem *item in playlist.items ?: @[]) {
            NSNumber *identifier = [item valueForProperty:MPMediaItemPropertyPersistentID];
            if (identifier != nil && identifier.unsignedLongLongValue == persistentID) {
                included = YES;
                break;
            }
        }
        [memberships addObject:@{
            @"name": MLCPlaylistName(playlist),
            @"included": @(included)
        }];
    }
    MLCPrintJSON(@{@"id": @(persistentID).stringValue, @"playlists": memberships});
    return 0;
}

int MLCAddSongToPlaylist(unsigned long long persistentID, NSString *playlistName) {
    MPMediaItem *item = MLCFindSong(persistentID);
    if (item == nil) {
        fprintf(stderr, "Song not found\n");
        return 1;
    }
    MPMediaPlaylist *playlist = MLCFindPlaylist(playlistName);
    if (playlist == nil) {
        fprintf(stderr, "Playlist not found: %s\n", playlistName.UTF8String);
        return 1;
    }
    for (MPMediaItem *existing in playlist.items ?: @[]) {
        NSNumber *identifier = [existing valueForProperty:MPMediaItemPropertyPersistentID];
        if (identifier != nil && identifier.unsignedLongLongValue == persistentID) {
            MLCPrintJSON(@{@"id": @(persistentID).stringValue, @"playlist": MLCPlaylistName(playlist), @"included": @YES, @"changed": @NO});
            return 0;
        }
    }
    dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
    __block NSError *operationError = nil;
    [playlist addMediaItems:@[item] completionHandler:^(NSError *error) {
        operationError = error;
        dispatch_semaphore_signal(semaphore);
    }];
    if (dispatch_semaphore_wait(semaphore, dispatch_time(DISPATCH_TIME_NOW, 30 * NSEC_PER_SEC)) != 0) {
        fprintf(stderr, "Timed out adding song to playlist\n");
        return 1;
    }
    if (operationError != nil) {
        fprintf(stderr, "%s\n", operationError.localizedDescription.UTF8String);
        return 1;
    }
    MLCPrintJSON(@{@"id": @(persistentID).stringValue, @"playlist": MLCPlaylistName(playlist), @"included": @YES, @"changed": @YES});
    return 0;
}


static BOOL MLCValidPlaylistName(
    NSString *playlistName
) {
    return (
        [playlistName isKindOfClass:[NSString class]] &&
        [playlistName
            stringByTrimmingCharactersInSet:
                NSCharacterSet
                    .whitespaceAndNewlineCharacterSet]
            .length > 0
    );
}


int MLCCreatePlaylist(
    NSString *playlistName
) {
    if (!MLCValidPlaylistName(playlistName)) {
        fprintf(
            stderr,
            "Invalid playlist name\n"
        );
        return 2;
    }

    playlistName = [
        playlistName
        stringByTrimmingCharactersInSet:
            NSCharacterSet
                .whitespaceAndNewlineCharacterSet
    ];

    MPMediaPlaylist *existing =
        MLCFindPlaylist(
            playlistName
        );

    if (existing != nil) {
        MLCPrintJSON(@{
            @"name":
                MLCPlaylistName(existing),
            @"created": @NO,
            @"changed": @NO
        });
        return 0;
    }

    MPMediaLibrary *library = [
        MPMediaLibrary
        defaultMediaLibrary
    ];

    SEL selector =
        @selector(addPlaylistWithName:);

    if (
        library == nil ||
        ![library
            respondsToSelector:
                selector]
    ) {
        fprintf(
            stderr,
            "Playlist creation selector "
            "is unavailable\n"
        );
        return 1;
    }

    /*
     * Runtime-verified on this iPadOS build:
     *
     * addPlaylistWithName:
     * type encoding @24@0:8@16
     *
     * The method synchronously returns an Objective-C
     * playlist object and takes one NSString argument.
     */
    MPMediaPlaylist *createdPlaylist = [
        library
        addPlaylistWithName:
            playlistName
    ];

    if (createdPlaylist == nil) {
        /*
         * The database may still have accepted the operation.
         * Perform a short, bounded verification before failing.
         */
        for (
            NSUInteger attempt = 0;
            attempt < 30;
            attempt++
        ) {
            createdPlaylist =
                MLCFindPlaylist(
                    playlistName
                );

            if (createdPlaylist != nil) {
                break;
            }

            usleep(100000);
        }
    }

    if (createdPlaylist == nil) {
        fprintf(
            stderr,
            "Apple Music rejected "
            "the playlist creation\n"
        );
        return 1;
    }

    MLCPrintJSON(@{
        @"name":
            MLCPlaylistName(
                createdPlaylist
            ),
        @"created": @YES,
        @"changed": @YES
    });

    return 0;
}



static BOOL MLCCopyPlaylistItems(MPMediaPlaylist *source, MPMediaPlaylist *destination, NSError **error) {
    NSArray *items = source.items ?: @[];
    if (items.count == 0) return YES;
    dispatch_semaphore_t semaphore = dispatch_semaphore_create(0);
    __block NSError *operationError = nil;
    [destination addMediaItems:items completionHandler:^(NSError *value) { operationError = value; dispatch_semaphore_signal(semaphore); }];
    if (dispatch_semaphore_wait(semaphore, dispatch_time(DISPATCH_TIME_NOW, 60 * NSEC_PER_SEC)) != 0) {
        if (error) *error = [NSError errorWithDomain:@"MediaCtlPlaylist" code:1 userInfo:@{NSLocalizedDescriptionKey:@"Timed out copying playlist songs"}];
        return NO;
    }
    if (operationError != nil) { if (error) *error = operationError; return NO; }
    return YES;
}
static MPMediaPlaylist *MLCCreateAndVerifyPlaylist(MPMediaLibrary *library, NSString *name) {
    MPMediaPlaylist *playlist = [library addPlaylistWithName:name];
    if (playlist != nil) return playlist;
    for (NSUInteger attempt = 0; attempt < 30; attempt++) { usleep(100000); playlist = MLCFindPlaylist(name); if (playlist != nil) return playlist; }
    return nil;
}
int MLCRenamePlaylist(NSString *oldName, NSString *newName) {
    if (!MLCValidPlaylistName(oldName) || !MLCValidPlaylistName(newName)) { fprintf(stderr, "Invalid playlist name\n"); return 2; }
    NSCharacterSet *whitespace = NSCharacterSet.whitespaceAndNewlineCharacterSet;
    oldName = [oldName stringByTrimmingCharactersInSet:whitespace];
    newName = [newName stringByTrimmingCharactersInSet:whitespace];
    MPMediaPlaylist *source = MLCFindPlaylist(oldName);
    if (source == nil) { fprintf(stderr, "Playlist not found: %s\n", oldName.UTF8String); return 1; }
    if ([oldName isEqualToString:newName]) { MLCPrintJSON(@{@"oldName":oldName,@"name":MLCPlaylistName(source),@"renamed":@YES,@"changed":@NO}); return 0; }
    BOOL caseOnlyRename = [oldName caseInsensitiveCompare:newName] == NSOrderedSame;
    if (!caseOnlyRename && MLCFindPlaylist(newName) != nil) { fprintf(stderr, "A playlist named %s already exists\n", newName.UTF8String); return 1; }
    MPMediaLibrary *library = [MPMediaLibrary defaultMediaLibrary];
    if (library == nil || ![library respondsToSelector:@selector(addPlaylistWithName:)] || ![library respondsToSelector:@selector(removePlaylist:)]) { fprintf(stderr, "Playlist editing selectors are unavailable\n"); return 1; }
    NSString *workingName = caseOnlyRename ? [NSString stringWithFormat:@"MediaCtl Rename %@", NSUUID.UUID.UUIDString] : newName;
    MPMediaPlaylist *working = MLCCreateAndVerifyPlaylist(library, workingName);
    if (working == nil) { fprintf(stderr, "Apple Music rejected the replacement playlist creation\n"); return 1; }
    NSError *copyError = nil;
    if (!MLCCopyPlaylistItems(source, working, &copyError)) { [library removePlaylist:working]; fprintf(stderr, "%s\n", copyError.localizedDescription.UTF8String); return 1; }
    if (![library removePlaylist:source]) { [library removePlaylist:working]; fprintf(stderr, "Apple Music rejected removal of the old playlist\n"); return 1; }
    if (caseOnlyRename) {
        for (NSUInteger attempt = 0; attempt < 50 && MLCFindPlaylist(oldName) != nil; attempt++) usleep(100000);
        MPMediaPlaylist *finalPlaylist = MLCCreateAndVerifyPlaylist(library, newName);
        if (finalPlaylist == nil) { fprintf(stderr, "Apple Music rejected the final playlist name\n"); return 1; }
        copyError = nil;
        if (!MLCCopyPlaylistItems(working, finalPlaylist, &copyError)) { [library removePlaylist:finalPlaylist]; fprintf(stderr, "%s\n", copyError.localizedDescription.UTF8String); return 1; }
        if (![library removePlaylist:working]) { fprintf(stderr, "The playlist was renamed, but temporary cleanup failed\n"); return 1; }
    }
    for (NSUInteger attempt = 0; attempt < 60; attempt++) {
        usleep(100000);
        MPMediaPlaylist *visibleNew = MLCFindPlaylist(newName);
        MPMediaPlaylist *visibleOld = MLCFindPlaylist(oldName);
        if (visibleNew != nil && (caseOnlyRename || visibleOld == nil)) { MLCPrintJSON(@{@"oldName":oldName,@"name":MLCPlaylistName(visibleNew),@"renamed":@YES,@"changed":@YES,@"count":@(visibleNew.items.count)}); return 0; }
    }
    fprintf(stderr, "Playlist rename was submitted but could not be verified\n"); return 1;
}

int MLCRemovePlaylist(
    NSString *playlistName
) {
    if (!MLCValidPlaylistName(playlistName)) {
        fprintf(
            stderr,
            "Invalid playlist name\n"
        );
        return 2;
    }

    playlistName = [
        playlistName
        stringByTrimmingCharactersInSet:
            NSCharacterSet
                .whitespaceAndNewlineCharacterSet
    ];

    MPMediaPlaylist *playlist =
        MLCFindPlaylist(
            playlistName
        );

    if (playlist == nil) {
        MLCPrintJSON(@{
            @"name": playlistName,
            @"removed": @YES,
            @"changed": @NO,
            @"songsPreserved": @YES
        });
        return 0;
    }

    MPMediaLibrary *library =
        [MPMediaLibrary
            defaultMediaLibrary];

    SEL selector =
        @selector(removePlaylist:);

    if (
        library == nil ||
        ![library
            respondsToSelector:
                selector]
    ) {
        fprintf(
            stderr,
            "Playlist removal selector "
            "is unavailable\n"
        );
        return 1;
    }

    /*
     * Runtime-verified on this iPadOS build:
     *
     * removePlaylist:
     * type encoding B24@0:8@16
     *
     * Therefore the method returns BOOL and accepts
     * one Objective-C object argument.
     */
    BOOL submitted =
        [library
            removePlaylist:
                playlist];

    if (!submitted) {
        fprintf(
            stderr,
            "Apple Music rejected "
            "the playlist removal\n"
        );
        return 1;
    }

    /*
     * Removing the playlist object does not call
     * deleteItems:, so its songs remain in the library.
     * Re-query until the asynchronous database update
     * becomes visible.
     */
    for (
        NSUInteger attempt = 0;
        attempt < 50;
        attempt++
    ) {
        usleep(100000);

        if (
            MLCFindPlaylist(
                playlistName
            ) == nil
        ) {
            MLCPrintJSON(@{
                @"name": playlistName,
                @"removed": @YES,
                @"changed": @YES,
                @"songsPreserved": @YES
            });
            return 0;
        }
    }

    fprintf(
        stderr,
        "Playlist removal was accepted, "
        "but the playlist still appears\n"
    );

    return 1;
}


int MLCRemoveSongFromLibrary(unsigned long long persistentID) {
    MPMediaItem *item = MLCFindSong(persistentID);
    if (item == nil) {
        MLCPrintJSON(@{
            @"id": @(persistentID).stringValue,
            @"removed": @YES,
            @"changed": @NO
        });
        return 0;
    }

    BOOL submitted = [[MPMediaLibrary defaultMediaLibrary]
        deleteItems:@[item]];

    if (!submitted) {
        fprintf(stderr, "Apple Music rejected the library removal\n");
        return 1;
    }

    for (NSUInteger attempt = 0; attempt < 80; attempt++) {
        usleep(100000);

        if (MLCFindSong(persistentID) == nil) {
            MLCPrintJSON(@{
                @"id": @(persistentID).stringValue,
                @"removed": @YES,
                @"changed": @YES
            });
            return 0;
        }
    }

    fprintf(stderr, "Removal was submitted, but the song still appears in Apple Music\n");
    return 1;
}
