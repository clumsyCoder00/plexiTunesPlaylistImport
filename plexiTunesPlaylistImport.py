#!/usr/bin/env python3
# coding=utf-8

# modified xml file export from user artv's post at: http://forums.slimdevices.com/showthread.php?35608-iTunes-playlist-script
# modified plex playlist import from JonnyWong16 at: https://gist.github.com/JonnyWong16/2607abf0e3431b6f133861bbe1bb694e
# refered to plexapi search functions in test script at: https://github.com/pkkid/python-plexapi/blob/master/tests/test_audio.py

# Plex API References
# lots of plex scripts: https://gist.github.com/JonnyWong16
# http://python-plexapi.readthedocs.io/en/latest/ # python PlexAPI Reference
# http://pydoc.net/PlexAPI/1.1.0/examples.examples/ # examples
# https://www.snip2code.com/Snippet/1684516/Create-a-Plex-Playlist-with-what-was-air # creating a playlist
#
# Install notes
#   - Dependencies:
#       python3
#           plexapi
#           xmltodict
#
#   - install under user cron at:
#       sudo crontab -e -u user
#       - enter: */5 * * * * '/home/user/Documents/iTunestoPlex.py' # to check for xml changes every 5 mins
#
# Usage
#   - Plex will take the liberty of correcting characters from common as in 'Celine Dion' to 'Céline Dion', breaking matches.
#   - Sometimes with ID3 tag versions below 2.3, Plex adds trailing '/////' characters in the whitespace of metadata. Updating to 2.3 in itunes (File>Convert>Convert ID3 Tags...) fixes the characters.
#   - Plex automattically parses files with dashes in them assuming artist - album - track format.
#       - Breaks an album named 'On The Radio - Single', assuming the artist name is 'On The Radio' and the album is 'Single'
#   - Some tracks in the iTunes music library are not stored in the 'Music' folder, and won't be found.
#       - ex. Voice Recordings
#   - Plex automatically trims trailing spaces from artists, albums and tracks. Question marks are trimmed.
#   - Scanned 5000 tracks in around 14:30
#
# todo
#   x all checks for returned artist,album & track names should be .tolower() before comparison (ex. Alt-J tracks in iTunes are stored under alt-J artist)
#   x better feedback when searching directly for album. Was the track found?
#   x search through all albums returned when searching all albums (ex. greatest hits)
#   x set artist,album,trackFound at beginning of process
#   x clean up print to file calls, maybe make a function
#   x clean up script flow move definitions to one end, main program/variable sets to the other?
#   x clean up cron call, check to see if it runs in root cron: It does not
#   x check for shelf file, make one and populate it if empty
#   - do time comparison of restructured search, may be more improvements to flow to be made
#       - 7.3.2017 - 2:36
#   - place ini, log files in folder of script automatically, so that relative paths can be used
#   - cannot find may erlewine albums through artist
#   - add sync for playlist deletion from iTunes through list of valid playlists stored in ini file
#       - if playlist previously synced was in itunes, but is no longer, delete playlist from plex

import time
import datetime
import os
import string
import xml.etree.cElementTree as ET
import urllib
import shelve

# ---- plex stuff ----
PLEX_URL = 'http://localhost:32400'
PLEX_TOKEN = 'secret token'
USERS = ['User 1','User 2']  # List of users to sync the playlists to

import requests
import xmltodict
from plexapi.server import PlexServer
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# ---- plex stuff ----

itunesxml = '/mnt/pond/media/iTunes Media/iTunes/iTunes Library.xml'
logPath = "/home/nuthanael/Documents/iTunestoPlex.log"
setIni = "/home/nuthanael/Documents/iTunestoPlex.ini"

# --- if shelf doesnt exist?
if not os.path.exists(setIni):
    shelf=shelve.open(setIni)
    timeLastRun=time.time()
    shelf["timeLastRun"] = timeLastRun
    shelf.sync() # Save
else:
    shelf=shelve.open(setIni)
    timeLastRun = shelf["timeLastRun"]
    xmlTimeModified=os.path.getmtime(itunesxml)
    timeNow=time.time()

