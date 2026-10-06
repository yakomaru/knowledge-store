# crate-sorter

A command-line tool that sorts a directory of mixed media files into a dated
folder structure.

## How it works

Reads the embedded creation timestamp where one exists, falls back to the
filesystem mtime where it does not, and moves each file into `YYYY/MM/`. Files
whose timestamp cannot be determined go to `unsorted/` rather than being guessed
at, because a wrong date is worse than an obvious gap.

## Usage

```bash
crate-sorter --src ~/Incoming --dst ~/Archive          # move
crate-sorter --src ~/Incoming --dst ~/Archive --copy   # copy instead
crate-sorter --src ~/Incoming --dst ~/Archive --dry-run
```

## Collision handling

If a destination filename already exists, the tool compares content hashes. An
identical file is skipped as a duplicate; a different file with the same name gets
a numeric suffix. It never overwrites, and there is no flag to make it overwrite.

## Known limitations

Timestamps from some camera firmware are stored in local time with no offset, so
files crossing a midnight boundary can land in the wrong day. There is no good fix
without knowing the camera's timezone.
