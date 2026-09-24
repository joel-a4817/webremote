#import <Foundation/Foundation.h>

int MLCPrintAllSongsJSON(void);
int MLCPlaySong(unsigned long long persistentID);
int MLCPrintSongPlaylistsJSON(unsigned long long persistentID);
int MLCAddSongToPlaylist(unsigned long long persistentID, NSString *playlistName);
int MLCCreatePlaylist(NSString *playlistName);
int MLCRemovePlaylist(NSString *playlistName);
int MLCRemoveSongFromLibrary(unsigned long long persistentID);