############ PLEX DEFINITIONS ########################
def fetch_plex_api(path='', method='GET', plextv=False, **kwargs):
    """Fetches data from the Plex API"""

    url = 'https://plex.tv' if plextv else PLEX_URL.rstrip('/')

    headers = {'X-Plex-Token': PLEX_TOKEN,
               'Accept': 'application/json'}

    params = {}
    if kwargs:
        params.update(kwargs)

    try:
        if method.upper() == 'GET':
            r = requests.get(url + path,
                             headers=headers, params=params, verify=False)
        elif method.upper() == 'POST':
            r = requests.post(url + path,
                              headers=headers, params=params, verify=False)
        elif method.upper() == 'PUT':
            r = requests.put(url + path,
                             headers=headers, params=params, verify=False)
        elif method.upper() == 'DELETE':
            r = requests.delete(url + path,
                                headers=headers, params=params, verify=False)
        else:
            print("Invalid request method provided: {method}".format(method=method))
            return

        if r and len(r.content):
            if 'application/json' in r.headers['Content-Type']:
                return r.json()
            elif 'application/xml' in r.headers['Content-Type']:
                return xmltodict.parse(r.content)
            else:
                return r.content
        else:
            return r.content

    except Exception as e:
        print("Error fetching from Plex API: {err}".format(err=e))

def get_user_tokens(server_id):
    api_users = fetch_plex_api('/api/users', plextv=True)
    api_shared_servers = fetch_plex_api('/api/servers/{server_id}/shared_servers'.format(server_id=server_id), plextv=True)
    user_ids = {user['@id']: user.get('@username', user.get('@title')) for user in api_users['MediaContainer']['User']}
    users = {user_ids[user['@userID']]: user['@accessToken'] for user in api_shared_servers['MediaContainer']['SharedServer']}
    return users
############ PLEX DEFINITIONS ########################

#    except Exception as e:
#        on_exception(e, "1", searchArtist, artist, searchAlbum, album, searchTrack, track)
def on_exception(e, instance, searchArtist, artist, searchAlbum, album, searchTrack, track):
    print("\n---   exception   ---")
    #print("searchArtist: ", end='')
    print(instance)
    print("Error: {err}".format(err=e))
    print(searchArtist)
    print(artist)
    print(searchAlbum)
    print(album)
    print(searchTrack)
    print(track)
    print("--- end exception ---\n")
    #exit()

