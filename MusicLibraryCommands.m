#import "MusicLibraryCommands.h"
#import <MediaPlayer/MediaPlayer.h>
#import <dispatch/dispatch.h>
#import <unistd.h>

@interface MPMediaLibrary (MediaCtlPrivateLibraryRemoval)
- (BOOL)deleteItems:(NSArray *)items;
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
