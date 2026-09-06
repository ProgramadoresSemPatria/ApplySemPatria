from . import defi, f6s, himalayas, opentoworkremote, remoteok, wellfound, weworkremotely

COLLECTORS = {
    "remoteok": remoteok.collect,
    "weworkremotely": weworkremotely.collect,
    "defi": defi.collect,
    "himalayas": himalayas.collect,
    "opentoworkremote": opentoworkremote.collect,
    "wellfound": wellfound.collect,
    "f6s": f6s.collect,
}
