#import "MusicPlaylistRemoval.h"
#import <MediaPlayer/MediaPlayer.h>
#import <unistd.h>

@interface MPMediaPlaylist (MediaCtlPrivateRemoval)
- (void)removeItems:(NSArray *)items
    atFilteredIndexes:(NSIndexSet *)indexes
    completionBlock:(id)completion;
@end


static void MPRPrintJSON(
    id object
) {
    if (
        ![NSJSONSerialization
            isValidJSONObject:object]
    ) {
        fprintf(
            stderr,
            "Could not encode JSON\n"
        );
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

    fwrite(
        data.bytes,
        1,
        data.length,
        stdout
    );

    fputc('\n', stdout);
    fflush(stdout);
}


static NSString *MPRPlaylistName(
    MPMediaPlaylist *playlist
) {
    id value =
        [playlist
            valueForProperty:
                MPMediaPlaylistPropertyName];

    if (
        [value
            isKindOfClass:
                [NSString class]]
    ) {
        return value;
    }

    return @"";
}


static MPMediaPlaylist *MPRFindPlaylist(
    NSString *requestedName
) {
    NSArray *collections =
        [MPMediaQuery
            playlistsQuery]
            .collections;

    for (
        MPMediaItemCollection *collection
        in collections ?: @[]
    ) {
        if (
            ![collection
                isKindOfClass:
                    [MPMediaPlaylist class]]
        ) {
            continue;
        }

        MPMediaPlaylist *playlist =
            (MPMediaPlaylist *)collection;

        if (
            [MPRPlaylistName(playlist)
                caseInsensitiveCompare:
                    requestedName]
            == NSOrderedSame
        ) {
            return playlist;
        }
    }

    return nil;
}


static BOOL MPRPlaylistContainsSong(
    MPMediaPlaylist *playlist,
    unsigned long long persistentID
) {
    for (
        MPMediaItem *item
        in playlist.items ?: @[]
    ) {
        NSNumber *identifier =
            [item
                valueForProperty:
                    MPMediaItemPropertyPersistentID];

        if (
            identifier != nil &&
            identifier.unsignedLongLongValue
                == persistentID
        ) {
            return YES;
        }
    }

    return NO;
}


static NSIndexSet *MPRIndexesForSong(
    MPMediaPlaylist *playlist,
    unsigned long long persistentID
) {
    NSMutableIndexSet *indexes =
        [NSMutableIndexSet indexSet];

    NSArray *items =
        playlist.items ?: @[];

    [items
        enumerateObjectsUsingBlock:^(
            MPMediaItem *item,
            NSUInteger index,
            BOOL *stop
        ) {
            NSNumber *identifier =
                [item
                    valueForProperty:
                        MPMediaItemPropertyPersistentID];

            if (
                identifier != nil &&
                identifier
                    .unsignedLongLongValue
                    == persistentID
            ) {
                [indexes addIndex:index];
            }
        }
    ];

    return indexes;
}


int MLCRemoveSongFromPlaylist(
    unsigned long long persistentID,
    NSString *playlistName
) {
    MPMediaPlaylist *playlist =
        MPRFindPlaylist(
            playlistName
        );

    if (playlist == nil) {
        fprintf(
            stderr,
            "Playlist not found: %s\n",
            playlistName.UTF8String
        );

        return 1;
    }

    SEL selector =
        NSSelectorFromString(
            @"removeItems:"
            @"atFilteredIndexes:"
            @"completionBlock:"
        );

    if (
        ![playlist
            respondsToSelector:selector]
    ) {
        fprintf(
            stderr,
            "Playlist removal selector "
            "is unavailable\n"
        );

        return 1;
    }

    NSIndexSet *indexes =
        MPRIndexesForSong(
            playlist,
            persistentID
        );

    if (indexes.count == 0) {
        MPRPrintJSON(@{
            @"id":
                @(persistentID).stringValue,

            @"playlist":
                MPRPlaylistName(playlist),

            @"included":
                @NO,

            @"changed":
                @NO,

            @"removedIndexes":
                @0
        });

        return 0;
    }

    NSUInteger removedCount =
        indexes.count;

    /*
     * Verified against Music on this iPadOS build:
     *
     * removeItems:@[]
     * atFilteredIndexes:<playlist item indexes>
     * completionBlock:<block>
     *
     * We intentionally use nil for the completion block.
     * The previous callback declaration did not match the
     * private method's actual callback contract. The removal
     * succeeded, but mediactl produced no response afterward.
     */
    [playlist
        removeItems:@[]
        atFilteredIndexes:indexes
        completionBlock:nil];

    /*
     * Media-library mutation is asynchronous. Re-query the
     * playlist until the song disappears instead of relying
     * on an unverified private completion-block signature.
     */
    for (
        NSUInteger attempt = 0;
        attempt < 40;
        attempt++
    ) {
        usleep(100000);

        MPMediaPlaylist *refreshed =
            MPRFindPlaylist(
                playlistName
            );

        if (
            refreshed == nil ||
            !MPRPlaylistContainsSong(
                refreshed,
                persistentID
            )
        ) {
            MPRPrintJSON(@{
                @"id":
                    @(persistentID).stringValue,

                @"playlist":
                    MPRPlaylistName(playlist),

                @"included":
                    @NO,

                @"changed":
                    @YES,

                @"removedIndexes":
                    @(removedCount)
            });

            return 0;
        }
    }

    fprintf(
        stderr,
        "Removal was submitted, but the song "
        "still appears in the playlist\n"
    );

    return 1;
}
