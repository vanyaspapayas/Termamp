from pathlib import Path
from mutagen import File
from rich.console import Console
from rich.table import Table
from rich import box
from rich.padding import Padding
from img2ascii import img_to_ascii
from collections import defaultdict

import sqlite3
import subprocess
import os

BASE = Path(__file__).parent
MUSIC = BASE / "music"

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
    album_name = first(audio, 'album') or path.parent.name
    album_author = first(audio, 'albumartist') or "Unknown Artist"
    album_key = album_name + album_author 
    album_key = album_key.strip() 
    album_key = album_key.lower()
    album_key = album_key.replace(' ', '_')

    cur = conn.execute("SELECT id FROM albums WHERE album_key = ?", (album_key,))
    res = cur.fetchone()


    if res is None: 
        name = album_name
        author = album_author
        genre = first(audio, 'genre')
        year = first(audio, 'date')

        dir = BASE / root / path.parent
        path_cover = None
        
        for file in sorted(dir.rglob("*")):
            if file.is_file() and file.suffix.lower() in {".jpeg", ".jpg", ".png"} and file.stem.lower() in {"cover", "picture", "front"}:
                path_cover = str(file.relative_to(root))
                break
        else:
            for file in dir.iterdir():
                if file.is_file() and file.suffix.lower() in {".jpeg", ".jpg", ".png"}:
                    path_cover = str(file.relative_to(root))
                    break
            else:
                for file in sorted(dir.rglob("*")):                            
                    if file.is_file() and file.suffix.lower() in {".jpeg", ".jpg", ".png"}:
                        path_cover = str(file.relative_to(root))
                        break
                        
        
        cur = conn.execute("INSERT INTO albums (name, author, genre, year, album_key, cover) VALUES (?,?,?,?,?,?)", (name, author, genre, year, album_key, path_cover))
        return cur.lastrowid
    else:
        return res[0]

SIDES = "ABCDEFGH"

def track_label(n):
    if n is None:
        return "?"
    if n >= 100:
        return f"{SIDES[n // 100 - 1]}{n % 100}"
    return str(n)

def parse_track_number(raw):
    if not raw:
        return None
    head = str(raw).strip().split('/')[0].strip()
    if not head:
        return None
    if head.isdigit():
        return int(head)
    if head[0].upper() in SIDES and head[1:].isdigit():
        side = SIDES.index(head[0].upper()) + 1
        return side * 100 + int(head[1:])
    if head.upper() in SIDES:          # bare 'A' — one piece per side
        return (SIDES.index(head.upper()) + 1) * 100 + 1
    return None

def track_to_db(audio, path, conn, root):
    """ add track to database according to schema """
    name   = first(audio, 'title')
    author = first(audio, 'artist')
    length = int(audio.info.length)
    raw = first(audio, 'tracknumber')

    number = parse_track_number(raw)

    album_id = get_or_create_album(audio, path, conn, root)

    conn.execute("INSERT INTO tracks (name, author, track_order, length, path, album_id) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET name = excluded.name, author = excluded.author, length = excluded.length", (name,author,number,length, str(path), album_id, ))


def scan_path(root, conn): 
    """ iterate all files in given path, add audio files to db """
    files = root.rglob("*")
    output = []
    for file in files:
        if not file.is_file(): continue
        if file.suffix.lower() not in {".mp3", ".flac"}: continue

        audio = File(file, easy=True)
        if audio is None: continue # metadata is not readable, skip for now
        if file.name == "pineapple.mp3": continue
        result = file.relative_to(root)
        track_to_db(audio, result, conn, root)
        output.append((result,audio))

    conn.commit()
    return output

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

def help(console):
    console.print("Commands:")
    table = Table(box = box.MINIMAL)
    table.add_column("Command", justify="left")
    table.add_column("Meaning", justify="left")
    table.add_row("albums", "List all albums")
    table.add_row("open <id>", "Open specific album by id")
    table.add_row("play", "Play the current album from start")
    table.add_row("play <id>", "Play the current album starting from specific track")
    table.add_row("back", "Leave the current album")
    table.add_row("scan", "Rescan the whole library")
    table.add_row("help", "You'll never guess what this does")
    table.add_row("secret", "dGhpcyB3aWxsIGdldCB5b3Ugcmlja3JvbGxlZC4=")
    table.add_row("exit", "Leave the application")
    console.print(table)

def scan(console):
    init_db(conn)
    new = scan_path(MUSIC,conn)
    old_paths = [x[0] for x in initial_scan]
    differences = [x[0] for x in new if x[0] not in old_paths]
    console.print("Successfuly finished scanning.")
    if len(differences) == 1: console.print("New track added:")
    if len(differences) >= 2: console.print("New tracks added:")
    for difference in differences:
        console.print(difference)
    if len(differences) == 0: console.print("Nothing new.")
    conn.commit()

def rickroll(console):
    print(open(BASE / "secret.txt").read())
    try:
        subprocess.run(["afplay", BASE / "music" / "pineapple.mp3"])
        console.print("Hope you enjoyed it!")
    except:
        console.print("\nYou didn't like it? Oke :(")

