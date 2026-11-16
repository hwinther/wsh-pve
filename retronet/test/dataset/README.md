# Synthetic archive dataset

A tiny store in the archive cache's own format (`v1/<kind>/<host>/<hash>.json|.body`), made-up
1999-style content only: the test imports it and runs the main checks against the archive cache in
offline (replay) mode. No archived third-party page belongs here: real warmed stores stay on the
gateways' volumes.

Made from `../fixture/` with:

```sh
A="python3 retronet/services/archive-cache/archive_cache.py --root retronet/test/dataset"
$A put-capture http://www.example.com/ 1999 19990117083513 text/html retronet/test/fixture/index.html --content-type "text/html; charset=iso-8859-1"
$A put-capture http://www.example.com/logo.gif 1999 19990117083513 image/gif retronet/test/fixture/logo.gif
```
