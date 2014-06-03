from gi.repository import TotemPlParser, Grl, GLib, Gio, GObject
from gi.repository import Tracker
from gnomemusic.grilo import grilo
from gnomemusic.query import Query

import os

from gnomemusic import log
import logging
logger = logging.getLogger(__name__)

try:
    tracker = Tracker.SparqlConnection.get(None)
except Exception as e:
    from sys import exit
    logger.error("Cannot connect to tracker, error '%s'\Exiting" % str(e))
    exit(1)


class Playlists(GObject.GObject):
    __gsignals__ = {
        'playlist-created': (GObject.SIGNAL_RUN_FIRST, None, (Grl.Media,)),
        'playlist-deleted': (GObject.SIGNAL_RUN_FIRST, None, (Grl.Media,)),
        'song-added-to-playlist': (
            GObject.SIGNAL_RUN_FIRST, None, (Grl.Media, Grl.Media)
        ),
        'song-removed-from-playlist': (
            GObject.SIGNAL_RUN_FIRST, None, (Grl.Media, Grl.Media)
        ),
    }
    instance = None

    @classmethod
    def get_default(self):
        if self.instance:
            return self.instance
        else:
            self.instance = Playlists()
        return self.instance

    @log
    def __init__(self):
        GObject.GObject.__init__(self)
        self.playlist_dir = os.path.join(GLib.get_user_data_dir(),
                                         'gnome-music',
                                         'playlists')

    @log
    def create_playlist(self, name):
        def get_callback(source, param, item, count, data, error):
            if item:
                self.emit('playlist-created', item)

        def query_callback(conn, res, data):
            cursor = conn.query_finish(res)
            if not cursor or not cursor.next():
                return
            playlist_id = cursor.get_integer(0)
            grilo.get_playlist_with_id(playlist_id, get_callback)

        def update_callback(conn, res, data):
            playlist_urn = conn.update_blank_finish(res)[0][0]['playlist']
            tracker.query_async(
                Query.get_playlist_with_urn(playlist_urn),
                None, query_callback, None
            )

        tracker.update_blank_async(
            Query.create_playlist(name), GLib.PRIORITY_DEFAULT,
            None, update_callback, None
        )

    @log
    def delete_playlist(self, item):
        def update_callback(conn, res, data):
            conn.update_finish(res)
            self.emit('playlist-deleted', item)

        tracker.update_async(
            Query.delete_playlist(item.get_id()), GLib.PRIORITY_DEFAULT,
            None, update_callback, None
        )

    @log
    def get_playlists(self):
        playlist_files = [pl_file for pl_file in os.listdir(self.playlist_dir)
                          if os.path.isfile(os.path.join(self.playlist_dir,
                                                         pl_file))]
        playlist_names = []
        for playlist_file in playlist_files:
            name, ext = os.path.splitext(playlist_file)
            if ext == '.pls':
                playlist_names.append(name)
        return playlist_names

    @log
    def add_to_playlist(self, playlist, items):
        def get_callback(source, param, item, count, data, error):
            if item:
                self.emit('song-added-to-playlist', playlist, item)

        def query_callback(conn, res, data):
            cursor = conn.query_finish(res)
            if not cursor or not cursor.next():
                return
            entry_id = cursor.get_integer(0)
            grilo.get_playlist_song_with_id(
                playlist.get_id(), entry_id, get_callback
            )

        def update_callback(conn, res, data):
            entry_urn = conn.update_blank_finish(res)[0][0]['entry']
            tracker.query_async(
                Query.get_playlist_song_with_urn(entry_urn),
                None, query_callback, None
            )

        for item in items:
            uri = item.get_url()
            if not uri:
                continue
            tracker.update_blank_async(
                Query.add_song_to_playlist(playlist.get_id(), uri),
                GLib.PRIORITY_DEFAULT,
                None, update_callback, None
            )

    @log
    def remove_from_playlist(self, playlist, items):
        def update_callback(conn, res, data):
            conn.update_finish(res)
            self.emit('song-removed-from-playlist', playlist, data)

        for item in items:
            tracker.update_async(
                Query.remove_song_from_playlist(
                    playlist.get_id(), item.get_id()
                ),
                GLib.PRIORITY_DEFAULT,
                None, update_callback, item
            )

    @log
    def get_path_to_playlist(self, playlist_name):
        return os.path.join(self.playlist_dir, "%s.pls" % playlist_name)

    @log
    def parse_playlist(self, playlist_name, callback):
        parser = TotemPlParser.Parser()
        parser.connect('entry-parsed', self._on_entry_parsed, callback)
        parser.parse_async(
            GLib.filename_to_uri(self.get_path_to_playlist(playlist_name), None),
            False, None, None, None
        )

    @log
    def _on_entry_parsed(self, parser, uri, metadata, data=None):
        filename = GLib.filename_from_uri(uri)[0]
        if filename and not os.path.isfile(filename):
            return

        grilo.get_media_from_uri(uri, data)