def albums(console, layout):
    table = Table(box=box.SIMPLE)
    console.print()
    console.print(f"Total tracks in all albums: {count}")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Artist")
    table.add_column("Album")
    table.add_column("Year", justify="right", style="dim")

    for item in layout.items():
        album = item[1]
        table.add_row(str(item[0]), album["author"], album["name"], str(album["year"]))
    console.print(table)

def open_album(args,console, layout):
    if len(args) <= 1: 
        console.print("Not enough arguments!")
        console.print("Reference: open 1")
        return None, None
    id = int(args[1])
    real_id = layout[id]['id']
    album = get_album(conn,real_id)

    console.rule(f"[bold]{album['author']} - {album['name']}[/bold]")
    console.print(f"[dim]{album['genre']} · {album['year']}[/dim]\n")

    if album['cover']: 
        console.print(img_to_ascii(MUSIC / album["cover"]))
     
    tracks = get_album_tracks(conn, real_id)

    for track in tracks:
        console.print(track_label(track['track_order']), track['name'], time_convert(track['length']))
    # if album["cover"]:
    #     table = Table()
    #     try:
    #         layout = Table.grid(padding=(0, 3))
    #         layout.add_column()
    #         layout.add_column()
    #         layout.add_row(img_to_ascii(music / album["cover"]), table)
    #         console.print(Padding(layout, (0, 0, 0, 0)))
    #     except Exception:
    #         console.print(table)
    # else:
    #     console.print(table)
    return real_id, tracks

def play(console, args, current_album, current_album_data):
    if len(args) == 1 and current_album is None:
        console.print("You shall first view the album, then play.")
        console.print("Reference: play <id>, <id> - a track id inside the album")
        console.print("Or just simply: play")
    elif len(args) == 1 and current_album is not None:
        try:
            for track in current_album_data:
                track_path = track["path"]
                track_path = MUSIC / track_path
                console.print(f"[dim]Playing:[/dim] {track['name']}")
                subprocess.run(["afplay", track_path])
        except:
            console.print("\nStopping.")
    elif len(args) == 2 and current_album is not None:
        try:
            # current_track = [track for track in current_album_data if track['track_order'] == int(args[1])][0]
            # track_path = current_track["path"]
            # track_path = MUSIC / track_path
            # console.print(f"[dim]Playing:[/dim] {current_track['name']}")
            # subprocess.run(["afplay", track_path])
            index = 0
            for i, track in enumerate(current_album_data):
                if int(track["track_order"]) == int(args[1]):
                    index = i
                    break
            else:
                raise IndexError
            for track in current_album_data[index:]:
                track_path = track["path"]
                track_path = MUSIC / track_path
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

def reset(console, conn):
    try:
        conn.execute("DROP TABLE IF EXISTS tracks")
        conn.execute("DROP TABLE IF EXISTS albums")
        init_db(conn)
        conn.commit()
        console.print("DB is succesfuly reset\nDo not forget to run scan again!")
    except:
        console.print("Could not remove the database file")

def init_scan():
    conn = sqlite3.connect(BASE / "db" / "MUSIC.db")
    init_db(conn)
    initial_scan = scan_path(MUSIC, conn)
    count = len(initial_scan)
    return initial_scan, count

def create_albums_dict(conn):
    albums = list_albums(conn)
    layout = defaultdict(dict)
    albums.sort(key = lambda x: (x['author'], x['name']))
    for id, album in enumerate(albums):
        layout[id] = album
    return layout

if __name__ == "__main__":
    console = Console()
    console.print()
    print(open(BASE / "banner.txt").read())
    console.print()
    console.print("Termamp v0.0.1\nFree to use\n", highlight=False)

    initial_scan, count = init_scan()
    conn = sqlite3.connect(BASE / "db" / "MUSIC.db")
    # REPL
    layout = create_albums_dict(conn)
    current_album = None
    current_album_data = None

    while True:
        line = input("$ ")
        line = line.strip()
        args = line.split()
        args[0] = args[0].lower()
        if args[0] == "help":
            help(console)
        elif args[0] == "scan":
            scan(console)
            layout = create_albums_dict(conn)
        elif args[0] == "secret":
            rickroll(console)
        elif args[0] == "albums" or args[0] == "album" or args[0] == "list" or (args[0] == "back" and current_album is not None):
            current_album = None
            current_album_data = None
            albums(console, layout)
        elif args[0] == "open":
            current_album, current_album_data = open_album(args, console, layout)
        elif args[0] == "play":
            play(console, args, current_album, current_album_data)
        elif args[0] == "back":
            console.print("Can be done only in album view mode.")
        elif args[0] == "reset":
            reset(console, conn)
            layout = create_albums_dict(conn)
        elif args[0] == "quit" or args[0] == "exit":
            console.print("Bye!")
            console.print("Always remember to listen to good music.")
            break
        else:
            console.print("There is no such command. Check help")
            