# when multiple albums under artist are found matching searchAlbum. search every album for track
def findInPlex(searchArtist, searchAlbum, searchAlbumArtist, searchTrack):
    artist=None
    album=None
    track=None
    artistList=None
    albumList=None
    trackList=None

    #try:
    # clean up inputs, might be a good idea to trap / characters here too, not sure how much it costs
    if searchArtist is not None and isinstance(searchArtist, str):
        searchArtist = searchArtist.lower().strip(' ')
    if searchAlbum is not None and isinstance(searchAlbum, str):
        searchAlbum = searchAlbum.lower().strip(' ')
    if searchAlbumArtist is not None:
        searchAlbumArtist = searchAlbumArtist.lower().strip(' ')
    if searchArtist is not None:
        searchTrack = searchTrack.lower().strip(' ')

    # ---- search for album by artist ---- may erlewine is a match, but Heart Song is under Daisy May

    # ---- search for artist in Artist metadata ----
    if searchArtist is not None and isinstance(searchArtist, str): # if searching for blank (or none), plex returns everything
        artistList = music.searchArtists(**{'title': searchArtist})

        # ---- search for exact artist match in results ----
        if artistList is not None:
            for thisArtist in artistList:
                if thisArtist.title.lower().strip('/') == searchArtist:
                    artist = thisArtist

                    # ---- search for album ----
                    if artist is not None and searchAlbum is not None:
                        if isinstance(searchAlbum, str): # if album isn't found, sometimes 0 is returned
                            for thisAlbum in artist.albums():
                                if thisAlbum.title.lower().strip('/') == searchAlbum:
                                    album = thisAlbum

                                    # ---- search for track in every album ----
                                    for thisTrack in album.tracks():
                                        if thisTrack.title.lower().strip('/') == searchTrack: # look for track in album (assume only one artist/album match?)
                                            track = thisTrack
                                            #toLog("----Artist----", logPath, 0,1,1)
                                            break
                                if track is not None: break
                if track is not None: break

        if track is None:
            # ---- search for artist in Album Artist metadata ----
            if searchArtist is not None:
                artistList = music.searchArtists(**{'title': searchAlbumArtist})

                # ---- search for exact artist match in results ----
                if artistList is not None:
                    for thisArtist in artistList:
                        if thisArtist.title.lower().strip('/') == searchAlbumArtist:
                            artist = thisArtist
                            # ---- search for album ----
                            #print(artist.albums())
                            if artist is not None and searchAlbum is not None:
                                #print(artistList)
                                if isinstance(searchAlbum, str): # if album isn't found, sometimes 0 is returned
                                    for thisAlbum in artist.albums():
                                        #print(thisAlbum.title.lower().strip('/'))
                                        if thisAlbum.title.lower().strip('/') == searchAlbum:
                                            album = thisAlbum
                                            # ---- search for track in every album ----
                                            for thisTrack in album.tracks():
                                                if thisTrack.title.lower().strip('/') == searchTrack: # look for track in album (assume only one artist/album match?)
                                                    track = thisTrack
                                                    #printData("Album Artist",searchArtist,artist,searchAlbum,album,searchTrack,track)
                                                    break
                                        if track is not None: break
                        if track is not None: break

            # ---- search for track in artist ----
            if track is None:
                for thisArtist in artistList:
                    for thisTrack in thisArtist.tracks():
                        if thisTrack.title.lower().strip('/') == searchTrack:
                            track = thisTrack
                            if isinstance(searchAlbum, str): # I only want to know if an album could have been found
                                printData("Found track in search of all artist's tracks:",searchArtist,thisArtist,searchAlbum,album,searchTrack,track)
                            break
                    if track is not None: break

    # ---- search for album in library ----
    if track is None:
        albumList = music.searchAlbums(**{'title': searchAlbum})
        for thisAlbum in albumList:
            if thisAlbum.title.lower().strip('/') == searchAlbum:
                album = thisAlbum

                # ---- search for track in every album that matches search album name ----
                for thisTrack in album.tracks():
                    if thisTrack.title.lower().strip('/') == searchTrack: # look for track in all albums with searchAlbum name
                        track = thisTrack
                        if searchArtist is not None:
                            printData("Found track in search of all albums in library:",searchArtist,artist,searchAlbum,album,searchTrack,track)

    # may yield unprdictable results since only track name is used
    # ---- search for track in library ----
    if track is None:
        if searchTrack is not None: # if searching for blank (or none), plex returns everything
            trackList = music.searchTracks(**{'title': searchTrack})
            for thisTrack in trackList:
                if thisTrack.title.lower().strip('/') == searchTrack: # look for track in all albums with searchAlbum name
                    track = thisTrack

    #except Exception as e:
    #    on_exception(e, "1", searchArtist, artist, searchAlbum, album, searchTrack, track)

    if artist is not None and album is not None and track is None:
        printData("!!!!Track could never be found!!!!",searchArtist,artist,searchAlbum,album,searchTrack,track)

    #printData("",searchArtist,artist,searchAlbum,album,searchTrack,track)
    return track

def getPlaylist():
    # Parsing iTunes xml
    root = ET.parse(itunesxml).getroot()

    for playlist in root[0].find('array').findall('dict'): # search for playlists in xml file
        l = list(playlist)
        plInfo = dict(zip([t.text for t in l[::2]], [t.text for t in l[1::2]]))
        plName = plInfo.get('Name',0) # name of playlist
        if plName not in blocklist and playlist.find('array') is not None:
        #if plName in allowlist and playlist.find('array') is not None:
            plexTracks=[]
            toLog("\nSyncing the '{title}' playlist...".format(title=plName), logPath, 0,0,1)
            if playlist.find('array') is not '':
                for tr in playlist.find('array').findall('dict'):
                    l = list(tr) # all tracks in playlist
                    tracks = dict(zip([t.text for t in l[::2]], [t.text for t in l[1::2]]))
                    thisTrackID=tracks.get('Track ID',0) # thisTrackID is the track ID in playlist, needs to be found in library
                    for trackList in root[0].find('dict').findall('dict'):# search for contents of all libraries
                        l = list(trackList) # all tracks in this library
                        trackInfo = dict(zip([t.text for t in l[::2]], [t.text for t in l[1::2]]))
                        track = trackInfo.get('Track ID',0) # get Track ID of this track
                        if track == thisTrackID: # compare this track ID to the track ID in the playlist
                            trackType = trackInfo.get('Track Type',0) # found a match!
                            if trackType == "File":
                                searchArtist=trackInfo.get('Artist',0)
                                searchAlbum=trackInfo.get('Album',0)
                                searchAlbumArtist=trackInfo.get('Album Artist')
                                searchTrack=trackInfo.get('Name',0)
                                plexTrack = findInPlex(searchArtist, searchAlbum, searchAlbumArtist, searchTrack) # search for track in plex
                                if plexTrack is not None:
                                    plexTracks.append(plexTrack)
            if plName == "Recently Added": # Put recently added sort order opposite that of the xml order
                plexTracks.reverse()
            exportToPlex(USERS, plName, plexTracks)

