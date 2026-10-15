from pathlib import Path
from mutagen import File
from rich.console import Console
from rich.table import Table
from rich import box
import sqlite3
import subprocess


# Errors

class AlbumNotFound(Exception):
    pass
class TrackNotFound(Exception):
    pass

def first(audio, tag):
    """ fix the stupid bug of mutagen """
    value = audio.get(tag)
    return value[0] if value else None

# DB interaction

def init_db(conn):
    """ Initialise database """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS albums (
            id         INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            author     TEXT NOT NULL,
            genre      TEXT,
            year       INTEGER,
            cover      TEXT,
            album_key  TEXT NOT NULL UNIQUE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id             INTEGER PRIMARY KEY,
            name           TEXT NOT NULL,
            author         TEXT NOT NULL,
            track_order    INTEGER,
            length         INTEGER,
            path           TEXT NOT NULL UNIQUE, 
            album_id       INTEGER REFERENCES albums(id)
        )
    """)
    # genre might be an array tho TODO

def get_or_create_album(audio, path, conn, root):
    """ create albums if non existent. define album_key from album name and artist. return id """
    album_key = first(audio, 'album') + first(audio, 'albumartist')
    album_key = album_key.strip()
    album_key = album_key.lower()
    album_key = album_key.replace(' ', '_')

    cur = conn.execute("SELECT id FROM albums WHERE album_key = ?", (album_key,))
    res = cur.fetchone()


    if res is None: 
        name = first(audio,'album')
        author = first(audio, 'albumartist')
        genre = first(audio, 'genre')
        year = first(audio, 'date')

        dir = root / path.parent
        path_cover = None

        for file in dir.iterdir():
            if file.stem.lower() in {"cover", "picture"}:
                path_cover = str(file.relative_to(root))
                break
        else:
            for file in dir.iterdir():
                if file.suffix.lower() in {".jpeg", ".jpg", ".png"}:
                    path_cover = str(file.relative_to(root))
                    break
        
        cur = conn.execute("INSERT INTO albums (name, author, genre, year, album_key, cover) VALUES (?,?,?,?,?,?)", (name, author, genre, year, album_key, path_cover))
        return cur.lastrowid
    else:
        return res[0]

def track_to_db(audio, path, conn, root):
    """ add track to database according to schema """
    name   = first(audio, 'title')
    author = first(audio, 'artist')

    raw = first(audio, 'tracknumber')
    number = int(raw.split('/')[0]) if raw else None # fix a bug when they give it with a slash
    length = int(audio.info.length)

    album_id = get_or_create_album(audio, path, conn, root)

    conn.execute("INSERT INTO tracks (name, author, track_order, length, path, album_id) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET name = excluded.name, author = excluded.author, length = excluded.length", (name,author,number,length, str(path), album_id, ))

    return NotImplementedError

def scan_path(root, conn): 
    """ iterate all files in given path, add audio files to db """
    files = root.rglob("*")
    output = []
    for file in files:
        if not file.is_file(): continue
        if file.suffix.lower() not in {".mp3", ".flac"}: continue

        audio = File(file, easy=True)
        if audio is None: continue # metadata is not readable, skip for now
        
        result = file.relative_to(root)
        track_to_db(audio, result, conn, root)
        output.append((result,audio))

    conn.commit()
    return len(output)

# Getters

def list_albums(conn):
    albums = conn.execute("SELECT id, name, author, genre, year, cover FROM albums ORDER BY id;")
    datas = albums.fetchall()
    return [{"id": data[0], "name": data[1], "author": data[2], "genre": data[3], "year": data[4], "cover": data[5]} for data in datas]

def get_album(conn, id):
    album = conn.execute("SELECT name, author, genre, year, cover FROM albums WHERE id = ?;", (id, ))
    data = album.fetchone()
    if data is None: raise AlbumNotFound
    return {"name": data[0], "author": data[1], "genre": data[2], "year": data[3], "cover": data[4]}

def get_album_tracks(conn, id):
    tracks = conn.execute("SELECT name, author, track_order, length, path, album_id FROM tracks WHERE album_id = ? ORDER BY track_order", (id, ))

    datas = tracks.fetchall()
    return [{"name": data[0], "author": data[1], "track_order": data[2], "length": data[3], "path": data[4], "album_id": data[5]} for data in datas]

def get_track(conn, id): # in case i would like to make playlist. so far it shall be album centered
    track = conn.execute("SELECT name, author, track_order, length, path, album_id FROM tracks WHERE id = ?", (id, ))
    data = track.fetchone()
    if data is None: raise TrackNotFound
    return {"name": data[0], "author": data[1], "track_order": data[2], "length": data[3], "path": data[4], "album_id": data[5]}

def time_convert(seconds):
    minutes = seconds // 60
    seconds -= minutes * 60
    return f"{minutes}:{seconds:02d}"


if __name__ == "__main__":
    console = Console()
    console.print()
    print(open("banner.txt").read())
    console.print()
    console.print("Termamp v0.0.1\nFree to use\n")

    music = Path('/Users/vanyaspapayas/music_player/music') # a dir where music files are stored

    conn = sqlite3.connect("db/music.db")
    init_db(conn)
    count = scan_path(music, conn)

    # REPL
    current_album = None
    current_album_data = None

    while True:
        line = input("$ ")
        line = line.strip()
        args = line.split()
        args[0] = args[0].lower()
        if args[0] == "help":
            console.print("Here's help.")
        elif args[0] == "quit" or args[0] == "exit":
            console.print("Bye!")
            console.print("Always remember to listen to good music.")
            break
        elif args[0] == "albums" or args[0] == "list":
            table = Table(box=box.SIMPLE)
            print()
            console.print(f"Total tracks in all albums: {count}")

            table.add_column("ID", justify="right", style="dim")
            table.add_column("Artist")
            table.add_column("Album")
            table.add_column("Year", justify="right", style="dim")

            albums = list_albums(conn)
            for album in albums:
                table.add_row(str(album["id"]), album["author"], album["name"], str(album["year"]))
            console.print(table)
        elif args[0] == "open":
            if len(args) <= 1: 
                console.print("Not enough arguments!")
                console.print("Reference: open 1")
                continue
            id = int(args[1])
            album = get_album(conn,id)


            current_album = id

            table = Table(show_header=False, box=None, padding = (0, 1))
            table.add_column(justify='right', style = 'dim')
            table.add_column()
            table.add_column(justify='right', style = 'dim')


            console.rule(f"[bold]{album['author']} - {album['name']}[/bold]")
            console.print(f"{album['genre']} / {album['year']}")
            console.print('Tracks:')

            tracks = get_album_tracks(conn, id)

            current_album_data = tracks

            track_list= [track for track in tracks]

            for track in track_list: 
                table.add_row(str(track['track_order']), track['name'], time_convert(track['length']))
            console.print(table)
        elif args[0] == "play":
            # now its where fun begins!
            if len(args) == 1 and current_album is None:
                console.print("You shall first view the album, then play.")
                console.print("Reference: play <id>, <id> - a track id inside the album")
                console.print("Or just simply: play")
            elif len(args) == 1 and current_album is not None:
                for track in current_album_data:
                    track_path = track["path"]
                    track_path = music / track_path
                    console.print(f"[dim]Playing:[/dim] {track['name']}")
                    subprocess.run(["afplay", track_path])
            elif len(args) == 2 and current_album is not None:
                try:
                    # current_track = [track for track in current_album_data if track['track_order'] == int(args[1])][0]
                    # track_path = current_track["path"]
                    # track_path = music / track_path
                    # console.print(f"[dim]Playing:[/dim] {current_track['name']}")
                    # subprocess.run(["afplay", track_path])
                    index = 0
                    for i, track in enumerate(current_album_data):
                        if int(track["track_order"]) == int(args[1]):
                            index = i
                            break
                    else:
                        index = None

                    for track in current_album_data[index:]:
                        track_path = track["path"]
                        track_path = music / track_path
                        console.print(f"[dim]Playing:[/dim] {track['name']}")
                        subprocess.run(["afplay", track_path])

                except ValueError:
                    console.print("Track number must be a number.")
                except IndexError:
                    console.print("No such track in this album.")
                except KeyboardInterrupt:
                    console.print("\nStopping. ")
                except:
                    console.print("Invalid arguments.")

        else:
            console.print("There is no such command. Check help")
            


    # albums = list_albums(conn)
    # album = get_album(conn, "selected_ambient_works_volume_iiaphex_twin")
    # tracks = get_album_tracks(conn, "selected_ambient_works_volume_iiaphex_twin")
    # print(albums, count)
    # print(album)
    # print(tracks)