def exportToPlex(USERS, plName, plexTracks):
    toLog(str(len(plexTracks))+" tracks... ",logPath,0,1,1)
    for user in USERS:
        user_token = plex_users.get(user)
        if not user_token:
            toLog("...User '{user}' not found in shared users. Skipping.".format(user=user), logPath, 0,1,1)
            continue

        user_plex = PlexServer(PLEX_URL, user_token)

        # Delete the old playlist
        try:
            user_playlist = user_plex.playlist(plName)
            user_playlist.delete()
        except:
            pass

        # Create a new playlist
        user_plex.createPlaylist(plName, plexTracks)
        toLog("...For '{user}'.".format(user=user), logPath, 0,1,1)

def printData(msg,searchArtist,artist,searchAlbum,album,searchTrack,track):
    toLog("\n"+msg, logPath, 0,1,1)
    toLog("Artist: ", logPath, 0,0,1)
    toLog(searchArtist, logPath, 0,0,1)
    toLog(" : ", logPath, 0,0,1)
    toLog(artist, logPath, 0,1,1)
    toLog("Album: ", logPath, 0,0,1)
    toLog(searchAlbum, logPath, 0,0,1)
    toLog(" : ", logPath, 0,0,1)
    toLog(album, logPath, 0,1,1)
    toLog("Track: ", logPath, 0,0,1)
    toLog(searchTrack, logPath, 0,0,1)
    toLog(" : ", logPath, 0,0,1)
    toLog(track, logPath, 0,1,1)

# toLog("", logPath, 0,1,1) #toStamp,toNewline,toAppend
def toLog(message, logPath, toStamp, toNewline, toAppend):
    if toAppend > 0:
        toAppend='a'
    else:
        toAppend='w'
    if toNewline > 0:
        toNewline = '\n'
    else:
        toNewline = ''
    if toStamp > 0:
        timeNow=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(timeNow, message, end=toNewline, file=open(logPath,toAppend))
    else:
        print(message, end=toNewline, file=open(logPath,toAppend))

# if date modified is greater than date last run and date last run is more than an hour ago, resync
if xmlTimeModified > timeLastRun and timeNow - timeLastRun > 3600:
#if True:
    # initiate Plex instance
    plex = PlexServer(PLEX_URL, PLEX_TOKEN)


    #TIMEOUT = CONFIG.get('plexapi.timeout', 30, int)

    plex_users = get_user_tokens(plex.machineIdentifier)
    music = plex.library.section('5 - Music')

    ################################################## ########################
    # Variable Setup
    ################################################## ########################
    toLog("\nSyncing Playlists", logPath, 1,1,1) #toStamp,toNewline,toAppend

    starttime = datetime.datetime.now()

    blocklist = "Library", "Camry Music", "Podcast", "iTunes U", "Internet Songs", "Voice Memos", "Recent Faves", "Camry Podcast", "Radio", "Camry Music iPod", "iTunes U","Audiobooks", "Movies", "Music", "Party Shuffle", "Podcasts", "Purchased", "TV Shows"
    allowlist = "Music"
    #toLog("Script Variables:", logPath, 0,1,1)
    #toLog("iTunes xml file path: " + itunesxml, logPath, 0,1,1)
    #toLog(str("Playlists not exported: ",''.join(blocklist)), logPath, 0,1,1)

    ################################################## ########################
    # Export Playlists
    ################################################## ########################
    # ---- test ----
    #searchArtist='Ben Folds'
    #searchAlbum='Ben Folds Presents: University a Cappella!'
    #searchTrack='Effington (University A Cappella Version)'
    #plexTrack = findInPlex(searchArtist, searchAlbum, "", searchTrack)
    #exit()
    # ---- test ----
    getPlaylist()

    ################################################## ############################
    # End of Playlist script
    # set timeLastRun
    shelf["timeLastRun"] = time.time()
    shelf.sync() # Save
    shelf.close()

    endtime = datetime.datetime.now()
    toLog("\nExecution Time: "+str(endtime - starttime)+"\n", logPath, 0,0,1)
    toLog("Playlist Sync Complete\n", logPath, 1,1,1)
    ################################################## ############################
else:
    toLog("Checked for changes to XML file, none", logPath, 1,1,1)
